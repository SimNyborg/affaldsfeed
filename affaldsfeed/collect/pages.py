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
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any, NamedTuple
from urllib.parse import unquote, urldefrag, urljoin, urlsplit

from cssselect import SelectorError
from dateutil import parser as dateparser
from lxml import etree
from lxml import html as lxml_html
from lxml.cssselect import CSSSelector

from affaldsfeed.collect import CollectContext, CollectResult, RawEntry, combine_errors
from affaldsfeed.config import source_hosts
from affaldsfeed.fetch import BUDGET_EXHAUSTED, ROBOTS_BLOCKED
from affaldsfeed.models import Keywords, Source
from affaldsfeed.normalize import TRANSLIT, host_of, item_id, matches_name, strip_site_tail
from affaldsfeed.relevance import compile_patterns, find_hits
from affaldsfeed.timeutil import CPH, cph_day_bounds, ensure_utc, now_utc, to_cph

if TYPE_CHECKING:
    from affaldsfeed.fetch import Fetcher, FetchResult

log = logging.getLogger(__name__)

MAX_XML_BYTES = 50 * 1024 * 1024  # loft over et udpakket sitemap
GZIP_MAGIC = b"\x1f\x8b"
_ENTITY_ABUSE = ("ENTITY_LOOP", "RESOURCE_LIMIT", "AMPLIFICATION")  # libxml2-fejltyper
MAX_INDEX_DEPTH = 1  # indeks → højst ét indlejret indeks → urlset
FUTURE_SLACK = timedelta(hours=2)
OLDEST = datetime(2000, 1, 1, tzinfo=UTC)  # ældre "datoer" er fejl i siden
TEXT_DATE_CHARS = 1500  # "første del" af article/main, hvor en dansk dato må stå
LIST_DATE_LEVELS = 5  # så mange forældre op fra et link søges der efter en dato
LIST_DATE_CHARS = 400
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

_HAS_TIME_RE = re.compile(r"\d{1,2}:\d{2}")
_ISO_DAY_RE = re.compile(r"\d{4}-?\d{2}-?\d{2}")
_YEAR_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
_MONTHS = {
    "januar": 1, "februar": 2, "marts": 3, "april": 4, "maj": 5, "juni": 6, "juli": 7, "august": 8,
    "september": 9, "oktober": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9,
    "okt": 10, "nov": 11, "dec": 12,
}  # fmt: skip
_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))
_DK_NAME_DATE_RE = re.compile(
    rf"(?<!\d)(?P<d>\d{{1,2}})\.?\s*(?P<m>{_MONTH_ALT})\.?,?\s+(?P<y>(?:19|20)\d{{2}})(?!\d)", re.IGNORECASE
)
_DK_NUM_DATE_RE = re.compile(r"(?<![\d.])(?P<d>\d{1,2})[./-](?P<m>\d{1,2})[./-](?P<y>(?:19|20)\d{2})(?!\d)")
_DK_TIME_RE = re.compile(r"[\s,–-]*(?:kl\.?|klokken)?\s*(?P<h>[01]?\d|2[0-3])[.:](?P<mi>[0-5]\d)(?!\d)")
_URL_DATE_RES = (
    re.compile(r"/(?P<y>(?:19|20)\d{2})/(?P<m>\d{1,2})/(?P<d>\d{1,2})(?!\d)"),
    re.compile(r"(?<!\d)(?P<y>(?:19|20)\d{2})-(?P<m>\d{2})-(?P<d>\d{2})(?!\d)"),
)


def _day_start(d: date) -> datetime:
    """En dato uden klokkeslæt er dagen i København."""
    return datetime.combine(d, time.min, tzinfo=CPH).astimezone(UTC)


