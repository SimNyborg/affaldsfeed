"""Test af run-kommandoen (pipeline.py) og health.py med falsk Fetcher, fixtures og tmp data-mappe."""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from affaldsfeed import paths, pipeline, store
from affaldsfeed.collect import COLLECTORS
from affaldsfeed.config import load_config, load_sources
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
    monkeypatch.delitem(COLLECTORS, "oda")  # kilden "ventende" (oda) skal vente som en metode uden indsamler
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

    # Steder: afsenderens faste geografi (affaldsselskab) og navne i titlen
    assert madaffald.places == ["k:nyborg"]
    assert gebyr.places == []
    assert cands["Nyt genbrugscenter åbner i Aarhus"].places == ["k:aarhus", "b:aarhus"]

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
    assert "https://www.testmedie.dk/rss" in {u for u, _ in fake.calls}
    # Kun den valgte kilde: feedet og dens logo (forsiden og /favicon.ico), ingen andre værter
    assert {urlsplit(u).netloc for u, _ in fake.calls} == {"www.testmedie.dk"}
    assert set(store.load_source_states()) == {"testmedie"}


def test_only_without_match_gives_exit_1(env, monkeypatch, caplog):
    monkeypatch.delitem(COLLECTORS, "oda")
    code, fake = _run(monkeypatch, only="findes-ikke,planlagt,ventende")
    assert code == 1 and fake.calls == []
    assert "Ukendt kilde i --only: findes-ikke" in caplog.text
    assert "planlagt har status 'planlagt'" in caplog.text


def test_only_forces_source_even_if_not_due(env, monkeypatch):
    assert _run(monkeypatch, only=["bing-news"])[0] == 0
    code, fake = _run(monkeypatch, only=["bing-news"], now=LATER)
    assert code == 0 and fake.calls


def test_run_budget_postpones_feeds_but_not_search(env, monkeypatch, caplog):
    """Er kørslens tidsbudget brugt, venter feeds til næste kørsel; søgekilderne kører stadig."""
    caplog.set_level(logging.WARNING)
    clock = iter(range(0, 10**6, 1000))  # hvert kald er 1000 s senere end det forrige
    monkeypatch.setattr(pipeline, "time", argparse.Namespace(monotonic=lambda: float(next(clock))))
    code, fake = _run(monkeypatch)
    assert code == 0
    states = store.load_source_states()
    assert "bing-news" in states and states["bing-news"].last_attempt is not None
    for sid in ("testmedie", "dr", "testorg", "affaldsselskab", "udateret"):
        assert sid not in states  # ikke forsøgt; den er stadig på tur næste gang
    assert "venter til næste kørsel" in caplog.text


def test_longest_waiting_feeds_run_first(env):
    config = load_config()
    sources = load_sources()
    now = datetime(2026, 10, 7, 8, 5, tzinfo=UTC)
    states = {
        "dr": SourceState(last_attempt=now - timedelta(hours=2)),
        "testmedie": SourceState(last_attempt=now - timedelta(hours=5)),
    }
    fetcher = _fakes().make_fetcher_class(None)(config.settings.fetch, {}, {}, now)
    due, _ = pipeline.plan_sources(sources, states, now, None, fetcher, 30.0)
    ids = [s.id for s in due]
    # Aldrig forsøgte først, så den ældste, så den nyeste; søgning altid til sidst
    assert ids.index("testmedie") < ids.index("dr")
    assert all(ids.index(x) < ids.index("testmedie") for x in ("testorg", "affaldsselskab", "udateret"))
    assert ids[-2:] == ["bing-news", "google-news"]


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


