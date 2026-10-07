"""Indsamlingsmetoder. Hver metode er en funktion collect(source, fetcher, ctx) -> CollectResult."""

from __future__ import annotations

import calendar
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

from dateutil import parser as dateparser

from affaldsfeed.models import Source

if TYPE_CHECKING:
    from affaldsfeed.config import Config
    from affaldsfeed.fetch import Fetcher

log = logging.getLogger(__name__)


@dataclass
class RawEntry:
    source_id: str
    url: str
    title: str
    teaser: str
    published: datetime | None
    date_quality: str
    lang: str
    categories: list[str]
    publisher_name: str | None
    publisher_domain: str | None
    found_via: str


@dataclass
class CollectContext:
    config: Config
    sources: list[Source]
    now: datetime
    publisher_lookup: dict[str, str]
    conditional: bool = True  # False ved kildens første kørsel og ved check --fetch
    first_run: bool = False  # kildens første kørsel (ingen vellykket kørsel endnu); også ved check --fetch
    last_ok: date | None = None  # dagen for kildens sidste vellykkede kørsel (SourceState.last_ok)
    # state/seen.json: {kilde-id: {item-id: "ÅÅÅÅ-MM-DD"}}. Sitemap og html opdaterer den undervejs.
    seen: dict[str, dict[str, str]] = field(default_factory=dict)


@dataclass
class CollectResult:
    entries: list[RawEntry] = field(default_factory=list)
    unknown_publishers: list[tuple[str, str, str]] = field(default_factory=list)  # (domæne, navn, url)
    error: str | None = None
    http_status: int | None = None
    diagnostics: list[str] = field(default_factory=list)  # til check --fetch --explain (gemmes ikke)
    # Sider eller dokumenter venter til næste kørsel (sitemap/html). Ved første kørsel er baseline så ikke
    # komplet, og næste kørsel er også en første kørsel (KONTRAKTER §5.6).
    backlog: bool = False


# ── Fælles hjælpere ─────────────────────────────────────────


def entry_date(entry: Any) -> datetime | None:
    """Dato fra et feedparser-indslag: published → updated. Altid UTC."""
    for key in ("published", "updated", "created"):
        parsed = entry.get(f"{key}_parsed")
        if parsed:
            try:
                return datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC)
            except (OverflowError, ValueError, TypeError):
                pass
        raw = entry.get(key)
        if raw:
            try:
                dt = dateparser.parse(raw)
            except (ValueError, OverflowError, TypeError):
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC)
    return None


def entry_categories(entry: Any, limit: int = 10) -> list[str]:
    out: list[str] = []
    for tag in entry.get("tags") or []:
        term = (tag.get("term") or tag.get("label") or "").strip()
        if term and term not in out:
            out.append(term[:80])
        if len(out) >= limit:
            break
    return out


def match_publisher(host: str, lookup: dict[str, str]) -> str | None:
    """Find afsender-id for en vært. Prøver værten og dens overdomæner (nyheder.tv2.dk → tv2.dk)."""
    host = (host or "").lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    parts = host.split(".")
    for i in range(len(parts) - 1):
        cand = ".".join(parts[i:])
        if cand in lookup:
            return lookup[cand]
    return None


def combine_errors(errors: list[str], ok_count: int) -> str | None:
    """Kilden fejler kun, når ingen af dens feeds lykkedes."""
    if ok_count > 0 or not errors:
        return None
    return "; ".join(dict.fromkeys(errors))[:500]


Collector = Callable[[Source, "Fetcher", CollectContext], CollectResult]

from affaldsfeed.collect import oda, pages, rss, search  # noqa: E402

COLLECTORS: dict[str, Collector] = {
    "rss": rss.collect,
    "search": search.collect,
    "sitemap": pages.collect_sitemap,
    "html": pages.collect_html,
    "oda": oda.collect,
}
