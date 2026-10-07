"""Testhjælpere: falsk Fetcher, falsk HTTP-session og et midlertidigt repo-miljø. Ingen netværk."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from types import SimpleNamespace

from affaldsfeed import paths
from affaldsfeed.fetch import BUDGET_EXHAUSTED, ROBOTS_BLOCKED, TOO_LARGE, FetchResult

FIXTURES = Path(__file__).resolve().parent
RSS_TYPE = "application/rss+xml; charset=utf-8"

# URL (eller præfiks) -> fixture-fil, bytes, HTTP-status (int; 304 = uændret), "raise", "budget", "robots",
# "timeout", "too_large" eller (fil/bytes, content-type). Uden content-type svares der som RSS.
DEFAULT_ROUTES: dict[str, str | int] = {
    "https://www.testmedie.dk/rss": "rss2.xml",
    "https://www.dr.dk/nyheder/service/feeds/indland": "dr.xml",
    "https://testorg.dk/atom.xml": "atom.xml",
    "https://testorg.dk/ekstra.xml": 404,
    "https://www.affaldsselskab.dk/rss": "html_description.xml",
    "https://udateret.dk/rss": "no_dates.xml",
    "https://news.google.com/rss/search": "gnews.xml",
    "https://www.bing.com/news/search": "bing.xml",
}


def make_fetcher_class(routes: dict[str, str | int | Path | bytes | tuple] | None = None, etags: bool = False):
    """Lav en Fetcher-erstatning med de givne ruter. Kald registreres i klassens .calls.

    Med etags=True opfører den sig som en server med ETags: ETag'en er en hash af indholdet, og en betinget
    forespørgsel, hvis ETag i http_cache passer, får 304. Uden svares der altid 200 (ETag "v1").
    Ruterne kan ændres mellem kørsler via klassens .routes.
    """
    table = dict(DEFAULT_ROUTES if routes is None else routes)

    class FakeFetcher:
        calls: list[tuple[str, bool]] = []
        statuses: list[tuple[str, int]] = []  # (url, status) for svar uden fejl (200 eller 304)
        instances: list = []
        routes = table

        def __init__(self, settings, http_cache, robots_cache, now):
            self.settings = settings
            self.http_cache = http_cache
            self.robots_cache = robots_cache
            self.now = now
            FakeFetcher.instances.append(self)

        def start_budget(self, seconds):
            pass

        def cached_crawl_delay(self, url):
            return 0.0

        def allowed(self, url):
            return True

        def get(self, url, conditional=True, max_bytes=None):
            FakeFetcher.calls.append((url, conditional))
            target = table.get(url)
            if target is None:
                for prefix, t in table.items():
                    if url.startswith(prefix):
                        target = t
                        break
            if target is None:
                return FetchResult(url, 404, None, None, False, "HTTP 404", {})
            if target == "raise":
                raise RuntimeError("kunstig fejl")
            if target == "budget":
                return FetchResult(url, 0, None, None, False, BUDGET_EXHAUSTED, {})
            if target == "robots":
                return FetchResult(url, 0, None, None, False, ROBOTS_BLOCKED, {})
            if target == "timeout":
                return FetchResult(url, 0, None, None, False, "timeout", {})
            if target == "too_large":
                return FetchResult(url, 200, None, None, False, f"{TOO_LARGE} (over 5 MB)", {})
            if target == 304:
                FakeFetcher.statuses.append((url, 304))
                return FetchResult(url, 304, None, None, True, None, {})
            if isinstance(target, int):
                return FetchResult(url, target, None, None, False, f"HTTP {target}", {})
            ctype = RSS_TYPE
            if isinstance(target, tuple):
                target, ctype = target
            if isinstance(target, bytes):
                content = target
            else:
                content = (target if isinstance(target, Path) else FIXTURES / target).read_bytes()
            etag = f'"{hashlib.sha1(content).hexdigest()[:12]}"' if etags else '"v1"'
            cached = self.http_cache.get(url) if conditional else None
            if etags and isinstance(cached, dict) and cached.get("etag") == etag:
                FakeFetcher.statuses.append((url, 304))
                return FetchResult(url, 304, None, None, True, None, {"ETag": etag})
            headers = {"ETag": etag}
            if ctype:
                headers["Content-Type"] = ctype
            self.http_cache[url] = {"etag": etag}  # som Fetcher._remember: erstatter posten
            text = content.decode("utf-8", errors="replace")
            FakeFetcher.statuses.append((url, 200))
            return FetchResult(url, 200, text, content, False, None, headers)

    return FakeFetcher


class FakeResponse:
    """requests.Response-erstatning. chunks (en iterator af bytes) giver et svar, der streames i bidder."""

    def __init__(self, status: int = 200, body: bytes | str = b"", headers: dict | None = None, chunks=None):
        self.status_code = status
        self.content = body.encode("utf-8") if isinstance(body, str) else body
        self.headers = headers or {}
        self.encoding = None
        self.chunks = chunks
        self.read = 0  # bytes læst via iter_content
        self.closed = False

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def iter_content(self, chunk_size=1):
        source = self.chunks if self.chunks is not None else (
            self.content[i : i + chunk_size] for i in range(0, len(self.content), chunk_size)
        )
        for chunk in source:
            self.read += len(chunk)
            yield chunk

    def close(self):
        self.closed = True


class FakeSession:
    """requests.Session-erstatning. responses: url -> liste af svar/undtagelser (det sidste genbruges)."""

    def __init__(self, responses: dict[str, list]):
        self.responses = {k: list(v) for k, v in responses.items()}
        self.calls: list[tuple[str, dict]] = []
        self.headers: dict = {}

    def get(self, url, headers=None, timeout=None, allow_redirects=True, stream=False):
        self.calls.append((url, dict(headers or {})))
        queue = self.responses.get(url)
        if not queue:
            return FakeResponse(404)
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        return item


def setup_env(tmp_path: Path, monkeypatch, sources: Path | None = None, medier: Path | None = None) -> SimpleNamespace:
    """Kopiér config/ og testkilder til tmp_path og peg paths dertil."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    for f in paths.CONFIG_DIR.iterdir():
        if f.is_file() and f.suffix in (".yaml", ".md"):
            shutil.copy(f, config_dir / f.name)
    shutil.copy(medier or FIXTURES / "medier.yaml", config_dir / "medier.yaml")
    sources_file = tmp_path / "sources.yaml"
    shutil.copy(sources or FIXTURES / "sources.yaml", sources_file)
    data = tmp_path / "data"
    monkeypatch.setattr(paths, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(paths, "SOURCES_FILE", sources_file)
    monkeypatch.setattr(paths, "DATA_DIR", data)
    monkeypatch.setattr(paths, "CANDIDATES_DIR", data / "candidates")
    monkeypatch.setattr(paths, "REJECTED_DIR", data / "rejected")
    monkeypatch.setattr(paths, "JUDGMENTS_DIR", data / "judgments")
    monkeypatch.setattr(paths, "OVERVIEW_DIR", data / "overview")
    monkeypatch.setattr(paths, "OVERVIEW_ARCHIVE_DIR", data / "overview" / "archive")
    monkeypatch.setattr(paths, "STATE_DIR", data / "state")
    monkeypatch.setattr(paths, "HEARTBEAT_FILE", data / "judgments" / "_heartbeat.json")
    return SimpleNamespace(root=tmp_path, config=config_dir, sources=sources_file, data=data)