def danish_date(text: str) -> tuple[datetime, bool] | None:
    """Første danske dato i teksten ("7. oktober 2026", "7. okt. 2026", "07.10.2026"), evt. med "kl. 14.32".

    Returnerer (UTC, har klokkeslæt).
    """
    found: list[tuple[int, int, date]] = []
    for rx, numeric in ((_DK_NAME_DATE_RE, False), (_DK_NUM_DATE_RE, True)):
        for m in rx.finditer(text or ""):
            month = int(m["m"]) if numeric else _MONTHS[m["m"].lower()]
            try:
                found.append((m.start(), m.end(), date(int(m["y"]), month, int(m["d"]))))
            except ValueError:
                continue
            break
    if not found:
        return None
    _, end, day = min(found)
    t = _DK_TIME_RE.match(text, end)
    if t:
        local = datetime.combine(day, time(int(t["h"]), int(t["mi"])), tzinfo=CPH)
        return local.astimezone(UTC), True
    return _day_start(day), False


def _dateutil(s: str) -> datetime | None:
    """dateutil som sidste udvej (fx RFC 822). Mangler år, måned eller dag, er strengen ingen dato."""
    try:
        a = dateparser.parse(s, dayfirst=True, default=datetime(2000, 1, 1))
        b = dateparser.parse(s, dayfirst=True, default=datetime(2001, 2, 2))
    except (ValueError, OverflowError, TypeError):  # dateutils ParserError er en ValueError
        return None
    return a if a.date() == b.date() else None


def parse_date(value: str | None) -> tuple[datetime, bool] | None:
    """Datostreng → (UTC, har klokkeslæt).

    Uden tidszone er tiden dansk; uden klokkeslæt er det dagen i København.
    """
    s = " ".join((value or "").split())
    if not s or len(s) > 80:
        return None
    try:
        if not _ISO_DAY_RE.match(s):
            raise ValueError("ikke ISO 8601")
        dt: datetime | None = dateparser.isoparse(s)
    except (ValueError, OverflowError):
        found = danish_date(s)
        if found is not None:
            return found
        dt = _dateutil(s) if _YEAR_RE.search(s) else None
    if dt is None or not 1900 <= dt.year <= 2100:  # fx "0001-01-01" fra et tomt CMS-felt
        return None
    if not _HAS_TIME_RE.search(s):
        return _day_start(dt.date()), False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=CPH)
    return dt.astimezone(UTC), True


def url_date(url: str) -> datetime | None:
    """Dato i URL'ens sti (/2026/10/07/ eller 2026-10-07) som dagens start i København."""
    try:
        path = unquote(urlsplit(url or "").path)
    except ValueError:
        return None
    for rx in _URL_DATE_RES:
        for m in rx.finditer(path):
            try:
                return _day_start(date(int(m["y"]), int(m["m"]), int(m["d"])))
            except ValueError:
                continue
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
_SINGLE_BYTE = {"iso8859-1", "iso8859-15", "cp1252", "ascii"}
_XML_DECL_RE = re.compile(r"^\s*<\?xml[^>]*\?>")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_VISIBLE_TEXT = etree.XPath(
    ".//text()[not(ancestor::script or ancestor::style or ancestor::noscript or ancestor::template)]"
)


def _codec(name: str | None) -> str | None:
    try:
        return codecs.lookup(name).name if name else None
    except LookupError:
        return None


def html_charset(content: bytes, content_type: str | None = None) -> str:
    """Tegnsæt: BOM → Content-Type → <meta charset> → utf-8 hvis gyldig → windows-1252.

    Siger header eller meta latin-1/windows-1252, men er siden gyldig utf-8 med æøå, er den utf-8
    (en hyppig fejl).
    """
    if content.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    m = _CHARSET_RE.search(content_type or "")
    declared = _codec(m.group(1)) if m else None
    if declared is None:
        mm = _META_CHARSET_RE.search(content[:4096])
        declared = _codec(mm.group(1).decode("ascii", "ignore")) if mm else None
    try:
        content.decode("utf-8")
        utf8 = True
    except UnicodeDecodeError:
        utf8 = False
    if declared == "utf-8":
        return declared if utf8 else "cp1252"
    if declared and not (declared in _SINGLE_BYTE and utf8 and not content.isascii()):
        return declared
    return "utf-8" if utf8 else "cp1252"


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
    text = content.decode(html_charset(content, content_type), errors="replace")
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


