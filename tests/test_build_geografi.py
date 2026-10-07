"""Tests for tools/build_geografi.py med syntetiske DST-svar. Intet netværk."""

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent


def _load():
    name = "affaldsfeed_tools_build_geografi"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / "build_geografi.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


geo = _load()

RULES = {
    "min_indbyggere": 1000,
    "regioner": {
        "081": {"id": "nordjylland", "kort": "Nordjylland"},
        "082": {"id": "midtjylland", "kort": "Midtjylland"},
        "083": {"id": "syddanmark", "kort": "Syddanmark"},
        "084": {"id": "hovedstaden", "kort": "Hovedstaden"},
        "085": {"id": "sjaelland", "kort": "Sjælland"},
    },
    "ikke_kommuner": ["411"],
    "officielle_navne": {"101": "Københavns Kommune"},
    "ekstra_navne": {"751": ["Århus"]},
    "kun_med_kommune": ["Vejen"],
    "ignorer_byer": ["Brande"],
    "byer_ekstra_navne": {"Ullerslev": ["Ullerslev By"], "Findesikke": ["X"]},
    "landsdele": {"Fyn": "syddanmark"},
}

# Rigtige navne til de kommuner, testene ser på; resten fyldes op med opdigtede
NAMED = {
    "084": [("101", "København"), ("411", "Christiansø")],
    "083": [("450", "Nyborg"), ("575", "Vejen"), ("461", "Odense")],
    "082": [("751", "Aarhus"), ("756", "Ikast-Brande")],
}


def folk1a() -> dict:
    values = [{"id": "000", "text": "Hele landet"}]
    fake = iter(range(600, 700))  # opdigtede koder, der ikke støder på de navngivne
    for rcode in ("084", "085", "083", "082", "081"):
        values.append({"id": rcode, "text": f"Region {RULES['regioner'][rcode]['kort']}"})
        named = NAMED.get(rcode, [])
        for code, text in named:
            values.append({"id": code, "text": text})
        n_real = sum(1 for code, _ in named if code not in RULES["ikke_kommuner"])
        for i in range(geo.EXPECTED_PER_REGION[rcode] - n_real):
            values.append({"id": str(next(fake)), "text": f"Fiktiv {rcode}-{i}"})
    tid = {"id": "Tid", "time": True, "values": [{"id": "2026K3"}]}
    return {"id": "FOLK1A", "variables": [{"id": "OMRÅDE", "values": values}, tid]}


def by3_info() -> dict:
    towns = [
        ("00001100", "000-01100 Hovedstadsområdet"),
        ("10101100", "101-01100 København (del af Hovedstadsområdet)"),
        ("10199999", "101-99999 Landdistrikter"),
        ("45011111", "450-11111 Nyborg"),
        ("45011112", "450-11112 Ullerslev"),
        ("45011113", "450-11113 Lilleby"),
        ("46111114", "461-11114 Odense"),
        ("46122222", "461-22222 Højby"),
        ("45022223", "450-22223 Højby"),
        ("75133333", "751-33333 Ejby"),
        ("46133334", "461-33334 Ejby"),
        ("75144444", "751-44444 Delby (del af flere kommuner)"),
        ("45044444", "450-44444 Delby (del af flere kommuner)"),
        ("75655555", "756-55555 Brande"),
    ]
    return {
        "id": "BY3",
        "variables": [
            {"id": "BYER", "values": [{"id": i, "text": t} for i, t in towns]},
            {"id": "FOLKARTÆT", "values": [{"id": "BEF", "text": "Folketal"}, {"id": "ARE", "text": "Areal"}]},
            {"id": "Tid", "time": True, "values": [{"id": "2025"}, {"id": "2026"}]},
        ],
    }


POP = {
    "00001100": 1400000,
    "10101100": 650000,
    "10199999": 10,
    "45011111": 17000,
    "45011112": 2900,
    "45011113": 400,
    "46111114": 182000,
    "46122222": 3000,
    "45022223": 2500,
    "75133333": 9000,
    "46133334": 1200,
    "75144444": 3000,
    "45044444": 1500,
    "75655555": 7000,
}


def csv_text() -> str:
    lines = ["BYER;FOLKARTÆT;TID;INDHOLD"] + [f"{k};BEF;2026;{v}" for k, v in POP.items()]
    return "﻿" + "\n".join(lines) + "\n"


def run(rules=RULES):
    calls = []

    def get_json(url):
        return folk1a() if "FOLK1A" in url else by3_info()

    def post_text(url, body):
        calls.append(body)
        return csv_text()

    data, notes = geo.build(get_json, post_text, rules, date(2026, 10, 7))
    return data, notes, calls


