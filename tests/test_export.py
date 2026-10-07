"""Eksport (KONTRAKTER §8-9): feed.json, status.json og _site/."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import date, timedelta

import pytest

from affaldsfeed import export, paths, store
from affaldsfeed.models import Candidate, Rejected, SourceState, Why
from affaldsfeed.normalize import item_id
from affaldsfeed.timeutil import parse_iso

NOW = parse_iso("2026-10-07T10:00:00Z")
REAL_CONFIG = paths.CONFIG_DIR

SOURCES_YAML = """
- {id: kefm, name: KEFM, category: myndighed, homepage: "https://kefm.dk", feeds: "https://kefm.dk/rss",
   basis: offentlig, checked: 2026-10-01}
- {id: altinget, name: Altinget, category: fagmedie, homepage: "https://altinget.dk",
   feeds: "https://altinget.dk/rss", basis: redaktionelt, paywall: delvis, checked: 2026-10-01}
- {id: gnews, name: Google News, category: nyhedsmedie, homepage: "https://news.google.com", method: search,
   feeds: "https://news.google.com/rss/search?q={q}", basis: redaktionelt, checked: 2026-10-01}
- {id: dakofa, name: DAKOFA, category: organisation, homepage: "https://dakofa.dk", method: sitemap,
   feeds: "https://dakofa.dk/sitemap.xml", match: /nyheder/, status: planlagt}
