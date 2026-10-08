"""Test af config.py: indlæsning, validering, publisher_lookup og check-kommandoen."""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
from pathlib import Path

import pytest

from affaldsfeed import config as cfgmod
from affaldsfeed import fetch as fetchmod
from affaldsfeed.collect import COLLECTORS
from affaldsfeed.config import ConfigError, load_config, load_sources, main_check, publisher_lookup

FIXTURES = Path(__file__).resolve().parent / "fixtures"


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


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_load_sources_fixture():
    sources = load_sources(FIXTURES / "sources.yaml")
    ids = [s.id for s in sources]
    assert ids[:3] == ["google-news", "bing-news", "testmedie"]
    testorg = next(s for s in sources if s.id == "testorg")
    assert testorg.feeds == ["https://testorg.dk/atom.xml", "https://testorg.dk/ekstra.xml"]
    dr = next(s for s in sources if s.id == "dr")
    assert dr.feeds == ["https://www.dr.dk/nyheder/service/feeds/indland"]
    assert dr.every_hours == 1
    assert next(s for s in sources if s.id == "google-news").every_hours == 2


def test_load_sources_reports_all_errors_with_ids(tmp_path):
    p = _write(
        tmp_path / "sources.yaml",
        """
- id: dublet
  name: A
  category: fagmedie
  homepage: https://a.dk
  feeds: https://a.dk/rss
  basis: redaktionelt
  checked: 2026-10-07
- id: dublet
  name: B
  category: fagmedie
  homepage: https://b.dk
  feeds: https://b.dk/rss
  basis: redaktionelt
  checked: 2026-10-07
- id: mangler-basis
  name: C
  category: fagmedie
  homepage: https://c.dk
  feeds: https://c.dk/rss
  checked: 2026-10-07
- id: daarligt-regex
  name: D
  category: fagmedie
  homepage: https://d.dk
  method: sitemap
  feeds: https://d.dk/sitemap.xml
  match: "([a-z"
  basis: redaktionelt
  checked: 2026-10-07
- id: ukendt-tema
  name: E
  category: fagmedie
  homepage: https://e.dk
  feeds: https://e.dk/rss
  topics: [rumfart]
  basis: redaktionelt
  checked: 2026-10-07
""",
    )
    with pytest.raises(ConfigError) as exc:
        load_sources(p)
    msg = str(exc.value)
    assert "sources.yaml: dublet: id findes flere gange" in msg
    assert "sources.yaml: mangler-basis:" in msg and "basis" in msg
    assert "sources.yaml: daarligt-regex:" in msg
    assert "sources.yaml: ukendt-tema: topics.0" in msg


def test_load_sources_yaml_error(tmp_path):
    p = _write(tmp_path / "sources.yaml", "- id: a\n  name: [ikke lukket\n")
    with pytest.raises(ConfigError, match="sources.yaml: YAML-fejl"):
        load_sources(p)


def test_load_config(env):
    cfg = load_config(env.config)
    assert len(cfg.topics) == 13
    assert len(cfg.categories) == 8
    assert {g.id for g in cfg.genres} >= {"nyhed", "debat", "hoering"}
    assert [p.id for p in cfg.publishers] == ["tv2", "tv2-ostjylland"]
    assert cfg.search.queries and cfg.search.when == "2d"
    assert cfg.settings.fetch.user_agent.startswith("Affaldsfeed/")
    assert "Relevansprofil" in cfg.profile
    assert cfg.overrides == []


def test_load_config_without_medier_is_ok(env):
    (env.config / "medier.yaml").unlink()
    cfg = load_config(env.config)
    assert cfg.publishers == []


