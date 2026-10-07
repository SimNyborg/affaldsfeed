"""Vurderinger (KONTRAKTER §6.2-6.3): pending, validate-judgments, heartbeat og display_mode."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import timedelta

import pytest

from affaldsfeed import judgments, paths, store
from affaldsfeed.models import Candidate, Heartbeat, RoutineSettings, Why
from affaldsfeed.normalize import item_id
from affaldsfeed.timeutil import parse_iso

NOW = parse_iso("2026-10-07T10:00:00Z")  # 12:00 i København
REAL_CONFIG = paths.CONFIG_DIR

SOURCES_YAML = """
- {id: kefm, name: KEFM, category: myndighed, homepage: "https://kefm.dk", feeds: "https://kefm.dk/rss",
   basis: offentlig, checked: 2026-10-01}
- {id: altinget, name: Altinget, category: fagmedie, homepage: "https://altinget.dk",
   feeds: "https://altinget.dk/rss", basis: redaktionelt, checked: 2026-10-01}
- {id: dr, name: DR, category: nyhedsmedie, homepage: "https://dr.dk", feeds: "https://dr.dk/rss", ai: false,
   basis: redaktionelt, checked: 2026-10-01}
- {id: zwe, name: Zero Waste Europe, category: eu_norden, homepage: "https://zwe.eu", feeds: "https://zwe.eu/feed",
   lang: en, basis: organisation, checked: 2026-10-01}