def _elsewhere(el: Any, main: Any | None) -> bool:
    """Står elementet i aside/nav/footer eller i en anden artikel end hovedindholdet (fx relaterede)?"""
    for anc in el.iterancestors():
        if anc is main:
            return False
        if anc.tag in ("aside", "nav", "footer") or (anc.tag == "article" and main is not None):
            return True
    return False


def _time_values(doc: Any, main: Any | None) -> Iterator[str]:
    """<time datetime> i hovedindholdet først (også dets header), derefter resten af siden i rækkefølge."""
    times = [el for el in doc.iter("time") if el.get("datetime") and not _elsewhere(el, main)]
    own = [el for el in times if main is not None and any(anc is main for anc in el.iterancestors())]
    yield from (el.get("datetime") for el in own + times)


def _published(
    doc: Any, main: Any | None, meta: dict[str, str], url: str, now: datetime
) -> tuple[datetime | None, str]:
    """Udgivelsesdato og date_quality efter KONTRAKTER §5.5."""
    for values in (
        _jsonld_dates(doc),
        (meta[k] for k in _META_PUBLISHED if k in meta),
        _time_values(doc, main),
        (meta[k] for k in _META_DATES if k in meta),
    ):
        for value in values:
            found = parse_date(value)
            if found and _plausible(found[0], now):
                return found[0], _quality(found[1])
    in_url = url_date(url)
    if in_url is not None and _plausible(in_url, now):
        return in_url, "url"
    found = danish_date(_text(main, TEXT_DATE_CHARS)) if main is not None else None
    if found and _plausible(found[0], now):
        return found[0], _quality(found[1])
    return None, "fundet"


def extract_page(
    content: bytes,
    url: str,
    content_type: str | None = None,
    *,
    now: datetime | None = None,
    names: Iterable[str] = (),
) -> Page | None:
    """Titel, dato, date_quality og teaser fra en artikelside. None, hvis svaret ikke er HTML.

    Ren funktion uden netværk. names (kildens navn og vært) bruges til at fjerne kildehaler fra titlen;
    now til at afvise datoer mere end 2 t ude i fremtiden.
    """
    if not content or not is_html(content_type, content):
        return None
    doc = parse_html(content, content_type)
    if doc is None:
        return None
    now = ensure_utc(now) if now else now_utc()
    meta = _meta(doc)
    main = _main(doc)
    published, quality = _published(doc, main, meta, url, now)
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


def _gunzip(data: bytes, limit: int = MAX_XML_BYTES) -> bytes:
    """Pak gzip ud (også flere medlemmer) med loft over den udpakkede størrelse."""
    out = bytearray()
    try:
        while data:
            d = zlib.decompressobj(16 + zlib.MAX_WBITS)
            out += d.decompress(data, limit + 1 - len(out))
            if len(out) > limit:
                raise SitemapError(f"udpakket over {limit // (1024 * 1024)} MB")
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


def _loc(text: str, base: str) -> str:
    """URL fra <loc>: whitespace i enderne fjernes og kodes inde i URL'en; relative URL'er gøres absolutte."""
    loc = re.sub(r"\s+", "%20", text.strip())
    if loc and base:
        loc = urljoin(base, loc)
    return loc if loc.startswith(("http://", "https://")) else ""


