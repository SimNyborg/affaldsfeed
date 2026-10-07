from __future__ import annotations

import pytest

from affaldsfeed.classify import Classifier, Overrides
from affaldsfeed.models import Genre, Override, Topic
from affaldsfeed.normalize import item_id

URL = "https://eksempel.dk/artikel/12345"


@pytest.fixture
def mini_topics() -> list[Topic]:
    return [
        Topic(
            id="sortering",
            name="Sortering",
            definition="",
            patterns=["sortering*", "tømning*", "skraldebil*"],
        ),
        Topic(id="gebyrer", name="Gebyrer", definition="", patterns=["affaldsgebyr*", "gebyr*", "takst*"]),
        Topic(id="forbraending", name="Forbrænding", definition="", patterns=["*forbrænding*"]),
        Topic(id="genanvendelse", name="Genanvendelse", definition="", patterns=["sorteringsanlæg*"]),
        Topic(id="regler", name="Regler", definition="", patterns=["bekendtgørelse*", "høring*"]),
    ]


@pytest.fixture
def mini_genres() -> list[Genre]:
    return [
        Genre(id="nyhed", label=""),
        Genre(id="debat", label="DEBAT", url_patterns=["/debat/"], title_prefixes=["Debat:", "Kronik:"]),
        Genre(id="pressemeddelelse", label="PRESSEMEDDELELSE", url_patterns=["/pressemeddelelse"]),
        Genre(
            id="analyse",
            label="ANALYSE OG RAPPORT",
            url_patterns=["/analyse/"],
            title_prefixes=["Ny rapport:"],
        ),
        Genre(
            id="hoering",
            label="HØRING OG REGLER",
            url_patterns=["/hoering"],
            title_prefixes=["Høring over", "Høring:"],
        ),
        Genre(id="folketing", label="FOLKETINGSSAG", url_patterns=["ft.dk/samling/"]),
    ]


@pytest.fixture
def clf(mini_topics, mini_genres) -> Classifier:
    return Classifier(mini_topics, mini_genres)


# ── Genre ──────────────────────────────────────────────────


def test_genre_source_wins(clf, make_source):
    src = make_source(genre="hoering")
    assert clf.genre_for("Debat: noget", "https://x.dk/debat/a", ["Debat"], src) == "hoering"


def test_genre_url_before_categories_and_title(clf, make_source):
    src = make_source()
    assert clf.genre_for("Ny rapport: x", "https://x.dk/debat/a", ["Analyse"], src) == "debat"


def test_genre_url_does_not_match_host(clf, make_source):
    # "/hoering" må ikke ramme værtsnavnet hoeringsportalen.dk
    assert clf.genre_for("Titel", "https://hoeringsportalen.dk/Hearing/1", [], make_source()) == "nyhed"


def test_genre_url_with_host_pattern(clf, make_source):
    url = "https://www.ft.dk/samling/20251/almdel/mof/spm/12/index.htm"
    assert clf.genre_for("Spørgsmål om affald", url, [], make_source()) == "folketing"


def test_genre_url_percent_encoded(mini_topics, make_source):
    genres = [Genre(id="nyhed", label=""), Genre(id="hoering", label="H", url_patterns=["/høring"])]
    c = Classifier(mini_topics, genres)
    assert c.genre_for("x", "https://x.dk/h%C3%B8ringer/123", [], make_source()) == "hoering"


@pytest.mark.parametrize(
    ("categories", "genre"),
    [
        (["Debat"], "debat"),
        (["Kronikker"], "debat"),
        (["Nyheder", "Analyser"], "analyse"),
        (["Nyheder, Pressemeddelelser"], "pressemeddelelse"),
        (["Høringer"], "hoering"),
        (["DEBAT"], "debat"),
        (["Nyheder"], "nyhed"),
        (["Affald"], "nyhed"),
        (["Debatten om affald"], "nyhed"),
    ],
)
def test_genre_from_rss_categories(clf, make_source, categories, genre):
    assert clf.genre_for("Titel", URL, categories, make_source()) == genre


@pytest.mark.parametrize(
    ("title", "genre"),
    [
        ("Debat: Gebyrerne er for høje", "debat"),
        ("KRONIK: Tænk cirkulært", "debat"),
        ("«Debat: Citat i titel»", "debat"),
        ("Ny rapport: Genanvendelsen stiger", "analyse"),
        ("Høring over ny bekendtgørelse", "hoering"),
        ("Høring overvejes i udvalget", "nyhed"),
        ("Debatten om affald raser", "nyhed"),
    ],
)
def test_genre_from_title_prefix(clf, make_source, title, genre):
    assert clf.genre_for(title, URL, [], make_source()) == genre


# ── Tema ───────────────────────────────────────────────────


