"""Kilder uden RSS (KONTRAKTER §5.6): nye artikel-URL'er findes i et sitemap eller på en listeside,
og titel, dato og teaser hentes fra selve siden med et fælles sideudtræk (extract_page)."""

from __future__ import annotations

import codecs
import json
import logging
import re
import zlib
from collections import deque
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone, tzinfo
from typing import TYPE_CHECKING, Any, NamedTuple
from urllib.parse import unquote, urldefrag, urljoin, urlsplit

from cssselect import SelectorError
from lxml import etree
from lxml import html as lxml_html
from lxml.cssselect import CSSSelector

from affaldsfeed.collect import CollectContext, CollectResult, RawEntry, combine_errors
from affaldsfeed.config import source_hosts
from affaldsfeed.fetch import BUDGET_EXHAUSTED, MB, ROBOTS_BLOCKED
from affaldsfeed.models import Keywords, Source
from affaldsfeed.normalize import TRANSLIT, host_of, item_id, matches_name, strip_site_tail
from affaldsfeed.relevance import compile_patterns, find_hits
from affaldsfeed.timeutil import CPH, cph_day_bounds, ensure_utc, now_utc, to_cph

if TYPE_CHECKING:
    from affaldsfeed.fetch import Fetcher, FetchResult

log = logging.getLogger(__name__)

MAX_XML_BYTES = 50 * MB  # standardloft over et udpakket sitemap (indsamlingen bruger fetch.max_response_mb)
GZIP_MAGIC = b"\x1f\x8b"
NEWS_NS = "http://www.google.com/schemas/sitemap-news/0.9"
_ENTITY_ABUSE = ("ENTITY_LOOP", "RESOURCE_LIMIT", "AMPLIFICATION")  # libxml2-fejltyper
MAX_INDEX_DEPTH = 1  # indeks → højst ét indlejret indeks → urlset
FUTURE_SLACK = timedelta(hours=2)
OLDEST = datetime(2000, 1, 1, tzinfo=UTC)  # ældre "datoer" er fejl i siden
TEXT_DATE_CHARS = 1500  # "første del" af article/main, hvor en dansk dato må stå
LIST_DATE_LEVELS = 5  # så mange forældre op fra et link søges der efter en dato
LIST_DATE_CHARS = 400
LABEL_CHARS = 30  # så langt før en dato søges der efter "Publiceret" o.l.
DIAG_URLS = 10
DIAG_LINKS = 20
DEFAULT_SELECT = "a[href]"


class Page(NamedTuple):
    """Udtræk af én artikelside."""

    title: str
    published: datetime | None  # UTC
    date_quality: str  # kilde, url, liste eller fundet
    teaser: str  # rå; normalize.clean_text renser senere


# ── Datoer ──────────────────────────────────────────────────
# Kun eksplicitte formater (KONTRAKTER §5.5): ISO 8601 og varianter med år først (aldrig dag-først-gæt),
# RFC 822-tidsstempler, danske datoer (månedsnavn eller dd.mm.åååå) og engelske månedsnavne for engelske kilder.

_MONTHS = {
    "januar": 1, "februar": 2, "marts": 3, "april": 4, "maj": 5, "juni": 6, "juli": 7, "august": 8,
    "september": 9, "oktober": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9,
    "okt": 10, "nov": 11, "dec": 12,
}  # fmt: skip
_EN_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9,
    "oct": 10, "nov": 11, "dec": 12,
}  # fmt: skip
_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))
_EN_MONTH_ALT = "|".join(sorted(_EN_MONTHS, key=len, reverse=True))
_YEAR = r"(?P<y>(?:19|20)\d{2})(?!\d)"
_DK_NAME_DATE_RE = re.compile(rf"(?<!\d)(?P<d>\d{{1,2}})\.?\s*(?P<m>{_MONTH_ALT})\.?,?\s+{_YEAR}", re.IGNORECASE)
_DK_NUM_DATE_RE = re.compile(rf"(?<![\d.])(?P<d>\d{{1,2}})[./-](?P<m>\d{{1,2}})[./-]{_YEAR}")
# "7 October 2026", "7th of Oct. 2026" og "October 7, 2026"
_EN_DAY_FIRST_RE = re.compile(
    rf"(?<!\d)(?P<d>\d{{1,2}})(?:st|nd|rd|th)?\.?\s+(?:of\s+)?(?P<m>{_EN_MONTH_ALT})\.?,?\s+{_YEAR}", re.IGNORECASE
)
_EN_MONTH_FIRST_RE = re.compile(
    rf"(?<![a-z])(?P<m>{_EN_MONTH_ALT})\.?\s+(?P<d>\d{{1,2}})(?:st|nd|rd|th)?,?\s+{_YEAR}", re.IGNORECASE
)
# Klokkeslæt lige efter en dato; aldrig starten af en ny dato ("07.10.2026 - 08.10.2026")
_DK_TIME_RE = re.compile(
    r"[\s,–-]*(?:kl\.?|klokken)?\s*(?P<h>[01]?\d|2[0-3])[.:](?P<mi>[0-5]\d)(?!\d)(?![./-]\d)"
    r"(?:\s*(?P<ap>[ap])\.?\s?m\b\.?)?",
    re.IGNORECASE,
)
_PUB_LABEL_RE = re.compile(
    r"\b(?:publicer\w*|udgiv\w*|offentliggj\w*|dato|skrevet|published|posted)\b[^\d\n]{0,12}$", re.IGNORECASE
)
# År først: 2026-10-07, 2026/10/07 eller 20261007, evt. med tid og tidszone ("Z", "+0200", " +02:00", " UTC",
# "GMT+2", " CEST")
_ISO_RE = re.compile(
    r"(?P<y>\d{4})(?:-(?P<m>\d{1,2})-(?P<d>\d{1,2})|/(?P<m2>\d{1,2})/(?P<d2>\d{1,2})|(?P<m3>\d{2})(?P<d3>\d{2}))"
    r"(?:(?:T\s*|\s+)(?P<H>\d{1,2}):?(?P<M>\d{2})(?::?(?P<S>\d{2})(?:[.,]\d+)?)?)?"
    r"(?:\s*(?P<tz>Z|[+-]\d{1,2}(?::?\d{2})?|[a-z]{2,5}(?:\s*[+-]\d{1,2}(?::?\d{2})?)?))?",
    re.IGNORECASE,
)
# RFC 822/1123: "Wed, 07 Oct 2026 10:00:00 GMT" (fast maskinformat, uanset kildens sprog)
_RFC822_RE = re.compile(
    r"(?:(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?,?\s*)?(?P<d>\d{1,2})\s+"
    r"(?P<m>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(?P<y>\d{4}),?\s+"
    r"(?P<H>\d{1,2}):(?P<M>\d{2})(?::(?P<S>\d{2}))?"
    r"(?:\s*(?P<tz>[+-]\d{2}:?\d{2}|[a-z]{1,5}(?:\s*[+-]\d{1,2}(?::?\d{2})?)?))?",
    re.IGNORECASE,
)
_ZONE_RE = re.compile(
    r"(?:(?P<name>[a-z]+)\s*)?(?:(?P<sign>[+-])(?P<h>\d{1,2})(?::?(?P<mi>\d{2}))?)?", re.IGNORECASE
)
# Tidszoner i minutter. Ukendte navne giver ingen dato frem for et gæt.
_ZONES = {"z": 0, "ut": 0, "utc": 0, "gmt": 0, "wet": 0, "west": 60, "bst": 60, "cet": 60, "met": 60,
          "cest": 120, "mest": 120, "eet": 120, "eest": 180}  # fmt: skip
