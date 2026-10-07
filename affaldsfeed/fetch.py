"""Høflig HTTP: ærlig User-Agent, robots.txt (protego), takt pr. vært, conditional GET, ét retry og loft
over svarets størrelse."""

from __future__ import annotations

import contextlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from urllib.parse import urlsplit

import requests
from protego import Protego

from affaldsfeed.models import FetchSettings
from affaldsfeed.timeutil import iso, parse_iso

log = logging.getLogger(__name__)

ROBOTS_MAX_BYTES = 500 * 1024
CHUNK_BYTES = 64 * 1024
MB = 1024 * 1024
RETRY_STATUSES = {500, 502, 504}
SKIP_STATUSES = {429, 503}
TRANSIENT_4XX = {408, 425, 429}  # 4xx, der kan gå over af sig selv

# Fejltekster, som indsamlerne genkender i FetchResult.error
BUDGET_EXHAUSTED = "tidsbudget opbrugt"
ROBOTS_BLOCKED = "blokeret af robots.txt"
TOO_LARGE = "svaret er for stort"


@dataclass
class FetchResult:
    url: str
    status: int
    text: str | None
    content: bytes | None
    not_modified: bool
    error: str | None
    headers: dict = field(default_factory=dict)
    final_url: str | None = None  # adressen efter omdirigeringer (kun ved 200)

    @property
    def ok(self) -> bool:
        return self.error is None and (self.status == 200 or self.not_modified)

    @property
    def permanent(self) -> bool:
        """Fejl, som et nyt forsøg ikke ændrer: 4xx (undtagen 408, 425, 429), robots.txt-forbud, for stort svar."""
        if self.error is None:
            return False
        if self.error == ROBOTS_BLOCKED or self.error.startswith(TOO_LARGE):
            return True
        return 400 <= self.status < 500 and self.status not in TRANSIENT_4XX


def _netloc(url: str) -> str:
    return urlsplit(url).netloc.lower()


def _header(headers: object, name: str) -> str | None:
    return {str(k).lower(): v for k, v in dict(headers or {}).items()}.get(name)


def _robots_url(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}/robots.txt"


