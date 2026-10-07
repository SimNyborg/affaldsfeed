"""Fælles fixtures. Holdes lille: rigtig config fra config/ og en fabrik til Source."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from affaldsfeed.models import Genre, Geo, Keywords, Settings, Source, Topic  # noqa: E402
from affaldsfeed.paths import CONFIG_DIR  # noqa: E402
from affaldsfeed.places import PlaceMatcher, compile_places  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load_yaml(name: str):
    with (CONFIG_DIR / name).open(encoding="utf-8") as f:
        return yaml.load(f, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))


def build_tool():
    """tools/build_geografi.py som modul (samme modulnavn som i test_build_geografi.py)."""
    name = "affaldsfeed_tools_build_geografi"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / "build_geografi.py")
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return sys.modules[name]


def geo_with_current_rules(data: dict, rules: dict) -> Geo:
    """Geografien, som "Byg geografi" vil bygge den med de nuværende regler for byer.

    config/geografi.yaml bygges først igen i GitHub Actions, når reglerne er på main. Reglerne for byer
    (ignorer_byer, byer_ekstra_navne og byer med en anden kommunes navn) anvendes derfor også her; er
    filen allerede bygget med dem, ændrer det intet.
    """
    towns, _ = build_tool().town_rules(data["byer"], data["kommuner"], rules)
    return Geo.model_validate({**data, "byer": towns})


@pytest.fixture(scope="session")
def keywords() -> Keywords:
    return Keywords(**_load_yaml("keywords.yaml"))


@pytest.fixture(scope="session")
def topics() -> list[Topic]:
    return [Topic(**t) for t in _load_yaml("topics.yaml")]


@pytest.fixture(scope="session")
def genres() -> list[Genre]:
    return [Genre(**g) for g in _load_yaml("genres.yaml")]


@pytest.fixture(scope="session")
def geo() -> Geo:
    """Den rigtige geografi fra config/geografi.yaml med de nuværende regler for byer (geo_with_current_rules)."""
    return geo_with_current_rules(_load_yaml("geografi.yaml"), _load_yaml("geografi_regler.yaml"))


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings.model_validate(_load_yaml("settings.yaml"))


@pytest.fixture(scope="session")
def place_matcher(geo, settings) -> PlaceMatcher:
    """Matcheren som i drift: geografien og settings.places fra config/."""
    return compile_places(geo, settings.places)


@pytest.fixture
def make_source():
    """Fabrik: make_source(id="x", category="kommunal", filter="strict", …) -> Source."""

    def _make(**kw) -> Source:
        data = {
            "id": "test-kilde",
            "name": "Testkilde",
            "category": "nyhedsmedie",
            "homepage": "https://eksempel.dk",
            "feeds": ["https://eksempel.dk/rss"],
            "basis": "redaktionelt",
            "checked": date(2026, 10, 7),
        }
        data.update(kw)
        return Source(**data)

    return _make