def test_processor_sets_places(env):
    from affaldsfeed.collect import RawEntry
    from affaldsfeed.config import load_sources

    sources = load_sources(env.sources)
    cfg = load_config(env.config)
    cfg.publishers.append(cfg.publishers[0].model_copy(
        update={"id": "nfs", "name": "Nyborg Forsyning", "category": "kommunal", "domains": ["nfs.dk"],
                "basis": "offentlig", "places": ["k:nyborg"]}))
    now = datetime(2026, 10, 7, 8, tzinfo=UTC)
    testmedie = next(s for s in sources if s.id == "testmedie")
    bing = next(s for s in sources if s.id == "bing-news")

    def raw(source_id: str, title: str, teaser: str = "", lang: str = "da", via: str = "feed") -> RawEntry:
        url = "https://x.dk/" + "".join(ch for ch in title.lower() if ch.isascii() and ch.isalnum())
        return RawEntry(source_id, url, title, teaser, now - timedelta(hours=2), "kilde", lang, [], None, None, via)

    proc = pipeline.Processor(cfg, sources, now, {}, set())
    out = proc.process(testmedie, [
        raw("testmedie", "Ny genbrugsplads i Ullerslev åbner", "Nyborg Kommune står for driften af affaldet."),
        raw("testmedie", "Aarhus Universitet forsker i affald og plast"),
        raw("testmedie", "New recycling centre for waste opens in Nyborg", lang="en"),
    ], first_run=False)
    by_title = {c.title: c for c in out.new}
    assert by_title["Ny genbrugsplads i Ullerslev åbner"].places == ["k:nyborg", "b:ullerslev"]
    assert by_title["Aarhus Universitet forsker i affald og plast"].places == []
    assert by_title["New recycling centre for waste opens in Nyborg"].places == []

    # Søgefund krediteres udgiveren og får dens faste steder
    out = proc.process(bing, [raw("nfs", "Ny ordning for haveaffald fra januar", via="search")], first_run=False)
    assert out.new[0].source == "nfs" and out.new[0].places == ["k:nyborg"]


def _old_cand(slug: str, title: str, days_ago: float, source: str = "testmedie", **kw):
    """En gemt kandidat fra en tidligere kørsel (fx før stedmærkningen fandtes)."""
    from affaldsfeed.models import Candidate

    t = datetime(2026, 10, 7, 8, 5, tzinfo=UTC) - timedelta(days=days_ago)
    url = f"https://gammel.dk/{slug}"
    return Candidate(id=f"{slug:x<12}"[:12], url=url, title=title, source=source, published=t,
                     date_quality="kilde", first_seen=t, why={"filter": "normal", "score": 4, "decision": "vis"},
                     **kw)


def test_run_refreshes_places_of_old_candidates(env, monkeypatch, caplog):
    """run genberegner regelmærkerne for danske kandidater i vinduet med den aktuelle geografi."""
    caplog.set_level(logging.INFO)
    before = [
        _old_cand("odense", "Ny genbrugsplads åbner i Odense til foråret", 10),         # fundet før steder
        _old_cand("forsvundet", "Kommunerne skal sortere mere affald", 12, places=["b:findes-ikke"]),
        _old_cand("selskab", "Ny ordning for haveaffald", 20, source="affaldsselskab"),  # fast k:nyborg
        _old_cand("udenfor", "Ny genbrugsplads åbner i Aarhus", 70),                    # uden for vinduet
        _old_cand("engelsk", "New recycling centre opens in Odense", 5, lang="en"),
        _old_cand("uaendret", "Affald i Svendborg", 3, places=["k:svendborg", "b:svendborg"]),
    ]
    store.save_candidates(before)
    mtimes = {f.name: f.stat().st_mtime_ns for f in paths.CANDIDATES_DIR.iterdir()}

    # --dry-run beregner, men gemmer intet
    code, _ = _run(monkeypatch, dry_run=True)
    assert code == 0
    assert {c.id: c.places for c in store.load_candidates()} == {c.id: c.places for c in before}
    assert "danske kandidater i vinduet (fra 2026-08-08): 3 ændret" in caplog.text  # inkl. nye fra kørslen

    code, _ = _run(monkeypatch)
    assert code == 0
    got = {c.title: c.places for c in store.load_candidates()}
    assert got["Ny genbrugsplads åbner i Odense til foråret"] == ["k:odense", "b:odense"]
    assert got["Kommunerne skal sortere mere affald"] == []
    assert got["Ny ordning for haveaffald"] == ["k:nyborg"]
    assert got["Ny genbrugsplads åbner i Aarhus"] == []  # uden for vinduet: urørt
    assert got["New recycling centre opens in Odense"] == []  # kun danske tekster
    assert got["Affald i Svendborg"] == ["k:svendborg", "b:svendborg"]
    # Måneden uden ændringer (juli) skrives ikke om
    assert paths.CANDIDATES_DIR.joinpath("2026-07.jsonl").stat().st_mtime_ns == mtimes["2026-07.jsonl"]

    # Næste kørsel: intet at ændre
    caplog.clear()
    code, _ = _run(monkeypatch, now=LATER)
    assert code == 0 and "): 0 ændret" in caplog.text