_RFC_ZONES = {**_ZONES, "est": -300, "edt": -240, "cst": -360, "cdt": -300, "mst": -420, "mdt": -360,
              "pst": -480, "pdt": -420}  # fmt: skip
_URL_DATE_RES = (
    re.compile(r"/(?P<y>(?:19|20)\d{2})/(?P<m>\d{1,2})/(?P<d>\d{1,2})(?!\d)"),
    re.compile(r"(?<!\d)(?P<y>(?:19|20)\d{2})-(?P<m>\d{2})-(?P<d>\d{2})(?!\d)"),
)


def _day_start(d: date) -> datetime:
    """En dato uden klokkeslæt er dagen i København."""
    return datetime.combine(d, time.min, tzinfo=CPH).astimezone(UTC)


def _zone(text: str | None, names: dict[str, int] = _ZONES) -> tzinfo | None:
    """Tidszone fra "Z", "+02:00", "+0200", "UTC", "GMT+2", "CEST" …; None, hvis den er ukendt eller ugyldig."""
    m = _ZONE_RE.fullmatch((text or "").strip())
    if not m or not (m["name"] or m["sign"]):
        return None
    minutes = 0
    if m["name"]:
        name = m["name"].lower()
        if name not in names or (m["sign"] and names[name]):  # ukendt navn eller fx "CEST+2"
            return None
        minutes = names[name]
    if m["sign"]:
        hours, mins = int(m["h"]), int(m["mi"] or 0)
        if hours > 23 or mins > 59:  # fx "+24:00"
            return None
        minutes += (hours * 60 + mins) * (1 if m["sign"] == "+" else -1)
    return timezone(timedelta(minutes=minutes))


def _at(day: date, hour: int, minute: int, second: int = 0, tz: tzinfo = CPH) -> datetime | None:
    """Tidspunkt i UTC; None ved ugyldige værdier (aldrig en undtagelse)."""
    try:
        return datetime.combine(day, time(hour, minute, second), tzinfo=tz).astimezone(UTC)
    except (ValueError, OverflowError):
        return None


def _date(y: str | int, m: str | int, d: str | int) -> date | None:
    try:
        day = date(int(y), int(m), int(d))
    except ValueError:
        return None
    return day if 1900 <= day.year <= 2100 else None  # fx "0001-01-01" fra et tomt CMS-felt


def _clock(day: date, text: str, end: int) -> tuple[datetime, bool]:
    """Datoen med et klokkeslæt lige efter ("kl. 14.32", ", 14:32", "2:15 PM"), ellers dagens start."""
    t = _DK_TIME_RE.match(text, end)
    if t:
        hour = int(t["h"])
        if t["ap"] and hour <= 12:
            hour = hour % 12 + (12 if t["ap"].lower() == "p" else 0)
        found = _at(day, hour, int(t["mi"]))
        if found is not None:
            return found, True
    return _day_start(day), False


def _text_dates(text: str, lang: str = "da") -> list[tuple[int, int, date]]:
    """Alle datoer i teksten som (start, slut, dato) i rækkefølge: danske og, for engelske kilder, engelske."""
    rxs: list[tuple[re.Pattern, dict[str, int] | None]] = [(_DK_NAME_DATE_RE, _MONTHS), (_DK_NUM_DATE_RE, None)]
    if lang == "en":
        rxs += [(_EN_DAY_FIRST_RE, _EN_MONTHS), (_EN_MONTH_FIRST_RE, _EN_MONTHS)]
    found: list[tuple[int, int, date]] = []
    for rx, names in rxs:
        for m in rx.finditer(text or ""):
            month = names[m["m"].lower()] if names else m["m"]
            day = _date(m["y"], month, m["d"])
            if day is not None:
                found.append((m.start(), m.end(), day))
    out: list[tuple[int, int, date]] = []
    for item in sorted(found):
        if not out or item[0] >= out[-1][1]:  # overlappende fund tælles én gang
            out.append(item)
    return out


def danish_date(text: str) -> tuple[datetime, bool] | None:
    """Første danske dato i teksten ("7. oktober 2026", "7. okt. 2026", "07.10.2026"), evt. med "kl. 14.32".

    Returnerer (UTC, har klokkeslæt).
    """
    found = _text_dates(text)
    return _clock(found[0][2], text, found[0][1]) if found else None


def text_date(text: str, now: datetime, lang: str = "da") -> tuple[datetime, bool] | None:
    """Udgivelsesdatoen blandt datoerne i en tekst (brødtekst eller listepunkt).

    Datoer mere end 2 t ude i fremtiden eller før 2000 springes over. En dato efter "Publiceret", "Udgivet",
    "Dato" o.l. vinder; ellers den seneste, fordi tidligere datoer i teksten typisk er henvisninger
    ("Siden 1. april 2025 …"), og en for gammel dato får artiklen afvist.
    """
    found = []
    for start, end, day in _text_dates(text, lang):
        dt = _clock(day, text, end)
        if _plausible(dt[0], now):
            labelled = bool(_PUB_LABEL_RE.search(text[max(0, start - LABEL_CHARS) : start]))
            found.append((labelled, dt))
    if not found:
        return None
    labelled = [dt for is_label, dt in found if is_label]
    return labelled[0] if labelled else max((dt for _, dt in found), key=lambda x: x[0])


def _iso_date(m: re.Match) -> tuple[datetime, bool] | None:
    day = _date(m["y"], m["m"] or m["m2"] or m["m3"], m["d"] or m["d2"] or m["d3"])
    if day is None:
        return None
    if m["H"] is None:
        return _day_start(day), False  # en tidszone ved en dato uden tid ændrer ikke dagen
    tz = _zone(m["tz"]) if m["tz"] else CPH
    found = _at(day, int(m["H"]), int(m["M"]), int(m["S"] or 0), tz) if tz else None
    return (found, True) if found else None


def _rfc822_date(m: re.Match) -> tuple[datetime, bool] | None:
    day = _date(m["y"], _EN_MONTHS[m["m"].lower()], m["d"])
    tz = _zone(m["tz"], _RFC_ZONES) if m["tz"] else CPH
    found = _at(day, int(m["H"]), int(m["M"]), int(m["S"] or 0), tz) if day and tz else None
    return (found, True) if found else None


def parse_date(value: str | None, lang: str = "da") -> tuple[datetime, bool] | None:
    """Datostreng → (UTC, har klokkeslæt), eller None. Rejser aldrig en undtagelse.

    År først (ISO 8601 og varianter) læses altid som år-måned-dag. Uden tidszone er tiden dansk; uden klokkeslæt
    er det dagen i København. En ukendt eller ugyldig tidszone giver None frem for et gæt.
    """
    s = " ".join((value or "").split())
    if not s or len(s) > 80:
        return None
    m = _ISO_RE.fullmatch(s)
    if m:
        return _iso_date(m)
    m = _RFC822_RE.fullmatch(s)
    if m:
        return _rfc822_date(m)
    found = _text_dates(s, lang)
    return _clock(found[0][2], s, found[0][1]) if found else None


def url_date(url: str) -> datetime | None:
    """Dato i URL'ens sti (/2026/10/07/ eller 2026-10-07) som dagens start i København."""
    try:
        path = unquote(urlsplit(url or "").path)
    except ValueError:
        return None
    for rx in _URL_DATE_RES:
        for m in rx.finditer(path):
            day = _date(m["y"], m["m"], m["d"])
            if day is not None:
                return _day_start(day)
    return None


