"""Testhjælpere: falsk Fetcher, falsk HTTP-session og et midlertidigt repo-miljø. Ingen netværk."""

from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

from affaldsfeed import paths
from affaldsfeed.fetch import FetchResult

FIXTURES = Path(__file__).resolve().parent

# URL (eller præfiks) -> fixture-fil, HTTP-status (int) eller "raise"
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


def make_fetcher_class(routes: dict[str, str | int | Path] | None = None):
    """Lav en Fetcher-erstatning med de givne ruter. Kald registreres i klassens .calls."""
    table = dict(DEFAULT_ROUTES if routes is None else routes)

    class FakeFetcher:
        calls: list[tuple[str, bool]] = []
        instances: list = []

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

        def get(self, url, conditional=True):
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
            if isinstance(target, int):
                return FetchResult(url, target, None, None, False, f"HTTP {target}", {})
            path = target if isinstance(target, Path) else FIXTURES / target
            content = path.read_bytes()
            headers = {"Content-Type": "application/rss+xml; charset=utf-8", "ETag": '"v1"'}
            self.http_cache[url] = {"etag": '"v1"'}
            return FetchResult(url, 200, content.decode("utf-8"), content, False, None, headers)

    return FakeFetcher


class FakeResponse:
    def __init__(self, status: int = 200, body: bytes | str = b"", headers: dict | None = None):
        self.status_code = status
        self.content = body.encode("utf-8") if isinstance(body, str) else body
        self.headers = headers or {}

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")


class FakeSession:
    """requests.Session-erstatning. responses: url -> liste af svar/undtagelser (det sidste genbruges)."""

    def __init__(self, responses: dict[str, list]):
        self.responses = {k: list(v) for k, v in responses.items()}
        self.calls: list[tuple[str, dict]] = []
        self.headers: dict = {}

    def get(self, url, headers=None, timeout=None, allow_redirects=True):
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