"""
MEDIER_YAML = """
- {id: fyens, name: Fyens Stiftstidende, category: nyhedsmedie, domains: [fyens.dk], basis: redaktionelt}
"""


@pytest.fixture
def repo(tmp_path, monkeypatch):
    shutil.copytree(REAL_CONFIG, tmp_path / "config")
    (tmp_path / "config" / "medier.yaml").write_text(MEDIER_YAML, encoding="utf-8")
    (tmp_path / "sources.yaml").write_text(SOURCES_YAML, encoding="utf-8")
    data = tmp_path / "data"
    for name, path in {
        "ROOT": tmp_path,
        "CONFIG_DIR": tmp_path / "config",
        "SOURCES_FILE": tmp_path / "sources.yaml",
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
    return tmp_path


def cand(slug: str, source: str = "altinget", hours_ago: float = 2, decision: str = "vis", **kw) -> Candidate:
    url = f"https://{source}.dk/{slug}"
    t = NOW - timedelta(hours=hours_ago)
    data = {
        "id": item_id(url),
        "url": url,
        "title": f"Affald: {slug}",
        "source": source,
        "published": t,
        "date_quality": "kilde",
        "first_seen": t,
        "topics": ["sortering"],
        "why": Why(filter="normal", score=4, decision=decision, hits=["titel: affald"]),
    }
    data.update(kw)
    return Candidate(**data)


def write_judgments(day: str, lines: list) -> None:
    path = paths.JUDGMENTS_DIR / f"{day}.jsonl"
    with path.open("a", encoding="utf-8") as f:
        for line in lines:
            f.write((line if isinstance(line, str) else json.dumps(line, ensure_ascii=False)) + "\n")


def j(id: str, relevant: bool = True, at: str = "2026-10-07T09:25:00Z", **kw) -> dict:
    return {"id": id, "relevant": relevant, "reason": "test", "judged_at": at, **kw}


def ns(**kw) -> argparse.Namespace:
    return argparse.Namespace(**kw)


# ── display_mode ────────────────────────────────────────────

ROUTINE = RoutineSettings(hours=list(range(6, 24)), minute=25, grace_hours=2.0)


@pytest.mark.parametrize(
    ("now", "slot"),
    [
        ("2026-10-07T10:00:00Z", "2026-10-07T09:25:00Z"),  # 12:00 CEST -> 11:25
        ("2026-10-07T04:24:00Z", "2026-10-06T21:25:00Z"),  # 06:24 -> i går 23:25
        ("2026-10-07T04:25:00Z", "2026-10-07T04:25:00Z"),  # 06:25
        ("2026-12-07T05:30:00Z", "2026-12-07T05:25:00Z"),  # vintertid: 06:30 CET -> 06:25
    ],
)
def test_last_scheduled_run(now, slot):
    assert judgments.last_scheduled_run(parse_iso(now), ROUTINE) == parse_iso(slot)


@pytest.mark.parametrize(
    ("last_run", "now", "mode"),
    [
        (None, "2026-10-07T10:00:00Z", "fallback"),
        ("2026-10-07T09:30:00Z", "2026-10-07T10:00:00Z", "claude"),
        ("2026-10-07T07:26:00Z", "2026-10-07T10:00:00Z", "claude"),  # 09:26 >= 11:25 - 2 t
        ("2026-10-07T07:20:00Z", "2026-10-07T10:00:00Z", "fallback"),  # over 2 t forsinket
        ("2026-10-06T21:30:00Z", "2026-10-07T01:00:00Z", "claude"),  # nat: venter til 06:25
        ("2026-10-06T21:30:00Z", "2026-10-07T04:30:00Z", "claude"),  # 06:30, kørslen 06:25 er lige startet
        ("2026-10-06T21:30:00Z", "2026-10-07T05:00:00Z", "claude"),  # 07:00, 06:25 er under 2 t forsinket
        ("2026-10-06T21:30:00Z", "2026-10-07T06:30:00Z", "fallback"),  # 08:30, kørslen 06:25 mangler
    ],
)
def test_display_mode(last_run, now, mode):
    hb = Heartbeat(last_run=parse_iso(last_run)) if last_run else None
    assert judgments.display_mode(parse_iso(now), hb, ROUTINE) == mode


# ── indlæsning ──────────────────────────────────────────────


def test_latest_judgment_wins_and_invalid_lines_skipped(repo):
    write_judgments("2026-10-06", [j("a", True, at="2026-10-06T10:00:00Z")])
    write_judgments("2026-10-07", [j("a", False), "{ikke json", j("b", True)])
    (paths.JUDGMENTS_DIR / "noter.jsonl").write_text(json.dumps(j("c")) + "\n", encoding="utf-8")
    latest = judgments.load_judgments()
    assert set(latest) == {"a", "b"}
    assert latest["a"].relevant is False
    assert len(judgments.load_judgment_list()) == 3


def test_load_heartbeat(repo):
    assert judgments.load_heartbeat() is None
    paths.HEARTBEAT_FILE.write_text('{"last_run":"2026-10-07T09:30:00Z","pending_before":3,"judged":3}',
                                    encoding="utf-8")
    hb = judgments.load_heartbeat()
    assert hb is not None and hb.judged == 3


# ── pending ─────────────────────────────────────────────────


def test_pending_output(repo, capsys):
    new = cand("ny", hours_ago=1, places=["b:ullerslev", "k:nyborg", "b:taget-ud-af-geografien"])
    older = cand("aeldre", hours_ago=5, decision="graa")
    judged = cand("vurderet", hours_ago=3)
    rules_only = cand("regler", source="dr", hours_ago=1)
    too_old = cand("gammel", hours_ago=80)
    en = cand("english", source="zwe", hours_ago=2, lang="en")
    unknown = cand("ukendt", source="nedlagt", hours_ago=1)
    store.save_candidates([new, older, judged, rules_only, too_old, en, unknown])
    sweep_url = "https://fyens.dk/a"
    write_judgments("2026-10-07", [
        j(judged.id, True),
        j(item_id(sweep_url), True, new_item={"url": sweep_url, "title": "Sweep", "source": "fyens",
                                             "published": "2026-10-07T08:00:00Z"}),
    ])

    assert judgments.main_pending(ns(max=200, hours=72, now="2026-10-07T10:00:00Z")) == 0
    raw = capsys.readouterr().out
    out = json.loads(raw)
    assert list(out) == ["now", "profile", "topics", "genres", "places_help", "pending", "recent_approved"]
    # places_help står med én post pr. linje, ikke som én lang linje
    lines = raw.splitlines()
    assert '    {"id":"nyborg","navn":"Nyborg Kommune"},' in lines
    assert '    {"id":"hovedstaden","navn":"Region Hovedstaden"},' in lines
    help_start = lines.index('"places_help":{')
    help_lines = lines[help_start:lines.index("},", help_start) + 1]
    assert len(help_lines) > 100 and max(len(ln) for ln in help_lines) < 80
    assert out["now"] == "2026-10-07T10:00:00Z"
    assert "Relevansprofil" in out["profile"]
    assert set(out["topics"][0]) == {"id", "name", "definition"}
    assert set(out["genres"][0]) == {"id", "label"}
    help_ = out["places_help"]
    assert list(help_) == ["format", "regioner", "kommuner"]  # byer slås op i config/geografi.yaml
    assert help_["format"] == "r:<region>, k:<kommune>, b:<by>"
    assert help_["regioner"][0] == {"id": "hovedstaden", "navn": "Region Hovedstaden"}
    assert len(help_["kommuner"]) == 98 and {"id": "nyborg", "navn": "Nyborg Kommune"} in help_["kommuner"]
    assert [p["id"] for p in out["pending"]] == [new.id, en.id, older.id]
    first = out["pending"][0]
    assert list(first) == ["id", "url", "title", "teaser", "source_name", "category", "lang", "published",
                           "rule_topics", "rule_genre", "rule_places", "prefilter"]
    assert first["source_name"] == "Altinget" and first["category"] == "fagmedie"
    assert first["rule_places"] == ["k:nyborg", "b:ullerslev"]  # id'er uden for geografien udelades
    assert out["pending"][1]["rule_places"] == []
    assert first["prefilter"] == {"decision": "vis", "score": 4, "hits": ["titel: affald"]}
    assert out["pending"][1]["lang"] == "en"
    assert [r["id"] for r in out["recent_approved"]] == [item_id(sweep_url), judged.id]
    assert set(out["recent_approved"][0]) == {"id", "title", "source_name", "published"}


def test_pending_max_and_hours(repo, capsys):
    store.save_candidates([cand(f"x{i}", hours_ago=i + 1) for i in range(5)])
    judgments.main_pending(ns(max=2, hours=3, now="2026-10-07T10:00:00Z"))
    out = json.loads(capsys.readouterr().out)
    assert len(out["pending"]) == 2
    judgments.main_pending(ns(max=200, hours=3, now="2026-10-07T10:00:00Z"))
    assert len(json.loads(capsys.readouterr().out)["pending"]) == 3


# ── validate-judgments ──────────────────────────────────────


def test_validate_ok(repo, capsys):
    a = cand("a")
    en = cand("en", source="zwe", lang="en")
    store.save_candidates([a, en])
    url = "https://www.fyens.dk/artikel?utm_source=x"
    write_judgments("2026-10-07", [
        j(a.id, True, topics=["gebyrer", "regler"], genre="nyhed", story_hint=en.id),
        j(en.id, True, summary_da="Kort dansk resumé"),
        j(item_id(url), True, new_item={"url": url, "title": "Sweep", "source": "fyens"}),
    ])
    assert judgments.main_validate(ns(file=None)) == 0
    assert "OK" in capsys.readouterr().out


def test_validate_errors(repo, capsys):
    a = cand("a")
    store.save_candidates([a])
    sweep = "https://fyens.dk/b"
    write_judgments("2026-10-07", [
        j(a.id, True),                                   # 1 ok
        "{ikke json",                                    # 2
        j("ukendt12345a", True),                         # 3 ukendt id
        j(a.id, True, reason="x" * 201),                 # 4 for lang
        j(a.id, True, topics=["affald"]),                # 5 ukendt tema
        j(a.id, True, summary_da="Unødvendig"),          # 6 dansk
        j("forkert-id", True, new_item={"url": sweep, "title": "T", "source": "fyens"}),  # 7
        j(item_id(sweep), True, new_item={"url": sweep, "title": "T", "source": "ukendt"}),  # 8
        j(item_id(sweep), False, new_item={"url": sweep, "title": "T", "source": "fyens"}),  # 9
        j(a.id, True, story_hint=a.id),                  # 10
        j(a.id, True, at="2026-10-08T09:00:00Z"),        # 11 forkert fil
        j(a.id, True, story_hint="fantasi12345"),        # 12
        j(a.id, True, topics=["regler", "udbud", "klima"]),  # 13 for mange temaer
    ])
    assert judgments.main_validate(ns(file=None)) == 1
    out = capsys.readouterr().out
    prefix = "data/judgments/2026-10-07.jsonl:"
    lines = [ln for ln in out.splitlines() if ln.startswith(prefix)]
    bad = {int(ln[len(prefix):].split(":")[0]) for ln in lines}
    assert bad == set(range(2, 14))
    assert f"{prefix}7: id skal være item_id(new_item.url) = {item_id(sweep)}" in out
    assert "data/judgments/2026-10-08.jsonl" in out


def test_validate_places(repo, capsys):
    a = cand("a")
    store.save_candidates([a])
    nine = ["aarhus", "odense", "nyborg", "vejle", "kolding", "horsens", "silkeborg", "herning", "viborg"]
    write_judgments("2026-10-07", [
        j(a.id, True),                                         # 1 ingen places: behold regelmærker
        j(a.id, True, places=None),                            # 2 null: behold regelmærker
        j(a.id, True, places=[]),                              # 3 tom liste: nationalt
        j(a.id, True, places=["b:ullerslev", "k:nyborg"]),     # 4 ok
        j(a.id, True, places=[f"k:{k}" for k in nine[:8]] + ["k:aarhus"]),  # 5 otte unikke + en dublet: ok
    ])
    assert judgments.main_validate(ns(file=None)) == 0
    assert "validate-judgments: OK, 5 linjer i 1 filer" in capsys.readouterr().out
    parsed = judgments.load_judgment_list()
    assert parsed[0].places is None and parsed[1].places is None and parsed[2].places == []
    assert parsed[3].places == ["k:nyborg", "b:ullerslev"]  # rækkefølgen normaliseres
    assert len(parsed[4].places) == 8


def test_validate_unknown_place_is_a_warning(repo, capsys):
    # Velformede, men ukendte id'er (fx efter en ny geografi): advarsel med forslag, exit 0
    a = cand("a")
    store.save_candidates([a])
    write_judgments("2026-10-07", [
        j(a.id, True, places=["k:kobenhavn"]),                     # 1 stavefejl
        j(a.id, True, places=["r:syddanmark", "k:ullerslev"]),     # 2 byen skrevet som kommune
        j(a.id, True, places=["b:qqqqqq"]),                        # 3 intet ligner
    ])
    assert judgments.main_validate(ns(file=None)) == 0
    out = capsys.readouterr().out
    prefix = "ADVARSEL data/judgments/2026-10-07.jsonl:"
    assert (f"{prefix}1: places: ukendt sted-id 'k:kobenhavn' (mente du 'k:koebenhavn'?); "
            "brug id'er fra config/geografi.yaml") in out
    assert f"{prefix}2: places: ukendt sted-id 'k:ullerslev' (mente du 'b:ullerslev'?)" in out
    assert f"{prefix}3: places: ukendt sted-id 'b:qqqqqq'; brug" in out
    assert "validate-judgments: OK, 3 linjer i 1 filer, 3 advarsler" in out


def test_validate_place_format_errors_in_danish(repo, capsys):
    a = cand("a")
    store.save_candidates([a])
    nine = ["aarhus", "odense", "nyborg", "vejle", "kolding", "horsens", "silkeborg", "herning", "viborg"]
    write_judgments("2026-10-07", [
        j(a.id, True, places=["nyborg"]),                      # 1 mangler præfiks
        j(a.id, True, places=["K:Odense"]),                    # 2 store bogstaver
        j(a.id, True, places=["k:københavn"]),                 # 3 æøå
        j(a.id, True, places=["kommune:odense", "k:odense "]),  # 4 langt præfiks og mellemrum
        j(a.id, True, places=[f"k:{k}" for k in nine]),        # 5 ni forskellige
        j(a.id, True, places=["k:atlantis"]),                  # 6 velformet: kun en advarsel
    ])
    assert judgments.main_validate(ns(file=None)) == 1
    out = capsys.readouterr().out
    prefix = "data/judgments/2026-10-07.jsonl:"
    bad = {int(ln[len(prefix):].split(":")[0]) for ln in out.splitlines() if ln.startswith(prefix)}
    assert bad == {1, 2, 3, 4, 5}
    hint = "skriv r:<region>, k:<kommune> eller b:<by> med små bogstaver og æ→ae, ø→oe, å→aa (fx k:koebenhavn)"
    assert f"{prefix}1: places: ugyldigt sted-id 'nyborg': {hint}" in out
    assert f"{prefix}2: places: ugyldigt sted-id 'K:Odense' (mente du 'k:odense'?): {hint}" in out
    assert f"{prefix}3: places: ugyldigt sted-id 'k:københavn' (mente du 'k:koebenhavn'?)" in out
    assert (f"{prefix}4: places: ugyldige sted-id'er 'kommune:odense' (mente du 'k:odense'?), "
            "'k:odense ' (mente du 'k:odense'?)") in out
    assert f"{prefix}5: places: højst 8 forskellige steder, her er der 9" in out
    assert "ADVARSEL data/judgments/2026-10-07.jsonl:6: places: ukendt sted-id 'k:atlantis'" in out
    assert "List should have" not in out and "Value error" not in out


def test_validate_places_without_geography(repo, capsys):
    (paths.CONFIG_DIR / "geografi.yaml").unlink()
    a = cand("a")
    store.save_candidates([a])
    write_judgments("2026-10-07", [j(a.id, True, places=["k:atlantis", "b:ullerslev"])])
    assert judgments.main_validate(ns(file=None)) == 0
    out = capsys.readouterr().out
    assert "ADVARSEL" not in out and "validate-judgments: OK, 1 linjer i 1 filer" in out


def test_validate_single_file(repo, capsys):
    a = cand("a")
    store.save_candidates([a])
    write_judgments("2026-10-06", [j("ukendt12345a", True, at="2026-10-06T09:00:00Z")])
    write_judgments("2026-10-07", [j(a.id, True)])
    assert judgments.main_validate(ns(file="data/judgments/2026-10-07.jsonl")) == 0
    assert judgments.main_validate(ns(file=None)) == 1
    capsys.readouterr()


# ── heartbeat ───────────────────────────────────────────────


def test_heartbeat(repo):
    a, b, c = cand("a"), cand("b"), cand("c")
    store.save_candidates([a, b, c])
    write_judgments("2026-10-07", [j(a.id, True), j(b.id, False)])
    assert judgments.main_heartbeat(ns(now="2026-10-07T09:31:00Z")) == 0
    hb = json.loads(paths.HEARTBEAT_FILE.read_text(encoding="utf-8"))
    assert hb == {"last_run": "2026-10-07T09:31:00Z", "pending_before": 3, "judged": 2}
    # næste kørsel uden nye vurderinger
    judgments.main_heartbeat(ns(now="2026-10-07T10:31:00Z"))
    hb = json.loads(paths.HEARTBEAT_FILE.read_text(encoding="utf-8"))
    assert hb == {"last_run": "2026-10-07T10:31:00Z", "pending_before": 1, "judged": 0}