def _plausible(dt: datetime, now: datetime) -> bool:
    """Datoer mere end 2 t ude i fremtiden (og tydelige fejl før 2000) ignoreres."""
    return OLDEST <= dt <= now + FUTURE_SLACK


def _quality(has_time: bool) -> str:
    # En dato uden klokkeslæt vises som kun dato (som datoer fra listen), ikke som "kl. 00.00"
    return "kilde" if has_time else "liste"


# ── HTML ────────────────────────────────────────────────────

_CHARSET_RE = re.compile(r"charset\s*=\s*[\"']?\s*([\w.:-]+)", re.IGNORECASE)
_META_CHARSET_RE = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?\s*([\w.:-]+)""", re.IGNORECASE)
_LATIN = {"cp1252", "iso8859-15"}  # erklæres ofte for sider, der i virkeligheden er utf-8
# Tekst-codecs, Python kender, men som ikke er tegnsæt for HTML
_NOT_CHARSETS = {"idna", "punycode", "raw-unicode-escape", "unicode-escape", "undefined", "utf-7", "charmap"}
_WIDE = {"utf-16", "utf-16-le", "utf-16-be", "utf-32", "utf-32-le", "utf-32-be"}
_BOMS = ((codecs.BOM_UTF8, "utf-8-sig"), (codecs.BOM_UTF16_LE, "utf-16"), (codecs.BOM_UTF16_BE, "utf-16"))
_XML_DECL_RE = re.compile(r"^\s*<\?xml[^>]*\?>")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_VISIBLE_TEXT = etree.XPath(
    ".//text()[not(ancestor::script or ancestor::style or ancestor::noscript or ancestor::template)]"
)


def _codec(name: str | None) -> str | None:
    """Pythons navn for et tegnsæt, eller None, hvis det er ukendt eller ikke tekst (base64, hex, zip, idna …).

    Som i browsere (WHATWG) er latin-1 og ascii windows-1252, og utf-16/32 uden BOM er utf-8 (en side, hvis
    erklæring kan læses som ASCII, er ikke utf-16).
    """
    if not name:
        return None
    try:
        codec = codecs.lookup(name).name
        b"<a>".decode(codec, "replace")  # LookupError for base64, hex, rot13, zip …
    except (LookupError, ValueError):
        return None
    if codec in _NOT_CHARSETS:
        return None
    if codec in _WIDE:
        return "utf-8"
    return {"iso8859-1": "cp1252", "ascii": "cp1252"}.get(codec, codec)


def _is_utf8(content: bytes) -> bool:
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def html_charset(content: bytes, content_type: str | None = None) -> str:
    """Tegnsæt: BOM → Content-Type → <meta charset> → utf-8, hvis bytes er gyldig utf-8 → windows-1252.

    Et erklæret tegnsæt bruges (afkodes med errors="replace"), også når enkelte bytes er ugyldige. Eneste
    undtagelse: erklærer siden latin-1/windows-1252, men er den gyldig utf-8 med æøå, er den utf-8 (en hyppig
    fejl). windows-1252 er kun sidste udvej, når intet er erklæret.
    """
    for bom, codec in _BOMS:
        if content.startswith(bom):
            return codec
    m = _CHARSET_RE.search(content_type or "")
    declared = _codec(m.group(1)) if m else None
    if declared is None:
        mm = _META_CHARSET_RE.search(content[:4096])
        declared = _codec(mm.group(1).decode("ascii", "ignore")) if mm else None
    if declared and not (declared in _LATIN and not content.isascii() and _is_utf8(content)):
        return declared
    return "utf-8" if _is_utf8(content) else "cp1252"


def is_html(content_type: str | None, content: bytes) -> bool:
    """Kun HTML-svar (content-type med html eller ingen content-type). PDF o.l. springes over."""
    ctype = (content_type or "").split(";")[0].strip().lower()
    if ctype and "html" not in ctype:
        return False
    return not content.lstrip()[:5].startswith(b"%PDF")


def parse_html(content: bytes, content_type: str | None = None) -> Any | None:
    """lxml-dokument med det rigtige tegnsæt, eller None."""
    if not content:
        return None
    try:
        text = content.decode(html_charset(content, content_type), errors="replace")
    except (LookupError, ValueError):  # html_charset giver kun tekst-tegnsæt; for en sikkerheds skyld
        text = content.decode("utf-8", errors="replace")
    text = _CONTROL_RE.sub("", _XML_DECL_RE.sub("", text, count=1))
    try:
        return lxml_html.document_fromstring(text)
    except (etree.ParserError, ValueError):
        return None


def _text(el: Any, limit: int | None = None) -> str:
    """Synlig tekst (uden script og style) med samlet whitespace."""
    text = " ".join(" ".join(_VISIBLE_TEXT(el)).split())
    return text[:limit] if limit else text


def _meta(doc: Any) -> dict[str, str]:
    """<meta> efter property, name eller itemprop (små bogstaver) → første ikke-tomme content."""
    out: dict[str, str] = {}
    for m in doc.iter("meta"):
        content = (m.get("content") or "").strip()
        if not content:
            continue
        for attr in ("property", "name", "itemprop"):
            key = (m.get(attr) or "").strip().lower()
            if key and key not in out:
                out[key] = content
    return out


def _main(doc: Any) -> Any | None:
    """Hovedindhold: article/main om sidens h1, ellers første article uden for aside/nav/footer, ellers main.

    Relaterede artikler (også <article>) må ikke forveksles med selve artiklen.
    """
    for h1 in doc.iter("h1"):
        for anc in h1.iterancestors():
            if anc.tag in ("article", "main") or anc.get("role") == "main":
                return anc
    for art in doc.iter("article"):
        if not any(anc.tag in ("aside", "nav", "footer") for anc in art.iterancestors()):
            return art
    found = doc.xpath("//main | //*[@role='main']")
    return found[0] if found else None


def _title(doc: Any, main: Any | None, meta: dict[str, str], names: Iterable[str]) -> str:
    """og:title → første h1 (helst i hovedindholdet) → <title>, uden kildehale.

    Er en kandidat kun sidens navn, prøves den næste.
    """
    names = list(names)
    headings = [next(main.iter("h1"), None) if main is not None else None, next(doc.iter("h1"), None)]
    candidates = [meta.get("og:title"), *(_text(h) for h in headings if h is not None)]
    title_el = doc.find(".//title")
    if title_el is not None:
        candidates.append(_text(title_el))
    for raw in candidates:
        title = strip_site_tail(" ".join((raw or "").split()), names)
        if title and not matches_name(title, names):
            return title
    return ""


_ARTICLE_TYPE_RE = re.compile(r"article|posting|report|release|news", re.IGNORECASE)
_JSONLD_WRAP_RE = re.compile(r"^\s*(?:<!--|<!\[CDATA\[)|(?:-->|\]\]>)\s*$")
_META_PUBLISHED = ("article:published_time", "og:article:published_time", "datepublished")
_META_DATES = ("publication-date", "publication_date", "pubdate", "date", "dc.date", "dc.date.issued",
               "dcterms.date", "dcterms.issued")  # fmt: skip


def _walk_ld(node: Any, depth: int = 0) -> Iterator[tuple[bool, str]]:
    """(er artikeltype, datePublished) for alle objekter, også i @graph og lister."""
    if depth > 10:
        return
    if isinstance(node, list):
        for x in node:
            yield from _walk_ld(x, depth + 1)
    elif isinstance(node, dict):
        value = node.get("datePublished")
        if isinstance(value, str) and value.strip():
            types = node.get("@type")
            types = types if isinstance(types, list) else [types]
            yield any(isinstance(t, str) and _ARTICLE_TYPE_RE.search(t) for t in types), value
        for v in node.values():
            if isinstance(v, dict | list):
                yield from _walk_ld(v, depth + 1)


def _jsonld_dates(doc: Any) -> list[str]:
    """datePublished fra JSON-LD; artikeltyper (NewsArticle, BlogPosting …) før fx WebPage."""
    preferred: list[str] = []
    other: list[str] = []
    for script in doc.iter("script"):
        if not (script.get("type") or "").strip().lower().startswith("application/ld+json"):
            continue
        raw = _JSONLD_WRAP_RE.sub("", script.text or "")
        if not raw.strip() or len(raw) > 1_000_000:
            continue
        try:
            data = json.loads(raw, strict=False)
        except (ValueError, RecursionError):
            continue
        for is_article, value in _walk_ld(data):
            (preferred if is_article else other).append(value)
    return preferred + other


_HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")
_ASIDE = ("aside", "nav", "footer")


def _body_article(main: Any | None) -> Any | None:
    """Står sidens h1 i <main> uden for et <article>, og rummer main præcis ét <article> uden egne overskrifter,
    er det artiklens brødtekst (med dens <time>) og ikke en anden artikel. Relaterede artikler har en titel."""
    if main is None or main.tag == "article":
        return None
    arts = [a for a in main.iter("article") if not any(anc.tag in _ASIDE for anc in a.iterancestors())]
    if len(arts) == 1 and next(arts[0].iter(*_HEADINGS), None) is None:
        return arts[0]
    return None


def _elsewhere(el: Any, main: Any | None, body: Any | None = None) -> bool:
    """Står elementet i aside/nav/footer eller i en anden artikel end hovedindholdet (fx relaterede)?"""
    for anc in el.iterancestors():
        if anc is main:
            return False
        if anc is body:
            continue
        if anc.tag in _ASIDE or (anc.tag == "article" and main is not None):
            return True
    return False


def _time_values(doc: Any, main: Any | None) -> Iterator[str]:
    """<time datetime> i hovedindholdet først (også dets header), derefter resten af siden i rækkefølge."""
    body = _body_article(main)
    times = [el for el in doc.iter("time") if el.get("datetime") and not _elsewhere(el, main, body)]
    own = [el for el in times if main is not None and any(anc is main for anc in el.iterancestors())]
    yield from (el.get("datetime") for el in own + times)


def _published(
    doc: Any, main: Any | None, meta: dict[str, str], url: str, now: datetime, lang: str = "da"
) -> tuple[datetime | None, str]:
    """Udgivelsesdato og date_quality efter KONTRAKTER §5.5."""
    for values in (
        _jsonld_dates(doc),
        (meta[k] for k in _META_PUBLISHED if k in meta),
        _time_values(doc, main),
        (meta[k] for k in _META_DATES if k in meta),
    ):
        for value in values:
            found = parse_date(value, lang)
            if found and _plausible(found[0], now):
                return found[0], _quality(found[1])
    in_url = url_date(url)
    if in_url is not None and _plausible(in_url, now):
        return in_url, "url"
    found = text_date(_text(main, TEXT_DATE_CHARS), now, lang) if main is not None else None
    if found:
        return found[0], _quality(found[1])
    return None, "fundet"


def extract_page(
    content: bytes,
    url: str,
    content_type: str | None = None,
    *,
    now: datetime | None = None,
    names: Iterable[str] = (),
    lang: str = "da",
) -> Page | None:
    """Titel, dato, date_quality og teaser fra en artikelside. None, hvis svaret ikke er HTML.

    Ren funktion uden netværk. names (kildens navn og vært) bruges til at fjerne kildehaler fra titlen;
    now til at afvise datoer mere end 2 t ude i fremtiden; lang (kildens sprog) til datoer med engelske
    månedsnavne, som kun læses for engelske kilder.
    """
    if not content or not is_html(content_type, content):
        return None
    doc = parse_html(content, content_type)
    if doc is None:
        return None
    now = ensure_utc(now) if now else now_utc()
    meta = _meta(doc)
    main = _main(doc)
    published, quality = _published(doc, main, meta, url, now, lang)
    teaser = meta.get("og:description") or meta.get("description") or ""
    return Page(_title(doc, main, meta, names), published, quality, teaser)


# ── Sitemap ─────────────────────────────────────────────────


class SitemapError(ValueError):
    """Svaret er ikke et brugbart sitemap."""


@dataclass
class SitemapEntry:
    loc: str
    lastmod: datetime | None = None
    news_title: str | None = None  # Google News-sitemap: <news:title>
    news_published: datetime | None = None  # <news:publication_date>
    news_quality: str = "kilde"


@dataclass
class Sitemap:
    kind: str  # "urlset" eller "sitemapindex"
    entries: list[SitemapEntry]
    news: bool = False  # Google News-sitemap (navnerummet er erklæret eller brugt)


def _gunzip(data: bytes, limit: int = MAX_XML_BYTES) -> bytes:
    """Pak gzip ud (også flere medlemmer) med loft over den udpakkede størrelse."""
    out = bytearray()
    try:
        while data:
            d = zlib.decompressobj(16 + zlib.MAX_WBITS)
            out += d.decompress(data, limit + 1 - len(out))
            if len(out) > limit:
                raise SitemapError(f"udpakket over {limit / MB:g} MB")
            data = d.unused_data if d.eof and d.unused_data[:2] == GZIP_MAGIC else b""
    except zlib.error as e:
        raise SitemapError(f"ugyldig gzip: {e}") from e
    return bytes(out)


def _xml_parser() -> etree.XMLParser:
    # Ingen DTD, ingen entiteter og intet netværk: XXE og "billion laughs" virker ikke
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        huge_tree=False,
        recover=True,
        remove_comments=True,
        remove_pis=True,
    )


def _local(el: Any) -> str:
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


def _child(el: Any, name: str) -> Any | None:
    """Første barn med det lokale navn (navnerummets præfiks er ligegyldigt)."""
    if el is None:
        return None
    for c in el:
        if _local(c) == name:
            return c
    return None


def _value(el: Any) -> str:
    """Elementets tekst (CDATA er almindelig tekst). Elementer med børn, fx en uopløst entitet, er tomme."""
    if el is None or len(el):
        return ""
    return (el.text or "").strip()


# Et & der ikke indleder en entitet ("navn;", "#123;", "#x1F;"). CDATA-sektioner springes over.
_BARE_AMP_RE = re.compile(rb"<!\[CDATA\[.*?\]\]>|&(?!(?:[A-Za-z_:][\w.:-]*|#\d+|#x[0-9A-Fa-f]+);)", re.DOTALL)


def _escape_amp(data: bytes) -> bytes:
    """Escape løse & ("?id=1&lang=da"), som libxml2 ellers smider væk sammen med navnet efter dem."""
    if b"&" not in data or data[:2] in (codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE) or b"\x00" in data[:4]:
        return data  # utf-16 kan ikke behandles som bytes
    return _BARE_AMP_RE.sub(lambda m: m.group(0) if m.group(0).startswith(b"<") else b"&amp;", data)


def _loc(text: str, base: str) -> str:
    """URL fra <loc>: whitespace i enderne fjernes og kodes inde i URL'en; relative URL'er gøres absolutte."""
    loc = re.sub(r"\s+", "%20", text.strip())
    if loc and base:
        loc = urljoin(base, loc)
    return loc if loc.startswith(("http://", "https://")) else ""


def parse_sitemap(content: bytes, url: str = "", max_bytes: int = MAX_XML_BYTES) -> Sitemap:
    """urlset eller sitemapindex fra (evt. gzippet) XML. Rejser SitemapError."""
    data = content or b""
    gz_url = url.lower().split("?")[0].endswith(".gz")
    # En .gz-URL kan være pakket ud af HTTP-laget allerede (Content-Encoding); så starter den med "<"
    if data[:2] == GZIP_MAGIC or (gz_url and not data.lstrip().startswith(b"<")):
        data = _gunzip(data, max_bytes)
    if len(data) > max_bytes:
        raise SitemapError(f"over {max_bytes / MB:g} MB")
    if not data.strip():
        raise SitemapError("tomt svar")
    parser = _xml_parser()
    try:
        root = etree.fromstring(_escape_amp(data), parser)
    except etree.XMLSyntaxError as e:
        raise SitemapError(f"ugyldig XML: {e}") from e
    # recover=True retter småfejl; et dokument, libxml2 stoppede pga. entiteter, afvises
    if any(k in err.type_name for err in parser.error_log for k in _ENTITY_ABUSE):
        raise SitemapError("afvist: entiteter i DTD'en (løkke eller for stor udfoldning)")
    kind = _local(root) if root is not None else ""
    if kind not in ("urlset", "sitemapindex"):
        raise SitemapError(f"ikke et sitemap (<{kind or '?'}>)")
    child = "url" if kind == "urlset" else "sitemap"
    is_news = NEWS_NS in (root.nsmap or {}).values()
    entries: list[SitemapEntry] = []
    for el in root:
        if _local(el) != child:
            continue
        loc = _loc(_value(_child(el, "loc")), url)
        if not loc:
            continue
        lastmod = parse_date(_value(_child(el, "lastmod")))
        entry = SitemapEntry(loc, lastmod[0] if lastmod else None)
        news = _child(el, "news")
        is_news = is_news or news is not None
        title = " ".join(_value(_child(news, "title")).split())
        published = parse_date(_value(_child(news, "publication_date")))
        if title and published:
            entry.news_title, entry.news_published = title, published[0]
            entry.news_quality = _quality(published[1])
        entries.append(entry)
    return Sitemap(kind, entries, is_news)


def choose_sub_sitemaps(entries: list[SitemapEntry], n: int) -> list[SitemapEntry]:
    """De n under-sitemaps med nyeste lastmod. Uden lastmod de sidste n i dokumentet (det sidste først).

    Ved samme lastmod (typisk genereringstidspunktet for dem alle) vinder det sidste i dokumentet, som uden
    lastmod.
    """
    if n <= 0:
        return []
    if any(e.lastmod for e in entries):
        order = sorted(
            range(len(entries)),
            key=lambda i: (entries[i].lastmod is None, -(entries[i].lastmod or OLDEST).timestamp(), -i),
        )
        return [entries[i] for i in order[:n]]
    return list(reversed(entries[-n:]))


# ── Fælles for sitemap og html ──────────────────────────────


def site_names(source: Source) -> list[str]:
    """Navne en kildehale kan have: navnet, dets dele ("ARC (Amager Ressourcecenter)"), aliases og værter."""
    names = [source.name, *source.aliases]
    m = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", source.name)
    if m:
        names += [m.group(1), m.group(2)]
    for h in source_hosts(source):
        names += [h, h.split(".")[0]]
    return names


def strict_patterns(keywords: Keywords) -> list[tuple[str, re.Pattern]]:
    """Stærke ord og navne fra keywords.yaml, også med æøå skrevet som ae/oe/aa (som i URL-slugs)."""
    pats = [p for lang in keywords.strong.values() for p in lang] + list(keywords.names)
    return compile_patterns(list(dict.fromkeys(pats + [p.translate(TRANSLIT) for p in pats])))


def slug_text(url: str) -> str:
    """URL'ens sti som tekst, hvor - _ / . og + er mellemrum ("/nyt/ny-plads" → "nyt ny plads")."""
    try:
        path = unquote(urlsplit(url or "").path)
    except ValueError:
        return ""
    return " ".join(re.sub(r"[-_/.+]+", " ", path).split())