def test_load_config_bad_overrides_and_regex(env):
    _write(
        env.config / "overrides.yaml",
        """
- match: {id: "abc123abc123"}
  action: tema
  value: [ukendt]
- match: {url_regex: "(["}
  action: skjul
- match: {id: "def456def456"}
  action: genre
  value: roman
""",
    )
    genres = (env.config / "genres.yaml").read_text(encoding="utf-8")
    _write(env.config / "genres.yaml", genres.replace('"/debat/"', '"([debat"'))
    with pytest.raises(ConfigError) as exc:
        load_config(env.config)
    msg = str(exc.value)
    assert "overrides.yaml: abc123abc123: ukendt tema-id: ukendt" in msg
    assert "overrides.yaml: ([: ugyldigt url_regex" in msg
    assert "overrides.yaml: def456def456: ukendt genre-id: roman" in msg
    assert "genres.yaml: debat: ugyldigt regex" in msg


def test_load_config_missing_topic(env):
    text = (env.config / "topics.yaml").read_text(encoding="utf-8")
    start = text.index("- id: tekstiler")
    end = text.index("- id: byg_farligt")
    _write(env.config / "topics.yaml", text[:start] + text[end:])
    with pytest.raises(ConfigError, match="topics.yaml: mangler id'er: tekstiler"):
        load_config(env.config)


def test_publisher_lookup(env):
    sources = load_sources(env.sources)
    cfg = load_config(env.config)
    lookup = publisher_lookup(sources, cfg.publishers)
    assert lookup["testmedie.dk"] == "testmedie"
    assert lookup["dr.dk"] == "dr"
    assert lookup["tv2.dk"] == "tv2"
    assert lookup["tv2ostjylland.dk"] == "tv2-ostjylland"  # www. fjernes fra domains
    assert "news.google.com" not in lookup  # søgekilder er aldrig afsender
    assert "bing.com" not in lookup
    assert "planlagt.dk" not in lookup  # kun aktive kilder


def test_publisher_lookup_sources_win_over_medier(env):
    sources = load_sources(env.sources)
    cfg = load_config(env.config)
    clash = cfg.publishers[0].model_copy(update={"id": "andet", "domains": ["dr.dk"]})
    lookup = publisher_lookup(sources, [clash])
    assert lookup["dr.dk"] == "dr"


def test_main_check_ok(env, capsys):
    assert main_check(argparse.Namespace(fetch=None, explain=False)) == 0
    out = capsys.readouterr().out
    assert "OK: 9 kilder (8 aktive), 2 udgivere i medier.yaml" in out


def test_main_check_collision_between_sources_and_medier(env, capsys):
    with (env.config / "medier.yaml").open("a", encoding="utf-8") as f:
        f.write("\n- id: dr\n  name: DR igen\n  category: nyhedsmedie\n  domains: [dr.dk]\n  basis: redaktionelt\n")
    assert main_check(argparse.Namespace(fetch=None, explain=False)) == 1
    out = capsys.readouterr().out
    assert "FEJL medier.yaml: dr: id findes også i sources.yaml" in out


def test_main_check_reports_file_and_id(env, capsys):
    text = env.sources.read_text(encoding="utf-8").replace("category: organisation\n  homepage: https://testorg.dk", "category: forening\n  homepage: https://testorg.dk")
    _write(env.sources, text)
    assert main_check(argparse.Namespace(fetch=None, explain=False)) == 1
    out = capsys.readouterr().out
    assert "FEJL sources.yaml: testorg: category:" in out


def test_main_check_search_template_needs_q(env, capsys):
    text = env.sources.read_text(encoding="utf-8").replace("search?q={q}&format", "search?q=affald&format")
    _write(env.sources, text)
    assert main_check(argparse.Namespace(fetch=None, explain=False)) == 1
    assert "bing-news: søgeskabelonen mangler {q}" in capsys.readouterr().out


def test_main_check_date_template_only_for_sitemaps(env, capsys):
    text = env.sources.read_text(encoding="utf-8").replace("https://www.testmedie.dk/rss", "https://www.testmedie.dk/rss/{dato}")
    _write(env.sources, text)
    assert main_check(argparse.Namespace(fetch=None, explain=False)) == 1
    assert "testmedie: {dato} virker kun med method: sitemap" in capsys.readouterr().out


