"""Kildernes små logoer (favicons) til kortene (KONTRAKTER §6.4).

Indsamlingen henter dem sjældent og høfligt med samme Fetcher som kilderne: forsidens <link rel="icon">
(og apple-touch-icon), ellers /favicon.ico. Kun rasterbilleder gemmes (PNG, ICO, GIF, JPEG og WebP).
SVG gemmes aldrig, fordi en SVG kan indeholde scripts, der ville køre på sitets eget domæne, hvis filen
åbnes direkte. Filerne ligger i data/state/logos/<id>.<ext> med en oversigt i data/state/logos.json.
En kilde med domains på andre sites end forsiden (fx de regionale TV 2-stationer) får også et logo pr. site
med id'et <kilde-id>--<domæne>, og kortet vælger efter artiklens domæne.
"""

from __future__ import annotations

import base64
import binascii
import logging
import math
import re
import struct
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import NamedTuple
from urllib.parse import unquote_to_bytes, urljoin, urlsplit

from affaldsfeed import paths, store
from affaldsfeed.collect.pages import parse_html
from affaldsfeed.fetch import BUDGET_EXHAUSTED, ROBOTS_BLOCKED
from affaldsfeed.models import LogoSettings
from affaldsfeed.timeutil import iso, parse_iso

log = logging.getLogger(__name__)

STATE_FILE = "logos.json"
DIR_NAME = "logos"
EXTS = ("png", "ico", "gif", "jpg", "webp")
MIN_BYTES = 67  # det mindste gyldige PNG; mindre er altid en fejl
MIN_PX = 16  # mindre logoer (fx 1 × 1 pladsholdere) afvises
HOMEPAGE_MAX_BYTES = 3 * 1024 * 1024
MAX_TRIES = 3  # billeder, der prøves pr. kilde (efter forsiden); et robots.txt-forbud tæller ikke
MAX_CANDIDATES = 12  # kandidater, der overhovedet ses på
ACCEPT_IMAGE = "image/png,image/x-icon,image/vnd.microsoft.icon,image/gif,image/jpeg,image/webp;q=0.9,*/*;q=0.5"
ACCEPT_HTML = "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5"
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def logo_dir() -> Path:
    return paths.STATE_DIR / DIR_NAME


# ── Hvilke logoer ───────────────────────────────────────────


def _same_site(a: str, b: str) -> bool:
    """Samme site: ens værtsnavne, eller det ene er et underdomæne af det andet (www. tæller ikke)."""
    a, b = a.lower().removeprefix("www."), b.lower().removeprefix("www.")
    return bool(a and b) and (a == b or a.endswith("." + b) or b.endswith("." + a))


def site_domains(homepage: str | None, domains: Iterable[str]) -> list[str]:
    """Kildens domæner, der er et andet site end forsiden, fx de regionale TV 2-stationer.

    Over- og underdomæner af forsiden (tv2.dk og nyheder.tv2.dk) er samme site og tæller ikke med.
    """
    home = (urlsplit(homepage).hostname or "") if homepage else ""
    out: list[str] = []
    for raw in domains:
        d = raw.strip().lower().removeprefix("www.")
        if d and d not in out and not _same_site(d, home):
            out.append(d)
    return out


def domain_key(sid: str, domain: str) -> str:
    """Logo-id for et af kildens andre sites: <kilde-id>--<domæne med bindestreger>."""
    return f"{sid}--{domain.replace('.', '-')}"


class LogoTarget(NamedTuple):
    key: str  # logo-id: kildens id eller <kilde-id>--<domæne>
    source: str  # kildens id (til prioritet og --only)
    homepage: str | None
    also: tuple[str, ...] = ()  # adresser, hvis /favicon.ico prøves sidst (kildens feeds på eget site)