"""
MEDIER_YAML = """
- {id: fyens, name: Fyens Stiftstidende, category: nyhedsmedie, domains: [fyens.dk], basis: redaktionelt}
- {id: jv, name: JydskeVestkysten, category: nyhedsmedie, domains: [jv.dk], basis: redaktionelt}
"""


@pytest.fixture
def repo(tmp_path, monkeypatch):
    shutil.copytree(REAL_CONFIG, tmp_path / "config")
    (tmp_path / "config" / "medier.yaml").write_text(MEDIER_YAML, encoding="utf-8")
    (tmp_path / "sources.yaml").write_text(SOURCES_YAML, encoding="utf-8")
    site = tmp_path / "site"
    (site / "assets").mkdir(parents=True)
    (site / "index.html").write_text("<!doctype html><title>Affaldsfeed</title>", encoding="utf-8")
    (site / "assets" / "app.js").write_text("// app", encoding="utf-8")
    (tmp_path / "examples").mkdir()
    (tmp_path / "examples" / "feed.sample.json").write_text('{"version":1}', encoding="utf-8")
    data = tmp_path / "data"
    for name, path in {
        "ROOT": tmp_path,
        "CONFIG_DIR": tmp_path / "config",
        "SOURCES_FILE": tmp_path / "sources.yaml",
        "SITE_DIR": site,
        "EXAMPLES_DIR": tmp_path / "examples",
        "DATA_DIR": data,
        "CANDIDATES_DIR": data / "candidates",
        "REJECTED_DIR": data / "rejected",
        "JUDGMENTS_DIR": data / "judgments",
        "OVERVIEW_DIR": data / "overview",
        "OVERVIEW_ARCHIVE_DIR": data / "overview" / "archive",
        "TIMELINE_DIR": data / "timeline",
        "STATE_DIR": data / "state",
        "HEARTBEAT_FILE": data / "judgments" / "_heartbeat.json",
    }.items():
        monkeypatch.setattr(paths, name, path)
    (data / "judgments").mkdir(parents=True)
    (data / "overview").mkdir(parents=True)
    return tmp_path


def cand(slug: str, source: str = "altinget", hours_ago: float = 2, title: str | None = None, **kw) -> Candidate:
    url = f"https://{source}.dk/{slug}"
    t = NOW - timedelta(hours=hours_ago)
    data = {
        "id": item_id(url),
        "url": url,
        "title": title or f"Affald og genbrug: {slug}",
        "teaser": "Kommunerne får nye regler for affaldssortering.",
        "source": source,
        "published": t,
        "date_quality": "kilde",
        "first_seen": t,
        "topics": ["sortering"],
        "why": Why(filter="normal", score=4, decision="vis", hits=["titel: affald"]),
    }
    data.update(kw)
    return Candidate(**data)


def judge(*lines: dict) -> None:
    with (paths.JUDGMENTS_DIR / "2026-10-07.jsonl").open("a", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps({"reason": "test", "judged_at": "2026-10-07T09:26:00Z", **line}, ensure_ascii=False))
            f.write("\n")


def heartbeat(last_run: str) -> None:
    paths.HEARTBEAT_FILE.write_text(json.dumps({"last_run": last_run, "pending_before": 0, "judged": 0}),
                                    encoding="utf-8")


def export_to(out, now: str = "2026-10-07T10:00:00Z") -> int:
    return export.main_export(argparse.Namespace(out=str(out), now=now))


@pytest.fixture
def scenario(repo):
    title = "Regeringen vil ændre reglerne for affaldsgebyrer i kommunerne"
    main = cand("gebyr", source="kefm", hours_ago=5, title=title)
    copy = cand("gebyr-altinget", hours_ago=4, title=title)
    other = cand("sortering", hours_ago=1)
    hidden = cand("skjult", hours_ago=1)
    waiting = cand("venter", hours_ago=1)
    old = cand("gammel", hours_ago=24 * 70)
    store.save_candidates([main, copy, other, hidden, waiting, old])
    sweep_url = "https://fyens.dk/nyt-affaldssystem"
    judge(
        {"id": main.id, "relevant": True, "topics": ["gebyrer", "regler"]},
        {"id": copy.id, "relevant": True},
        {"id": other.id, "relevant": True, "genre": "analyse"},
        {"id": hidden.id, "relevant": False},
        {"id": old.id, "relevant": True},
        {"id": item_id(sweep_url), "relevant": True, "new_item": {
            "url": sweep_url, "title": "Nyt affaldssystem på Fyn", "source": "fyens",
            "published": "2026-10-07T07:00:00Z"}},
    )
    heartbeat("2026-10-07T09:30:00Z")
    store.save_source_states({
        "kefm": SourceState(last_ok=date(2026, 10, 7), health="groen", items_30d=4, first_run_done=True),
        "altinget": SourceState(fails=2, last_error="HTTP 503", health="gul", items_30d=9, first_run_done=True),
        "gnews": SourceState(health="groen", items_30d=0, first_run_done=True),
    })
    store.save_rejected(
        [Rejected(id="r1", url="https://x.dk/1", title="X", source="altinget", first_seen=NOW - timedelta(days=2),
                  why=Why(filter="normal", score=0, decision="afvist"))],
        keep_days=90, now=NOW,
    )
    return {"main": main, "copy": copy, "other": other, "hidden": hidden, "waiting": waiting, "old": old,
            "sweep": item_id(sweep_url)}


def read(out, name: str) -> tuple[str, dict]:
    text = (out / "data" / name).read_text(encoding="utf-8")
    return text, json.loads(text)


def test_export_builds_site(repo, scenario, tmp_path):
    out = tmp_path / "_site"
    assert export_to(out) == 0
    assert (out / "index.html").is_file()
    assert (out / "assets" / "app.js").is_file()
    assert (out / "data" / "feed.sample.json").read_text(encoding="utf-8") == '{"version":1}'

    text, feed = read(out, "feed.json")
    assert list(feed) == ["version", "generated", "window_days", "mode", "last_judgment", "categories", "topics",
                          "genres", "sources", "geo", "overview", "items"]
    assert feed["version"] == 1
    assert feed["generated"] == "2026-10-07T10:00:00Z"
    assert feed["window_days"] == 60
    assert feed["mode"] == "claude"
    assert feed["last_judgment"] == "2026-10-07T09:30:00Z"
    assert text == json.dumps(feed, ensure_ascii=False, separators=(",", ":")) + "\n"  # kompakt
    assert "æ" in text  # ensure_ascii=False
    assert len(feed["categories"]) == 8 and set(feed["categories"][0]) == {
        "id", "name", "short", "color", "color_dark", "icon", "help"}
    assert list(feed["topics"][0]) == ["id", "name", "short", "definition"]
    topics = {t["id"]: t for t in feed["topics"]}
    assert topics["sortering"]["short"] is None
    assert topics["genbrugspladser"]["short"] == "Genbrugspladser og genbrug"
    assert set(feed["genres"][0]) == {"id", "label"}
    assert feed["overview"] == {"dag": None, "uge": None, "maaned": None, "aar": None}

    s = scenario
    items = feed["items"]
    assert [i["id"] for i in items] == [s["other"].id, s["sweep"], s["main"].id]
    story = items[2]
    assert story["story"] == s["main"].id
    assert [a["id"] for a in story["also"]] == [s["copy"].id]
    assert set(story["also"][0]) == {"id", "source", "url", "title", "published"}
    assert story["topics"] == ["gebyrer", "regler"]
    assert items[0]["genre"] == "analyse"
    assert items[1]["source"] == "fyens" and items[1]["reviewed"] is True
    assert list(items[0]) == ["id", "story", "url", "title", "teaser", "source", "published", "date_quality",
                              "first_seen", "baseline", "topics", "places", "genre", "lang", "summary_da",
                              "reviewed", "reason", "also", "why"]
    assert items[2]["places"] == [] and items[0]["places"] == []
    # Sweep-fundet "Nyt affaldssystem på Fyn" uden places i vurderingen får regelmærker
    assert items[1]["places"] == ["r:syddanmark"]
    assert feed["geo"]["byer"] == []

    sources = {x["id"]: x for x in feed["sources"]}
    assert set(sources) == {"altinget", "fyens", "kefm"}  # ikke søgekilder, planlagte eller ubrugte medier
    assert sources["fyens"]["via_search"] is True and sources["fyens"]["homepage"] == "https://fyens.dk"
    assert sources["altinget"] == {"id": "altinget", "name": "Altinget", "category": "fagmedie",
                                   "homepage": "https://altinget.dk", "lang": "da", "paywall": "delvis",
                                   "owner": None, "status": "aktiv", "health": "gul", "via_search": False,
                                   "logo": None}
    assert [x["id"] for x in feed["sources"]] == sorted(sources)


def test_status_json(repo, scenario, tmp_path):
    out = tmp_path / "_site"
    export_to(out)
    _, status = read(out, "status.json")
    assert list(status) == ["generated", "sources", "counts"]
    by_id = {x["id"]: x for x in status["sources"]}
    assert set(by_id) == {"kefm", "altinget", "gnews", "dakofa"}
    assert by_id["altinget"] == {"id": "altinget", "name": "Altinget", "category": "fagmedie", "status": "aktiv",
                                 "health": "gul", "last_ok": None, "fails": 2, "last_error": "HTTP 503",
                                 "items_30d": 9, "silent": False}
    assert by_id["kefm"]["last_ok"] == "2026-10-07"
    assert by_id["gnews"]["silent"] is True
    assert by_id["dakofa"]["health"] == "graa"
    assert status["counts"] == {"candidates_60d": 5, "shown_60d": 4, "rejected_30d": 1}


def test_fallback_mode_shows_unreviewed(repo, scenario, tmp_path):
    heartbeat("2026-10-07T05:00:00Z")  # over 2 t forsinket kl. 12
    out = tmp_path / "_site"
    export_to(out)
    _, feed = read(out, "feed.json")
    assert feed["mode"] == "fallback"
    by_id = {i["id"]: i for i in feed["items"]}
    assert by_id[scenario["waiting"].id]["reviewed"] is False
    assert scenario["hidden"].id not in by_id


def test_export_is_deterministic(repo, scenario, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    export_to(a)
    export_to(b)
    for name in ("feed.json", "status.json"):
        assert (a / "data" / name).read_bytes() == (b / "data" / name).read_bytes()


def test_overview_embedded(repo, scenario, tmp_path):
    ov = {"period": "dag", "window": {"start": "2026-10-06T22:00:00Z", "end": "2026-10-07T09:30:00Z"},
          "generated": "2026-10-07T09:30:00Z", "since": None, "headline": "Kort sagt: Nye gebyrregler.",
          "bullets": [{"text": "Regeringen vil ændre gebyrreglerne.", "item_ids": [scenario["main"].id],
                       "topics": ["gebyrer"]}], "based_on": 4}
    (paths.OVERVIEW_DIR / "dag.json").write_text(json.dumps(ov, ensure_ascii=False), encoding="utf-8")
    feed = export.build_feed(NOW)
    assert feed["overview"]["dag"] == ov
    assert feed["overview"]["uge"] is None


def test_out_inside_site_is_refused(repo):
    assert export_to(paths.SITE_DIR / "x") == 1


def test_geo_block_and_places(repo):
    title = "Regeringen vil ændre reglerne for affaldsgebyrer i kommunerne"
    national = cand("gebyr", source="kefm", hours_ago=5, title=title)
    local = cand("gebyr-lokalt", hours_ago=4, title=title, places=["k:nyborg", "b:ullerslev"])
    region = cand("lossepladser", hours_ago=3, title="Region Syddanmark kortlægger gamle lossepladser",
                  places=["r:syddanmark"])
    town = cand("hoersholm", hours_ago=2, title="Ny genbrugsplads i Hørsholm", places=["k:hoersholm", "b:hoersholm"])
    stale = cand("forsvundet", hours_ago=1, title="Byen er taget ud af geografien", places=["b:findes-ikke"])
    corrected = cand("rettet", hours_ago=1, title="Aarhus Universitet forsker i plast", places=["k:aarhus"])
    store.save_candidates([national, local, region, town, stale, corrected])
    judge(
        {"id": national.id, "relevant": True},
        {"id": local.id, "relevant": True},
        {"id": region.id, "relevant": True, "places": None},
        {"id": town.id, "relevant": True},
        {"id": stale.id, "relevant": True},
        {"id": corrected.id, "relevant": True, "places": []},
    )
    heartbeat("2026-10-07T09:30:00Z")
    feed = export.build_feed(NOW)

    by_id = {i["id"]: i for i in feed["items"]}
    # Historien: hovedindslaget er nationalt, men et indslag i also er lokalt
    assert [a["id"] for a in by_id[national.id]["also"]] == [local.id]
    assert by_id[national.id]["places"] == ["k:nyborg", "b:ullerslev"]
    assert by_id[region.id]["places"] == ["r:syddanmark"]
    assert by_id[town.id]["places"] == ["k:hoersholm", "b:hoersholm"]
    assert by_id[stale.id]["places"] == []  # ukendt id fjernes
    assert by_id[corrected.id]["places"] == []  # vurderingens tomme liste erstatter regelmærket

    geo = feed["geo"]
    assert list(geo) == ["regioner", "kommuner", "byer"]
    assert [r["id"] for r in geo["regioner"]] == ["hovedstaden", "sjaelland", "syddanmark", "midtjylland",
                                                   "nordjylland"]
    assert geo["regioner"][2] == {"id": "syddanmark", "navn": "Region Syddanmark", "kort": "Syddanmark"}
    assert len(geo["kommuner"]) == 98
    assert {"id": "nyborg", "navn": "Nyborg Kommune", "kort": "Nyborg", "region": "syddanmark"} in geo["kommuner"]
    assert {"id": "koebenhavn", "navn": "Københavns Kommune", "kort": "København",
            "region": "hovedstaden"} in geo["kommuner"]
    # Kun byer, som indslagene nævner (også via also)
    assert geo["byer"] == [
        {"id": "hoersholm", "navn": "Hørsholm", "kommune": "hoersholm",
         "kommuner": ["fredensborg", "hoersholm", "rudersdal"]},
        {"id": "ullerslev", "navn": "Ullerslev", "kommune": "nyborg", "kommuner": ["nyborg"]},
    ]


def test_story_places_are_not_cut_at_eight(repo, tmp_path):
    """Review: 10 steder fordelt på 3 indslag; by=vojens og by=soenderborg skal stadig finde historien."""
    title = "Kommunerne i Sønderjylland samarbejder om nyt sorteringsanlæg"
    main = cand("anlaeg", source="kefm", hours_ago=5, title=title,
                places=["r:syddanmark", "k:aabenraa", "k:haderslev"])
    a = cand("anlaeg-a", hours_ago=4, title=title, places=["k:soenderborg", "k:toender", "b:aabenraa", "b:haderslev"])
    b = cand("anlaeg-b", hours_ago=3, title=title, places=["b:soenderborg", "b:toender", "b:vojens"])
    store.save_candidates([main, a, b])
    judge(*({"id": c.id, "relevant": True} for c in (main, a, b)))
    heartbeat("2026-10-07T09:30:00Z")
    assert export_to(tmp_path / "_site") == 0
    feed = json.loads((tmp_path / "_site" / "data" / "feed.json").read_text(encoding="utf-8"))
    [story] = feed["items"]
    assert len(story["also"]) == 2 and len(story["places"]) == 10
    assert {"b:soenderborg", "b:vojens"} <= set(story["places"])
    assert [t["id"] for t in feed["geo"]["byer"]] == ["aabenraa", "haderslev", "soenderborg", "toender", "vojens"]


def test_geo_block_sorts_towns_by_id():
    # KONTRAKTER §8: byerne sorteres efter id, også når geografi.yaml ikke er sorteret
    from affaldsfeed.models import DisplayItem, Geo

    geo = Geo.model_validate({
        "regioner": [{"id": "syddanmark", "kode": "083", "navn": "Region Syddanmark", "kort": "Syddanmark"}],
        "kommuner": [{"id": "nyborg", "kode": "450", "navn": "Nyborg Kommune", "kort": "Nyborg",
                      "region": "syddanmark", "navne": ["Nyborg"]}],
        "byer": [{"id": i, "navn": i.title(), "navne": [i.title()], "kommune": "nyborg"}
                 for i in ("ullerslev", "aunslev", "nyborg", "oerbaek")],
    })
    item = DisplayItem(id="x", story="x", url="https://x.dk", title="T", source="s", date_quality="kilde",
                       first_seen=NOW, places=["b:ullerslev", "b:nyborg", "b:aunslev"])
    assert [t["id"] for t in export.geo_block(geo, [item])["byer"]] == ["aunslev", "nyborg", "ullerslev"]


def test_without_geography_geo_is_null(repo):
    (paths.CONFIG_DIR / "geografi.yaml").unlink()
    c = cand("lokalt", title="Ny genbrugsplads i Nyborg", places=["k:nyborg", "b:nyborg"])
    store.save_candidates([c])
    judge({"id": c.id, "relevant": True})
    feed = export.build_feed(NOW)
    assert feed["geo"] is None
    assert feed["items"][0]["places"] == []


def test_feed_contract_is_validated(repo, scenario, monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(export, "geo_block", lambda geo, items: {"regioner": [], "kommuner": [], "byer": [
        {"id": "ullerslev", "navn": "Ullerslev", "kommune": "nyborg", "kommuner": ["nyborg"]}]})
    assert export_to(tmp_path / "_site") == 1
    assert "skemafejl" in caplog.text


def test_export_includes_logos_for_sources_in_feed(repo, scenario, tmp_path):
    """Logoer fra data/state/logos/ (KONTRAKTER §6.4) står i sources[].logo og kopieres til _site/logos/."""
    folder = paths.STATE_DIR / "logos"
    folder.mkdir(parents=True)
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 80
    (folder / "altinget.png").write_bytes(png)
    (folder / "jv.ico").write_bytes(b"\x00\x00\x01\x00" + b"\x00" * 80)  # JydskeVestkysten er ikke i feedet
    store.write_json(paths.STATE_DIR / "logos.json", {
        "altinget": {"file": "altinget.png", "src": "https://altinget.dk/f.png", "checked": "2026-10-07T06:00:00Z"},
        "jv": {"file": "jv.ico", "src": "https://jv.dk/favicon.ico", "checked": "2026-10-07T06:00:00Z"},
        "kefm": {"file": "kefm.png", "src": None, "checked": "2026-10-07T06:00:00Z"},  # filen mangler
    })
    out = tmp_path / "_site"
    assert export_to(out) == 0
    _, feed = read(out, "feed.json")
    logos = {s["id"]: s["logo"] for s in feed["sources"]}
    assert logos == {"altinget": "logos/altinget.png", "fyens": None, "kefm": None}
    assert (out / "logos" / "altinget.png").read_bytes() == png
    assert sorted(p.name for p in (out / "logos").iterdir()) == ["altinget.png"]
