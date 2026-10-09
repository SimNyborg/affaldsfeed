"""Folketingets åbne data (oda.ft.dk): dokumenter med affaldsord i titlen (KONTRAKTER §5.7).

Ét kald pr. side til entiteten Dokument med et serverfilter på titlen og opdateringsdatoen. Linket er
dokumentets offentlige fil på ft.dk, datoen er frigivelsesdatoen. Tider fra ODA er dansk tid uden zone.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, time, timedelta
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, urljoin

from affaldsfeed.collect import CollectContext, CollectResult, RawEntry
from affaldsfeed.models import OdaSettings, Source
from affaldsfeed.timeutil import CPH, to_cph

if TYPE_CHECKING:
    from affaldsfeed.fetch import Fetcher

log = logging.getLogger(__name__)

PUBLIC = "O"  # offentlighedskode for offentlige dokumenter


def _odata_str(s: str) -> str:
    """Streng til et OData-filter: ' fordobles."""
    return s.replace("'", "''")


def build_url(base: str, words: list[str], since: datetime, top: int) -> str:
    """Første side: offentlige dokumenter med et af ordene i titlen, opdateret efter since (dansk tid)."""
    terms = " or ".join(f"substringof('{_odata_str(w.strip())}',titel)" for w in words if w.strip())
    flt = (
        f"({terms}) and opdateringsdato gt datetime'{since:%Y-%m-%dT%H:%M:%S}'"
        f" and offentlighedskode eq '{PUBLIC}'"
    )
    params = {
        "$filter": flt,
        "$orderby": "opdateringsdato desc",
        "$top": str(top),
        "$expand": "Dokumenttype,Fil",
        "$format": "json",
    }
    query = "&".join(f"{k}={quote(v, safe='(),:')}" for k, v in params.items())
    return f"{urljoin(base if base.endswith('/') else base + '/', 'Dokument')}?{query}"


def lookback_days(ctx: CollectContext, cfg: OdaSettings) -> int:
    """Dage tilbage: first_run_days ved første kørsel, ellers mindst days og ellers siden sidste gode kørsel.
    Ved bagudindsamling tilbage til window_start."""
    if ctx.backfill_since is not None:
        return max(cfg.first_run_days, (to_cph(ctx.now).date() - ctx.backfill_since).days)
    if ctx.first_run or ctx.last_ok is None:
        return cfg.first_run_days
    since_ok = (to_cph(ctx.now).date() - ctx.last_ok).days + 1
    return max(cfg.days, min(cfg.first_run_days, since_ok))


