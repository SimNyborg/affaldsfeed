"""Test af fetch.py og collect/ (rss, search) med fixtures. Ingen netværkskald."""

from __future__ import annotations

import base64
import gzip
import importlib.util
import io
import sys
import tracemalloc
from datetime import UTC, datetime
from pathlib import Path

import pytest
import requests
import urllib3

from affaldsfeed.collect import COLLECTORS, CollectContext, match_publisher
from affaldsfeed.collect.search import bing_target, build_url, decode_google_link
from affaldsfeed.config import load_config, load_sources, publisher_lookup
from affaldsfeed.fetch import (
    BUDGET_EXHAUSTED,
    MAX_REDIRECTS,
    ROBOTS_BLOCKED,
    ROBOTS_MAX_BYTES,
    TOO_LARGE,
    Fetcher,
)
from affaldsfeed.models import FetchSettings

FIXTURES = Path(__file__).resolve().parent / "fixtures"
NOW = datetime(2026, 10, 7, 8, 5, tzinfo=UTC)
UA = "Affaldsfeed/0.1 (+https://github.com/SimNyborg/affaldsfeed)"


def _fakes():
    name = "affaldsfeed_test_fakes"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, FIXTURES / "fakes.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return sys.modules[name]


@pytest.fixture
def env(tmp_path, monkeypatch):
    return _fakes().setup_env(tmp_path, monkeypatch)


@pytest.fixture
def ctx(env):
    sources = load_sources(env.sources)
    cfg = load_config(env.config)
    return CollectContext(config=cfg, sources=sources, now=NOW, publisher_lookup=publisher_lookup(sources, cfg.publishers))


def _source(ctx, sid):
    return next(s for s in ctx.sources if s.id == sid)


def _fetcher(routes=None):
    return _fakes().make_fetcher_class(routes)(None, {}, {}, NOW)


# ── RSS ─────────────────────────────────────────────────────


def test_rss2(ctx):
    res = COLLECTORS["rss"](_source(ctx, "testmedie"), _fetcher(), ctx)
    assert res.error is None
    assert len(res.entries) == 9
    first = res.entries[0]
    assert first.source_id == "testmedie"
    assert first.title == "Nye regler for affaldsgebyrer i kommunerne"
    assert first.url == "https://www.testmedie.dk/nyheder/affaldsgebyrer?utm_source=rss"
    assert first.published == datetime(2026, 10, 6, 8, 0, tzinfo=UTC)
    assert first.date_quality == "kilde"
    assert first.categories == ["Kommunal", "Forsyning"]
    assert first.found_via == "feed" and first.lang == "da"
    # Relativt link gøres absolut
    assert res.entries[-1].url == "https://www.testmedie.dk/nyheder/relativ-genbrugsplads"


def test_atom_and_multiple_feeds_with_one_failing(ctx):
    res = COLLECTORS["rss"](_source(ctx, "testorg"), _fetcher(), ctx)
    assert res.error is None  # ekstra.xml giver 404, men atom.xml virker
    assert [e.title for e in res.entries] == [
        "Høring over ny affaldsbekendtgørelse",
        "Årsrapport om tekstilindsamling",
        "Medlemsmøde i november",
    ]
    assert res.entries[0].published == datetime(2026, 10, 6, 6, 15, tzinfo=UTC)  # published før updated
    assert res.entries[1].published == datetime(2026, 10, 5, 12, 0, tzinfo=UTC)  # kun updated
    assert res.entries[0].categories == ["Høring"]


def test_all_feeds_failing_is_an_error(ctx):
    fetcher = _fetcher({"https://testorg.dk/": 500})
    res = COLLECTORS["rss"](_source(ctx, "testorg"), fetcher, ctx)
    assert res.entries == []
    assert "HTTP 500" in res.error


def test_html_page_is_not_a_feed(ctx):
    res = COLLECTORS["rss"](_source(ctx, "testmedie"), _fetcher({"https://www.testmedie.dk/rss": "not_a_feed.html"}), ctx)
    assert res.entries == []
    assert "ikke et gyldigt feed" in res.error