def test_main_check_fetch_prints_decisions_and_writes_nothing(env, monkeypatch, capsys):
    fake = _fakes().make_fetcher_class()
    monkeypatch.setattr(fetchmod, "Fetcher", fake)
    assert main_check(argparse.Namespace(fetch="testmedie", explain=True)) == 0
    out = capsys.readouterr().out
    assert "BEHOLDT" in out and "AFVIST" in out
    assert "Nye regler for affaldsgebyrer i kommunerne" in out
    assert "for gammel" in out
    assert "veto" in out
    # check --fetch henter altid ubetinget og skriver intet
    assert all(cond is False for _, cond in fake.calls)
    assert not env.data.exists() or not any(env.data.rglob("*.*"))


def test_main_check_fetch_unknown_and_phase2(env, monkeypatch, capsys):
    monkeypatch.setattr(fetchmod, "Fetcher", _fakes().make_fetcher_class())
    # Alle metoder er bygget; en metode uden indsamler simuleres for kilden "ventende" (oda)
    monkeypatch.delitem(COLLECTORS, "oda")
    assert main_check(argparse.Namespace(fetch="findes-ikke", explain=False)) == 1
    assert main_check(argparse.Namespace(fetch="ventende", explain=False)) == 1
    out = capsys.readouterr().out
    assert "ukendt kilde: findes-ikke" in out
    assert "fase 2" in out


def test_load_config_geography_and_short_names(env):
    cfg = load_config(env.config)
    assert [r.id for r in cfg.geo.regioner] == ["hovedstaden", "sjaelland", "syddanmark", "midtjylland",
                                                 "nordjylland"]
    assert len(cfg.geo.kommuner) == 98 and len(cfg.geo.byer) > 400
    assert {"r:syddanmark", "k:nyborg", "b:ullerslev"} <= cfg.geo.place_ids()
    topics = {t.id: t for t in cfg.topics}
    assert topics["genbrugspladser"].short == "Genbrugspladser og genbrug"
    assert topics["arbejdsmiljoe"].short == "Arbejdsmiljø"
    assert topics["sortering"].short is None
    assert all(len(t.short or t.name) <= cfgmod.TOPIC_UI_MAX for t in cfg.topics)
    assert cfg.settings.places.institution_words == [
        "Universit", "Lufthavn", "Vestegn", "Amt", "Landevej", "Bugt", "Motorvej", "konvention"]
    assert cfg.geo_errors == []


def test_missing_geography_is_only_a_warning(env, capsys):
    (env.config / "geografi.yaml").unlink()
    assert load_config(env.config).geo.place_ids() == set()
    _write(env.sources, env.sources.read_text(encoding="utf-8").replace('  places: ["k:nyborg"]\n', ""))
    assert main_check(argparse.Namespace(fetch=None, explain=False)) == 0
    out = capsys.readouterr().out
    assert "ADVARSEL geografi.yaml: filen findes ikke (ingen stedmærkning)" in out
    assert "geografi: 0 regioner, 0 kommuner, 0 byer" in out


GEO_BAD = """
regioner:
- {id: syddanmark, kode: 083, navn: Region Syddanmark, kort: Syddanmark}
- {id: syddanmark, kode: 084, navn: Region Igen, kort: Igen}
landsdele: {Fyn: syddanmark, Atlantis: ukendt}
kommuner:
- {id: nyborg, kode: '450', navn: Nyborg Kommune, kort: Nyborg, region: syddanmark, navne: [Nyborg]}
- {id: odense, kode: '461', navn: Odense Kommune, kort: Odense, region: midtjylland, navne: [Odense]}
byer:
- {id: ullerslev, navn: Ullerslev, navne: [Ullerslev], kommune: nyborg, kommuner: [kerteminde, nyborg]}
- {id: odense, navn: Odense, navne: [Odense], kommune: odense, kommuner: [nyborg]}
"""