def logo_targets(info: Mapping, sources: Iterable) -> list[LogoTarget]:
    """Hver kendt afsender én gang og hvert andet site under en aktiv kilde.

    info er display.known_sources (tidligere id'er peger på kilden, der har overtaget dem), sources er
    kilderne fra sources.yaml (domains og feeds). Feeds på kildens eget site (forsidens vært og domains, der
    ikke er andre sites) giver ekstra bud på /favicon.ico, fx oda.ft.dk for Folketinget, hvis forside ikke
    kan hentes. Feeds hos tredjepart (fx en pressetjeneste) giver aldrig kildens logo.
    """
    by_id = {s.id: s for s in sources}
    out: list[LogoTarget] = []
    seen: set[str] = set()
    for si in info.values():
        if si.id in seen:
            continue
        seen.add(si.id)
        src = None if si.via_search else by_id.get(si.id)
        if src is None:
            out.append(LogoTarget(si.id, si.id, si.homepage))
            continue
        others = site_domains(src.homepage, src.domains)
        own = [urlsplit(src.homepage or "").hostname or ""]
        own += [d for d in src.domains if d.strip().lower().removeprefix("www.") not in others]
        also = tuple(u for u in src.feeds if any(_same_site(urlsplit(u).hostname or "", d) for d in own))
        out.append(LogoTarget(si.id, si.id, si.homepage, also))
        out += [LogoTarget(domain_key(si.id, d), si.id, f"https://{d}/") for d in others]
    return out


# ── Billeder ────────────────────────────────────────────────