def test_html_in_description_is_kept_raw_for_cleaning(ctx):
    res = COLLECTORS["rss"](_source(ctx, "affaldsselskab"), _fetcher(), ctx)
    e = res.entries[0]
    assert "<strong>madaffald</strong>" in e.teaser  # renses i pipeline med clean_text
    assert "<script" not in e.teaser  # feedparser fjerner scripts


def test_feed_without_dates(ctx):
    res = COLLECTORS["rss"](_source(ctx, "udateret"), _fetcher(), ctx)
    assert len(res.entries) == 2
    assert all(e.published is None and e.date_quality == "fundet" for e in res.entries)


def test_conditional_flag_is_passed(ctx):
    fake = _fakes().make_fetcher_class()
    ctx.conditional = False
    COLLECTORS["rss"](_source(ctx, "testmedie"), fake(None, {}, {}, NOW), ctx)
    assert fake.calls == [("https://www.testmedie.dk/rss", False)]


# ── Søgning ─────────────────────────────────────────────────


def test_build_url_encodes_query():
    tpl = "https://news.google.com/rss/search?q={q}+when:2d&hl=da"
    assert build_url(tpl, 'affald OR "direkte genbrug"', "2d") == (
        "https://news.google.com/rss/search?q=affald+OR+%22direkte+genbrug%22+when:2d&hl=da"
    )
    assert build_url("https://x/?q={q}&w={when}", "æ", "2d") == "https://x/?q=%C3%A6&w=2d"


def test_decode_google_link():
    url = "https://www.dr.dk/nyheder/indland/kommuner-skal-sortere-mere-affald"
    raw = b"\x08\x13\x22" + bytes([len(url)]) + url.encode() + b"\xd2\x01\x00"
    token = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    assert decode_google_link(f"https://news.google.com/rss/articles/{token}?oc=5") == url
    # Nyt format (krypteret nøgle) kan ikke afkodes
    assert decode_google_link("https://news.google.com/rss/articles/CBMiXEFVX3lxTFBsb2thbGJsYWRldA?oc=5") is None
    assert decode_google_link("https://news.google.com/rss/articles/!!!") is None
    assert decode_google_link("https://example.dk/") is None


def test_bing_target():
    link = "http://www.bing.com/news/apiclick.aspx?ref=FexRss&aid=&url=https%3a%2f%2fwww.dr.dk%2fa%3fx%3d1&c=1"
    assert bing_target(link) == "https://www.dr.dk/a?x=1"
    assert bing_target("https://www.dr.dk/b") == "https://www.dr.dk/b"


def test_match_publisher_walks_up_domains():
    lookup = {"tv2.dk": "tv2", "dr.dk": "dr"}
    assert match_publisher("nyheder.tv2.dk", lookup) == "tv2"
    assert match_publisher("www.dr.dk", lookup) == "dr"
    assert match_publisher("dk", lookup) is None
    assert match_publisher("eksempel.dk", lookup) is None


def test_google_news(ctx):
    fake = _fakes().make_fetcher_class()
    res = COLLECTORS["search"](_source(ctx, "google-news"), fake(None, {}, {}, NOW), ctx)
    assert res.error is None
    # Én forespørgsel pr. linje i search.yaml, q er URL-encodet
    assert len(fake.calls) == len(ctx.config.search.queries)
    assert fake.calls[0][0].startswith("https://news.google.com/rss/search?q=affald+OR+affaldet")
    by_title = {e.title: e for e in res.entries}
    dr = by_title["Kommuner skal sortere mere affald"]  # " - DR" er fjernet
    assert dr.source_id == "dr"
    assert dr.url == "https://www.dr.dk/nyheder/indland/kommuner-skal-sortere-mere-affald"
    assert dr.found_via == "search" and dr.publisher_name == "DR" and dr.teaser == ""
    tv2 = by_title["Nyt genbrugscenter åbner i Aarhus"]
    assert tv2.source_id == "tv2-ostjylland"
    assert tv2.url.startswith("https://news.google.com/rss/articles/")  # kunne ikke afkodes
    assert res.unknown_publishers == [
        (
            "lokalbladet-nord.dk",
            "Lokalbladet Nord",
            "https://news.google.com/rss/articles/CBMiXEFVX3lxTFBsb2thbGJsYWRldA?oc=5",
        )
    ]
    assert len(res.entries) == 2  # dubletter på tværs af forespørgsler er fjernet