class Fetcher:
    """Én forespørgsel ad gangen. State (http_cache, robots_cache) gemmes af kalderen."""

    def __init__(self, settings: FetchSettings, http_cache: dict, robots_cache: dict, now: datetime):
        self.settings = settings
        self.http_cache = http_cache
        self.robots_cache = robots_cache
        self.now = now
        self.ua_token = settings.user_agent.split("/")[0].strip() or "*"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": settings.user_agent,
                "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.9, */*;q=0.5",
                "Accept-Language": "da, en;q=0.7",
            }
        )
        self._parsers: dict[str, Protego | None] = {}
        self._blocked_hosts: dict[str, str] = {}  # vært -> grund (kun denne kørsel)
        self._last_request: dict[str, float] = {}
        self._deadline: float | None = None
        self.requests_made = 0
        self.max_bytes = int(settings.max_response_mb * MB)

    # ── Tidsbudget ──────────────────────────────────────────

    def start_budget(self, seconds: float | None) -> None:
        """Sæt et tidsbudget for de næste kald (typisk én kilde)."""
        self._deadline = time.monotonic() + seconds if seconds else None

    def _remaining(self) -> float | None:
        if self._deadline is None:
            return None
        return self._deadline - time.monotonic()

    # ── robots.txt ──────────────────────────────────────────

    def _parser(self, url: str) -> Protego | None:
        """Protego for værten. None = intet tilladt i denne kørsel."""
        host = _netloc(url)
        if host in self._parsers:
            return self._parsers[host]
        cached = self.robots_cache.get(host)
        fresh = False
        if cached and cached.get("fetched"):
            try:
                age = self.now - parse_iso(cached["fetched"])
                fresh = age < timedelta(hours=self.settings.robots_cache_hours)
            except ValueError:
                fresh = False
        if cached and fresh:
            parser = Protego.parse(cached.get("body") or "")
        else:
            parser = self._fetch_robots(url, cached)
        self._parsers[host] = parser
        return parser

    def _fetch_robots(self, url: str, cached: dict | None) -> Protego | None:
        host = _netloc(url)
        robots_url = _robots_url(url)
        status: int | None = None
        err = ""
        self._pace(host, crawl_delay=0.0)  # TimeoutError (budget) løftes til kalderen
        raw = b""
        try:
            timeout = self.settings.timeout_seconds
            remaining = self._remaining()
            if remaining is not None:
                timeout = max(1.0, min(timeout, remaining))
            resp = self.session.get(robots_url, timeout=timeout, allow_redirects=True, stream=True)
            self.requests_made += 1
            with contextlib.closing(resp):
                if 200 <= resp.status_code < 300:
                    raw = self._read(resp, ROBOTS_MAX_BYTES, truncate=True) or b""  # resten ignoreres
                status = resp.status_code
        except requests.RequestException as e:
            err = type(e).__name__
        if status is not None and 200 <= status < 300:
            body = raw.decode("utf-8", errors="replace")
        elif status is not None and 400 <= status < 500:
            body = ""  # 4xx: alt er tilladt
        else:
            # 5xx eller netværksfejl: brug gammel kopi hvis vi har en, ellers intet denne kørsel
            reason = f"HTTP {status}" if status is not None else err
            if cached and cached.get("body") is not None:
                log.info("robots.txt for %s svarer ikke (%s); bruger gammel kopi", host, reason)
                return Protego.parse(cached.get("body") or "")
            log.warning("robots.txt for %s svarer ikke (%s); værten springes over i denne kørsel", host, reason)
            self._blocked_hosts[host] = f"robots.txt utilgængelig ({reason})"
            return None
        self.robots_cache[host] = {"fetched": iso(self.now), "body": body}
        return Protego.parse(body)

    def allowed(self, url: str) -> bool:
        """Må vi hente URL'en ifølge robots.txt (egen token, ellers *)?"""
        parser = self._parser(url)
        if parser is None:
            return False
        try:
            return bool(parser.can_fetch(url, self.ua_token))
        except Exception:  # protego er robust, men vi tager ingen chancer
            return True

    def crawl_delay(self, url: str) -> float:
        parser = self._parser(url)
        if parser is None:
            return 0.0
        try:
            delay = parser.crawl_delay(self.ua_token)
        except Exception:
            delay = None
        return float(delay or 0.0)

    def cached_crawl_delay(self, url: str) -> float:
        """Crawl-delay fra cachen uden netværkskald (0 hvis ukendt)."""
        cached = self.robots_cache.get(_netloc(url))
        if not cached or not cached.get("body"):
            return 0.0
        try:
            return float(Protego.parse(cached["body"]).crawl_delay(self.ua_token) or 0.0)
        except Exception:
            return 0.0

    # ── Takt ────────────────────────────────────────────────

    def _pace(self, host: str, crawl_delay: float) -> None:
        interval = self.settings.min_interval_seconds
        if 0 < crawl_delay <= self.settings.max_crawl_delay_seconds:
            interval = max(interval, crawl_delay)
        last = self._last_request.get(host)
        if last is not None:
            wait = interval - (time.monotonic() - last)
            if wait > 0:
                remaining = self._remaining()
                if remaining is not None and wait > remaining:
                    raise TimeoutError(BUDGET_EXHAUSTED)
                time.sleep(wait)
        self._last_request[host] = time.monotonic()

    # ── Hentning ────────────────────────────────────────────

    def _fail(self, url: str, status: int, error: str, headers: dict | None = None) -> FetchResult:
        return FetchResult(url=url, status=status, text=None, content=None, not_modified=False, error=error, headers=headers or {})

    def _read(self, resp: requests.Response, limit: int, truncate: bool = False) -> bytes | None:
        """Læs svaret i bidder, så et for stort svar aldrig ligger i hukommelsen.

        gzip og deflate (Content-Encoding) pakkes ud undervejs, så loftet gælder den udpakkede størrelse.
        Over loftet: None (eller de første limit bytes med truncate). Rejser TimeoutError, når tidsbudgettet
        er brugt.
        """
        length = _header(resp.headers, "content-length")
        if not truncate and length and length.strip().isdigit() and int(length) > limit:
            return None
        buf = bytearray()
        for chunk in resp.iter_content(chunk_size=CHUNK_BYTES):
            buf += chunk
            if len(buf) > limit:
                return bytes(buf[:limit]) if truncate else None
            remaining = self._remaining()
            if remaining is not None and remaining <= 0:
                raise TimeoutError(BUDGET_EXHAUSTED)
        return bytes(buf)

    def get(
        self, url: str, conditional: bool = True, max_bytes: int | None = None, accept: str | None = None
    ) -> FetchResult:
        """Hent url. max_bytes er loftet over svaret (standard fetch.max_response_mb).

        accept erstatter sessionens Accept-header (feeds først), fx "application/json" til ODA.
        """
        host = _netloc(url)
        if host in self._blocked_hosts:
            return self._fail(url, 0, f"springes over: {self._blocked_hosts[host]}")
        try:
            allowed = self.allowed(url)
        except TimeoutError as e:
            return self._fail(url, 0, str(e))
        if not allowed:
            if host in self._blocked_hosts:
                return self._fail(url, 0, f"springes over: {self._blocked_hosts[host]}")
            return self._fail(url, 0, ROBOTS_BLOCKED)

        headers: dict[str, str] = {"Accept": accept} if accept else {}
        cached = self.http_cache.get(url) if conditional else None
        if isinstance(cached, dict):
            if cached.get("etag"):
                headers["If-None-Match"] = cached["etag"]
            if cached.get("last_modified"):
                headers["If-Modified-Since"] = cached["last_modified"]

        delay = self.crawl_delay(url)
        limit = max_bytes or self.max_bytes
        attempts = 2
        last_error = "ukendt fejl"
        last_status = 0
        for attempt in range(attempts):
            remaining = self._remaining()
            if remaining is not None and remaining <= 0:
                return self._fail(url, last_status, BUDGET_EXHAUSTED)
            timeout = self.settings.timeout_seconds
            if remaining is not None:
                timeout = max(1.0, min(timeout, remaining))
            try:
                self._pace(host, delay)
                resp = self.session.get(url, headers=headers, timeout=timeout, allow_redirects=True, stream=True)
                self.requests_made += 1
                with contextlib.closing(resp):
                    status = resp.status_code
                    resp_headers = dict(resp.headers)
                    final_url = getattr(resp, "url", None) or url
                    content = self._read(resp, limit) if 200 <= status < 300 else b""
            except TimeoutError as e:
                return self._fail(url, last_status, str(e))
            except requests.Timeout:
                last_error, last_status = "timeout", 0
                continue
            except requests.RequestException as e:
                last_error, last_status = f"netværksfejl: {type(e).__name__}", 0
                if isinstance(e, requests.ConnectionError) and attempt == 0:
                    continue
                return self._fail(url, 0, last_error)

            if status == 304:
                return FetchResult(url=url, status=304, text=None, content=None, not_modified=True, error=None, headers=resp_headers)
            if 200 <= status < 300:
                if content is None:
                    log.warning("%s: over %.3g MB; hentningen er afbrudt", url, limit / MB)
                    return self._fail(url, status, f"{TOO_LARGE} (over {limit / MB:.3g} MB)", resp_headers)
                self._remember(url, resp_headers)
                try:
                    text = content.decode(getattr(resp, "encoding", None) or "utf-8", errors="replace")
                except (LookupError, ValueError):  # ukendt eller ikke-tekst-codec i Content-Type
                    text = content.decode("utf-8", errors="replace")
                return FetchResult(
                    url=url, status=status, text=text, content=content, not_modified=False, error=None,
                    headers=resp_headers, final_url=final_url,
                )
            if status in SKIP_STATUSES:
                retry_after = resp_headers.get("Retry-After") or resp_headers.get("retry-after")
                note = f" (Retry-After: {retry_after})" if retry_after else ""
                self._blocked_hosts[host] = f"HTTP {status}{note}"
                return self._fail(url, status, f"HTTP {status}{note}; springes over i denne kørsel", resp_headers)
            if status in RETRY_STATUSES:
                last_error, last_status = f"HTTP {status}", status
                continue
            return self._fail(url, status, f"HTTP {status}", resp_headers)
        return self._fail(url, last_status, last_error)

    def _remember(self, url: str, headers: dict) -> None:
        lower = {k.lower(): v for k, v in headers.items()}
        entry = {}
        if lower.get("etag"):
            entry["etag"] = lower["etag"]
        if lower.get("last-modified"):
            entry["last_modified"] = lower["last-modified"]
        if entry:
            self.http_cache[url] = entry
        else:
            self.http_cache.pop(url, None)