def sniff(data: bytes) -> str | None:
    """Filtypen ud fra de første bytes (png, ico, gif, jpg, webp), ellers None (også SVG og HTML)."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\x00\x00\x01\x00"):
        return "ico"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def pixel_size(data: bytes, ext: str) -> int | None:
    """Største side i pixels for PNG, GIF og ICO (den største i ikonfilen); None, når den ikke kendes."""
    try:
        if ext == "png" and len(data) >= 24:
            w, h = struct.unpack(">II", data[16:24])
            return max(w, h)
        if ext == "gif" and len(data) >= 10:
            w, h = struct.unpack("<HH", data[6:10])
            return max(w, h)
        if ext == "ico" and len(data) >= 6:
            count = struct.unpack("<H", data[4:6])[0]
            sizes = []
            for i in range(min(count, 32)):
                entry = data[6 + 16 * i : 6 + 16 * i + 2]
                if len(entry) < 2:
                    break
                sizes.extend(b or 256 for b in entry)  # 0 betyder 256
            return max(sizes) if sizes else None
    except struct.error:
        return None
    return None


def acceptable(data: bytes | None, max_bytes: int) -> str | None:
    """Filtypen, når data er et brugbart logo, ellers None."""
    if not data or len(data) < MIN_BYTES or len(data) > max_bytes:
        return None
    ext = sniff(data)
    if ext is None:
        return None
    size = pixel_size(data, ext)
    if size is not None and size < MIN_PX:
        return None
    return ext


# ── Kandidater på forsiden ──────────────────────────────────


@dataclass(frozen=True)
class IconLink:
    url: str  # http(s)-adresse eller en data:-URI
    rank: float  # lavere er bedre


def _size_of(sizes: str) -> int | None:
    """Største størrelse i sizes="16x16 32x32"; None ved "any" eller intet."""
    best = None
    for part in (sizes or "").lower().split():
        m = re.fullmatch(r"(\d+)x(\d+)", part)
        if m:
            best = max(best or 0, int(m.group(1)), int(m.group(2)))
    return best


def _rank(size: int | None, touch: bool, ico: bool) -> float:
    """Bedst er 32 til 96 px (skarpt i 16 px på skærme med høj opløsning) og PNG frem for ICO."""
    if size is None:
        base = 1.5 if touch else 1.0
    elif 32 <= size <= 96:
        base = 0.0
    elif 96 < size <= 192:
        base = 1.0
    elif size >= MIN_PX:
        base = 2.0 + (0.5 if size < 32 else math.log2(size / 192))
    else:
        base = 9.0
    return base + (0.25 if ico else 0.0)


def icon_links(content: bytes, page_url: str, content_type: str | None = None) -> list[IconLink]:
    """Ikonerne i forsidens <link rel="icon"> og apple-touch-icon, bedste først. SVG og mask-icon udelades."""
    doc = parse_html(content, content_type)
    if doc is None:
        return []
    base = page_url
    for href in doc.xpath("//base/@href")[:1]:
        base = urljoin(page_url, href.strip())
    out: dict[str, float] = {}
    for i, link in enumerate(doc.xpath("//link[@rel][@href]")):
        rels = set((link.get("rel") or "").lower().split())
        if "mask-icon" in rels or not rels & {"icon", "apple-touch-icon", "apple-touch-icon-precomposed"}:
            continue
        href = (link.get("href") or "").strip()
        ctype = (link.get("type") or "").lower()
        path = urlsplit(href).path.lower()
        if not href or "svg" in ctype or path.endswith(".svg") or href.lower().startswith("data:image/svg"):
            continue
        url = href if href.lower().startswith("data:") else urljoin(base, href)
        if not url.lower().startswith(("http://", "https://", "data:")):
            continue
        touch = "icon" not in rels
        ico = path.endswith(".ico") or "x-icon" in ctype or "microsoft.icon" in ctype
        rank = _rank(_size_of(link.get("sizes") or ""), touch, ico) + i / 1000  # rækkefølgen afgør ved lighed
        out[url] = min(rank, out.get(url, rank))
    return [IconLink(u, r) for u, r in sorted(out.items(), key=lambda x: x[1])]


def favicon_urls(*page_urls: str) -> list[str]:
    """/favicon.ico på hver af sidernes værter (den ønskede og den endelige efter omdirigering)."""
    out: list[str] = []
    for u in page_urls:
        parts = urlsplit(u or "")
        if parts.scheme in ("http", "https") and parts.netloc:
            fav = f"{parts.scheme}://{parts.netloc}/favicon.ico"
            if fav not in out:
                out.append(fav)
    return out


def decode_data_uri(uri: str) -> bytes | None:
    """Indholdet af en data:-URI (base64 eller procent-kodet), eller None."""
    head, sep, body = uri.partition(",")
    if not sep:
        return None
    try:
        if head.lower().endswith(";base64"):
            return base64.b64decode(body, validate=False)
        return unquote_to_bytes(body)
    except (binascii.Error, ValueError):
        return None


# ── Hentning ────────────────────────────────────────────────


@dataclass
class LogoResult:
    data: bytes | None
    ext: str | None
    src: str | None
    error: str | None
    budget: bool = False  # tidsbudgettet er brugt; resten venter


def fetch_logo(fetcher, homepage: str, max_bytes: int, also: Sequence[str] = ()) -> LogoResult:
    """Find og hent kildens logo: forsidens ikoner (bedste først), derefter /favicon.ico.

    also: andre adresser (fx kildens feeds), hvis værters /favicon.ico prøves til sidst.
    """
    page = fetcher.get(homepage, conditional=False, max_bytes=HOMEPAGE_MAX_BYTES, accept=ACCEPT_HTML)
    if page.error == BUDGET_EXHAUSTED:
        return LogoResult(None, None, None, page.error, budget=True)
    final = page.final_url or homepage
    ctype = {str(k).lower(): v for k, v in (page.headers or {}).items()}.get("content-type")
    links = icon_links(page.content or b"", final, ctype) if page.ok and page.content else []
    urls = [link.url for link in links]
    urls += [u for u in favicon_urls(final, homepage, *also) if u not in urls]
    errors: list[str] = []  # den første fejl (det bedste ikon) er den mest sigende
    tries = 0
    for url in urls[:MAX_CANDIDATES]:
        if url.lower().startswith("data:"):
            data = decode_data_uri(url)
            ext = acceptable(data, max_bytes)
            if ext:
                return LogoResult(data, ext, "data:", None)
            continue
        if tries >= MAX_TRIES:
            break
        res = fetcher.get(url, conditional=False, max_bytes=max_bytes, accept=ACCEPT_IMAGE)
        if res.error == BUDGET_EXHAUSTED:
            return LogoResult(None, None, None, res.error, budget=True)
        if res.error != ROBOTS_BLOCKED:  # et forbud koster ingen (eller én omdirigerende) forespørgsel
            tries += 1
        if not res.ok:
            errors.append(res.error or f"HTTP {res.status}")
            continue
        ext = acceptable(res.content, max_bytes)
        if ext:
            return LogoResult(res.content, ext, url, None)
        errors.append("ikke et brugbart billede (kun PNG, ICO, GIF, JPEG og WebP på mindst 16 px)")
    return LogoResult(None, None, None, errors[0] if errors else page.error or "intet brugbart ikon")


# ── State ───────────────────────────────────────────────────


def load_state() -> dict:
    raw = store.read_json(paths.STATE_DIR / STATE_FILE, {})
    return raw if isinstance(raw, dict) else {}


def save_state(state: dict) -> bool:
    return store.write_json(paths.STATE_DIR / STATE_FILE, {k: state[k] for k in sorted(state)})


def _due(entry: dict | None, now: datetime, settings: LogoSettings) -> bool:
    """Skal kilden (have) et nyt forsøg? Aldrig prøvet, logo ældre end refresh_days eller fejl ældre end retry_days."""
    if not entry or not entry.get("checked"):
        return True
    try:
        checked = parse_iso(entry["checked"])
    except (ValueError, TypeError):
        return True
    days = settings.refresh_days if entry.get("file") else settings.retry_days
    return now - checked >= timedelta(days=days)


def _write_logo(sid: str, data: bytes, ext: str) -> str:
    """Gem logoet atomisk og fjern kildens filer med andre endelser. Returnerer filnavnet."""
    folder = logo_dir()
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{sid}.{ext}"
    path = folder / name
    if not path.is_file() or path.read_bytes() != data:
        tmp = path.with_name(name + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
    for other in EXTS:
        if other != ext:
            (folder / f"{sid}.{other}").unlink(missing_ok=True)
    return name


def refresh_logos(
    targets: Iterable[tuple[str, str | None]],
    fetcher,
    now: datetime,
    settings: LogoSettings,
    priority: Mapping[str, int] | None = None,
    force: set[str] | None = None,
    also: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, int]:
    """Hent logoer for de kilder, der er på tur (højst max_per_run). Gemmer filer og state.

    targets: (logo-id, forside), se logo_targets. Logoer med høj priority (kilder med indslag i feedet)
    kommer først. force: logo-id'er, der hentes uanset tidspunkt (fx --only). also: logo-id → ekstra
    adresser til /favicon.ico (LogoTarget.also). Et mislykket forsøg beholder et tidligere logo.
    """
    state = load_state()
    priority = priority or {}
    seen: set[str] = set()
    due: list[tuple[str, str]] = []
    for sid, homepage in targets:
        if sid in seen or not homepage or not _ID_RE.match(sid):
            continue
        seen.add(sid)
        if (force and sid in force) or (not force and _due(state.get(sid), now, settings)):
            due.append((sid, homepage))
    due.sort(key=lambda t: (-priority.get(t[0], 0), t[0]))
    counts = {"hentet": 0, "fejl": 0, "venter": max(0, len(due) - settings.max_per_run)}
    max_bytes = settings.max_kb * 1024
    batch = due[: settings.max_per_run]
    for i, (sid, homepage) in enumerate(batch):
        res = fetch_logo(fetcher, homepage, max_bytes, (also or {}).get(sid, ()))
        if res.budget:
            counts["venter"] += len(batch) - i
            log.info("Logoer: tidsbudgettet er brugt; %d venter til næste kørsel", len(batch) - i)
            break
        old = state.get(sid) or {}
        if res.data and res.ext:
            name = _write_logo(sid, res.data, res.ext)
            state[sid] = {"file": name, "src": res.src, "checked": iso(now), "error": None}
            counts["hentet"] += 1
            log.info("Logo: %s ← %s", sid, res.src)
        else:
            # Et tidligere logo bevares; fejlen noteres, og et nyt forsøg kommer efter retry_days
            keep = old.get("file") if old.get("file") and (logo_dir() / old["file"]).is_file() else None
            state[sid] = {"file": keep, "src": old.get("src") if keep else None, "checked": iso(now), "error": res.error}
            counts["fejl"] += 1
            log.info("Logo: %s mangler (%s)", sid, res.error)
    # Poster for kilder, der ikke længere findes, og filer uden post ryddes
    for sid in [s for s in state if s not in seen]:
        state.pop(sid)
    keep_files = {e["file"] for e in state.values() if e.get("file")}
    folder = logo_dir()
    if folder.is_dir():
        for f in folder.iterdir():
            if f.is_file() and f.name not in keep_files:
                f.unlink()
    save_state(state)
    return counts


def logo_files() -> dict[str, str]:
    """id → filnavn for de logoer, der findes på disken (til export). Kun navne på formen <id>.<ext>."""
    folder = logo_dir()
    out: dict[str, str] = {}
    for sid, entry in load_state().items():
        name = entry.get("file") if isinstance(entry, dict) else None
        if not name or not _ID_RE.match(sid) or name not in {f"{sid}.{ext}" for ext in EXTS}:
            continue
        if (folder / name).is_file():
            out[sid] = name
    return out