def _local(value: Any) -> datetime | None:
    """ODA-tid ("2026-10-02T10:59:40" eller med brøkdele) som dansk tid; None ved alt andet."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return dt.replace(tzinfo=CPH) if dt.tzinfo is None else dt


def published_of(doc: dict) -> tuple[datetime | None, str]:
    """Frigivelsesdatoen (med klokkeslæt) eller dokumentets dato (kun dag). Altid UTC."""
    released = _local(doc.get("frigivelsesdato"))
    if released is not None:
        return released.astimezone(UTC), "kilde"
    day = _local(doc.get("dato"))
    if day is not None:
        start = datetime.combine(day.date(), time.min, tzinfo=CPH)
        return start.astimezone(UTC), "liste"
    return None, "fundet"


def file_url(files: Any) -> str | None:
    """Dokumentets offentlige fil: helst PDF-varianten (variantkode P), ellers den første med en URL."""
    if not isinstance(files, list):
        return None
    urls = [f for f in files if isinstance(f, dict) and str(f.get("filurl") or "").startswith("http")]
    if not urls:
        return None
    best = next((f for f in urls if f.get("variantkode") == "P"), urls[0])
    return str(best["filurl"]).strip()


def entry_from_doc(doc: dict, source: Source, exclude: set[str]) -> tuple[RawEntry | None, str]:
    """Et indslag fra et ODA-dokument, eller (None, grund)."""
    dtype = str((doc.get("Dokumenttype") or {}).get("type") or "").strip()
    if dtype.casefold() in exclude:
        return None, "type"
    if (doc.get("offentlighedskode") or PUBLIC) != PUBLIC:
        return None, "ikke offentlig"
    title = " ".join(str(doc.get("titel") or "").split())
    if not title:
        return None, "uden titel"
    url = file_url(doc.get("Fil"))
    if not url:
        return None, "uden fil"
    published, quality = published_of(doc)
    teaser = " ".join(str(doc.get("spørgsmålsordlyd") or "").split())
    entry = RawEntry(
        source_id=source.id,
        url=url,
        title=title,
        teaser=teaser,
        published=published,
        date_quality=quality,
        lang=source.lang,
        categories=[dtype] if dtype else [],
        publisher_name=None,
        publisher_domain=None,
        found_via="feed",
    )
    return entry, ""


def collect(source: Source, fetcher: Fetcher, ctx: CollectContext) -> CollectResult:
    result = CollectResult()
    cfg = ctx.config.settings.oda
    if not source.feeds:
        result.error = "mangler feeds (ODA's adresse)"
        return result
    days = lookback_days(ctx, cfg)
    since = to_cph(ctx.now).replace(tzinfo=None) - timedelta(days=days)
    if ctx.backfill_since is not None:
        since = min(since, datetime.combine(ctx.backfill_since, time.min))  # fra midnat på window_start
    url: str | None = build_url(source.feeds[0], cfg.words, since, cfg.top)
    exclude = {t.casefold() for t in cfg.exclude_types}
    seen: set[str] = set()
    skipped: dict[str, int] = {}
    total = pages = 0
    max_pages = cfg.max_pages
    if ctx.backfill_since is not None:
        max_pages = max(max_pages, ctx.config.settings.backfill.oda_max_pages)
    failure: str | None = None  # fejlen, der stoppede bladringen
    while url and pages < max_pages:
        # ODA svarer med Atom, når Accept foretrækker XML (sessionens standard); derfor JSON eksplicit
        res = fetcher.get(url, conditional=False, accept="application/json")
        result.http_status = res.status or result.http_status
        if res.error:
            log.warning("%s: %s", source.id, res.error)
            failure = f"ODA: {res.error}"[:500]  # adressen er for lang til fejlteksten
            break
        try:
            data = json.loads(res.content or b"")
        except ValueError:
            ctype = {k.lower(): v for k, v in res.headers.items()}.get("content-type", "ukendt")
            failure = f"ODA svarede ikke med gyldig JSON ({ctype})"
            break
        docs = data.get("value") if isinstance(data, dict) else None
        if not isinstance(docs, list):
            failure = "ODA-svaret mangler value"
            break
        pages += 1
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            total += 1
            entry, why = entry_from_doc(doc, source, exclude)
            if entry is None:
                skipped[why] = skipped.get(why, 0) + 1
                continue
            if entry.url in seen:
                skipped["dublet"] = skipped.get("dublet", 0) + 1
                continue
            seen.add(entry.url)
            result.entries.append(entry)
        nxt = data.get("odata.nextLink")
        url = nxt if isinstance(nxt, str) and nxt.startswith("http") else None
    if failure:
        # En fejl midt i bladringen koster kun resten; uden en eneste side fejler kilden. Ved bagudindsamling
        # tages den om ved næste kørsel (§5.8)
        result.error = None if pages else failure
        result.backlog = bool(pages) and ctx.backfill_since is not None
        if pages:
            result.diagnostics.append(f"bladringen stoppede efter side {pages}: {failure}")
    elif url and ctx.backfill_since is not None:
        log.warning("%s: loftet på %d sider er nået; de ældste dokumenter i bagudindsamlingen mangler", source.id, pages)
    rest =", ".join(f"{n} {why}" for why, n in sorted(skipped.items()))
    result.diagnostics.append(
        f"ODA: {days} dage tilbage, {pages} sider, {total} dokumenter, {len(result.entries)} indslag"
        + (f" (sprunget over: {rest})" if rest else "")
        + (" - flere sider venter" if url else "")
    )
    return result
