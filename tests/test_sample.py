"""examples/feed.sample.json følger kontrakten (KONTRAKTER §8-9) og valideres af modellerne."""

from __future__ import annotations

import json

import pytest

from affaldsfeed import paths
from affaldsfeed.config import load_config
from affaldsfeed.export import FEED_VERSION, _sort_items, geo_block
from affaldsfeed.models import DisplayItem, Feed
from affaldsfeed.places import compile_places, rule_places

SAMPLE = paths.EXAMPLES_DIR / "feed.sample.json"


@pytest.fixture(scope="module")
def raw() -> dict:
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def feed(raw) -> Feed:
    return Feed.model_validate(raw)


@pytest.fixture(scope="module")
def config():
    return load_config()


def selected(geo, item: DisplayItem, chosen: set[str]) -> bool:
    """Stedfiltret som i KONTRAKTER §9: indslagets steder udvides med forældre og sammenlignes med valget."""
    expanded = set().union(*(geo.expand(p) for p in item.places)) if item.places else set()
    return bool(expanded & chosen)


def test_sample_is_a_valid_feed(raw, feed):
    assert list(raw) == ["version", "generated", "window_days", "mode", "last_judgment", "categories", "topics",
                         "genres", "sources", "geo", "overview", "items"]
    assert feed.version == FEED_VERSION
    assert all(list(it) == list(DisplayItem.model_fields) for it in raw["items"])
    assert [it.id for it in _sort_items(feed.items)] == [it.id for it in feed.items]
    assert SAMPLE.read_text(encoding="utf-8") == json.dumps(raw, ensure_ascii=False, indent=1) + "\n"


def test_sample_topics_follow_config(feed, config):
    assert [t.model_dump() for t in feed.topics] == [
        {"id": t.id, "name": t.name, "short": t.short, "definition": t.definition} for t in config.topics
    ]


def test_sample_geo_is_what_export_would_write(raw, feed, config):
    assert raw["geo"] == geo_block(config.geo, feed.items)
    assert len(feed.geo.regioner) == 5 and len(feed.geo.kommuner) == 98
    assert 0 < len(feed.geo.byer) < 20  # kun byer, som indslagene nævner


def test_sample_sources_cover_items(feed):
    ids = {s.id for s in feed.sources}
    assert {it.source for it in feed.items} <= ids
    assert {a.source for it in feed.items for a in it.also} <= ids


def test_sample_places_are_realistic(feed, config):
    geo = config.geo
    with_places = [it for it in feed.items if it.places]
    assert 8 <= len(with_places) <= len(feed.items) // 2  # mange nationale indslag uden steder
    by_title = {it.title: it for it in feed.items}
    cat = {s.id: s.category for s in feed.sources}

    nyborg = by_title["Ny genbrugsplads i Ullerslev åbner til foråret"]
    assert nyborg.places == ["k:nyborg", "b:ullerslev"] and cat[nyborg.source] == "kommunal"
    assert by_title["Ny ordning for haveaffald fra 1. januar"].places == ["k:nyborg"]
    assert by_title["Aarhus Kommune indfører indsamling af tekstiler ved etageboliger"].places == ["k:aarhus"]
    region = by_title["Region Syddanmark vil undersøge 140 gamle lossepladser for forurening"]
    assert region.places == ["r:syddanmark"]
    hoersholm = by_title["Ny genbrugsstation i Hørsholm skal have byttemarked"]
    assert "b:hoersholm" in hoersholm.places
    # Institutionsnavne giver ingen steder
    assert by_title["Forskere: Biopulp fra madaffald kan give mere biogas"].places == []

    # En national historie, hvor kun et indslag i also er lokalt
    matcher = compile_places(geo, config.settings.places)
    story = next(it for it in feed.items if it.also and it.places
                 and not rule_places(it.title, it.teaser, it.lang, [], matcher))
    assert any(rule_places(a.title, "", "da", [], matcher) for a in story.also)

    # Filtersemantikken fra KONTRAKTER §9
    def shown(*chosen: str) -> set[str]:
        return {it.title for it in feed.items if selected(geo, it, set(chosen))}

    assert {nyborg.title, region.title} <= shown("r:syddanmark")
    assert nyborg.title in shown("k:nyborg") and region.title not in shown("k:nyborg")
    assert shown("b:ullerslev") == {nyborg.title}
    # En by tæller kun under sin primære kommune: Hørsholm ligger også i Fredensborg og Rudersdal
    assert {"fredensborg", "rudersdal"} <= set(next(t for t in feed.geo.byer if t.id == "hoersholm").kommuner)
    assert hoersholm.title in shown("k:hoersholm") and hoersholm.title in shown("r:hovedstaden")
    assert hoersholm.title not in shown("k:fredensborg") and hoersholm.title not in shown("k:rudersdal")
    assert shown("k:nyborg", "k:aarhus") == shown("k:nyborg") | shown("k:aarhus")
    # Alle steder ligger i en region, og landsdækkende indslag vises ikke, når et sted er valgt
    assert shown(*(f"r:{r.id}" for r in geo.regioner)) == {it.title for it in with_places}