def _content_type(res: FetchResult) -> str | None:
    return {k.lower(): v for k, v in res.headers.items()}.get("content-type")


def _sample(items: list, n: int) -> list:
    """Op til n jævnt fordelte eksempler (så det ikke kun er menuen øverst på siden)."""
    if len(items) <= n:
        return list(items)
    step = len(items) / n
    return [items[int(i * step)] for i in range(n)]


def _day(dt: datetime | None) -> str:
    return to_cph(dt).date().isoformat() if dt else "uden lastmod"


@dataclass
class _Target:
    """En ny side, der skal hentes."""

    url: str
    iid: str
    lastmod: datetime | None = None
    order: int = 0
    text: str = ""  # linktekst (html)
    list_date: datetime | None = None  # dato ved linket på listen (html)


class _Job:
    """Én kildes kørsel: filtre, seen-state, sidehentning, fejl og diagnose."""

    def __init__(self, source: Source, fetcher: Fetcher, ctx: CollectContext):
        self.source = source
        self.fetcher = fetcher
        self.ctx = ctx
        self.cfg = ctx.config.settings.pages
        self.now = ensure_utc(ctx.now)
        today = to_cph(self.now).date()
        self.today = today.isoformat()
        self.refresh_before = (today - timedelta(days=self.cfg.seen_refresh_days)).isoformat()
        self.seen = ctx.seen.setdefault(source.id, {})
        self.hosts = source_hosts(source)
        self.match = re.compile(source.match) if source.match else None
        self.names = site_names(source)
        self.strict = strict_patterns(ctx.config.keywords) if source.filter == "strict" else None
        self.result = CollectResult()
        self.errors: list[str] = []  # hver af dem gør kilden fejlet i denne kørsel
        self.docs: list[str] = []  # sitemaps og lister, der er forespurgt i denne kørsel
        self.backlog = False  # sider, der venter til næste kørsel
        self.incomplete = False  # sitemaps/lister, der ikke blev læst (forbigående fejl eller tidsbudget)
        self.unchanged = 0  # sitemaps (ikke indeks) og lister, der svarede 304

    def diag(self, line: str) -> None:
        self.result.diagnostics.append(line)

    def on_host(self, url: str) -> bool:
        """På kildens vært (homepage eller domains, også underdomæner)?"""
        host = host_of(url)
        return any(host == h or host.endswith("." + h) for h in self.hosts)

    def matches(self, url: str) -> bool:
        """På kildens vært og match-regex (ingen match = alle)."""
        return self.on_host(url) and (self.match is None or bool(self.match.search(url)))

    def seen_before(self, iid: str) -> bool:
        """Kendt URL? Datoen fornyes kun, når den er ældre end seen_refresh_days (ingen ændring hver time)."""
        stamp = self.seen.get(iid)
        if stamp is None:
            return False
        if stamp < self.refresh_before:
            self.seen[iid] = self.today
        return True

    def touch_all(self) -> None:
        """Uændret sitemap eller liste (304): alt, vi kender fra den, er stadig observeret."""
        for iid, stamp in self.seen.items():
            if stamp < self.refresh_before:
                self.seen[iid] = self.today

    def mark(self, iid: str) -> None:
        self.seen[iid] = self.today

    def strict_ok(self, url: str, text: str = "") -> bool:
        """filter strict: stærkt ord eller navn i slug'en (eller linkteksten), ellers hentes siden ikke."""
        if self.strict is None:
            return True
        return bool(find_hits(slug_text(url), self.strict) or (text and find_hits(text, self.strict)))

    def get_doc(self, url: str) -> FetchResult:
        """Hent et sitemap eller en listeside (conditional GET efter første kørsel)."""
        res = self.fetcher.get(url, conditional=self.ctx.conditional)
        self.result.http_status = res.status or self.result.http_status
        self.docs.append(url)
        return res

    def forget(self, url: str) -> None:
        """Glem dokumentets ETag (og husket indeks), så det hentes helt ved næste kørsel."""
        self.fetcher.http_cache.pop(url, None)

    def remembered_subs(self, url: str) -> list[str] | None:
        """Under-sitemaps, som indekset pegede på sidst (state/http.json); None, hvis url ikke var et indeks."""
        return _subs(self.fetcher.http_cache, url)

    def remember_subs(self, url: str, subs: list[str]) -> None:
        entry = self.fetcher.http_cache.get(url)
        # Altid en ny dict: pipeline ruller http_cache tilbage med en overfladisk kopi, hvis kilden fejler
        self.fetcher.http_cache[url] = {**(entry if isinstance(entry, dict) else {}), SUBS_KEY: subs}

    def fetch_pages(self, targets: list[_Target]) -> None:
        """Hent nye sider i rækkefølge, højst max_pages. Resten tages næste gang og markeres ikke som set.

        Varige fejl (4xx undtagen 408/425/429, robots.txt-forbud, for stort svar) markeres som set, så siden ikke
        prøves ved hver kørsel. Forbigående fejl (5xx, timeout, 429) markeres ikke og prøves igen.
        """
        limit = self.cfg.max_pages
        max_bytes = int(self.cfg.max_page_mb * MB)
        attempts = ok = permanent = blocked = not_html = untitled = broken = 0
        failures: list[str] = []
        for n, t in enumerate(targets):
            if attempts >= limit:
                self.backlog = True
                self.diag(f"{len(targets) - n} sider venter til næste kørsel (højst {limit} pr. kørsel)")
                break
            res = self.fetcher.get(t.url, conditional=False, max_bytes=max_bytes)
            if res.error == BUDGET_EXHAUSTED:
                self.backlog = True
                rest = len(targets) - n
                log.warning(
                    "%s: tidsbudgettet er brugt; %d sider venter til næste kørsel", self.source.id, rest
                )
                self.diag(f"tidsbudgettet er brugt: {rest} sider venter til næste kørsel")
                break
            if res.error == ROBOTS_BLOCKED:
                blocked += 1
                self.mark(t.iid)  # forbudt af robots.txt: prøves ikke igen
                log.info("%s: %s er blokeret af robots.txt", self.source.id, t.url)
                continue
            attempts += 1
            if res.error or res.content is None:
                failures.append(f"{t.url}: {res.error or 'intet indhold'}")
                if res.permanent:
                    permanent += 1
                    self.mark(t.iid)  # varig fejl (fx 404 eller 410): prøves ikke igen
                else:
                    self.backlog = True  # forbigående fejl: prøves igen ved næste kørsel
                continue
            ok += 1
            self.mark(t.iid)  # hentet og udtrukket: også hvis forfiltret afviser den bagefter
            try:
                page = extract_page(
                    res.content,
                    t.url,
                    _content_type(res),
                    now=self.now,
                    names=self.names,
                    lang=self.source.lang,
                )
            except Exception:  # én side må ikke vælte hele kilden
                log.exception("%s: %s kunne ikke udtrækkes", self.source.id, t.url)
                broken += 1
                continue
            if page is None:
                not_html += 1
                continue
            if not page.title:
                untitled += 1
                continue
            published, quality = page.published, page.date_quality
            if published is None and t.list_date is not None:
                published, quality = t.list_date, "liste"
            self.result.entries.append(
                RawEntry(
                    source_id=self.source.id,
                    url=t.url,
                    title=page.title,
                    teaser=page.teaser,
                    published=published,
                    date_quality=quality,
                    lang=self.source.lang,
                    categories=[],
                    publisher_name=None,
                    publisher_domain=None,
                    found_via="feed",
                )
            )
        self.diag(
            f"sider: {attempts} hentet ({ok} ok, {len(failures)} fejl), {permanent} med varig fejl, "
            f"{blocked} blokeret af robots.txt, {not_html} ikke HTML, {untitled} uden titel"
            + (f", {broken} kunne ikke udtrækkes" if broken else "")
        )
        for f in failures[:DIAG_URLS]:
            self.diag(f"  fejl: {f}")
        if failures and ok == 0:
            self.errors.append(f"alle {attempts} sidehentninger fejlede ({failures[0]})")
        elif failures:
            log.warning(
                "%s: %d af %d sidehentninger fejlede, fx %s",
                self.source.id,
                len(failures),
                attempts,
                failures[0],
            )
        elif blocked and ok == 0:
            self.errors.append(f"alle {blocked} sider er blokeret af robots.txt")

    def finish(self) -> CollectResult:
        if self.errors or self.backlog:
            # Næste kørsel skal læse sitemaps og lister helt: en fejl vurderes igen og står i sundheden, til den
            # er rettet, og en 304 skjuler ikke restkøen
            for url in self.docs:
                self.forget(url)
        if self.errors:
            self.result.error = "; ".join(dict.fromkeys(self.errors))[:500]
        self.result.backlog = self.backlog or self.incomplete
        if self.result.backlog and self.ctx.first_run:
            self.diag("første kørsel: baseline er ikke komplet, så næste kørsel er også en første kørsel")
        return self.result


