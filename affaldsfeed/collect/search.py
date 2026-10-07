"""Nyhedssøgning (Google News og Bing News RSS). Søgemaskinen finder kun artiklen; udgiveren krediteres."""

from __future__ import annotations

import base64
import binascii
import logging
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, quote_plus, urlsplit

from affaldsfeed.collect import (
    CollectContext,
    CollectResult,
    RawEntry,
    combine_errors,
    entry_categories,
    entry_date,
    match_publisher,
)
from affaldsfeed.collect.rss import is_feed, parse_feed
from affaldsfeed.models import Source
from affaldsfeed.normalize import clean_text, host_of, strip_publisher_suffix
from affaldsfeed.relevance import Prefilter

if TYPE_CHECKING:
    from affaldsfeed.fetch import Fetcher

log = logging.getLogger(__name__)

_GOOGLE_ID_RE = re.compile(r"/(?:rss/)?articles/([A-Za-z0-9_\-]+)")


def build_url(template: str, query: str, when: str) -> str:
    """Udfyld en søgeskabelon. {q} URL-encodes; {when} er valgfri."""
    return template.replace("{q}", quote_plus(query)).replace("{when}", quote_plus(when))


def engine_of(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    if host.endswith("news.google.com"):
        return "google"
    if host.endswith("bing.com"):
        return "bing"
    return "other"


# ── Google News ─────────────────────────────────────────────


def _varint(buf: bytes, i: int) -> tuple[int, int]:
    shift = result = 0
    while i < len(buf):
        b = buf[i]
        i += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, i
        shift += 7
        if shift > 63:
            break
    raise ValueError("ugyldig varint")


def decode_google_link(link: str) -> str | None:
    """Prøv at afkode artikel-URL'en af et Google News-link (gammelt base64/protobuf-format).

    Nyere links indeholder en krypteret nøgle og kan ikke afkodes uden netværk; så returneres None.
    """
    m = _GOOGLE_ID_RE.search(urlsplit(link).path)
    if not m:
        return None
    token = m.group(1)
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
    except (binascii.Error, ValueError):
        return None
    # Gå protobuf-felterne igennem og find et længdeafgrænset felt, der er en URL
    i = 0
    try:
        while i < len(raw):
            key, i = _varint(raw, i)
            wire = key & 0x07
            if wire == 0:
                _, i = _varint(raw, i)
            elif wire == 2:
                n, i = _varint(raw, i)
                chunk = raw[i : i + n]
                i += n
                if chunk.startswith((b"http://", b"https://")):
                    try:
                        return chunk.decode("utf-8")
                    except UnicodeDecodeError:
                        return None
            elif wire == 5:
                i += 4
            elif wire == 1:
                i += 8
            else:
                break
    except ValueError:
        pass
    m2 = re.search(rb"https?://[\x21-\x7e]+", raw)
    if m2:
        return m2.group().decode("ascii")
    return None


def _google_entry(e: Any) -> tuple[str, str | None, str | None]:
    """(artikel-URL, udgivernavn, udgiver-URL)."""
    link = (e.get("link") or "").strip()
    src = e.get("source") or {}
    name = (src.get("title") or "").strip() or None
    pub_url = (src.get("href") or src.get("url") or "").strip() or None
    decoded = decode_google_link(link) if link else None
    return decoded or link, name, pub_url


# ── Bing News ───────────────────────────────────────────────


def bing_target(link: str) -> str:
    """URL fra url-parameteren i et apiclick.aspx-link (ellers linket selv)."""
    try:
        qs = parse_qs(urlsplit(link).query)
    except ValueError:
        return link
    for key in ("url", "URL", "u"):
        if qs.get(key):
            target = qs[key][0].strip()
            if target.startswith(("http://", "https://")):
                return target
    return link


def _bing_entry(e: Any) -> tuple[str, str | None, str | None]:
    link = (e.get("link") or "").strip()
    url = bing_target(link) if link else ""
    name = None
    for key in ("news_source", "source"):
        val = e.get(key)
        if isinstance(val, str) and val.strip():
            name = val.strip()
            break
        if isinstance(val, dict) and val.get("title"):
            name = val["title"].strip()
            break
    return url, name, None


def _generic_entry(e: Any) -> tuple[str, str | None, str | None]:
    src = e.get("source")
    if not isinstance(src, dict):
        return (e.get("link") or "").strip(), None, None
    name = (src.get("title") or "").strip() or None
    pub_url = (src.get("href") or "").strip() or None
    return (e.get("link") or "").strip(), name, pub_url


# ── Indsamling ──────────────────────────────────────────────


def _publisher_langs(ctx: CollectContext) -> dict[str, str]:
    langs = {s.id: s.lang for s in ctx.sources}
    for p in ctx.config.publishers:
        langs.setdefault(p.id, p.lang)
    return langs


def collect(source: Source, fetcher: Fetcher, ctx: CollectContext) -> CollectResult:
    result = CollectResult()
    queries = ctx.config.search.queries
    when = ctx.config.search.when
    langs = _publisher_langs(ctx)
    errors: list[str] = []
    ok = 0
    seen: set[str] = set()
    unknown_seen: set[str] = set()
    prefilter = Prefilter(ctx.config.keywords)

    # Én forespørgsel pr. søgning i search.yaml og pr. skabelon i kildens feeds
    urls = [build_url(t, q, when) for q in queries for t in source.feeds]
    for url in urls:
        res = fetcher.get(url, conditional=ctx.conditional)
        result.http_status = res.status or result.http_status
        if res.error:
            errors.append(res.error)
            log.warning("%s: %s: %s", source.id, url, res.error)
            continue
        if res.not_modified:
            ok += 1
            continue
        ctype = {k.lower(): v for k, v in res.headers.items()}.get("content-type")
        parsed = parse_feed(res.content or b"", url, ctype)
        if not is_feed(parsed):
            errors.append(f"{engine_of(url)}: ikke et gyldigt feed")
            log.warning("%s: %s gav ikke et gyldigt feed", source.id, url)
            continue
        ok += 1
        engine = engine_of(url)
        for e in parsed.entries:
            if engine == "google":
                art_url, pub_name, pub_url = _google_entry(e)
            elif engine == "bing":
                art_url, pub_name, pub_url = _bing_entry(e)
            else:
                art_url, pub_name, pub_url = _generic_entry(e)
            if not art_url or art_url in seen:
                continue
            seen.add(art_url)

            # Udgiverens vært: fra <source url> (Google) eller artiklens egen vært
            host = host_of(pub_url) if pub_url else host_of(art_url)
            title = strip_publisher_suffix((e.get("title") or "").strip(), pub_name)
            publisher_id = match_publisher(host, ctx.publisher_lookup) if host else None
            if publisher_id is None:
                # Kun relevante artikler gør en ukendt udgiver til kildeforslag (søgemaskinerne er brede)
                teaser = "" if engine == "google" else (e.get("summary") or "")
                if (
                    host
                    and not host.endswith(("google.com", "bing.com"))
                    and art_url not in unknown_seen
                    and prefilter.evaluate(clean_text(title, 300), clean_text(teaser, 300), source).decision != "afvist"
                ):
                    unknown_seen.add(art_url)
                    result.unknown_publishers.append((host, pub_name or host, art_url))
                continue
            published = entry_date(e)
            result.entries.append(
                RawEntry(
                    source_id=publisher_id,
                    url=art_url,
                    title=title,
                    # Googles beskrivelse er blot titel + udgiver, så den bruges ikke
                    teaser="" if engine == "google" else (e.get("summary") or ""),
                    published=published,
                    date_quality="kilde" if published else "fundet",
                    lang=langs.get(publisher_id, source.lang),
                    categories=entry_categories(e),
                    publisher_name=pub_name,
                    publisher_domain=host,
                    found_via="search",
                )
            )
    result.error = combine_errors(errors, ok)
    return result
