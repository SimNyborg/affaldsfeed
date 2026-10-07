"""Kører tests/cases.yaml mod forfilter, tema og genre med den rigtige config."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from affaldsfeed.classify import Classifier
from affaldsfeed.places import rule_places
from affaldsfeed.relevance import Prefilter

CASES_FILE = Path(__file__).resolve().parent / "cases.yaml"
DEFAULT_URL = "https://eksempel.dk/artikel/12345"
LEVELS = ("none", "normal", "strict")


def _load_cases() -> list[dict]:
    with CASES_FILE.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


CASES = _load_cases()


def test_cases_file_is_rich_enough():
    assert len(CASES) >= 140
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids)), "dublet-id i cases.yaml"
    langs = {c.get("lang", "da") for c in CASES}
    assert {"da", "en"} <= langs


def _source(case: dict, make_source, level: str):
    return make_source(
        category=case.get("category", "nyhedsmedie"),
        lang=case.get("lang", "da"),
        topics=case.get("source_topics", []),
        genre=case.get("source_genre", "nyhed"),
        filter=level,
    )


def test_cases_have_places():
    assert sum("places" in c["expect"] for c in CASES) >= 10


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_case(case, keywords, topics, genres, make_source, place_matcher):
    expect = case["expect"]
    if "places" in expect:
        got = rule_places(case["title"], case.get("teaser", ""), case.get("lang", "da"), [], place_matcher)
        assert got == expect["places"]
    prefilter = Prefilter(keywords)
    classifier = Classifier(topics, genres)
    title = case["title"]
    teaser = case.get("teaser", "")
    url = case.get("url", DEFAULT_URL)

    for level in LEVELS:
        if level not in expect:
            continue
        why = prefilter.evaluate(title, teaser, _source(case, make_source, level))
        assert why.decision == expect[level], f"{level}: {why.model_dump()}"

    source = _source(case, make_source, "normal")
    genre = classifier.genre_for(title, url, case.get("categories", []), source)
    if "genre" in expect:
        assert genre == expect["genre"]
    if "topics" in expect:
        got = classifier.topics_for(title, teaser, url, source, genre=genre)
        assert got == expect["topics"], classifier.topic_scores(title, teaser, url, source)