# ── method: sitemap ─────────────────────────────────────────

SUBS_KEY = "sitemaps"  # state/http.json: de under-sitemaps, et indeks pegede på, da det sidst blev læst


def _subs(http_cache: dict, url: str) -> list[str] | None:
    entry = http_cache.get(url)
    subs = entry.get(SUBS_KEY) if isinstance(entry, dict) else None
    return [u for u in subs if isinstance(u, str)] if isinstance(subs, list) else None


def remembered_sitemaps(http_cache: dict, feeds: Iterable[str]) -> set[str]:
    """Under-sitemaps, kildens indeks pegede på ved sidste læsning. Deres ETags gemmes også i state/http.json."""
    out: set[str] = set()
    todo = [(url, 0) for url in feeds]
    while todo:
        url, depth = todo.pop()
        subs = _subs(http_cache, url) if depth <= MAX_INDEX_DEPTH else None
        for u in subs or []:
            if u not in out:
                out.add(u)
                todo.append((u, depth + 1))
    return out


def _read_sitemaps(job: _Job) -> list[Sitemap] | None:
    """Hent kildens sitemaps og følg indeks.

    Et indeks, der svarer 304, betyder ikke "intet nyt": de under-sitemaps, det pegede på sidst, hentes stadig
    med deres egne betingede forespørgsler. Returnerer de læste urlsets, eller None, hvis intet urlset blev læst
    (fejl, eller alt var uændret).
    """
    cfg = job.cfg
    max_bytes = int(job.ctx.config.settings.fetch.max_response_mb * MB)
    # (url, dybde, topniveau)
    queue: deque[tuple[str, int, bool]] = deque((url, 0, True) for url in job.source.feeds)
    done: set[str] = set()  # samme sitemap hentes kun én gang pr. kørsel
    urlsets: list[Sitemap] = []
    top_errors: list[str] = []
    sub_errors: list[str] = []
    notes: list[str] = []  # hvorfor et indeks ikke gav noget at følge
    top_ok = fetches = 0
    stopped = False
    while queue:
        url, depth, top = queue.popleft()
        if item_id(url) in done:
            continue
        if fetches >= cfg.max_sitemap_fetches:
            job.diag(f"højst {fetches} sitemap-hentninger pr. kørsel: {len(queue) + 1} springes over")
            notes.append(f"loftet på {fetches} sitemap-hentninger er nået")
            break
        done.add(item_id(url))
        fetches += 1
        res = job.get_doc(url)
        errors = top_errors if top else sub_errors
        if res.error:
            errors.append(f"{url}: {res.error}")
            log.warning("%s: %s: %s", job.source.id, url, res.error)
            if res.error == BUDGET_EXHAUSTED:
                stopped = job.incomplete = True  # resten læses ved næste kørsel
                break
            job.incomplete = job.incomplete or not res.permanent
            continue
        if res.not_modified:
            top_ok += 1 if top else 0
            subs = job.remembered_subs(url)
            if subs is None:
                job.unchanged += 1
                job.touch_all()
                job.diag(f"sitemap {url}: uændret (304)")
                continue
            # Indekset er uændret, men dets under-sitemaps kan have fået nye URL'er
            if depth > MAX_INDEX_DEPTH:
                subs = []
            subs = [u for u in subs if job.on_host(u)][: cfg.max_sub_sitemaps]
            job.diag(f"indeks {url}: uændret (304); følger de {len(subs)} under-sitemaps fra sidst")
            if not subs:
                notes.append(f"{url}: ingen under-sitemaps at følge")
            queue.extendleft((u, depth + 1, False) for u in reversed(subs))
            continue
        try:
            sm = parse_sitemap(res.content or b"", url, max_bytes)
        except SitemapError as e:
            errors.append(f"{url}: {e}")
            log.warning("%s: %s: %s", job.source.id, url, e)
            job.forget(url)  # fejl i indholdet: hentes helt igen næste gang
            continue
        top_ok += 1 if top else 0
        if sm.kind == "sitemapindex":
            if depth > MAX_INDEX_DEPTH:
                job.remember_subs(url, [])
                job.diag(f"indeks {url}: for dybt indlejret; følges ikke")
                notes.append(f"{url}: for dybt indlejret")
                continue
            # Kun under-sitemaps på kildens egne værter (et indeks må ikke sende os til fremmede værter)
            own = [e for e in sm.entries if job.on_host(e.loc)]
            chosen = choose_sub_sitemaps(own, cfg.max_sub_sitemaps)
            job.remember_subs(url, [e.loc for e in chosen])
            foreign = len(sm.entries) - len(own)
            note = f" ({foreign} på fremmede værter springes over)" if foreign else ""
            job.diag(f"indeks {url}: {len(sm.entries)} under-sitemaps, følger {len(chosen)}{note}")
            for e in chosen:
                job.diag(f"  {e.loc} (lastmod {_day(e.lastmod)})")
            if not chosen:
                why = f"{foreign} under-sitemaps på fremmede værter (tjek domains)" if foreign else "tomt indeks"
                notes.append(f"{url}: {why}")
            # Dybde først: et indlejret indeks' nyeste sitemaps hentes før de næste på listen
            queue.extendleft((e.loc, depth + 1, False) for e in reversed(chosen))
        else:
            urlsets.append(sm)
            job.diag(f"sitemap {url}: {len(sm.entries)} URL'er" + (" (Google News)" if sm.news else ""))
    if top_ok == 0:
        if not stopped:
            job.errors.append(combine_errors(top_errors, 0) or "ingen sitemap-URL i feeds")
        return None
    for e in top_errors + sub_errors:
        log.warning("%s: delvis fejl: %s", job.source.id, e)
    if not urlsets:
        # Intet nyt, hvis alt var uændret (304), eller tidsbudgettet stoppede læsningen; ellers en fejl
        if not job.unchanged and not stopped:
            if sub_errors:
                job.errors.append("ingen under-sitemaps kunne hentes: " + "; ".join(sub_errors)[:300])
            else:
                job.errors.append("indeks uden brugbare under-sitemaps: " + ("; ".join(notes) or "intet urlset"))
        return None
    return urlsets