def test_geography_errors_only_fail_check(env, capsys, caplog):
    _write(env.config / "geografi.yaml", GEO_BAD)
    # Ved kørsel: fejlen logges, og geografien er tom (ingen stedmærkning), men intet stopper
    with caplog.at_level(logging.ERROR, logger="affaldsfeed.config"):
        cfg = load_config(env.config)
    assert cfg.geo.place_ids() == set() and len(cfg.geo_errors) == 5
    assert "geografi.yaml er ugyldig, så stedmærkningen er slået fra" in caplog.text
    # check fejler stadig
    assert main_check(argparse.Namespace(fetch=None, explain=False)) == 1
    out = capsys.readouterr().out
    for msg in (
        "geografi.yaml: regioner: syddanmark: id findes flere gange",
        "geografi.yaml: kommuner: odense: ukendt region midtjylland",
        "geografi.yaml: byer: ullerslev: ukendt kommune kerteminde",
        "geografi.yaml: byer: odense: kommune odense står ikke i kommuner",
        "geografi.yaml: landsdele: Atlantis: ukendt region ukendt",
    ):
        assert f"FEJL {msg}" in out


def test_geography_schema_errors(env, capsys):
    _write(env.config / "geografi.yaml", "regioner:\n- {id: Syd Danmark, kode: '083', navn: Region Syd}\n")
    assert load_config(env.config).geo.place_ids() == set()
    assert main_check(argparse.Namespace(fetch=None, explain=False)) == 1
    out = capsys.readouterr().out
    assert "FEJL geografi.yaml: -: regioner.0.id: String should match pattern" in out
    assert "FEJL geografi.yaml: -: regioner.0.kort: Field required" in out


def test_invalid_geography_does_not_stop_commands(env, monkeypatch, tmp_path, capsys, caplog):
    """run, pending, validate-judgments, heartbeat, overview-input og export kører videre med tom geografi."""
    from affaldsfeed import export, judgments, overview, pipeline, store

    _write(env.config / "geografi.yaml", GEO_BAD)
    with (env.config / "medier.yaml").open("a", encoding="utf-8") as f:
        f.write("\n- id: lokalt-selskab\n  name: Lokalt selskab\n  category: kommunal\n  domains: [lokalt.dk]\n"
                "  basis: offentlig\n  places: [k:findes-ikke]\n")
    monkeypatch.setattr(pipeline, "Fetcher", _fakes().make_fetcher_class())
    now = "2026-10-07T08:05:00Z"
    ns = argparse.Namespace
    caplog.set_level(logging.INFO)
    assert pipeline.main_run(ns(only=None, dry_run=False, now=now)) == 0
    assert "stedmærkningen er slået fra" in caplog.text
    cands = store.load_candidates()
    assert cands and all(c.places == [] for c in cands)  # heller ikke affaldsselskabets faste k:nyborg
    capsys.readouterr()
    assert judgments.main_pending(ns(max=200, hours=72, now=now)) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["pending"] and out["places_help"]["kommuner"] == []
    assert judgments.main_validate(ns(file=None)) == 0
    assert judgments.main_heartbeat(ns(now=now)) == 0
    assert overview.main_overview_input(ns(period="dag", now=now)) == 0
    assert export.main_export(ns(out=str(tmp_path / "ud"), now=now)) == 0
    feed = json.loads((tmp_path / "ud" / "data" / "feed.json").read_text(encoding="utf-8"))
    assert feed["geo"] is None
    capsys.readouterr()
    assert main_check(ns(fetch=None, explain=False)) == 1


