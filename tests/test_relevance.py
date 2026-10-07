from __future__ import annotations

import pytest

from affaldsfeed.models import Keywords
from affaldsfeed.relevance import Prefilter, compile_patterns, find_hits

# ── Mønstermotor ───────────────────────────────────────────


@pytest.mark.parametrize(
    ("pattern", "regex"),
    [
        ("affald*", r"(?<!\w)affald\w*(?!\w)"),
        ("*affald*", r"\w*affald\w*"),
        ("pant", r"(?<!\w)pant(?!\w)"),
        ("*affald", r"\w*affald(?!\w)"),
        ("direkte genbrug", r"(?<!\w)direkte\s+genbrug(?!\w)"),
    ],
)
def test_compile_patterns_regex(pattern, regex):
    [(orig, rx)] = compile_patterns([pattern])
    assert orig == pattern
    assert rx.pattern == regex


def test_compile_patterns_skips_empty():
    assert compile_patterns(["", "  ", "*"]) == []


@pytest.mark.parametrize(
    ("pattern", "text", "hit"),
    [
        ("pant", "Pant på saftflasker", True),
        ("pant", "Rentestigning på pantebrev", False),
        ("ARGO", "ARGO bygger nyt anlæg", True),
        ("ARGO", "EU indfører embargo", False),
        ("affald*", "Affaldsgebyret stiger", True),
        ("affald*", "Restaffald hentes sjældnere", False),
        ("*affald*", "Restaffald hentes sjældnere", True),
        ("skrald", "Skrald fylder i gaderne", True),
        ("skrald", "Ny skraldespand", False),
        ("direkte genbrug", "Mere direkte  genbrug i Aarhus", True),
        ("direkte genbrug", "Direkte og genbrug", False),
        ("co2-afgift*", "CO2-afgiften rammer forbrændingen", True),
        ("genbrugsplads*", "GENBRUGSPLADSERNE holder åbent", True),
        ("waste", "Ministers wasted no time", False),
        ("waste", "New rules on packaging waste.", True),
        ("EPR", "EPR-ordningen for emballage", True),
        ("åbningstid*", "Ændrede åbningstider i julen", True),
    ],
)
def test_find_hits_word_boundaries(pattern, text, hit):
    assert bool(find_hits(text, compile_patterns([pattern]))) is hit


def test_find_hits_returns_patterns_in_order_without_duplicates():
    compiled = compile_patterns(["*affald*", "affaldsgebyr*", "pant", "*affald*"])
    assert find_hits("Affaldsgebyret og affald", compiled) == ["*affald*", "affaldsgebyr*"]
    assert find_hits("", compiled) == []


def test_find_hits_handles_decomposed_unicode():
    # "å" skrevet som a + kombinerende ring (NFD) skal stadig matche
    text = "Nye åbningstider"
    assert find_hits(text, compile_patterns(["åbningstid*"])) == ["åbningstid*"]


# ── Forfilter ──────────────────────────────────────────────


@pytest.fixture
def mini_keywords() -> Keywords:
    return Keywords(
        strong={"da": ["*affald*", "genbrugsplads*", "pant"], "en": ["waste"]},
        names=["ARC"],
        weak={"da": ["plast*", "*emballage*", "genbrug*"], "en": ["packaging"]},
        veto=["atomaffald*", "Nordic Waste"],
        service=["åbningstid*"],
    )


def test_score_title_teaser_weak(mini_keywords):
    pf = Prefilter(mini_keywords)
    # titel: *affald* (4), teaser: to forskellige stærke (2+2), svag plast (1)
    score, hits, title_hit = pf.score("Nyt om affald", "Genbrugspladser og pant. Plast.")
    assert title_hit
    assert score == 4 + 4 + 1
    assert "titel: *affald*" in hits
    assert "teaser: genbrugsplads*" in hits and "teaser: pant" in hits
    assert "svag: plast*" in hits