def _window_days(job: _Job) -> int:
    """lastmod-vinduet i dage: 14 ved første kørsel, ellers 3. Har kilden været nede, rækker vinduet tilbage til
    dagen før sidste vellykkede kørsel (højst 14 dage), så artikler fra nedetiden ikke tabes."""
    cfg = job.cfg
    if job.ctx.first_run:
        return cfg.first_run_lastmod_days
    if job.ctx.last_ok is None:
        return cfg.lastmod_days
    since = (to_cph(job.now).date() - job.ctx.last_ok).days + 1
    return max(cfg.lastmod_days, min(cfg.first_run_lastmod_days, since))


def collect_sitemap(source: Source, fetcher: Fetcher, ctx: CollectContext) -> CollectResult:
    """Nye artikler fra kildens sitemaps (KONTRAKTER §5.6). lastmod finder dem, men er aldrig deres dato."""
    job = _Job(source, fetcher, ctx)
    urlsets = _read_sitemaps(job)
    if urlsets is None:
        return job.finish()

    days = _window_days(job)
    cutoff = cph_day_bounds(job.now - timedelta(days=days))[0]
    total = matching = in_window = no_lastmod = baseline = news = 0
    nonmatching: list[str] = []
    matched: list[str] = []
    targets: list[_Target] = []
    done: set[str] = set()
    entries = [e for sm in urlsets for e in sm.entries]
    for order, e in enumerate(entries):
        iid = item_id(e.loc)  # dubletter (også i flere sitemaps eller med www./uden) tælles én gang
        if iid in done:
            continue
        done.add(iid)
        total += 1
        if not job.matches(e.loc):
            nonmatching.append(e.loc)
            continue
        matching += 1
        matched.append(e.loc)
        if e.news_title:
            # Google News-sitemap: titel og dato står i sitemappet, så artiklen hentes ikke
            news += 1
            job.result.entries.append(
                RawEntry(
                    source_id=source.id,
                    url=e.loc,
                    title=e.news_title,
                    teaser="",
                    published=e.news_published,
                    date_quality=e.news_quality,
                    lang=source.lang,
                    categories=[],
                    publisher_name=None,
                    publisher_domain=None,
                    found_via="feed",
                )
            )
            continue
        known = job.seen_before(iid)
        if e.lastmod is None:
            no_lastmod += 1
            if known:
                continue
            if ctx.first_run:
                job.mark(iid)  # baseline: registreres uden at blive hentet
                baseline += 1
                continue
        else:
            if e.lastmod < cutoff:
                continue
            in_window += 1
            if known:
                continue
        targets.append(_Target(e.loc, iid, e.lastmod, order))

    new = len(targets)
    targets = [t for t in targets if job.strict_ok(t.url)]
    # Nyeste lastmod først; URL'er uden lastmod til sidst i dokumentets rækkefølge
    targets.sort(key=lambda t: (t.lastmod is None, -(t.lastmod or OLDEST).timestamp(), t.order))
    job.diag(
        f"URL'er: {total} i alt, {matching} matcher, {in_window} med lastmod inden for {days} dage, "
        f"{no_lastmod} uden lastmod ({baseline} registreret som baseline), {news} fra Google News, "
        f"{new} nye, {new - len(targets)} sprunget over (strict)"
    )
    if matched:
        job.diag(f"URL'er, der matcher (eksempler, match {source.match!r}):")
        for u in _sample(matched, DIAG_URLS):
            job.diag(f"  {u}")
    if nonmatching:
        job.diag(f"URL'er, der ikke matcher (eksempler, match {source.match!r}):")
        for u in _sample(nonmatching, DIAG_URLS):
            job.diag(f"  {u}")
    if total == 0:
        if all(sm.news for sm in urlsets):
            # Et Google News-sitemap viser kun de seneste 48 timer og er tomt i stille perioder
            job.diag("tomt Google News-sitemap: ingen artikler de seneste 48 timer (ikke en fejl)")
        elif not job.unchanged:
            job.errors.append("tomt sitemap (ingen URL'er)")
    elif matching == 0:
        if job.unchanged:  # de uændrede sitemaps kan rumme de matchende URL'er
            job.diag("0 matchende URL'er i de læste sitemaps; andre var uændrede (304)")
        else:
            job.errors.append("0 matchende URL'er i sitemap (tjek match og domains)")
    job.fetch_pages(targets)
    return job.finish()


