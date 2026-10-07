"""RSS og Atom: titel, link, dato, beskrivelse og kategorier tages direkte fra feedet."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from urllib.parse import urljoin

import feedparser

from affaldsfeed.collect import (
    CollectContext,
    CollectResult,
    RawEntry,
    combine_errors,
    entry_categories,
    entry_date,
)
from affaldsfeed.models import Source

if TYPE_CHECKING:
    from affaldsfeed.fetch import Fetcher

log = logging.getLogger(__name__)


def parse_feed(content: bytes, url: str, content_type: str | None = None) -> feedparser.FeedParserDict:
    """Parse hentet indhold med feedparser (ikke feedparsers egen HTTP)."""
    headers = {"content-location": url}
    if content_type:
        headers["content-type"] = content_type
    return feedparser.parse(content, response_headers=headers)


def is_feed(parsed: feedparser.FeedParserDict) -> bool:
    """Ligner det et feed? Et tomt RSS/Atom-feed er ok; en HTML-side er ikke.

    feedparsers bozo-flag bruges ikke: det sættes også ved harmløse fejl som manglende Content-Type.
    """
    return bool(parsed.entries) or bool(parsed.get("version"))


def entries_from_feed(parsed: feedparser.FeedParserDict, feed_url: str, source: Source) -> list[RawEntry]:
    out: list[RawEntry] = []
    for e in parsed.entries:
        link = (e.get("link") or "").strip()
        if not link:
            # Atom uden alternate-link: tag første link
            links = e.get("links") or []
            link = (links[0].get("href") or "").strip() if links else ""
        if not link:
            link = (e.get("id") or "").strip() if str(e.get("id", "")).startswith("http") else ""
        if not link:
            continue
        link = urljoin(feed_url, link)
        title = (e.get("title") or "").strip()
        teaser = e.get("summary") or ""
        if not teaser and e.get("content"):
            teaser = e["content"][0].get("value") or ""
        published = entry_date(e)
        out.append(
            RawEntry(
                source_id=source.id,
                url=link,
                title=title,
                teaser=teaser,
                published=published,
                date_quality="kilde" if published else "fundet",
                lang=source.lang,
                categories=entry_categories(e),
                publisher_name=None,
                publisher_domain=None,
                found_via="feed",
            )
        )
    return out


def collect(source: Source, fetcher: Fetcher, ctx: CollectContext) -> CollectResult:
    result = CollectResult()
    errors: list[str] = []
    ok = 0
    seen: set[str] = set()
    for feed_url in source.feeds:
        res = fetcher.get(feed_url, conditional=ctx.conditional)
        result.http_status = res.status or result.http_status
        if res.error:
            errors.append(f"{feed_url}: {res.error}")
            log.warning("%s: %s: %s", source.id, feed_url, res.error)
            continue
        if res.not_modified:
            ok += 1
            log.debug("%s: %s uændret (304)", source.id, feed_url)
            continue
        ctype = {k.lower(): v for k, v in res.headers.items()}.get("content-type")
        parsed = parse_feed(res.content or b"", feed_url, ctype)
        if not is_feed(parsed):
            exc = parsed.get("bozo_exception")
            why = f" ({type(exc).__name__})" if exc else ""
            errors.append(f"{feed_url}: ikke et gyldigt feed{why}")
            log.warning("%s: %s er ikke et gyldigt feed%s", source.id, feed_url, why)
            continue
        ok += 1
        for entry in entries_from_feed(parsed, feed_url, source):
            if entry.url in seen:
                continue
            seen.add(entry.url)
            result.entries.append(entry)
    if errors and ok:
        log.warning("%s: %d af %d feeds fejlede", source.id, len(errors), len(source.feeds))
    result.error = combine_errors(errors, ok)
    return result
