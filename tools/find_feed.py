"""Find RSS/Atom-feeds og sitemaps for en hjemmeside (fase 4).

Brug: python tools/find_feed.py URL [--json] [--max-sitemaps N]
      python -m affaldsfeed find-feed URL

Rækkefølge: <link rel="alternate"> på forsiden, faste stier (/feed/, /rss, /rss.xml, /feed,
/atom.xml), sitemaps fra robots.txt og /sitemap.xml. Hver kandidat hentes én gang, og der
rapporteres antal indslag, nyeste dato og robots-status (inkl. AI-fravalg).
robots.txt respekteres, og der holdes mindst 2 sek. pause mellem kald til samme vært.
Exit 0 når mindst ét feed eller sitemap virker, ellers 1.
"""

import argparse
import contextlib
import gzip
import io
import json
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import urljoin, urlsplit, urlunsplit

import feedparser
import requests
import yaml
from dateutil import parser as dateparser
from lxml import etree
from lxml import html as lxml_html
from protego import Protego
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from affaldsfeed.models import FetchSettings, Settings  # noqa: E402
from affaldsfeed.paths import CONFIG_DIR  # noqa: E402
from affaldsfeed.timeutil import iso, to_cph  # noqa: E402

FEED_TYPES = ("application/rss+xml", "application/atom+xml", "application/rdf+xml")
GUESS_PATHS = ("/feed/", "/rss", "/rss.xml", "/feed", "/atom.xml")
AI_BOTS = (
    "GPTBot",
    "ChatGPT-User",
    "ClaudeBot",
    "anthropic-ai",
    "CCBot",
    "Google-Extended",
    "PerplexityBot",
    "Bytespider",
    "Applebot-Extended",
)
MIN_PAUSE = 2.0
MAX_REDIRECTS = 5
ACCEPT = (
    "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.9, "
    "text/html;q=0.8, */*;q=0.5"
)

BLOCKED = -1  # status for URL'er, robots.txt forbyder
NETWORK_ERROR = 0


class Response(NamedTuple):
    url: str  # endelig URL efter omdirigeringer
    status: int  # HTTP-status, 0 = netværksfejl, -1 = blokeret af robots.txt
    content: bytes
    content_type: str
    error: str | None


class RobotsInfo(NamedTuple):
    origin: str
    status: str  # "fundet" | "ingen" | "utilgængelig"
    parser: Protego | None
    allow_all: bool
    crawl_delay: float | None
    sitemaps: list[str]
    ai_blocked: list[str]


def origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}".lower()


def normalize_start(url: str) -> str:
    url = url.strip()
    if "://" not in url:
        url = "https://" + url
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError(f"ugyldig URL: {url!r}")
    return urlunsplit(parts._replace(path=parts.path or "/", fragment=""))


# ── Høflig klient ───────────────────────────────────────────