def test_score_teaser_capped_at_six():
    kw = Keywords(strong={"da": ["a", "b", "c", "d", "e"]})
    score, _, title_hit = Prefilter(kw).score("intet", "a b c d e")
    assert not title_hit
    assert score == 6


def test_weak_alone_gives_nothing(mini_keywords):
    score, hits, _ = Prefilter(mini_keywords).score("Ny plan for plast", "")
    assert score == 0
    assert hits == ["svag: plast*"]


def test_two_weak_words_count(mini_keywords):
    score, _, _ = Prefilter(mini_keywords).score("Plast og genbrug", "")
    assert score == 2


def test_weak_max_two(mini_keywords):
    score, _, _ = Prefilter(mini_keywords).score("Affald, plast, emballage og genbrug", "")
    assert score == 4 + 2


def test_weak_inside_strong_word_is_not_counted(mini_keywords):
    # "genbrugspladsen" er et stærkt ord; "genbrug*" må ikke også tælle som svagt ord
    score, hits, _ = Prefilter(mini_keywords).score("Ny genbrugspladsen åbner", "")
    assert score == 4
    assert not any(h.startswith("svag") for h in hits)


def test_name_counts_only_in_title(mini_keywords):
    pf = Prefilter(mini_keywords)
    assert pf.score("ARC sænker prisen", "")[0] == 4
    assert pf.score("Ny pris", "ARC sænker prisen")[0] == 0


@pytest.mark.parametrize(
    ("level", "title", "teaser", "decision"),
    [
        ("none", "Kommunen holder byfest", "", "vis"),
        ("normal", "Kommunen holder byfest", "", "afvist"),
        ("normal", "Nyt om affald", "", "vis"),
        ("normal", "Ny aftale", "Om genbrugspladser.", "graa"),
        ("normal", "Ny aftale", "Om genbrugspladser og pant.", "vis"),
        ("strict", "Ny aftale", "Om genbrugspladser og pant.", "graa"),
        ("strict", "Ny aftale", "Om genbrugspladser.", "graa"),
        ("strict", "Nyt om affald", "", "vis"),
        ("strict", "Kommunen holder byfest", "", "afvist"),
        ("strict", "Plast og emballage", "", "graa"),
    ],
)
def test_decision_table(mini_keywords, make_source, level, title, teaser, decision):
    why = Prefilter(mini_keywords).evaluate(title, teaser, make_source(filter=level))
    assert why.decision == decision
    assert why.filter == level
    if decision == "vis":
        assert why.reason is None
    else:
        assert why.reason


@pytest.mark.parametrize("level", ["none", "normal", "strict"])
def test_veto_wins_everywhere(mini_keywords, make_source, level):
    why = Prefilter(mini_keywords).evaluate(
        "Nordic Waste skal rydde op i affald", "", make_source(filter=level)
    )
    assert why.decision == "afvist"
    assert why.reason == "veto: Nordic Waste"
    assert why.hits[0] == "veto: Nordic Waste"


def test_veto_only_in_title(mini_keywords, make_source):
    why = Prefilter(mini_keywords).evaluate("Nyt om affald", "Ikke atomaffald", make_source(filter="normal"))
    assert why.decision == "vis"


def test_service_only_for_kommunal(mini_keywords, make_source):
    pf = Prefilter(mini_keywords)
    title = "Nye åbningstider på genbrugspladsen"
    kom = pf.evaluate(title, "", make_source(category="kommunal", filter="none"))
    assert kom.decision == "afvist"
    assert kom.reason.startswith("driftsbesked")
    med = pf.evaluate(title, "", make_source(category="nyhedsmedie", filter="normal"))
    assert med.decision == "vis"


def test_service_only_in_title(mini_keywords, make_source):
    why = Prefilter(mini_keywords).evaluate(
        "Ny genbrugsplads i byen", "Se åbningstider her", make_source(category="kommunal", filter="none")
    )
    assert why.decision == "vis"


def test_real_keywords_load(keywords):
    pf = Prefilter(keywords)
    assert pf.strong and pf.names and pf.weak and pf.veto and pf.service