# ── method: html ────────────────────────────────────────────


_NOT_LINKS = ("javascript:", "mailto:", "tel:", "data:")


def _anchor(el: Any) -> Any | None:
    """Linket for et valgt element: elementet selv, første a[href] indeni eller nærmeste a[href] udenom."""
    if el.tag == "a" and el.get("href"):
        return el
    for a in el.iter("a"):
        if a.get("href"):
            return a
    for a in el.iterancestors("a"):
        if a.get("href"):
            return a
    return None


def _absolute(base: str, href: str | None) -> str | None:
    """Absolut http(s)-URL uden fragment, eller None."""
    href = (href or "").strip()
    if not href or href.startswith("#") or href.lower().startswith(_NOT_LINKS):
        return None
    try:
        url = urldefrag(urljoin(base, href)).url
    except ValueError:
        return None
    return url if url.startswith(("http://", "https://")) else None


def _link_text(a: Any) -> str:
    """Linkets tekst, title eller aria-label; et billedlink uden tekst giver billedets alt-tekst."""
    text = _text(a) or a.get("title") or a.get("aria-label") or ""
    if not text.strip():
        text = next((img.get("alt") for img in a.iter("img") if (img.get("alt") or "").strip()), "")
    return " ".join(text.split())[:200]


def _node_date(node: Any, now: datetime, lang: str = "da") -> datetime | None:
    for t in node.iter("time"):
        found = parse_date(t.get("datetime") or _text(t), lang)
        if found and _plausible(found[0], now):
            return found[0]
    found = text_date(_text(node, LIST_DATE_CHARS), now, lang)
    return found[0] if found else None