def test_regioner_og_kommuner():
    data, _, _ = run()
    assert [r["id"] for r in data["regioner"]] == ["hovedstaden", "sjaelland", "syddanmark", "midtjylland", "nordjylland"]
    assert len(data["kommuner"]) == 98
    kbh = next(m for m in data["kommuner"] if m["kode"] == "101")
    assert kbh == {
        "id": "koebenhavn", "kode": "101", "navn": "Københavns Kommune", "kort": "København",
        "region": "hovedstaden", "navne": ["København"], "kun_med_kommune": False,
    }
    aarhus = next(m for m in data["kommuner"] if m["kode"] == "751")
    assert aarhus["navne"] == ["Aarhus", "Århus"] and aarhus["region"] == "midtjylland"
    assert next(m for m in data["kommuner"] if m["kort"] == "Vejen")["kun_med_kommune"] is True
    assert all(m["kode"] != "411" for m in data["kommuner"])


def test_byer():
    data, notes, calls = run()
    byer = {t["id"]: t for t in data["byer"]}
    # Hovedstadsområdet, landdistrikter og små byer kommer ikke med; Brande er ignoreret
    assert set(byer) == {"nyborg", "ullerslev", "odense", "ejby", "delby"}
    assert byer["ullerslev"] == {
        "id": "ullerslev", "navn": "Ullerslev", "navne": ["Ullerslev", "Ullerslev By"],
        "kommune": "nyborg", "kommuner": ["nyborg"], "indbyggere": 2900,
    }
    # By i flere kommuner: hovedkommunen er den største del
    assert byer["delby"]["kommune"] == "aarhus" and byer["delby"]["kommuner"] == ["aarhus", "nyborg"]
    assert byer["delby"]["indbyggere"] == 4500
    # Flertydige navne: Ejby er klart størst i Aarhus; Højby er ikke
    assert byer["ejby"]["kommune"] == "aarhus"
    assert any("Højby" in n and "udeladt" in n for n in notes)
    assert any("Brande" in n for n in notes)
    assert any("ADVARSEL" in n and "Findesikke" in n for n in notes)
    # Forespørgslen beder om folketal for nyeste år
    body = calls[0]
    assert {"code": "Tid", "values": ["2026"]} in body["variables"]
    assert {"code": "FOLKARTÆT", "values": ["BEF"]} in body["variables"]


def test_folketal_med_decimalkomma():
    text = "BYER;TID;FOLKARTAET;INDHOLD\r\n10101100;2026;FOLKETAL;671714,0\r\n15110223;2026;FOLKETAL;8.663,0\r\n"
    assert geo.parse_population(text) == {"10101100": 671714, "15110223": 8663}


def test_forkert_antal_kommuner_stopper():
    info = folk1a()
    info["variables"][0]["values"].pop()  # fjern en kommune
    with pytest.raises(geo.GeoError, match="antal kommuner"):
        geo.parse_areas(info, RULES)


def test_forkert_regionsnavn_stopper():
    info = folk1a()
    for v in info["variables"][0]["values"]:
        if v["id"] == "083":
            v["text"] = "Region Sydjylland"
    with pytest.raises(geo.GeoError, match="083"):
        geo.parse_areas(info, RULES)


def test_ukendte_koder_i_regler_stopper():
    rules = {**RULES, "ekstra_navne": {"999": ["Ingen"]}}
    with pytest.raises(geo.GeoError, match="999"):
        geo.parse_areas(folk1a(), rules)


def test_stavevarianter():
    assert geo.spelling_variants("Grenaa") == ["Grenå"]
    assert geo.spelling_variants("Årslev") == ["Aarslev"]
    assert geo.spelling_variants("Nyborg") == []
    assert geo.with_variants(["Aarhus", "Århus"]) == ["Aarhus", "Århus"]


def test_slug():
    assert geo.slug("Høje-Taastrup") == "hoeje-taastrup"
    assert geo.slug("Ærø") == "aeroe"
    assert geo.slug("Kongens Lyngby") == "kongens-lyngby"


def test_dump_er_gyldig_yaml():
    data, _, _ = run()
    text = geo.dump(data)
    assert text.startswith("# Genereret")
    assert yaml.safe_load(text) == data


def test_regelfilen_er_gyldig():
    rules = yaml.safe_load((ROOT / "config" / "geografi_regler.yaml").read_text(encoding="utf-8"))
    region_ids = {r["id"] for r in rules["regioner"].values()}
    assert len(region_ids) == 5
    assert set(rules["landsdele"].values()) <= region_ids
    assert set(rules["regioner"]) == set(geo.EXPECTED_PER_REGION)