def test_bing_news(ctx):
    res = COLLECTORS["search"](_source(ctx, "bing-news"), _fetcher(), ctx)
    assert res.error is None
    by_url = {e.url: e for e in res.entries}
    tv2 = by_url["https://nyheder.tv2.dk/samfund/2026-10-06-nye-affaldsregler-faar-stik-modsat-effekt"]
    assert tv2.source_id == "tv2" and tv2.publisher_name == "TV 2"
    assert tv2.publisher_domain == "nyheder.tv2.dk"
    assert tv2.teaser.startswith("Kommunerne advarer")
    assert by_url["https://www.dr.dk/nyheder/indland/kommuner-skal-sortere-mere-affald"].source_id == "dr"
    assert by_url["https://www.tv2ostjylland.dk/aarhus/nyt-genbrugscenter"].source_id == "tv2-ostjylland"
    # Kun relevante artikler fra ukendte udgivere bliver kildeforslag (sladder.dk er irrelevant)
    assert res.unknown_publishers == [("ukendtblog.dk", "Ukendt Blog", "https://www.ukendtblog.dk/skraldespande")]


def test_search_engine_blocked_is_error(ctx):
    res = COLLECTORS["search"](_source(ctx, "bing-news"), _fetcher({"https://www.bing.com/": 429}), ctx)
    assert res.entries == [] and "HTTP 429" in res.error


# ── Fetcher ─────────────────────────────────────────────────


def _real_fetcher(responses, http_cache=None, robots_cache=None):
    f = Fetcher(FetchSettings(user_agent=UA, min_interval_seconds=0), http_cache or {}, robots_cache or {}, NOW)
    f.session = _fakes().FakeSession(responses)
    return f


def _resp(*a, **kw):
    return _fakes().FakeResponse(*a, **kw)


def test_fetcher_robots_disallow_and_cache():
    robots = "User-agent: *\nDisallow: /privat/\n"
    f = _real_fetcher(
        {"https://x.dk/robots.txt": [_resp(200, robots)], "https://x.dk/rss": [_resp(200, "<rss/>")]}
    )
    res = f.get("https://x.dk/privat/rss")
    assert res.error == "blokeret af robots.txt"
    assert f.get("https://x.dk/rss").ok
    assert [c[0] for c in f.session.calls] == ["https://x.dk/robots.txt", "https://x.dk/rss"]
    assert f.robots_cache["x.dk"] == {"fetched": "2026-10-07T08:05:00Z", "body": robots}


def test_fetcher_own_token_group_wins():
    robots = "User-agent: Affaldsfeed\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
    f = _real_fetcher({"https://x.dk/robots.txt": [_resp(200, robots)]})
    assert f.allowed("https://x.dk/rss") is False


def test_fetcher_robots_4xx_allows_all_5xx_blocks_run():
    f = _real_fetcher({"https://a.dk/robots.txt": [_resp(404)], "https://a.dk/rss": [_resp(200, "ok")],
                       "https://b.dk/robots.txt": [_resp(503)]})
    assert f.get("https://a.dk/rss").ok
    assert f.robots_cache["a.dk"]["body"] == ""
    res = f.get("https://b.dk/rss")
    assert not res.ok and "robots.txt" in res.error
    assert "b.dk" not in f.robots_cache
    assert all(c[0] != "https://b.dk/rss" for c in f.session.calls)


def test_fetcher_uses_fresh_robots_cache():
    cache = {"x.dk": {"fetched": "2026-10-07T01:00:00Z", "body": "User-agent: *\nDisallow: /\n"}}
    f = _real_fetcher({}, robots_cache=cache)
    assert f.allowed("https://x.dk/rss") is False
    assert f.session.calls == []