def parse_sitemap(content: bytes, url: str = "") -> Sitemap:
    """urlset eller sitemapindex fra (evt. gzippet) XML. Rejser SitemapError."""
    data = content or b""
    gz_url = url.lower().split("?")[0].endswith(".gz")
    # En .gz-URL kan være pakket ud af HTTP-laget allerede (Content-Encoding); så starter den med "<"
    if data[:2] == GZIP_MAGIC or (gz_url and not data.lstrip().startswith(b"<")):
        data = _gunzip(data)
    if len(data) > MAX_XML_BYTES:
        raise SitemapError(f"over {MAX_XML_BYTES // (1024 * 1024)} MB")
    if not data.strip():
        raise SitemapError("tomt svar")
    parser = _xml_parser()
    try:
        root = etree.fromstring(data, parser)
    except etree.XMLSyntaxError as e:
        raise SitemapError(f"ugyldig XML: {e}") from e
    # recover=True retter småfejl (fx et & uden escape); et dokument, libxml2 stoppede pga. entiteter, afvises
    if any(k in err.type_name for err in parser.error_log for k in _ENTITY_ABUSE):
        raise SitemapError("afvist: entiteter i DTD'en (løkke eller for stor udfoldning)")
    kind = _local(root) if root is not None else ""
    if kind not in ("urlset", "sitemapindex"):
        raise SitemapError(f"ikke et sitemap (<{kind or '?'}>)")
    child = "url" if kind == "urlset" else "sitemap"
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
        title = " ".join(_value(_child(news, "title")).split())
        published = parse_date(_value(_child(news, "publication_date")))
        if title and published:
            entry.news_title, entry.news_published = title, published[0]
            entry.news_quality = _quality(published[1])
        entries.append(entry)
    return Sitemap(kind, entries)