def test_topics_title_beats_teaser(clf, make_source):
    # titel: gebyrer 3; teaser: sortering 1 → kun gebyrer
    assert clf.topics_for("Affaldsgebyret stiger", "Tømning bliver dyrere", URL, make_source()) == ["gebyrer"]


def test_topics_second_topic_needs_half_of_best(clf, make_source):
    # gebyrer 6 (affaldsgebyr*, takst*), sortering 3 → 3 ≥ 6/2 → begge
    got = clf.topics_for("Affaldsgebyret og taksten stiger ved hver tømning", "", URL, make_source())
    assert got == ["gebyrer", "sortering"]


def test_topics_second_topic_dropped_below_half(clf, make_source):
    # gebyrer 7 (2 titelhit + 1 teaserhit), sortering 3 → 3 < 3.5 → kun gebyrer
    got = clf.topics_for("Affaldsgebyret og taksten stiger ved hver tømning", "Nyt gebyr", URL, make_source())
    assert got == ["gebyrer"]


def test_topics_max_two(clf, make_source):
    got = clf.topics_for("Gebyr for tømning og bekendtgørelse om forbrænding", "", URL, make_source())
    assert len(got) == 2


def test_topics_url_hint_and_source_topics(clf, make_source):
    # teaser 1 + URL-hint 1 + kildens tema 1 = 3 → nok til et tema
    url = "https://x.dk/nyheder/affaldsforbraending-i-fremtiden"
    src = make_source(topics=["forbraending"])
    assert clf.topic_scores("Ny plan", "Om forbrænding", url, src)["forbraending"][0] == 3
    assert clf.topics_for("Ny plan", "Om forbrænding", url, src) == ["forbraending"]


def test_topics_url_hint_with_unicode_slug(clf, make_source):
    url = "https://x.dk/nyheder/affaldsforbr%C3%A6nding"
    assert clf.topic_scores("Ny plan", "", url, make_source())["forbraending"][0] == 1


def test_topics_fallback_to_source_topics(clf, make_source):
    src = make_source(topics=["gebyrer", "sortering", "regler"])
    assert clf.topics_for("Nyt kontrolrum indviet", "", URL, src) == ["gebyrer", "sortering"]


def test_topics_empty_without_hits(clf, make_source):
    assert clf.topics_for("Kommunen holder byfest", "", URL, make_source()) == []


def test_topics_tie_prefers_specific_pattern(clf, make_source):
    # sortering* og sorteringsanlæg* rammer begge; det mest specifikke mønster står først
    assert clf.topics_for("Nyt sorteringsanlæg i Roskilde", "", URL, make_source()) == [
        "genanvendelse",
        "sortering",
    ]


@pytest.mark.parametrize("genre", ["hoering", "folketing"])
def test_rule_genres_always_give_regler(clf, make_source, genre):
    src = make_source(genre=genre)
    assert clf.topics_for("Kommunen holder byfest", "", URL, src) == ["regler"]
    got = clf.topics_for("Affaldsgebyret og taksten stiger ved hver tømning", "", URL, src)
    assert got == ["gebyrer", "regler"]


def test_genre_argument_is_used(clf, make_source):
    # genre fra RSS-kategori gives udefra
    got = clf.topics_for("Affaldsgebyret stiger", "", URL, make_source(), genre="hoering")
    assert got == ["gebyrer", "regler"]
    assert clf.topics_for("Affaldsgebyret stiger", "", URL, make_source(), genre="debat") == ["gebyrer"]


def test_regler_not_duplicated(clf, make_source):
    got = clf.topics_for("Høring over ny bekendtgørelse", "", URL, make_source())
    assert got == ["regler"]


# ── Overrides ──────────────────────────────────────────────


def test_overrides_find_by_id_and_url():
    url = "https://www.altinget.dk/forsyning/artikel/123?utm_source=x"
    iid = item_id(url)
    ovs = [
        Override(match={"id": iid}, action="skjul"),
        Override(match={"url_regex": r"altinget\.dk/forsyning/"}, action="tema", value=["gebyrer"]),
        Override(match={"id": "000000000000"}, action="vis"),
        Override(
            match={"url_regex": r"^https://altinget\.dk/forsyning/artikel/123$"},
            action="genre",
            value="debat",
        ),
        Override(match={"id": iid, "url_regex": "andet-site"}, action="split"),
        Override(match={"url_regex": "("}, action="vis"),
        Override(match={"ukendt": "x"}, action="vis"),
    ]
    found = Overrides(ovs).find(iid, url)
    assert [o.action for o in found] == ["skjul", "tema", "genre"]


def test_overrides_empty():
    assert Overrides([]).find("abc", "https://x.dk") == []