def test_fetcher_conditional_get_and_cache_update():
    http_cache = {"https://x.dk/rss": {"etag": '"abc"', "last_modified": "Tue, 06 Oct 2026 10:00:00 GMT"}}
    f = _real_fetcher(
        {"https://x.dk/robots.txt": [_resp(404)], "https://x.dk/rss": [_resp(304)]}, http_cache=http_cache
    )
    res = f.get("https://x.dk/rss")
    assert res.not_modified and res.ok and res.status == 304
    sent = f.session.calls[-1][1]
    assert sent["If-None-Match"] == '"abc"'
    assert sent["If-Modified-Since"] == "Tue, 06 Oct 2026 10:00:00 GMT"

    f.session.responses["https://x.dk/rss"] = [_resp(200, "<rss/>", {"ETag": '"def"'})]
    res = f.get("https://x.dk/rss", conditional=False)
    assert res.status == 200 and res.content == b"<rss/>"
    assert "If-None-Match" not in f.session.calls[-1][1]
    assert http_cache["https://x.dk/rss"] == {"etag": '"def"'}


def test_fetcher_accept_overrides_the_session_default():
    f = _real_fetcher({"https://x.dk/robots.txt": [_resp(404)], "https://x.dk/api": [_resp(200, "{}")]})
    f.get("https://x.dk/api", conditional=False, accept="application/json")
    assert f.session.calls[-1][1]["Accept"] == "application/json"
    f.get("https://x.dk/api", conditional=False)
    assert "Accept" not in f.session.calls[-1][1]  # sessionens standard (feeds først) gælder


def test_fetcher_retries_once_on_5xx_and_timeout():
    f = _real_fetcher({"https://x.dk/robots.txt": [_resp(404)], "https://x.dk/rss": [_resp(502), _resp(200, "ok")]})
    assert f.get("https://x.dk/rss").ok
    assert [c[0] for c in f.session.calls].count("https://x.dk/rss") == 2

    f = _real_fetcher({"https://y.dk/robots.txt": [_resp(404)], "https://y.dk/rss": [requests.Timeout()]})
    res = f.get("https://y.dk/rss")
    assert res.error == "timeout"
    assert [c[0] for c in f.session.calls].count("https://y.dk/rss") == 2


def test_fetcher_429_skips_host_for_rest_of_run():
    f = _real_fetcher(
        {"https://x.dk/robots.txt": [_resp(404)], "https://x.dk/a": [_resp(429, "", {"Retry-After": "3600"})]}
    )
    res = f.get("https://x.dk/a")
    assert res.status == 429 and "Retry-After: 3600" in res.error
    res2 = f.get("https://x.dk/b")
    assert "springes over" in res2.error
    assert [c[0] for c in f.session.calls].count("https://x.dk/a") == 1
    assert all(c[0] != "https://x.dk/b" for c in f.session.calls)


# ── Fetcher: omdirigeringer ─────────────────────────────────


def test_fetcher_follows_redirects_itself_and_reports_the_final_url():
    hop = _resp(301, "", {"Location": "/ny/rss"})
    f = _real_fetcher(
        {
            "https://x.dk/robots.txt": [_resp(404)],
            "https://x.dk/rss": [hop],
            "https://x.dk/ny/rss": [_resp(200, "<rss/>", {"ETag": '"1"'})],
        }
    )
    res = f.get("https://x.dk/rss")
    assert res.ok and res.url == "https://x.dk/rss" and res.final_url == "https://x.dk/ny/rss"
    assert [c[0] for c in f.session.calls] == ["https://x.dk/robots.txt", "https://x.dk/rss", "https://x.dk/ny/rss"]
    assert [a for u, a in f.session.follow if not u.endswith("/robots.txt")] == [False, False]  # requests følger aldrig selv
    assert hop.closed
    assert f.http_cache == {"https://x.dk/rss": {"etag": '"1"'}}  # gemt under den adresse, der blev bedt om


