"""Test af run-kommandoen (pipeline.py) og health.py med falsk Fetcher, fixtures og tmp data-mappe."""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from affaldsfeed import paths, pipeline, store
from affaldsfeed.config import load_config
from affaldsfeed.health import is_due, record_result, silent
from affaldsfeed.models import SourceState

FIXTURES = Path(__file__).resolve().parent / "fixtures"
NOW = "2026-10-07T08:05:00Z"
LATER = "2026-10-07T09:05:00Z"


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


def _run(monkeypatch, routes=None, **kw) -> tuple[int, type]:
    fake = _fakes().make_fetcher_class(routes)
    monkeypatch.setattr(pipeline, "Fetcher", fake)
    args = argparse.Namespace(only=kw.get("only"), dry_run=kw.get("dry_run", False), now=kw.get("now", NOW))
    return pipeline.main_run(args), fake


def _cands() -> dict:
    return {c.id: c for c in store.load_candidates()}


def _by_title(cands: dict) -> dict:
    return {c.title: c for c in cands.values()}


# ── Første kørsel ───────────────────────────────────────────


def test_first_run(env, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    code, fake = _run(monkeypatch)
    assert code == 0
    # Første kørsel er ubetinget (ingen If-None-Match)
    assert all(cond is False for _, cond in fake.calls)

    cands = _by_title(_cands())
    assert set(cands) == {
        "Nye regler for affaldsgebyrer i kommunerne",
        "Kronik: Genanvendelse af plast halter langt bagefter",
        "Relativt link om genbrugspladser",
        "Kommuner skal sortere mere affald",
        "Høring over ny affaldsbekendtgørelse",
        "Årsrapport om tekstilindsamling",
        "Medlemsmøde i november",
        "Ny ordning for madaffald & plast fra 1. januar",
        "Nye affaldsregler får stik modsat effekt",
        "Nyt genbrugscenter åbner i Aarhus",
    }
    assert all(c.baseline for c in cands.values())
    assert all(c.first_seen == datetime(2026, 10, 7, 8, 5, tzinfo=UTC) for c in cands.values())

    gebyr = cands["Nye regler for affaldsgebyrer i kommunerne"]
    assert gebyr.source == "testmedie" and gebyr.why.decision == "vis"
    assert gebyr.published == datetime(2026, 10, 6, 8, 0, tzinfo=UTC) and gebyr.date_quality == "kilde"
    assert gebyr.categories == ["Kommunal", "Forsyning"]
    assert gebyr.url.endswith("?utm_source=rss")  # original-URL gemmes; id er af normaliseret URL
    assert cands["Kronik: Genanvendelse af plast halter langt bagefter"].genre == "debat"
    assert cands["Høring over ny affaldsbekendtgørelse"].genre == "hoering"
    assert "regler" in cands["Høring over ny affaldsbekendtgørelse"].topics

    madaffald = cands["Ny ordning for madaffald & plast fra 1. januar"]
    assert "<" not in madaffald.teaser and "alert" not in madaffald.teaser
    assert madaffald.teaser.startswith("Fra 1. januar skal alle husstande sortere madaffald")

    # Søgefund krediteres udgiveren; DR-fundet er en dublet af DR's eget feed
    tv2 = cands["Nye affaldsregler får stik modsat effekt"]
    assert tv2.source == "tv2" and tv2.found_via == "search"
    assert cands["Kommuner skal sortere mere affald"].source == "dr"
    assert cands["Kommuner skal sortere mere affald"].found_via == "feed"
    # Googles TV2 Østjylland-link er dedupet på titel + udgiver mod Bings fund
    aarhus = cands["Nyt genbrugscenter åbner i Aarhus"]
    assert aarhus.source == "tv2-ostjylland"
    assert aarhus.url == "https://www.tv2ostjylland.dk/aarhus/nyt-genbrugscenter"

    rejected = {r.title: r for r in store.load_rejected()}
    assert rejected["Fodboldkamp aflyst i regnvejr"].why.decision == "afvist"
    assert rejected["Ledig stilling: projektleder til affaldsområdet"].why.reason.startswith("veto")
    assert rejected["Gammel nyhed om affaldssortering i boligforeninger"].why.reason == "for gammel"
    # Gamle indslag gemmes kun, hvis de ellers var relevante og er nyere end rejected_keep_days
    assert "Gammel sportsnyhed om håndbold" not in rejected
    assert "Meget gammel nyhed om affaldsgebyrer" not in rejected
    assert rejected["Forsinket tømning i uge 42"].why.reason.startswith("driftsbesked")
    assert "Regeringen vil sænke skatten" in rejected
    # Fremtidsdato og udaterede indslag springes over ved første kørsel
    all_titles = set(cands) | set(rejected)
    assert "Skraldebil med el kører i fremtiden" not in all_titles
    assert "Affaldsplan for 2027 er vedtaget" not in all_titles

    states = store.load_source_states()
    assert set(states) == {"google-news", "bing-news", "testmedie", "dr", "testorg", "affaldsselskab", "udateret"}
    assert states["testmedie"].first_run_done and states["testmedie"].health == "groen"
    assert states["testmedie"].last_ok == date(2026, 10, 7)
    assert states["testmedie"].items_30d == 3
    assert states["udateret"].items_30d == 0

    kf = json.loads((paths.STATE_DIR / "kildeforslag.json").read_text(encoding="utf-8"))
    assert set(kf) == {"ukendtblog.dk", "lokalbladet-nord.dk"}
    assert (paths.STATE_DIR / "kildeforslag.md").exists()
    http = json.loads((paths.STATE_DIR / "http.json").read_text(encoding="utf-8"))
    assert http["https://www.testmedie.dk/rss"] == {"etag": '"v1"'}

    log = caplog.text
    assert "Opsummering" in log
    assert "Venter på fase 2 (metode ikke implementeret): ventende" in log
    assert "Nye kandidater: 10" in log
    assert "Nye pr. kategori:" in log


def test_second_run_dedupes_and_respects_schedule(env, monkeypatch, tmp_path):
    assert _run(monkeypatch)[0] == 0
    before = _cands()

    # Ny titel på et kendt indslag
    changed = tmp_path / "rss2_changed.xml"
    changed.write_text(
        (FIXTURES / "rss2.xml").read_text(encoding="utf-8").replace(
            "Nye regler for affaldsgebyrer i kommunerne", "Nye regler for affaldsgebyrer i alle kommuner"
        ),
        encoding="utf-8",
    )
    routes = dict(_fakes().DEFAULT_ROUTES)
    routes["https://www.testmedie.dk/rss"] = changed
    code, fake = _run(monkeypatch, routes, now=LATER)
    assert code == 0
    called = {u for u, _ in fake.calls}
    # Søgekilder har every: 2 og er ikke på tur efter 1 time
    assert not any("google" in u or "bing" in u for u in called)
    assert all(cond is True for _, cond in fake.calls)  # conditional GET efter første kørsel

    after = _cands()
    assert len(after) == len(before) + 3  # fremtidsdato + 2 udaterede
    upd = next(c for c in after.values() if c.title == "Nye regler for affaldsgebyrer i alle kommuner")
    orig = before[upd.id]
    assert upd.first_seen == orig.first_seen and upd.published == orig.published

    titles = _by_title(after)
    fut = titles["Skraldebil med el kører i fremtiden"]
    assert fut.date_quality == "fundet" and fut.published == fut.first_seen == datetime(2026, 10, 7, 9, 5, tzinfo=UTC)
    assert not fut.baseline
    plan = titles["Affaldsplan for 2027 er vedtaget"]
    assert plan.date_quality == "fundet" and plan.source == "udateret" and not plan.baseline

    # Afviste genfindes uden dubletter og beholder første fund
    rej = store.load_rejected()
    assert len(rej) == len({r.id for r in rej})
    fodbold = next(r for r in rej if r.title == "Fodboldkamp aflyst i regnvejr")
    assert fodbold.first_seen == datetime(2026, 10, 7, 8, 5, tzinfo=UTC)


def test_dry_run_writes_nothing(env, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    code, _ = _run(monkeypatch, dry_run=True)
    assert code == 0
    assert not env.data.exists() or not any(p.is_file() for p in env.data.rglob("*"))
    assert "Dry-run: intet er skrevet" in caplog.text
    assert "+ [vis" in caplog.text


def test_only_limits_sources(env, monkeypatch):
    code, fake = _run(monkeypatch, only="testmedie,findes-ikke")
    assert code == 0
    assert {u for u, _ in fake.calls} == {"https://www.testmedie.dk/rss"}
    assert set(store.load_source_states()) == {"testmedie"}


def test_only_without_match_gives_exit_1(env, monkeypatch, caplog):
    code, fake = _run(monkeypatch, only="findes-ikke,planlagt,ventende")
    assert code == 1 and fake.calls == []
    assert "Ukendt kilde i --only: findes-ikke" in caplog.text
    assert "planlagt har status 'planlagt'" in caplog.text


def test_only_forces_source_even_if_not_due(env, monkeypatch):
    assert _run(monkeypatch, only=["bing-news"])[0] == 0
    code, fake = _run(monkeypatch, only=["bing-news"], now=LATER)
    assert code == 0 and fake.calls


def test_failing_source_is_isolated(env, monkeypatch):
    routes = dict(_fakes().DEFAULT_ROUTES)
    routes["https://www.testmedie.dk/rss"] = "raise"
    routes["https://www.dr.dk/nyheder/service/feeds/indland"] = 500
    code, _ = _run(monkeypatch, routes)
    assert code == 0  # 2 af 7 fejler
    states = store.load_source_states()
    assert states["testmedie"].fails == 1 and states["testmedie"].health == "gul"
    assert "RuntimeError" in states["testmedie"].last_error
    assert not states["testmedie"].first_run_done
    assert states["dr"].last_error == "https://www.dr.dk/nyheder/service/feeds/indland: HTTP 500"
    assert states["testorg"].fails == 0
    assert any(c.source == "testorg" for c in store.load_candidates())


def test_too_many_failures_gives_exit_1(env, monkeypatch):
    routes = {"https://testorg.dk/atom.xml": "atom.xml"}  # alt andet giver 404
    code, _ = _run(monkeypatch, routes)
    assert code == 1
    assert store.load_source_states()["testorg"].health == "groen"


def test_red_source_after_repeated_failures(env, monkeypatch):
    routes = dict(_fakes().DEFAULT_ROUTES)
    routes["https://udateret.dk/rss"] = 500
    for i in range(5):
        now = (datetime(2026, 10, 7, 8, 5, tzinfo=UTC) + timedelta(hours=i)).isoformat()
        _run(monkeypatch, routes, only="udateret", now=now)
    st = store.load_source_states()["udateret"]
    assert st.fails == 5 and st.health == "roed"


def test_invalid_config_gives_exit_1(env, monkeypatch, caplog):
    env.sources.write_text("- id: Ugyldigt Id\n", encoding="utf-8")
    code, _ = _run(monkeypatch)
    assert code == 1
    assert "Konfigurationen er ugyldig" in caplog.text


def test_override_vis_rescues_rejected(env, monkeypatch):
    from affaldsfeed.normalize import item_id

    fid = item_id("https://www.testmedie.dk/sport/fodbold-aflyst")
    (env.config / "overrides.yaml").write_text(f'- match: {{id: "{fid}"}}\n  action: vis\n', encoding="utf-8")
    assert _run(monkeypatch, only="testmedie")[0] == 0
    c = _cands()[fid]
    assert c.why.decision == "vis" and c.why.reason == "vist via overrides.yaml"


def test_processor_search_uses_strictest_filter(env):
    from affaldsfeed.config import load_sources

    sources = load_sources(env.sources)
    cfg = load_config(env.config)
    proc = pipeline.Processor(cfg, sources, datetime(2026, 10, 7, tzinfo=UTC), {}, set())
    bing = next(s for s in sources if s.id == "bing-news")
    assert proc.rule_source(bing, "dr").filter == "strict"  # DR er strict, Bing normal
    tv2 = proc.rule_source(bing, "tv2")
    assert tv2.category == "nyhedsmedie" and tv2.filter == "normal" and tv2.id == "tv2"


def test_processor_dedupes_same_article_in_two_section_feeds(env):
    from affaldsfeed.collect import RawEntry
    from affaldsfeed.config import load_sources

    sources = load_sources(env.sources)
    cfg = load_config(env.config)
    now = datetime(2026, 10, 7, 8, tzinfo=UTC)
    src = next(s for s in sources if s.method == "rss" and s.status == "aktiv")

    def raw(url: str, title: str) -> RawEntry:
        return RawEntry(src.id, url, title, "", now - timedelta(hours=2), "kilde", "da", [], None, None, "feed")

    proc = pipeline.Processor(cfg, sources, now, {}, set())
    long_title = "Ny plan for affald i kommunerne vedtaget"
    out = proc.process(
        src,
        [
            raw("https://x.dk/forsyning/artikel/plan", long_title),
            raw("https://x.dk/klima/artikel/plan", long_title),
            raw("https://x.dk/a/affald", "Affald"),
            raw("https://x.dk/b/affald", "Affald"),
        ],
        first_run=False,
    )
    titles = [c.title for c in out.new]
    assert titles.count(long_title) == 1  # samme artikel i to sektionsfeeds
    assert titles.count("Affald") == 2  # korte titler dedupes ikke


# ── health ─────────────────────────────────────────────────


def _settings(env):
    return load_config(env.config).settings


def test_is_due(make_source):
    now = datetime(2026, 10, 7, 10, 5, tzinfo=UTC)
    rss = make_source()
    assert is_due(rss, SourceState(), now)
    assert is_due(rss, SourceState(last_attempt=now - timedelta(minutes=40)), now)  # forsinket cron
    assert not is_due(rss, SourceState(last_attempt=now - timedelta(minutes=10)), now)
    search = make_source(method="search", feeds=["https://x/?q={q}"])
    assert not is_due(search, SourceState(last_attempt=now - timedelta(hours=1)), now)
    assert is_due(search, SourceState(last_attempt=now - timedelta(hours=2)), now)
    red = SourceState(last_attempt=now - timedelta(hours=3), health="roed", fails=5)
    assert not is_due(rss, red, now)
    assert is_due(rss, red.model_copy(update={"last_attempt": now - timedelta(hours=24)}), now)


def test_record_result_and_silent(env):
    s = _settings(env)
    now = datetime(2026, 10, 6, 22, 30, tzinfo=UTC)  # 00:30 dansk tid den 7.
    st = record_result(SourceState(), True, None, now, s)
    assert st.health == "groen" and st.last_ok == date(2026, 10, 7) and st.first_run_done
    assert st.last_attempt == now
    assert silent(st)  # svarer, men ingen indslag
    assert not silent(st.model_copy(update={"items_30d": 2}))
    for i in range(1, 6):
        st = record_result(st, False, "HTTP 500", now, s)
        assert st.fails == i
        assert st.health == ("roed" if i >= 5 else "gul")
    assert st.last_ok == date(2026, 10, 7) and st.last_error == "HTTP 500"
    assert not silent(st)
    st = record_result(st, True, None, now, s)
    assert st.fails == 0 and st.last_error is None and st.health == "groen"
