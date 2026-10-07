"""Test af config.py: indlæsning, validering, publisher_lookup og check-kommandoen."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import pytest

from affaldsfeed import config as cfgmod
from affaldsfeed import fetch as fetchmod
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
    assert main_check(argparse.Namespace(fetch="findes-ikke", explain=False)) == 1
    assert main_check(argparse.Namespace(fetch="ventende", explain=False)) == 1
    out = capsys.readouterr().out
    assert "ukendt kilde: findes-ikke" in out
    assert "fase 2" in out


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