def test_places_on_sources_and_medier(env, capsys):
    text = env.sources.read_text(encoding="utf-8")
    text = text.replace('  places: ["k:nyborg"]\n', '  places: ["k:nyborg", "b:atlantis"]\n')
    text = text.replace("  homepage: https://www.testmedie.dk\n",
                        "  homepage: https://www.testmedie.dk\n  places: [r:syddanmark]\n")
    _write(env.sources, text)
    with (env.config / "medier.yaml").open("a", encoding="utf-8") as f:
        f.write("\n- id: lokalt-selskab\n  name: Lokalt selskab\n  category: kommunal\n  domains: [lokalt.dk]\n"
                "  basis: offentlig\n  places: [k:odense, k:findes-ikke]\n")
    # Ukendte sted-id'er tjekkes i cross_check: check fejler, men konfigurationen kan indlæses
    cfg = load_config(env.config)
    assert next(p for p in cfg.publishers if p.id == "lokalt-selskab").places == ["k:findes-ikke", "k:odense"]
    errors, _ = cfgmod.cross_check(load_sources(env.sources), cfg)
    assert errors == [
        "sources.yaml: affaldsselskab: places: ukendt sted-id b:atlantis (se config/geografi.yaml)",
        "medier.yaml: lokalt-selskab: places: ukendt sted-id k:findes-ikke (se config/geografi.yaml)",
    ]
    assert main_check(argparse.Namespace(fetch=None, explain=False)) == 1
    out = capsys.readouterr().out
    assert "FEJL medier.yaml: lokalt-selskab: places: ukendt sted-id k:findes-ikke" in out
    assert "FEJL sources.yaml: affaldsselskab: places: ukendt sted-id b:atlantis" in out
    assert "k:odense" not in out
    assert "ADVARSEL sources.yaml: testmedie: places bruges kun til afsendere med fast geografi" in out


def test_places_format_is_validated(tmp_path):
    p = _write(tmp_path / "sources.yaml", """
- id: selskab
  name: Selskab
  category: kommunal
  homepage: https://selskab.dk
  feeds: https://selskab.dk/rss
  places: [nyborg]
  basis: offentlig
  checked: 2026-10-07
""")
    with pytest.raises(ConfigError) as exc:
        load_sources(p)
    assert ("sources.yaml: selskab: places: ugyldigt sted-id 'nyborg': skriv r:<region>, k:<kommune> eller b:<by> "
            "med små bogstaver og æ→ae, ø→oe, å→aa (fx k:koebenhavn)") in str(exc.value)


def test_long_topic_name_is_a_warning(env, capsys):
    text = (env.config / "topics.yaml").read_text(encoding="utf-8").replace("  short: Arbejdsmiljø\n", "")
    _write(env.config / "topics.yaml", text)
    assert main_check(argparse.Namespace(fetch=None, explain=False)) == 0
    out = capsys.readouterr().out
    assert ("ADVARSEL topics.yaml: arbejdsmiljoe: navnet i brugerfladen er 27 tegn (højst 26), "
            "tilføj eller forkort short: Arbejdsmiljø og renovatører") in out


def test_cross_check_warns_on_shared_host(env):
    sources = load_sources(env.sources)
    cfg = load_config(env.config)
    extra = sources[2].model_copy(update={"id": "testmedie-2"})
    errors, warnings = cfgmod.cross_check([*sources, extra], cfg)
    assert not errors
    assert any("testmedie-2: værten testmedie.dk bruges også af testmedie" in w for w in warnings)


def test_cross_check_replaces(env):
    sources = load_sources(env.sources)
    cfg = load_config(env.config)
    pub = cfg.publishers[0].id
    ok = sources[2].model_copy(update={"id": "ny-kilde", "replaces": ["nedlagt-dk"]})
    errors, _ = cfgmod.cross_check([*sources, ok], cfg)
    assert not errors
    still_there = sources[2].model_copy(update={"id": "ny-kilde", "replaces": [pub, sources[3].id]})
    errors, _ = cfgmod.cross_check([*sources, still_there], cfg)
    assert any(f"replaces nævner {pub}, som stadig findes i medier.yaml" in e for e in errors)
    assert any(f"replaces nævner {sources[3].id}, som stadig findes i sources.yaml" in e for e in errors)
    twice = sources[2].model_copy(update={"id": "ny-kilde-2", "replaces": ["nedlagt-dk"]})
    errors, _ = cfgmod.cross_check([*sources, ok, twice], cfg)
    assert any("som ny-kilde allerede overtager" in e for e in errors)