def _list_date(
    a: Any, url: str, articles: set[str], base: str, now: datetime, lang: str = "da"
) -> datetime | None:
    """Dato ved linket på listen: <time datetime> eller dansk dato i linkets nærmeste container.

    Der søges højst LIST_DATE_LEVELS forældre op og aldrig i en container, der også rummer andre artikellinks.
    """
    node = a
    for _ in range(LIST_DATE_LEVELS + 1):
        if node is not a:
            hrefs = {_absolute(base, x.get("href")) for x in node.iter("a")}
            if (hrefs & articles) - {url}:
                break
        found = _node_date(node, now, lang)
        if found is not None:
            return found
        node = node.getparent()
        if node is None or node.tag in ("body", "html"):
            break
    return None


def _read_list(
    job: _Job, doc: Any, page_url: str, selector: CSSSelector, links: dict[str, _Target], own: set[str]
) -> None:
    """Find artikellinks på én listeside (højst max_links, dokumentets rækkefølge) og læg dem i links.

    own er item_id for kildens egne listesider, som aldrig er artikler (fx et menulink til listen selv).
    """
    base_el = doc.find(".//base[@href]")
    base = urljoin(page_url, base_el.get("href").strip()) if base_el is not None else page_url
    every = [a for a in doc.iter("a") if a.get("href")]
    picked: dict[str, Any] = {}  # url -> første link i dokumentets rækkefølge
    texts: dict[str, str] = {}  # url -> længste linktekst (et billedlink før titellinket er ofte tomt)
    for el in selector(doc):
        a = _anchor(el)
        url = _absolute(base, a.get("href")) if a is not None else None
        if not url:
            continue
        picked.setdefault(url, a)
        for x in (a, *el.iter("a")):
            if x.get("href") and _absolute(base, x.get("href")) == url:
                text = _link_text(x)
                if len(text) > len(texts.get(url, "")):
                    texts[url] = text
    matching = [(u, a) for u, a in picked.items() if job.matches(u) and item_id(u) not in own]
    job.diag(
        f"liste {page_url}: {len(every)} links på siden, {len(picked)} valgt af select "
        f"{job.source.select or DEFAULT_SELECT!r}, {len(matching)} matcher {job.source.match!r}"
    )
    job.diag("alle links (eksempler):")
    for a in _sample(every, DIAG_LINKS):
        job.diag(f"  {_absolute(base, a.get('href')) or a.get('href')} | {_link_text(a)}")
    job.diag("matchende links (eksempler):")
    for u, _ in matching[:DIAG_LINKS]:
        job.diag(f"  {u} | {texts.get(u, '')}")

    articles = {u for u, _ in matching}
    added = 0
    for u, a in matching:
        if added >= job.cfg.max_links:
            break
        iid = item_id(u)
        if iid in links:
            continue
        date_near = _list_date(a, u, articles, base, job.now, job.source.lang)
        links[iid] = _Target(u, iid, order=len(links), text=texts.get(u, ""), list_date=date_near)
        added += 1


def collect_html(source: Source, fetcher: Fetcher, ctx: CollectContext) -> CollectResult:
    """Nye artikler fra kildens listesider (kun første side; KONTRAKTER §5.6)."""
    job = _Job(source, fetcher, ctx)
    select = source.select or DEFAULT_SELECT
    try:
        selector = CSSSelector(select, translator="html")
    except SelectorError as e:
        job.errors.append(f"ugyldig select {select!r}: {e}")
        return job.finish()

    links: dict[str, _Target] = {}
    own = {item_id(u) for u in source.feeds}
    errors: list[str] = []
    ok = read = 0
    for list_url in source.feeds:
        res = job.get_doc(list_url)
        if res.error:
            errors.append(f"{list_url}: {res.error}")
            log.warning("%s: %s: %s", source.id, list_url, res.error)
            job.incomplete = job.incomplete or not res.permanent
            continue
        if res.not_modified:
            ok += 1
            job.unchanged += 1
            job.touch_all()
            job.diag(f"liste {list_url}: uændret (304)")
            continue
        content = res.content or b""
        doc = parse_html(content, _content_type(res)) if is_html(_content_type(res), content) else None
        if doc is None:
            errors.append(f"{list_url}: listesiden er ikke HTML")
            log.warning("%s: %s er ikke HTML", source.id, list_url)
            job.forget(list_url)  # fejl i indholdet: hentes helt igen næste gang
            continue
        ok += 1
        read += 1
        _read_list(job, doc, list_url, selector, links, own)
    if ok == 0:
        job.errors.append(combine_errors(errors, 0) or "ingen listeside i feeds")
        return job.finish()
    for e in errors:
        log.warning("%s: delvis fejl: %s", source.id, e)
    if read and not links:
        if job.unchanged:  # de uændrede lister kan rumme de matchende links
            job.diag("0 matchende links på de læste listesider; andre var uændrede (304)")
        else:
            job.errors.append("0 matchende links på listesiden (tjek select og match)")

    targets = [t for t in links.values() if not job.seen_before(t.iid)]
    new = len(targets)
    targets = [t for t in targets if job.strict_ok(t.url, t.text)]
    job.diag(f"links: {len(links)} matchende, {new} nye, {new - len(targets)} sprunget over (strict)")
    job.fetch_pages(targets)
    return job.finish()