def test_fetcher_never_follows_a_redirect_into_a_path_robots_txt_forbids():
    robots = "User-agent: *\nDisallow: /wp-content/uploads/\n"
    f = _real_fetcher(
        {
            "https://x.dk/robots.txt": [_resp(200, robots)],
            "https://x.dk/favicon.ico": [_resp(302, "", {"Location": "https://x.dk/wp-content/uploads/ikon.png"})],
        }
    )
    res = f.get("https://x.dk/favicon.ico")
    assert res.error == ROBOTS_BLOCKED and res.permanent and res.url == "https://x.dk/favicon.ico"
    assert all("/wp-content/" not in c[0] for c in f.session.calls)


def test_fetcher_checks_robots_txt_on_the_host_it_is_redirected_to():
    f = _real_fetcher(
        {
            "https://x.dk/robots.txt": [_resp(404)],
            "https://x.dk/rss": [_resp(308, "", {"Location": "https://www.y.dk/rss"})],
            "https://www.y.dk/robots.txt": [_resp(200, "User-agent: *\nDisallow: /\n")],
        }
    )
    assert f.get("https://x.dk/rss").error == ROBOTS_BLOCKED
    assert [c[0] for c in f.session.calls] == ["https://x.dk/robots.txt", "https://x.dk/rss", "https://www.y.dk/robots.txt"]

    # Svarer målets robots.txt ikke, springes værten over, ligesom når den hentes direkte
    f = _real_fetcher(
        {
            "https://x.dk/robots.txt": [_resp(404)],
            "https://x.dk/rss": [_resp(301, "", {"Location": "https://z.dk/rss"})],
            "https://z.dk/robots.txt": [_resp(503)],
        }
    )
    assert f.get("https://x.dk/rss").error.startswith("springes over: robots.txt utilgængelig")
    assert all(c[0] != "https://z.dk/rss" for c in f.session.calls)


def test_fetcher_stops_redirect_loops_and_odd_redirects():
    f = _real_fetcher(
        {
            "https://x.dk/robots.txt": [_resp(404)],
            "https://x.dk/a": [_resp(302, "", {"Location": "/b"})],
            "https://x.dk/b": [_resp(302, "", {"Location": "/a"})],
        }
    )
    res = f.get("https://x.dk/a")
    assert res.error == f"for mange omdirigeringer (over {MAX_REDIRECTS})"
    assert len(f.session.calls) == 1 + MAX_REDIRECTS + 1  # robots.txt og højst MAX_REDIRECTS + 1 hop

    f = _real_fetcher(
        {
            "https://x.dk/robots.txt": [_resp(404)],
            "https://x.dk/a": [_resp(301, "", {"Location": "ftp://x.dk/a"})],
            "https://x.dk/c": [_resp(301)],
        }
    )
    assert "ikke er http(s)" in f.get("https://x.dk/a").error
    assert f.get("https://x.dk/c").error == "HTTP 301"  # uden Location


def test_fetcher_429_after_a_redirect_skips_the_host_that_answered():
    f = _real_fetcher(
        {
            "https://x.dk/robots.txt": [_resp(404)],
            "https://y.dk/robots.txt": [_resp(404)],
            "https://x.dk/a": [_resp(301, "", {"Location": "https://y.dk/a"})],
            "https://y.dk/a": [_resp(429)],
            "https://x.dk/b": [_resp(200, "ok")],
        }
    )
    assert f.get("https://x.dk/a").status == 429
    assert f.get("https://x.dk/b").ok  # x.dk svarede ikke 429
    assert "springes over" in f.get("https://y.dk/c").error


