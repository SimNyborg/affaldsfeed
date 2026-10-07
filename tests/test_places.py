"""Stedmærkning (places.py, KONTRAKTER §4.1) med den rigtige geografi og rigtige danske overskrifter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from affaldsfeed.models import Geo, PlaceSettings, sort_places
from affaldsfeed.places import compile_places, match_places, place_names, rule_places

FIXTURES = Path(__file__).resolve().parent / "fixtures"

POSITIVE = [
    # kommune med "Kommune"-endelse giver kun kommunen
    ("Aarhus Kommune indfører ny ordning for madaffald", ["k:aarhus"]),
    ("Københavns Kommune hæver affaldsgebyret med 8 procent", ["k:koebenhavn"]),
    ("Bornholms Regionskommune sender indsamlingen i udbud", ["k:bornholm"]),
    ("Nyborg kommune vil have flere genbrugsbutikker", ["k:nyborg"]),
    ("Lyngby-Taarbæk Kommunes nye affaldsplan er klar", ["k:lyngby-taarbaek"]),
    # Vejen matches kun med "Kommune"
    ("Vejen Kommune vil indsamle tekstiler ved husstandene", ["k:vejen"]),
    # by med samme navn som kommunen giver både k: og b:, også i ejefald
    ("Nyborgs borgmester vil have mere genbrug", ["k:nyborg", "b:nyborg"]),
    ("Skraldebilerne kører nu med ti fraktioner i Odense", ["k:odense", "b:odense"]),
    # by alene
    ("Ny genbrugsplads i Ullerslev åbner til foråret", ["b:ullerslev"]),
    ("I Ullerslev åbner en ny genbrugsplads", ["b:ullerslev"]),
    # aa/å-varianter
    ("Skraldemænd i Århus nedlægger arbejdet", ["k:aarhus", "b:aarhus"]),
    ("Ny sorteringsordning i Grenå og Åbenrå", ["k:aabenraa", "b:aabenraa", "b:grenaa"]),
    ("Grenaa får ny genbrugsstation", ["b:grenaa"]),
    # længste navn vinder
    ("Ikast-Brande Kommune åbner ny genbrugsplads", ["k:ikast-brande"]),
    ("Ikast-Brande vil udbyde indsamlingen", ["k:ikast-brande"]),
    ("Ny genbrugsstation i Nykøbing Falster", ["b:nykoebing-f"]),
    ("Pant på flasker i Nykøbing F. og Nykøbing Mors", ["b:nykoebing-f", "b:nykoebing-m"]),
    ("Affaldsselskab på Lolland-Falster vil bygge sorteringsanlæg", ["r:sjaelland"]),
    # bindestreg er en ordgrænse
    ("Aarhus-firma vinder udbud om indsamling af affald", ["k:aarhus", "b:aarhus"]),
    # regioner og landsdele
    ("Region Syddanmark kortlægger forurening fra gamle lossepladser", ["r:syddanmark"]),
    ("Region Hovedstadens nye plan for jordforurening", ["r:hovedstaden"]),
    ("Affaldsselskaberne på Fyn vil bygge fælles anlæg", ["r:syddanmark"]),
    ("Erfaren skraldemand søges til rute i Nordsjælland", ["r:hovedstaden"]),
    # by i flere kommuner
    ("Ny genbrugsplads åbner i Hørsholm til foråret", ["k:hoersholm", "b:hoersholm"]),
    ("Madaffald bliver til biogas i Solrød", ["k:solroed", "b:solroed-strand"]),
]

NEGATIVE = [
    "Vejen til mindre affald går gennem bedre sortering",  # kun_med_kommune
    "Ørsted bygger nyt anlæg til CO2-fangst",  # udeladt by (firma)
    "Aarhus Universitet forsker i plast",  # institution
    "Københavns Universitet udvikler metode til at spore mikroplast",
    "Forskere på Aarhus Universitetshospital sorterer engangsplast",
    "Københavns Lufthavn vil genbruge mere affald fra flyene",
    "Minister Lars Aagaard vil have mere genanvendelse",  # efternavn (byen Ågård)
    "Lars Aagaard: Kommunerne skal sortere mere",
    "Ringe interesse for ny ordning for haveaffald",  # udeladt by (almindeligt ord)
    "Brande",  # udeladt by; kommunen hedder Ikast-Brande
    "Kommuner på Sjælland samarbejder om genbrug af byggematerialer",  # Sjælland er ikke en landsdel
    "Jylland får tre nye sorteringsanlæg",
    "Amager Bakke får CO2-fangst for 1,5 mia. kr.",
    "aarhus kommune",  # store og små bogstaver tæller
    "Aarhusianerne sorterer mest",  # ordgrænse
    "Regeringen vil ændre reglerne for affaldsgebyrer i kommunerne",
]


@pytest.mark.parametrize(("text", "expected"), POSITIVE)
def test_positive(text, expected, place_matcher):
    assert match_places(text, place_matcher) == expected


@pytest.mark.parametrize("text", NEGATIVE)
def test_negative(text, place_matcher):
    assert match_places(text, place_matcher) == []


def test_only_danish_texts(place_matcher):
    title, teaser = "New recycling centre opens in Nyborg", "Aarhus and Odense follow next year."
    assert rule_places(title, teaser, "en", [], place_matcher) == []
    assert rule_places(title, teaser, "sv", ["k:nyborg"], place_matcher) == ["k:nyborg"]  # afsenderens steder
    assert rule_places("Ny genbrugsplads i Nyborg", "", "da", [], place_matcher) == ["k:nyborg", "b:nyborg"]


def test_rule_places_title_teaser_and_source(place_matcher):
    got = rule_places(
        "Ny genbrugsplads i Ullerslev åbner til foråret",
        "Forsyningen bygger pladsen ved motorvejen. Region Syddanmark har givet tilladelse.",
        "da",
        ["k:nyborg"],
        place_matcher,
    )
    assert got == ["r:syddanmark", "k:nyborg", "b:ullerslev"]


def test_title_and_teaser_are_matched_separately(place_matcher):
    # "Nyborg" i slutningen af titlen må ikke ligne et fornavn foran byen i teaseren
    assert rule_places("Ny plan i Nyborg", "Ullerslev får ny plads", "da", [], place_matcher) == [
        "k:nyborg", "b:nyborg", "b:ullerslev"]


def test_max_eight_in_fixed_order(place_matcher):
    text = ("Odense, Svendborg, Nyborg, Kerteminde, Middelfart, Assens, Langeland og Ærø "
            "samarbejder med Region Syddanmark")
    got = match_places(text, place_matcher)
    assert len(got) == 8
    assert got == sort_places(got)
    assert got[0] == "r:syddanmark"
    assert all(p.startswith("k:") for p in got[1:])


def test_no_implicit_parents(place_matcher):
    assert match_places("Ny genbrugsplads i Ullerslev", place_matcher) == ["b:ullerslev"]


def test_whitespace_and_unicode_normalization(place_matcher):
    assert match_places("Ny plads i Nykøbing Falster", place_matcher) == ["b:nykoebing-f"]
    decomposed = "Århus Kommune"  # Å skrevet som A + ring
    assert match_places(decomposed, place_matcher) == ["k:aarhus"]


def test_institution_words_can_be_changed(geo):
    matcher = compile_places(geo, PlaceSettings(institution_words=[]))
    assert match_places("Aarhus Universitet forsker i plast", matcher) == ["k:aarhus", "b:aarhus"]
    matcher = compile_places(geo, PlaceSettings(institution_words=["Havn"]))
    assert match_places("Esbjerg Havn vil sortere mere", matcher) == []
    assert match_places("Esbjerg havnefront", matcher) == []  # ord, der begynder med ordet
    assert match_places("Esbjerg får ny havn", matcher) == ["k:esbjerg", "b:esbjerg"]


def test_person_guard_only_for_pure_town_names(place_matcher):
    # Navne, der også er kommuner, beholdes: "Kommunerne Nyborg og Kerteminde"
    assert match_places("Kommunerne Nyborg og Kerteminde vil udbyde sammen", place_matcher) == [
        "k:kerteminde", "k:nyborg", "b:kerteminde", "b:nyborg"]
    assert match_places("Både Ullerslev og Ørbæk får nye containere", place_matcher) == ["b:oerbaek"]


def test_place_names(geo):
    names = place_names(geo)
    assert names["Kongens Lyngby"] == {"k:lyngby-taarbaek"}
    assert names["Nyborg"] == {"k:nyborg", "b:nyborg"}
    assert names["Nyborg Kommune"] == {"k:nyborg"}
    assert names["Nyborgs"] == {"k:nyborg", "b:nyborg"}
    assert "Aarhuss" not in names  # intet ejefalds-s efter s
    assert "Vejen" not in names and names["Vejen Kommune"] == {"k:vejen"}
    assert names["Region Sjællands"] == {"r:sjaelland"}
    assert "Sjælland" not in names
    assert names["Bornholms regionskommune"] == {"k:bornholm"}


def test_empty_geography_matches_nothing():
    matcher = compile_places(Geo())
    assert match_places("Aarhus Kommune", matcher) == []
    assert rule_places("Aarhus Kommune", "", "da", ["k:aarhus"], matcher) == ["k:aarhus"]


def test_sort_places():
    assert sort_places(["b:a", "k:b", "r:c", "k:a", "b:a"]) == ["r:c", "k:a", "k:b", "b:a"]
    assert len(sort_places([f"k:{i:02d}" for i in range(12)])) == 8
    assert len(sort_places([f"k:{i:02d}" for i in range(12)], limit=None)) == 12


def test_geo_hierarchy(geo):
    assert geo.expand("k:nyborg") == {"k:nyborg", "r:syddanmark"}
    assert geo.expand("b:ullerslev") == {"b:ullerslev", "k:nyborg", "r:syddanmark"}
    assert geo.expand("r:midtjylland") == {"r:midtjylland"}
    assert geo.expand("b:findes-ikke") == {"b:findes-ikke"}
    ids = geo.place_ids()
    assert len([p for p in ids if p.startswith("r:")]) == 5
    assert len([p for p in ids if p.startswith("k:")]) == 98
    assert "b:ullerslev" in ids


def test_town_counts_only_under_its_primary_municipality(geo):
    # Hørsholm ligger også i Fredensborg og Rudersdal, Birkerød også i Allerød og Furesø (KONTRAKTER §9)
    hoersholm = next(t for t in geo.byer if t.id == "hoersholm")
    assert {"fredensborg", "rudersdal"} <= set(hoersholm.kommuner)
    assert geo.expand("b:hoersholm") == {"b:hoersholm", "k:hoersholm", "r:hovedstaden"}
    birkeroed = next(t for t in geo.byer if t.id == "birkeroed")
    assert len(birkeroed.kommuner) > 1
    assert geo.expand("b:birkeroed") == {"b:birkeroed", f"k:{birkeroed.kommune}", "r:hovedstaden"}


# ── Præcision (review af stedgenkendelsen): navne på noget andet end stedet ──

NOT_THE_PLACE = [
    # institutionsord fra settings.places.institution_words, også efter bindestreg
    ("Kommunerne på Københavns Vestegn vil have fælles affaldsordning", []),
    ("Københavns Vestegns Politi efterforsker ulovlig dumpning af asbest", []),
    ("Brand i genbrugscontainer på Gammel Køge Landevej", []),
    ("Lastbil med affald væltede på Roskilde Landevej i Albertslund", ["k:albertslund"]),
    ("Kø på Køge Bugt Motorvejen efter brand i skraldebil", []),
    ("Holbæk-motorvejen spærret efter uheld med affaldstransport", []),
    ("Aarhus-konventionen giver borgerne ret til miljøoplysninger om deponiet", []),
    ("Aalborg University: Danes sort better than expected", []),
    ("Københavns Amt havde mange gamle lossepladser", []),
    # byen Frederiksberg i Sorø er udeladt (hedder det samme som Frederiksberg Kommune)
    ("Frederiksberg Forsyning indfører ny ordning for madaffald", ["k:frederiksberg"]),
    ("Frederiksbergs borgmester vil have flere affaldsøer", ["k:frederiksberg"]),
    # efternavne og almindelige ord fra geografi_regler.yaml
    ("Malling: Vi når ikke målene for genanvendelse i 2030", []),
    ("Bække og åer er fulde af mikroplast", []),
    ("Ny genbrugsplads i Dronningmølle åbner til foråret", []),
    # stadig rigtige
    ("Aarhus-firma vinder udbud om indsamling af affald", ["k:aarhus", "b:aarhus"]),
    ("Ny genbrugsplads i Hornbæk åbner til foråret", ["b:hornbaek-dronningmoelle"]),
    ("Ny genbrugsplads i Beder åbner til foråret", ["b:beder-malling"]),
]


@pytest.mark.parametrize(("text", "expected"), NOT_THE_PLACE)
def test_names_of_other_things_are_not_places(text, expected, place_matcher):
    assert match_places(text, place_matcher) == expected


def test_person_guard_handles_initials(place_matcher):
    # Stenstrup er en by i Svendborg og et efternavn
    assert match_places("Borgmester Mette K. Stenstrup vil have flere genbrugspladser", place_matcher) == []
    assert match_places("Lars C. H. Stenstrup: Kommunerne mangler plads til jord", place_matcher) == []
    assert match_places("Ny genbrugsplads i Stenstrup", place_matcher) == ["b:stenstrup"]
    # Med en geografi, hvor Aagaard stadig er et bynavn (som før commit 7f17dfa)
    old = Geo.model_validate({
        "regioner": [{"id": "syddanmark", "kode": "083", "navn": "Region Syddanmark", "kort": "Syddanmark"}],
        "kommuner": [{"id": "vejle", "kode": "630", "navn": "Vejle Kommune", "kort": "Vejle",
                      "region": "syddanmark", "navne": ["Vejle"]}],
        "byer": [{"id": "aagaard", "navn": "Ågård", "navne": ["Ågård", "Aagaard"], "kommune": "vejle"}],
    })
    matcher = compile_places(old)
    assert match_places("Lars C. Aagaard vil have flere til at sortere madaffald", matcher) == []
    assert match_places("Lars Aagaard vil have flere til at sortere madaffald", matcher) == []
    assert match_places("Ny genbrugsplads i Ågård", matcher) == ["b:aagaard"]


def test_real_hits_are_unchanged(place_matcher):
    """Rigtige danske indslag fra data/ (review af stedgenkendelsen): 44 rigtige træf, 0 forkerte."""
    rows = json.loads((FIXTURES / "real_places.json").read_text(encoding="utf-8"))
    assert len(rows) == 40
    got = {r["id"]: rule_places(r["title"], r["teaser"], "da", [], place_matcher) for r in rows}
    assert got == {r["id"]: r["places"] for r in rows}