def choose_sub_sitemaps(entries: list[SitemapEntry], n: int) -> list[SitemapEntry]:
    """De n under-sitemaps med nyeste lastmod. Uden lastmod de sidste n i dokumentet (det sidste først)."""
    if n <= 0:
        return []
    if any(e.lastmod for e in entries):
        order = sorted(
            range(len(entries)),
            key=lambda i: (entries[i].lastmod is None, -(entries[i].lastmod or OLDEST).timestamp(), i),
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
        self.docs: list[str] = []  # hentede sitemaps og lister
        self.backlog = False  # sider, der venter til næste kørsel

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

    def fetch_pages(self, targets: list[_Target]) -> None:
        """Hent nye sider i rækkefølge, højst max_pages. Resten tages næste gang og markeres ikke som set."""
        limit = self.cfg.max_pages
        attempts = ok = blocked = not_html = untitled = 0
        failures: list[str] = []
        for n, t in enumerate(targets):
            if attempts >= limit:
                self.backlog = True
                self.diag(f"{len(targets) - n} sider venter til næste kørsel (højst {limit} pr. kørsel)")
                break
            res = self.fetcher.get(t.url, conditional=False)
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
                log.info("%s: %s er blokeret af robots.txt", self.source.id, t.url)
                continue
            attempts += 1
            if res.error or res.content is None:
                failures.append(f"{t.url}: {res.error or 'intet indhold'}")
                self.backlog = True
                continue
            ok += 1
            self.mark(t.iid)  # hentet og udtrukket: også hvis forfiltret afviser den bagefter
            page = extract_page(res.content, t.url, _content_type(res), now=self.now, names=self.names)
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
            f"sider: {attempts} hentet ({ok} ok, {len(failures)} fejl), {blocked} blokeret af robots.txt, "
            f"{not_html} ikke HTML, {untitled} uden titel"
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
        if self.backlog:
            # Restkø: glem sitemappets/listens ETag, så en 304 ikke skjuler resten ved næste kørsel
            for url in self.docs:
                self.fetcher.http_cache.pop(url, None)
        if self.errors:
            self.result.error = "; ".join(dict.fromkeys(self.errors))[:500]
        return self.result


# ── method: sitemap ─────────────────────────────────────────


def _read_sitemaps(job: _Job) -> list[SitemapEntry] | None:
    """Hent kildens sitemaps og følg indeks.

    Returnerer URL-posterne i rækkefølge, eller None, hvis intet urlset blev læst.
    """
    cfg = job.cfg
    # (url, dybde, topniveau)
    queue: deque[tuple[str, int, bool]] = deque((url, 0, True) for url in job.source.feeds)
    entries: list[SitemapEntry] = []
    top_errors: list[str] = []
    sub_errors: list[str] = []
    top_ok = urlsets = unchanged = fetches = 0
    stopped = False
    while queue:
        if fetches >= cfg.max_sitemap_fetches:
            job.diag(f"højst {fetches} sitemap-hentninger pr. kørsel: {len(queue)} springes over")
            break
        url, depth, top = queue.popleft()
        fetches += 1
        res = job.get_doc(url)
        errors = top_errors if top else sub_errors
        if res.error:
            errors.append(f"{url}: {res.error}")
            log.warning("%s: %s: %s", job.source.id, url, res.error)
            if res.error == BUDGET_EXHAUSTED:
                stopped = job.backlog = True  # resten af sitemappet læses ved næste kørsel
                break
            continue
        if res.not_modified:
            top_ok += 1 if top else 0
            unchanged += 1
            job.touch_all()
            job.diag(f"sitemap {url}: uændret (304)")
            continue
        try:
            sm = parse_sitemap(res.content or b"", url)
        except SitemapError as e:
            errors.append(f"{url}: {e}")
            log.warning("%s: %s: %s", job.source.id, url, e)
            continue
        top_ok += 1 if top else 0
        if sm.kind == "sitemapindex":
            if depth > MAX_INDEX_DEPTH:
                job.diag(f"indeks {url}: for dybt indlejret; følges ikke")
                continue
            # Kun under-sitemaps på kildens egne værter (et indeks må ikke sende os til fremmede værter)
            own = [e for e in sm.entries if job.on_host(e.loc)]
            chosen = choose_sub_sitemaps(own, cfg.max_sub_sitemaps)
            foreign = len(sm.entries) - len(own)
            note = f" ({foreign} på fremmede værter springes over)" if foreign else ""
            job.diag(f"indeks {url}: {len(sm.entries)} under-sitemaps, følger {len(chosen)}{note}")
            for e in chosen:
                job.diag(f"  {e.loc} (lastmod {_day(e.lastmod)})")
            # Dybde først: et indlejret indeks' nyeste sitemaps hentes før de næste på listen
            queue.extendleft((e.loc, depth + 1, False) for e in reversed(chosen))
        else:
            urlsets += 1
            job.diag(f"sitemap {url}: {len(sm.entries)} URL'er")
            entries.extend(sm.entries)
    if top_ok == 0:
        if not stopped:
            job.errors.append(combine_errors(top_errors, 0) or "ingen sitemap-URL i feeds")
        return None
    if urlsets == 0:
        if sub_errors and not unchanged and not stopped:
            job.errors.append("ingen under-sitemaps kunne hentes: " + "; ".join(sub_errors)[:300])
        return None
    for e in top_errors + sub_errors:
        log.warning("%s: delvis fejl: %s", job.source.id, e)
    return entries


def collect_sitemap(source: Source, fetcher: Fetcher, ctx: CollectContext) -> CollectResult:
    """Nye artikler fra kildens sitemaps (KONTRAKTER §5.6). lastmod finder dem, men er aldrig deres dato."""
    job = _Job(source, fetcher, ctx)
    entries = _read_sitemaps(job)
    if entries is None:
        return job.finish()

    days = job.cfg.first_run_lastmod_days if ctx.first_run else job.cfg.lastmod_days
    cutoff = cph_day_bounds(job.now - timedelta(days=days))[0]
    total = matching = in_window = no_lastmod = baseline = news = 0
    nonmatching: list[str] = []
    targets: list[_Target] = []
    done: set[str] = set()
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
    if nonmatching:
        job.diag(f"URL'er, der ikke matcher (eksempler, match {source.match!r}):")
        for u in _sample(nonmatching, DIAG_URLS):
            job.diag(f"  {u}")
    if matching == 0:
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
    return (_text(a) or a.get("title") or a.get("aria-label") or "").strip()[:200]


def _node_date(node: Any, now: datetime) -> datetime | None:
    for t in node.iter("time"):
        found = parse_date(t.get("datetime") or _text(t))
        if found and _plausible(found[0], now):
            return found[0]
    found = danish_date(_text(node, LIST_DATE_CHARS))
    if found and _plausible(found[0], now):
        return found[0]
    return None


def _list_date(a: Any, url: str, articles: set[str], base: str, now: datetime) -> datetime | None:
    """Dato ved linket på listen: <time datetime> eller dansk dato i linkets nærmeste container.

    Der søges højst LIST_DATE_LEVELS forældre op og aldrig i en container, der også rummer andre artikellinks.
    """
    node = a
    for _ in range(LIST_DATE_LEVELS + 1):
        if node is not a:
            hrefs = {_absolute(base, x.get("href")) for x in node.iter("a")}
            if (hrefs & articles) - {url}:
                break
        found = _node_date(node, now)
        if found is not None:
            return found
        node = node.getparent()
        if node is None or node.tag in ("body", "html"):
            break
    return None


def _read_list(job: _Job, doc: Any, page_url: str, selector: CSSSelector, links: dict[str, _Target]) -> None:
    """Find artikellinks på én listeside (højst max_links, dokumentets rækkefølge) og læg dem i links."""
    base_el = doc.find(".//base[@href]")
    base = urljoin(page_url, base_el.get("href").strip()) if base_el is not None else page_url
    every = [a for a in doc.iter("a") if a.get("href")]
    picked: list[tuple[str, Any]] = []
    urls: set[str] = set()
    for el in selector(doc):
        a = _anchor(el)
        url = _absolute(base, a.get("href")) if a is not None else None
        if url and url not in urls:
            urls.add(url)
            picked.append((url, a))
    matching = [(u, a) for u, a in picked if job.matches(u)]
    job.diag(
        f"liste {page_url}: {len(every)} links på siden, {len(picked)} valgt af select "
        f"{job.source.select or DEFAULT_SELECT!r}, {len(matching)} matcher {job.source.match!r}"
    )
    job.diag("alle links (eksempler):")
    for a in _sample(every, DIAG_LINKS):
        job.diag(f"  {_absolute(base, a.get('href')) or a.get('href')} | {_link_text(a)}")
    job.diag("matchende links (eksempler):")
    for u, a in matching[:DIAG_LINKS]:
        job.diag(f"  {u} | {_link_text(a)}")

    articles = {u for u, _ in matching}
    added = 0
    for u, a in matching:
        if added >= job.cfg.max_links:
            break
        iid = item_id(u)
        if iid in links:
            continue
        date_near = _list_date(a, u, articles, base, job.now)
        links[iid] = _Target(u, iid, order=len(links), text=_link_text(a), list_date=date_near)
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
    errors: list[str] = []
    ok = read = 0
    for list_url in source.feeds:
        res = job.get_doc(list_url)
        if res.error:
            errors.append(f"{list_url}: {res.error}")
            log.warning("%s: %s: %s", source.id, list_url, res.error)
            continue
        if res.not_modified:
            ok += 1
            job.touch_all()
            job.diag(f"liste {list_url}: uændret (304)")
            continue
        content = res.content or b""
        doc = parse_html(content, _content_type(res)) if is_html(_content_type(res), content) else None
        if doc is None:
            errors.append(f"{list_url}: listesiden er ikke HTML")
            log.warning("%s: %s er ikke HTML", source.id, list_url)
            continue
        ok += 1
        read += 1
        _read_list(job, doc, list_url, selector, links)
    if ok == 0:
        job.errors.append(combine_errors(errors, 0) or "ingen listeside i feeds")
        return job.finish()
    for e in errors:
        log.warning("%s: delvis fejl: %s", source.id, e)
    if read and not links:
        job.errors.append("0 matchende links på listesiden (tjek select og match)")

    targets = [t for t in links.values() if not job.seen_before(t.iid)]
    new = len(targets)
    targets = [t for t in targets if job.strict_ok(t.url, t.text)]
    job.diag(f"links: {len(links)} matchende, {new} nye, {new - len(targets)} sprunget over (strict)")
    job.fetch_pages(targets)
    return job.finish()
