"""Fælles fixtures. Holdes lille: rigtig config fra config/ og en fabrik til Source."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from affaldsfeed.models import Genre, Keywords, Source, Topic  # noqa: E402
from affaldsfeed.paths import CONFIG_DIR  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load_yaml(name: str):
    with (CONFIG_DIR / name).open(encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="session")
def keywords() -> Keywords:
    return Keywords(**_load_yaml("keywords.yaml"))


@pytest.fixture(scope="session")
def topics() -> list[Topic]:
    return [Topic(**t) for t in _load_yaml("topics.yaml")]


@pytest.fixture(scope="session")
def genres() -> list[Genre]:
    return [Genre(**g) for g in _load_yaml("genres.yaml")]


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