def test_run_does_not_clear_places_without_geography(env, monkeypatch, caplog):
    store.save_candidates([_old_cand("odense", "Ny genbrugsplads åbner i Odense", 10, places=["k:odense", "b:odense"])])
    (env.config / "geografi.yaml").write_text("regioner: [ikke gyldig]\n", encoding="utf-8")
    caplog.set_level(logging.INFO)
    code, _ = _run(monkeypatch)
    assert code == 0
    assert "stedmærkningen er slået fra" in caplog.text
    assert "Steder genberegnet for 0 danske kandidater" in caplog.text
    old = next(c for c in store.load_candidates() if c.title == "Ny genbrugsplads åbner i Odense")
    assert old.places == ["k:odense", "b:odense"]  # en midlertidig fejl i geografien sletter ikke stederne


def test_run_ignores_unknown_fixed_places(env, monkeypatch, caplog):
    text = env.sources.read_text(encoding="utf-8").replace('  places: ["k:nyborg"]\n',
                                                           '  places: ["k:nyborg", "k:findes-ikke"]\n')
    env.sources.write_text(text, encoding="utf-8")
    medier = (env.config / "medier.yaml").read_text(encoding="utf-8")
    medier = medier.replace("  domains: [tv2.dk]\n", "  domains: [tv2.dk]\n  places: [b:atlantis]\n")
    (env.config / "medier.yaml").write_text(medier, encoding="utf-8")
    caplog.set_level(logging.INFO)
    code, _ = _run(monkeypatch)
    assert code == 0
    assert ("sources.yaml: affaldsselskab: places: ukendt sted-id k:findes-ikke (se config/geografi.yaml) "
            "(check fejler; id'et ignoreres)") in caplog.text
    assert "medier.yaml: tv2: places: ukendt sted-id b:atlantis" in caplog.text
    cands = _by_title(_cands())
    assert cands["Ny ordning for madaffald & plast fra 1. januar"].places == ["k:nyborg"]
    assert cands["Nye affaldsregler får stik modsat effekt"].places == []  # tv2's ukendte sted er droppet