def test_fetcher_budget_ends_a_redirect_chain(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("affaldsfeed.fetch.time.monotonic", lambda: clock[0])
    f = _real_fetcher(
        {"https://x.dk/a": [_resp(301, "", {"Location": "/b"})], "https://x.dk/b": [_resp(200, "ok")]},
        robots_cache={"x.dk": {"fetched": "2026-10-07T08:00:00Z", "body": ""}},
    )
    session_get = f.session.get

    def slow_get(url, **kw):
        clock[0] += 10  # hvert kald tager 10 sek.
        return session_get(url, **kw)

    f.session.get = slow_get
    f.start_budget(5)
    res = f.get("https://x.dk/a")
    assert res.error == BUDGET_EXHAUSTED and res.url == "https://x.dk/a"
    assert [c[0] for c in f.session.calls] == ["https://x.dk/a"]


def test_fetcher_sets_honest_user_agent():
    f = Fetcher(FetchSettings(user_agent=UA), {}, {}, NOW)
    assert f.session.headers["User-Agent"] == UA
    assert f.ua_token == "Affaldsfeed"


# ── Fetcher: loft over svarets størrelse ────────────────────


def _endless(chunk: bytes = b"x" * 65536):
    while True:
        yield chunk


def test_fetcher_stops_reading_a_response_over_the_limit():
    big = _resp(200, chunks=_endless())
    f = _real_fetcher({"https://x.dk/robots.txt": [_resp(404)], "https://x.dk/stor.xml": [big]})
    res = f.get("https://x.dk/stor.xml", max_bytes=1024 * 1024)
    assert res.content is None and res.error.startswith(TOO_LARGE) and res.permanent
    assert big.read <= 1024 * 1024 + 65536 and big.closed  # afbrudt lige over loftet, ikke læst færdig
    assert "https://x.dk/stor.xml" not in f.http_cache


def test_fetcher_limit_comes_from_settings_and_content_length_is_checked_first():
    f = Fetcher(FetchSettings(user_agent=UA, min_interval_seconds=0, max_response_mb=0.5), {}, {}, NOW)
    huge = _resp(200, b"x", {"Content-Length": str(10**9)})
    f.session = _fakes().FakeSession(
        {
            "https://x.dk/robots.txt": [_resp(404)],
            "https://x.dk/a": [huge],
            "https://x.dk/b": [_resp(200, b"x" * 600_000)],
            "https://x.dk/c": [_resp(200, b"x" * 1000, {"ETag": '"1"'})],
        }
    )
    assert TOO_LARGE in f.get("https://x.dk/a").error and huge.read == 0  # intet læses
    assert "over 0.5 MB" in f.get("https://x.dk/b").error
    res = f.get("https://x.dk/c")
    assert res.ok and res.content == b"x" * 1000 and f.http_cache["https://x.dk/c"] == {"etag": '"1"'}


def test_fetcher_stops_a_gzip_bomb_while_unpacking():
    """Content-Encoding: gzip pakkes ud i bidder, så loftet gælder den udpakkede størrelse."""
    bomb = gzip.compress(b"\0" * (32 * 1024 * 1024))  # 32 MB nuller fylder ca. 32 kB pakket
    raw = urllib3.HTTPResponse(
        body=io.BytesIO(bomb), headers={"Content-Encoding": "gzip"}, status=200, preload_content=False
    )
    resp = requests.Response()
    resp.status_code, resp.raw = 200, raw
    resp.headers = requests.structures.CaseInsensitiveDict(
        {"Content-Encoding": "gzip", "Content-Length": str(len(bomb))}
    )
    f = _real_fetcher({"https://x.dk/robots.txt": [_resp(404)], "https://x.dk/sitemap.xml": [resp]})
    tracemalloc.start()
    try:
        res = f.get("https://x.dk/sitemap.xml", max_bytes=1024 * 1024)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert res.error.startswith(TOO_LARGE) and res.content is None
    assert peak < 16 * 1024 * 1024  # de 32 MB har aldrig ligget i hukommelsen


def test_fetcher_reads_only_the_start_of_a_huge_robots_txt():
    robots = _resp(200, chunks=_endless(b"# kommentar\n" * 4096))
    f = _real_fetcher({"https://x.dk/robots.txt": [robots], "https://x.dk/rss": [_resp(200, "<rss/>")]})
    assert f.get("https://x.dk/rss").ok
    assert len(f.robots_cache["x.dk"]["body"]) == ROBOTS_MAX_BYTES and robots.closed
