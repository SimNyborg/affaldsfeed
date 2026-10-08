"""AI-overblikket (KONTRAKTER §7): vinduer, punktgrænser, overview-input og validate-overview."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import timedelta

import pytest

from affaldsfeed import overview, paths, store
from affaldsfeed.models import Candidate, Why
from affaldsfeed.normalize import item_id
from affaldsfeed.timeutil import parse_iso

NOW = parse_iso("2026-10-07T10:00:00Z")  # 12:00 i København (sommertid)
REAL_CONFIG = paths.CONFIG_DIR

SOURCES_YAML = """
- {id: kefm, name: KEFM, category: myndighed, homepage: "https://kefm.dk", feeds: "https://kefm.dk/rss",
   basis: offentlig, checked: 2026-10-01}
- {id: altinget, name: Altinget, category: fagmedie, homepage: "https://altinget.dk",
   feeds: "https://altinget.dk/rss", basis: redaktionelt, checked: 2026-10-01}
- {id: zwe, name: Zero Waste Europe, category: eu_norden, homepage: "https://zwe.eu", feeds: "https://zwe.eu/feed",
   lang: en, basis: organisation, checked: 2026-10-01}
"""


@pytest.fixture
def repo(tmp_path, monkeypatch):
    shutil.copytree(REAL_CONFIG, tmp_path / "config")
    (tmp_path / "config" / "medier.yaml").write_text("[]\n", encoding="utf-8")
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
    (data / "overview" / "archive").mkdir(parents=True)
    return tmp_path


def cand(slug: str, source: str = "altinget", hours_ago: float = 2, title: str | None = None, **kw) -> Candidate:
    url = f"https://{source}.dk/{slug}"
    t = NOW - timedelta(hours=hours_ago)
    data = {
        "id": item_id(url),
        "url": url,
        "title": title or f"Affald: {slug}",
        "teaser": f"Teaser om {slug}.",
        "source": source,
        "published": t,
        "date_quality": "kilde",
        "first_seen": t,
        "why": Why(filter="normal", score=4, decision="vis"),
    }
    data.update(kw)
    return Candidate(**data)


def approve(*cands: Candidate, relevant: bool = True, **kw) -> None:
    with (paths.JUDGMENTS_DIR / "2026-10-07.jsonl").open("a", encoding="utf-8") as f:
        for c in cands:
            line = {"id": c.id, "relevant": relevant, "reason": "test", "judged_at": "2026-10-07T09:50:00Z", **kw}
            f.write(json.dumps(line, ensure_ascii=False) + "\n")


def run_input(period: str, capsys, now: str = "2026-10-07T10:00:00Z") -> dict:
    assert overview.main_overview_input(argparse.Namespace(period=period, now=now)) == 0
    return json.loads(capsys.readouterr().out)


def write_overview(period: str, obj: dict) -> None:
    (paths.OVERVIEW_DIR / f"{period}.json").write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def ov(period: str, item_ids: list[str], *, start: str, end: str = "2026-10-07T10:00:00Z", n: int = 1,
       headline: str = "Kort sagt: Ny regel om affald.", based_on: int | None = None) -> dict:
    return {
        "period": period,
        "window": {"start": start, "end": end},
        "generated": end,
        "since": None,
        "headline": headline,
        "bullets": [{"text": f"Punkt {i + 1} om affald.", "item_ids": item_ids, "topics": ["regler"]}
                    for i in range(n)],
        "based_on": based_on if based_on is not None else len(item_ids),
    }


def validate(period: str | None = None, archive: bool = False, now: str = "2026-10-07T10:05:00Z") -> int:
    return overview.main_validate_overview(argparse.Namespace(period=period, archive=archive, now=now))


# ── vinduer og grænser ──────────────────────────────────────


def test_window_for():
    assert overview.window_for("dag", NOW) == (parse_iso("2026-10-06T22:00:00Z"), NOW)
    winter = parse_iso("2026-12-07T10:00:00Z")
    assert overview.window_for("dag", winter)[0] == parse_iso("2026-12-06T23:00:00Z")
    assert overview.window_for("uge", NOW)[0] == NOW - timedelta(days=7)
    assert overview.window_for("maaned", NOW)[0] == NOW - timedelta(days=30)
    assert overview.window_for("aar", NOW)[0] == NOW - timedelta(days=365)


@pytest.mark.parametrize(
    ("period", "based_on", "limits"),
    [
        ("dag", 2, (1, 5)),
        ("dag", 6, (3, 5)),
        ("uge", 30, (3, 5)),
        ("uge", 4, (1, 5)),
        ("maaned", 9, (3, 8)),
        ("maaned", 40, (5, 8)),
        ("aar", 2, (1, 8)),
    ],
)
def test_bullet_limits(period, based_on, limits):
    assert overview.bullet_limits(period, based_on) == limits


# ── overview-input ──────────────────────────────────────────


def test_input_dag(repo, capsys):
    today = cand("i-dag", hours_ago=1)
    en = cand("english", source="zwe", hours_ago=2, lang="en")
    yesterday = cand("i-gaar", hours_ago=13)  # 23:00 i går dansk tid
    rejected = cand("afvist", hours_ago=1)
    unjudged = cand("uvurderet", hours_ago=1)
    store.save_candidates([today, en, yesterday, rejected, unjudged])
    approve(today, yesterday)
    approve(en, summary_da="Dansk resumé")
    approve(rejected, relevant=False)

    out = run_input("dag", capsys)
    assert list(out) == ["period", "now", "window", "since", "rules", "items", "lower_overviews",
                         "allowed_item_ids", "based_on"]
    assert out["window"] == {"start": "2026-10-06T22:00:00Z", "end": "2026-10-07T10:00:00Z"}
    assert out["rules"] == {"headline_max_words": 25, "bullet_max_words": 30, "bullets_min": 1, "bullets_max": 5}
    assert [i["id"] for i in out["items"]] == [today.id, en.id]
    assert set(out["items"][0]) == {"id", "title", "teaser_or_summary", "source_name", "category", "genre",
                                    "topics", "published", "story_size"}
    assert out["items"][1]["teaser_or_summary"] == "Dansk resumé"
    assert out["allowed_item_ids"] == sorted([today.id, en.id])
    assert out["based_on"] == 2
    assert out["lower_overviews"] == []
    assert out["since"] is None


def test_input_uge_groups_stories(repo, capsys):
    title = "Regeringen vil ændre reglerne for affaldsgebyrer i kommunerne"
    a = cand("a", source="altinget", hours_ago=30, title=title)
    b = cand("b", source="kefm", hours_ago=31, title=title)
    c = cand("c", hours_ago=10)
    store.save_candidates([a, b, c])
    approve(a, b, c)
    out = run_input("uge", capsys)
    assert [i["id"] for i in out["items"]] == [b.id, c.id]  # myndigheden er hovedindslag, størst først
    assert out["items"][0]["story_size"] == 2
    assert out["based_on"] == 3
    assert out["allowed_item_ids"] == sorted([b.id, c.id])
    assert out["since"] == "2026-10-06"  # data begynder efter vinduets start


def test_input_maaned_uses_archived_weeks(repo, capsys):
    a = cand("a", hours_ago=24 * 3)
    store.save_candidates([a])
    approve(a)
    arch = paths.OVERVIEW_ARCHIVE_DIR
    for day, hl in (("2026-10-05", "Kort sagt: gammel."), ("2026-10-06", "Kort sagt: ny.")):
        week = ov("uge", [a.id], start="2026-09-29T08:00:00Z", end=f"{day}T08:00:00Z", headline=hl)
        (arch / f"uge-{day}.json").write_text(json.dumps(week), encoding="utf-8")
    (arch / "uge-2026-08-01.json").write_text(
        json.dumps(ov("uge", [a.id], start="2026-07-25T08:00:00Z", end="2026-08-01T08:00:00Z")), encoding="utf-8"
    )
    out = run_input("maaned", capsys)
    assert [o["headline"] for o in out["lower_overviews"]] == ["Kort sagt: gammel.", "Kort sagt: ny."]
    assert out["allowed_item_ids"] == [a.id]


def test_input_aar_newest_month_overview(repo, capsys):
    arch = paths.OVERVIEW_ARCHIVE_DIR
    for day in ("2026-09-03", "2026-09-28", "2026-10-06"):
        m = ov("maaned", ["x"], start="2026-08-01T00:00:00Z", end=f"{day}T04:30:00Z", headline=f"Kort sagt: {day}")
        (arch / f"maaned-{day}.json").write_text(json.dumps(m), encoding="utf-8")
    out = run_input("aar", capsys)
    assert [o["headline"] for o in out["lower_overviews"]] == ["Kort sagt: 2026-09-28", "Kort sagt: 2026-10-06"]


# ── validate-overview ───────────────────────────────────────


def test_validate_ok_and_archive(repo, capsys):
    a, b = cand("a", hours_ago=1), cand("b", hours_ago=3)
    store.save_candidates([a, b])
    approve(a, b)
    write_overview("dag", ov("dag", [a.id, b.id], start="2026-10-06T22:00:00Z", n=2))
    assert validate("dag", archive=True) == 0
    assert "OK" in capsys.readouterr().out
    archived = paths.OVERVIEW_ARCHIVE_DIR / "dag-2026-10-07.json"
    assert archived.read_bytes() == (paths.OVERVIEW_DIR / "dag.json").read_bytes()
    loaded = overview.load_overviews()
    assert loaded["dag"] is not None and loaded["uge"] is None


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"headline": "Nyt om affald i dag."}, "headline skal begynde med 'Kort sagt:'"),
        ({"headline": "Kort sagt: " + "ord " * 30}, "headline har 32 ord (maks 25)"),
        ({"bullets": [{"text": "ord " * 31, "item_ids": ["A"]}]}, "punkt 1 har 31 ord (maks 30)"),
        ({"bullets": [{"text": "Om noget.", "item_ids": ["fantasi12345"]}]}, "item_id 'fantasi12345' er ikke"),
        ({"bullets": [{"text": "Om noget.", "item_ids": ["OLD"]}]}, "item_id"),
        ({"bullets": [{"text": "Om noget.", "item_ids": ["NO"]}]}, "item_id"),
        ({"window": {"start": "2026-10-06T00:00:00Z", "end": "2026-10-07T10:00:00Z"}}, "window.start skal være"),
        ({"period": "uge"}, "period er 'uge'"),
        ({"based_on": 7}, "punkter; tilladt er 3-5"),
        ({"based_on": 9}, "based_on er 9, men der er kun"),
    ],
)
def test_validate_errors(repo, capsys, change, message):
    a = cand("a", hours_ago=1)
    old = cand("old", hours_ago=24)  # godkendt, men uden for dagens vindue
    no = cand("no", hours_ago=2)
    extra = [cand(f"e{i}", hours_ago=1) for i in range(6)]
    store.save_candidates([a, old, no, *extra])
    approve(a, old, *extra)
    approve(no, relevant=False)
    obj = ov("dag", [a.id], start="2026-10-06T22:00:00Z")
    obj.update(change)
    for b in obj["bullets"]:
        b["item_ids"] = [{"A": a.id, "OLD": old.id, "NO": no.id}.get(x, x) for x in b["item_ids"]]
    write_overview("dag", obj)
    assert validate("dag", archive=True) == 1
    out = capsys.readouterr().out
    assert "data/overview/dag.json: " in out
    assert message in out
    assert not (paths.OVERVIEW_ARCHIVE_DIR / "dag-2026-10-07.json").exists()


def test_validate_fails_when_source_is_no_longer_active(repo, capsys):
    """Et gyldigt overblik bliver ugyldigt, når en kilde det henviser til, ikke længere er aktiv."""
    a, z = cand("a", hours_ago=1), cand("z", source="zwe", hours_ago=2)
    store.save_candidates([a, z])
    approve(a, z)
    write_overview("dag", ov("dag", [a.id, z.id], start="2026-10-06T22:00:00Z", n=2))
    assert validate() == 0
    paused = SOURCES_YAML.replace("basis: organisation,", "basis: organisation, status: planlagt,")
    assert paused != SOURCES_YAML
    paths.SOURCES_FILE.write_text(paused, encoding="utf-8")
    capsys.readouterr()
    assert validate() == 1
    assert f"data/overview/dag.json: punkt 1: item_id '{z.id}' er ikke et godkendt indslag i vinduet" in (
        capsys.readouterr().out
    )


def test_validate_schema_error_and_missing(repo, capsys):
    (paths.OVERVIEW_DIR / "uge.json").write_text('{"period":"uge"}', encoding="utf-8")
    assert validate() == 1
    out = capsys.readouterr().out
    assert "data/overview/uge.json: window: Field required" in out
    assert validate("maaned") == 1
    assert "filen findes ikke" in capsys.readouterr().out
    (paths.OVERVIEW_DIR / "uge.json").unlink()
    assert validate() == 0