def test_run_keeps_month_file_it_cannot_read(env, monkeypatch, caplog):
    """Efter en tilbagerulning af koden: run skriver ikke månedsfilen om og logger de nye kandidater som fejl."""
    path = paths.CANDIDATES_DIR / "2026-10.jsonl"
    path.parent.mkdir(parents=True)
    line = _old_cand("fremtid", "Linje fra en nyere version", 1).model_dump(mode="json") | {"nyt_felt": True}
    text = json.dumps(line, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")
    caplog.set_level(logging.INFO)
    code, _ = _run(monkeypatch)
    assert code == 0
    assert path.read_text(encoding="utf-8") == text
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1 and "candidates/2026-10.jsonl: 1 linjer kan ikke læses" in errors[0]
    assert "10 nye eller ændrede poster for måneden gemmes ikke" in errors[0]


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
    assert st.last_attempt == now and st.since == date(2026, 10, 7)
    # Svarer, men ingen indslag: tavs først, når kilden er fulgt i 30 dage
    assert not silent(st, date(2026, 10, 7))
    assert not silent(st, date(2026, 11, 5))
    assert silent(st, date(2026, 11, 6))
    assert not silent(st.model_copy(update={"items_30d": 2}), date(2026, 11, 6))
    assert not silent(st.model_copy(update={"since": None}), date(2026, 11, 6))  # ukendt start: aldrig tavs
    later = record_result(st, True, None, now + timedelta(days=40), s)
    assert later.since == date(2026, 10, 7)  # startdatoen flytter sig ikke
    st = st.model_copy(update={"since": date(2026, 9, 1)})
    for i in range(1, 6):
        st = record_result(st, False, "HTTP 500", now, s)
        assert st.fails == i
        assert st.health == ("roed" if i >= 5 else "gul")
    assert st.last_ok == date(2026, 10, 7) and st.last_error == "HTTP 500"
    assert not silent(st, date(2026, 11, 6))
    st = record_result(st, True, None, now, s)
    assert st.fails == 0 and st.last_error is None and st.health == "groen" and st.since == date(2026, 9, 1)


def test_run_fetches_logos_after_sources_but_not_in_dry_run(env, monkeypatch):
    """Logoerne (KONTRAKTER §6.4) hentes efter kilderne; en prøvekørsel henter og skriver intet."""
    code, fake = _run(monkeypatch, dry_run=True)
    assert code == 0
    assert "https://www.testmedie.dk" not in {u for u, _ in fake.calls}
    assert not (paths.STATE_DIR / "logos.json").exists()

    icon = "https://www.testmedie.dk/favicon.ico"
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + b"IHDR" + (32).to_bytes(4, "big") * 2 + b"\x00" * 60
    routes = {**_fakes().DEFAULT_ROUTES, "https://www.testmedie.dk": 404, icon: (png, "image/png")}
    code, fake = _run(monkeypatch, routes=routes)
    assert code == 0
    urls = [u for u, _ in fake.calls]
    assert urls.index(icon) > urls.index("https://www.testmedie.dk/rss")  # efter kilderne
    state = json.loads((paths.STATE_DIR / "logos.json").read_text(encoding="utf-8"))
    assert state["testmedie"]["file"] == "testmedie.png"
    assert (paths.STATE_DIR / "logos" / "testmedie.png").read_bytes() == png


def test_run_fetches_a_logo_for_each_other_site_of_a_source(env, monkeypatch):
    """En kilde med domains på et andet site end forsiden får også et logo for det site (KONTRAKTER §6.4)."""
    text = env.sources.read_text(encoding="utf-8")
    env.sources.write_text(
        text.replace("  homepage: https://www.testmedie.dk\n",
                     "  homepage: https://www.testmedie.dk\n  domains: [testmedie-syd.dk, nyheder.testmedie.dk]\n", 1),
        encoding="utf-8",
    )
    code, fake = _run(monkeypatch)
    assert code == 0
    urls = [u for u, _ in fake.calls]
    assert "https://testmedie-syd.dk/" in urls  # et andet site
    assert all(urlsplit(u).hostname != "nyheder.testmedie.dk" for u in urls)  # samme site som forsiden
    state = json.loads((paths.STATE_DIR / "logos.json").read_text(encoding="utf-8"))
    assert state["testmedie--testmedie-syd-dk"]["error"] == "HTTP 404"


def test_http_cache_keeps_the_expanded_daily_sitemaps(env):
    """{dato} giver dagens og gårsdagens sitemap; deres ETags er gyldige, gamle dages fjernes (KONTRAKTER §5.6)."""
    config = load_config(paths.CONFIG_DIR)
    sources = [s.model_copy(update={"method": "sitemap", "feeds": ["https://www.testmedie.dk/sitemap/{dato}"]})
               if s.id == "testmedie" else s for s in load_sources(paths.SOURCES_FILE)]
    valid = pipeline._valid_cache_urls(sources, config, {}, datetime(2026, 10, 7, 22, 30, tzinfo=UTC))
    assert {"https://www.testmedie.dk/sitemap/2026-10-08", "https://www.testmedie.dk/sitemap/2026-10-07"} <= valid
    assert "https://www.testmedie.dk/sitemap/2026-10-06" not in valid
    assert "https://www.testmedie.dk/sitemap/{dato}" not in valid



# ── Bagudindsamling til window_start (KONTRAKTER §5.8) ─────


def test_window_since_and_needs_backfill():
    settings = load_config(paths.CONFIG_DIR).settings.model_copy(update={"window_start": None, "window_days": 60})
    now = datetime(2026, 10, 7, 8, 5, tzinfo=UTC)
    assert settings.window_since(now) == now - timedelta(days=60)
    assert not settings.needs_backfill(SourceState()) and not settings.needs_backfill(None)
    settings = settings.model_copy(update={"window_start": date(2026, 1, 1)})
    assert settings.window_since(now) == datetime(2025, 12, 31, 23, 0, tzinfo=UTC)  # midnat i København
    assert settings.needs_backfill(None) and settings.needs_backfill(SourceState(backfill_runs=3))
    assert not settings.needs_backfill(SourceState(backfilled_from=date(2026, 1, 1)))
    assert not settings.needs_backfill(SourceState(backfilled_from=date(2025, 6, 1)))  # hentet længere tilbage
    assert settings.needs_backfill(SourceState(backfilled_from=date(2026, 3, 1)))  # window_start er flyttet bagud


def test_forget_seen_keeps_only_urls_that_became_candidates():
    seen = {"a": {"k1": "2026-10-07", "x": "2026-10-07", "y": "2026-10-01"}, "b": {"z": "2026-10-07"}}
    assert pipeline.forget_seen(seen, "a", {"k1", "z"}) == 2
    assert seen == {"a": {"k1": "2026-10-07"}, "b": {"z": "2026-10-07"}}
    assert pipeline.forget_seen(seen, "ukendt", set()) == 0 and "ukendt" not in seen


def test_backfill_with_a_backlog_is_due_hourly_and_runs_after_the_others(env):
    config = load_config()
    settings = config.settings.model_copy(update={"window_start": date(2026, 1, 1)})
    sources = [s.model_copy(update={"every": 6}) if s.id == "testorg" else s for s in load_sources()]
    now = datetime(2026, 10, 7, 8, 5, tzinfo=UTC)
    hour_ago = now - timedelta(hours=1)
    done = {"backfilled_from": date(2026, 1, 1)}
    states = {
        "testorg": SourceState(last_attempt=now - timedelta(hours=3), backfill_runs=2),  # restkø: hver time
        "testmedie": SourceState(last_attempt=hour_ago, **done),
        "dr": SourceState(last_attempt=hour_ago - timedelta(minutes=5), **done),
        "affaldsselskab": SourceState(last_attempt=hour_ago, **done),
        "udateret": SourceState(last_attempt=hour_ago, **done),
    }
    fetcher = _fakes().make_fetcher_class(None)(config.settings.fetch, {}, {}, now)
    due, _ = pipeline.plan_sources(sources, states, now, None, fetcher, 30.0, settings.needs_backfill)
    ids = [s.id for s in due]
    assert "testorg" in ids and ids.index("testorg") > ids.index("dr")  # efter de andre feeds
    assert ids.index("testorg") < ids.index("bing-news")  # søgning stadig til sidst
    # Uden restkø gælder kildens egen takt (hver 6. time)
    states["testorg"] = SourceState(last_attempt=now - timedelta(hours=3))
    due, _ = pipeline.plan_sources(sources, states, now, None, fetcher, 30.0, settings.needs_backfill)
    assert "testorg" not in [s.id for s in due]


@pytest.fixture
def backfill_env(tmp_path, monkeypatch):
    return _fakes().setup_env(tmp_path, monkeypatch, window_start="2026-01-01")


def test_backfill_run_keeps_this_years_old_items_as_baseline(backfill_env, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.delitem(COLLECTORS, "oda")
    code, fake = _run(monkeypatch)
    assert code == 0
    assert all(cond is False for _, cond in fake.calls)  # ubetinget som en første kørsel
    cands = _by_title(_cands())
    old = cands["Gammel nyhed om affaldssortering i boligforeninger"]  # 28. juli: med, fordi feedet går til 1. januar
    assert old.baseline and old.published == datetime(2026, 7, 28, 6, 0, tzinfo=UTC)
    rejected = {r.title: r for r in store.load_rejected()}
    # Ældre end 14 dage og afvist af forfiltret: gemmes ikke som afvist (ellers fylder et år data/rejected/)
    assert "Gammel sportsnyhed om håndbold" not in rejected
    # Fra før 1. januar: hverken kandidat eller afvist
    assert "Meget gammel nyhed om affaldsgebyrer" not in cands and "Meget gammel nyhed om affaldsgebyrer" not in rejected
    assert rejected["Fodboldkamp aflyst i regnvejr"].why.decision == "afvist"  # nyt indslag: som altid
    states = store.load_source_states()
    assert states["testmedie"].backfilled_from == date(2026, 1, 1) and states["testmedie"].backfill_runs == 0
    assert "opdaterede, bagudindsamling (" in caplog.text

    # Næste kørsel er almindelig: betingede forespørgsler, og kun de udaterede indslag er nye (som altid)
    code, fake = _run(monkeypatch, now=LATER)
    assert code == 0
    assert [cond for u, cond in fake.calls if u == "https://www.testmedie.dk/rss"] == [True]
    new = [c for t, c in _by_title(_cands()).items() if t not in cands]
    assert new and all(c.date_quality == "fundet" and not c.baseline for c in new)


def test_backfill_is_not_finished_by_a_failing_run(backfill_env, monkeypatch):
    monkeypatch.delitem(COLLECTORS, "oda")
    routes = {**_fakes().DEFAULT_ROUTES, "https://www.testmedie.dk/rss": 500}
    assert _run(monkeypatch, routes=routes)[0] == 0
    state = store.load_source_states()["testmedie"]
    assert state.backfilled_from is None and state.backfill_runs == 0 and state.fails == 1
    assert _run(monkeypatch, now=LATER)[0] == 0  # kilden svarer igen: bagudindsamlingen gøres færdig
    assert store.load_source_states()["testmedie"].backfilled_from == date(2026, 1, 1)
    assert "Gammel nyhed om affaldssortering i boligforeninger" in _by_title(_cands())