class Client:
    """robots.txt pr. vært (RFC 9309), mindst 2 sek. mellem kald til samme vært, egne omdirigeringer."""

    def __init__(
        self,
        user_agent: str,
        timeout: float = 20.0,
        min_interval: float = MIN_PAUSE,
        session: Any = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.user_agent = user_agent
        self.timeout = timeout
        self.min_interval = max(MIN_PAUSE, min_interval)
        self.session = session if session is not None else requests.Session()
        self._sleep = sleep
        self._clock = clock
        self._last: dict[str, float] = {}
        self.robots: dict[str, RobotsInfo] = {}
        self.requests_made = 0

    def _pace(self, origin: str) -> None:
        info = self.robots.get(origin)
        delay = self.min_interval
        if info and info.crawl_delay:
            delay = max(delay, info.crawl_delay)
        last = self._last.get(origin)
        if last is not None:
            wait = delay - (self._clock() - last)
            if wait > 0:
                self._sleep(wait)
        self._last[origin] = self._clock()

    def _fetch_once(self, url: str) -> Response:
        self._pace(origin_of(url))
        self.requests_made += 1
        headers = {"User-Agent": self.user_agent, "Accept": ACCEPT}
        try:
            r = self.session.get(url, headers=headers, timeout=self.timeout, allow_redirects=False)
        except requests.RequestException as exc:
            return Response(url, NETWORK_ERROR, b"", "", f"{type(exc).__name__}: {exc}")
        ctype = (r.headers.get("Content-Type") or "").lower()
        if 300 <= r.status_code < 400 and r.headers.get("Location"):
            return Response(urljoin(url, r.headers["Location"]), r.status_code, b"", ctype, None)
        error = None if r.status_code < 400 else f"HTTP {r.status_code}"
        return Response(url, r.status_code, r.content or b"", ctype, error)

    def _follow(self, url: str, check_robots: bool) -> Response:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            if check_robots and not self.allowed(current):
                return Response(current, BLOCKED, b"", "", "blokeret af robots.txt")
            resp = self._fetch_once(current)
            if 300 <= resp.status < 400 and resp.url != current:
                current = resp.url
                continue
            return resp
        return Response(current, NETWORK_ERROR, b"", "", "for mange omdirigeringer")

    def robots_for(self, url: str) -> RobotsInfo:
        origin = origin_of(url)
        if origin in self.robots:
            return self.robots[origin]
        resp = self._follow(origin + "/robots.txt", check_robots=False)
        if resp.status == 200:
            rp = Protego.parse(resp.content.decode("utf-8", errors="replace"))
            delay = rp.crawl_delay(self.user_agent)
            ai = [bot for bot in AI_BOTS if not rp.can_fetch(origin + "/", bot)]
            info = RobotsInfo(
                origin, "fundet", rp, True, float(delay) if delay else None, list(rp.sitemaps), ai
            )
        elif 400 <= resp.status < 500:
            # RFC 9309: robots.txt utilgængelig (4xx) → alt er tilladt
            info = RobotsInfo(origin, "ingen", None, True, None, [], [])
        else:
            # 5xx eller netværksfejl → intet hentes
            info = RobotsInfo(origin, "utilgængelig", None, False, None, [], [])
        self.robots[origin] = info
        return info

    def allowed(self, url: str) -> bool:
        info = self.robots_for(url)
        if info.parser is not None:
            return bool(info.parser.can_fetch(url, self.user_agent))
        return info.allow_all

    def get(self, url: str) -> Response:
        return self._follow(url, check_robots=True)


# ── Tolkning (rene funktioner) ───────────────────────────────


def feed_links(content: bytes, base_url: str) -> list[str]:
    """Feed-URL'er fra <link rel="alternate" type="application/rss+xml|atom+xml">."""
    if not content or not content.strip():
        return []
    try:
        doc = lxml_html.fromstring(content)
    except (etree.ParserError, ValueError):
        return []
    base = base_url
    base_href = doc.xpath("//base/@href")
    if base_href:
        base = urljoin(base_url, str(base_href[0]).strip())
    out: list[str] = []
    for link in doc.xpath("//link[@href]"):
        rel = (link.get("rel") or "").lower().split()
        ctype = (link.get("type") or "").lower().split(";")[0].strip()
        if "alternate" in rel and ctype in FEED_TYPES:
            href = urljoin(base, link.get("href").strip())
            if href not in out:
                out.append(href)
    return out


def guess_urls(start: str) -> list[str]:
    """Faste stier, først under den angivne sti (fx /miljoe/feed/), så fra roden."""
    parts = urlsplit(start)
    root = f"{parts.scheme}://{parts.netloc}/"
    bases = []
    if parts.path not in ("", "/"):
        bases.append(f"{parts.scheme}://{parts.netloc}{parts.path.rstrip('/')}/")
    bases.append(root)
    out: list[str] = []
    for base in bases:
        for p in GUESS_PATHS:
            u = urljoin(base, p.lstrip("/"))
            if u not in out:
                out.append(u)
    return out


def _struct_to_dt(tm: Any) -> datetime | None:
    try:
        return datetime(*tm[:6], tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def summarize_feed(content: bytes) -> dict | None:
    """Antal indslag, nyeste dato og titel, eller None hvis det ikke er et feed."""
    if not content:
        return None
    parsed = feedparser.parse(io.BytesIO(content))
    if not parsed.get("version") and not parsed.entries:
        return None
    dates = []
    for e in parsed.entries:
        tm = e.get("published_parsed") or e.get("updated_parsed")
        dt = _struct_to_dt(tm) if tm else None
        if dt:
            dates.append(dt)
    return {
        "kind": parsed.get("version") or "ukendt",
        "title": (parsed.feed.get("title") or "").strip() or None,
        "items": len(parsed.entries),
        "dated": len(dates),
        "newest": max(dates) if dates else None,
    }


def _local(tag: Any) -> str:
    return etree.QName(tag).localname if isinstance(tag, str) else ""


def summarize_sitemap(content: bytes, url: str = "") -> dict | None:
    """urlset/sitemapindex: antal poster og nyeste lastmod, eller None."""
    if not content:
        return None
    if url.endswith(".gz") or content[:2] == b"\x1f\x8b":
        try:
            content = gzip.decompress(content)
        except OSError:
            return None
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=True, huge_tree=False)
    try:
        root = etree.fromstring(content, parser)
    except etree.XMLSyntaxError:
        return None
    if root is None:
        return None
    kind = _local(root.tag)
    if kind not in ("urlset", "sitemapindex"):
        return None
    child = "url" if kind == "urlset" else "sitemap"
    entries = [el for el in root if _local(el.tag) == child]
    dates = []
    for el in root.iter():
        if _local(el.tag) in ("lastmod", "publication_date") and el.text:
            try:
                dt = dateparser.isoparse(el.text.strip())
            except (ValueError, OverflowError):
                continue
            dates.append(dt if dt.tzinfo else dt.replace(tzinfo=UTC))
    return {"kind": kind, "entries": len(entries), "newest": max(dates) if dates else None}


# ── Opdagelse ───────────────────────────────────────────────


def _check_feed(client: Client, url: str, found_via: str) -> dict:
    resp = client.get(url)
    row: dict[str, Any] = {
        "url": url,
        "final_url": resp.url,
        "found_via": found_via,
        "status": resp.status,
        "ok": False,
        "error": resp.error,
    }
    if resp.status == 200:
        info = summarize_feed(resp.content)
        if info:
            row.update(info, ok=True)
        else:
            row["error"] = "ikke et feed"
    return row


def _check_sitemap(client: Client, url: str, found_via: str) -> dict:
    resp = client.get(url)
    row: dict[str, Any] = {
        "url": url,
        "final_url": resp.url,
        "found_via": found_via,
        "status": resp.status,
        "ok": False,
        "error": resp.error,
    }
    if resp.status == 200:
        info = summarize_sitemap(resp.content, resp.url)
        if info:
            row.update(info, ok=True)
        else:
            row["error"] = "ikke et sitemap"
    return row


def discover(start: str, client: Client, max_sitemaps: int = 5) -> dict:
    """Find feeds og sitemaps for start-URL'en. Hver URL hentes højst én gang."""
    start = normalize_start(start)
    robots = client.robots_for(start)
    report: dict[str, Any] = {
        "url": start,
        "robots": {
            "status": robots.status,
            "allowed": client.allowed(start),
            "crawl_delay": robots.crawl_delay,
            "ai_blocked": robots.ai_blocked,
            "sitemaps": robots.sitemaps,
        },
        "homepage": None,
        "feeds": [],
        "sitemaps": [],
    }
    checked: set[str] = set()
    ok_final: dict[str, str] = {}

    def add_feed(url: str, via: str, resp: Response | None = None) -> None:
        if url in checked:
            return
        checked.add(url)
        if resp is not None:
            row = {"url": url, "final_url": resp.url, "found_via": via, "status": resp.status, "ok": True}
            row.update(summarize_feed(resp.content) or {})
        else:
            row = _check_feed(client, url, via)
        if row["ok"]:
            if row["final_url"] in ok_final:
                row["same_as"] = ok_final[row["final_url"]]
            else:
                ok_final[row["final_url"]] = url
        report["feeds"].append(row)

    home = client.get(start)
    report["homepage"] = {"status": home.status, "final_url": home.url, "error": home.error}
    if home.status == 200:
        if summarize_feed(home.content) and "html" not in home.content_type:
            add_feed(start, "input", home)
        else:
            for link in feed_links(home.content, home.url):
                add_feed(link, "link-tag")
    checked.add(start)

    for url in guess_urls(start):
        add_feed(url, "sti")

    sitemap_urls = [(u, "robots.txt") for u in robots.sitemaps[:max_sitemaps]]
    root_map = origin_of(start) + "/sitemap.xml"
    if root_map not in {u for u, _ in sitemap_urls}:
        sitemap_urls.append((root_map, "sti"))
    for url, via in sitemap_urls:
        report["sitemaps"].append(_check_sitemap(client, url, via))
    return report


# ── Rapport ─────────────────────────────────────────────────


def _fmt_dt(dt: datetime | None) -> str:
    return to_cph(dt).strftime("%d.%m.%Y %H:%M") if dt else "ingen dato"


def _status_label(row: dict) -> str:
    if row["ok"]:
        return "OK"
    if row["status"] == BLOCKED:
        return "robots"
    if row["status"] == NETWORK_ERROR:
        return "fejl"
    return str(row["status"])


def print_report(report: dict, user_agent: str) -> None:
    rb = report["robots"]
    print(f"Find feed: {report['url']}")
    line = f"  robots.txt: {rb['status']}"
    line += ", vi må hente siden" if rb["allowed"] else ", vi må IKKE hente siden"
    if rb["crawl_delay"]:
        line += f", Crawl-delay {rb['crawl_delay']:g} s"
    print(line)
    print("  AI-fravalg: " + (", ".join(rb["ai_blocked"]) if rb["ai_blocked"] else "ingen"))
    home = report["homepage"] or {}
    print(f"  forside: {home.get('error') or 'HTTP ' + str(home.get('status'))}")
    print(f"  User-Agent: {user_agent}")
    print()

    print("Feeds")
    for row in report["feeds"]:
        label = _status_label(row)
        head = f"  {label:<6} {row['url']}  [{row['found_via']}]"
        if row["ok"]:
            if row.get("same_as"):
                print(f"{head}  samme feed som {row['same_as']}")
                continue
            title = f', "{row["title"]}"' if row.get("title") else ""
            moved = f" → {row['final_url']}" if row["final_url"] != row["url"] else ""
            print(
                f"{head}{moved}  {row['kind']}, {row['items']} indslag, nyeste {_fmt_dt(row['newest'])}{title}"
            )
        else:
            print(f"{head}  {row.get('error') or ''}".rstrip())
    print()

    print("Sitemaps")
    for row in report["sitemaps"]:
        head = f"  {_status_label(row):<6} {row['url']}  [{row['found_via']}]"
        if row["ok"]:
            noun = "adresser" if row["kind"] == "urlset" else "under-sitemaps"
            print(f"{head}  {row['kind']}, {row['entries']} {noun}, nyeste {_fmt_dt(row['newest'])}")
        else:
            print(f"{head}  {row.get('error') or ''}".rstrip())
    print()

    feeds = [r for r in report["feeds"] if r["ok"] and not r.get("same_as")]
    maps = [r for r in report["sitemaps"] if r["ok"]]
    if feeds:
        best = max(feeds, key=lambda r: (r["items"] > 0, r["newest"] or datetime.min.replace(tzinfo=UTC)))
        print("Forslag til sources.yaml:")
        print("  method: rss")
        print(f"  feeds: {best['final_url']}")
    elif maps:
        print("Forslag til sources.yaml (fase 2):")
        print("  method: sitemap")
        print(f"  feeds: {maps[0]['final_url']}")
        print('  match: "<regex for artikel-URL\'er>"')
    else:
        print("Intet feed eller sitemap fundet. Prøv en underside (fx /nyheder) eller method: html (fase 2).")


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return iso(obj)
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    return obj


def load_fetch_settings(config_dir: Path = CONFIG_DIR) -> FetchSettings:
    data = yaml.safe_load((config_dir / "settings.yaml").read_text(encoding="utf-8"))
    return Settings.model_validate(data).fetch


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="find-feed", description="Find RSS/Atom og sitemaps for en hjemmeside."
    )
    parser.add_argument("url", help="hjemmesidens adresse")
    parser.add_argument("--json", action="store_true", help="udskriv rapporten som JSON")
    parser.add_argument("--max-sitemaps", type=int, default=5, help="højst så mange sitemaps fra robots.txt")
    args = parser.parse_args(argv)
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(errors="replace")  # type: ignore[union-attr]

    try:
        fetch = load_fetch_settings()
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        print(f"FEJL: kunne ikke læse config/settings.yaml: {exc}", file=sys.stderr)
        return 1
    client = Client(fetch.user_agent, timeout=fetch.timeout_seconds, min_interval=fetch.min_interval_seconds)
    try:
        report = discover(args.url, client, max_sitemaps=args.max_sitemaps)
    except ValueError as exc:
        print(f"FEJL: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(_jsonable(report), ensure_ascii=False, indent=2))
    else:
        print_report(report, fetch.user_agent)
        delay = report["robots"]["crawl_delay"]
        if delay and delay > fetch.max_crawl_delay_seconds:
            print(f"Bemærk: Crawl-delay {delay:g} s er over {fetch.max_crawl_delay_seconds:g} s.")
            print("Pipelinen henter derfor kun kilden én gang i døgnet.")
    found = any(r["ok"] for r in report["feeds"]) or any(r["ok"] for r in report["sitemaps"])
    return 0 if found else 1


if __name__ == "__main__":
    sys.exit(main())
