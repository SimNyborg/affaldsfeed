"""Tidslinjen (KONTRAKTER §7.3): model, indlæsning, timeline-input, validate-timeline og eksport."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from affaldsfeed import export, paths, store, timeline
from affaldsfeed.config import load_config
from affaldsfeed.models import (
    Candidate,
    SourceState,
    TimelineDeletion,
    TimelineEvent,
    TimelineFeed,
    Why,
    parse_timeline_line,
)
from affaldsfeed.normalize import item_id
from affaldsfeed.timeutil import iso, parse_iso

NOW = parse_iso("2026-10-07T20:25:00Z")  # 22.25 i København
REAL_CONFIG = paths.CONFIG_DIR

SOURCES_YAML = """
- {id: kefm, name: "Klima-, Energi- og Forsyningsministeriet", category: myndighed, homepage: "https://kefm.dk",
   feeds: "https://kefm.dk/rss", basis: offentlig, checked: 2026-10-01}
- {id: altinget, name: Altinget, category: fagmedie, homepage: "https://altinget.dk",
   feeds: "https://altinget.dk/rss", basis: redaktionelt, checked: 2026-10-01}
- {id: dr, name: DR, category: nyhedsmedie, homepage: "https://dr.dk", feeds: "https://dr.dk/rss",
   basis: redaktionelt, checked: 2026-10-01}
"""


@pytest.fixture
def repo(tmp_path, monkeypatch):
    shutil.copytree(REAL_CONFIG, tmp_path / "config")
    # Den almindelige drift: vindue på window_days (window_start afprøves for sig)
    settings = tmp_path / "config" / "settings.yaml"
    settings.write_text("".join(ln for ln in settings.read_text(encoding="utf-8").splitlines(keepends=True)
                                if not ln.startswith("window_start:")), encoding="utf-8")
    (tmp_path / "config" / "medier.yaml").write_text("[]\n", encoding="utf-8")
    (tmp_path / "sources.yaml").write_text(SOURCES_YAML, encoding="utf-8")
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("<!doctype html><title>Affaldsfeed</title>", encoding="utf-8")
    (tmp_path / "examples").mkdir()
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
    (data / "timeline").mkdir(parents=True)
    return tmp_path


def cand(slug: str, source: str = "altinget", days_ago: float = 1, title: str | None = None, **kw) -> Candidate:
    url = f"https://{source}.dk/{slug}"
    t = NOW - timedelta(days=days_ago)
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


def approve(*cands: Candidate, relevant: bool = True) -> None:
    store.save_candidates(list(cands))
    with (paths.JUDGMENTS_DIR / "2026-10-07.jsonl").open("a", encoding="utf-8") as f:
        for c in cands:
            line = {"id": c.id, "relevant": relevant, "reason": "test", "judged_at": "2026-10-07T20:00:00Z"}
            f.write(json.dumps(line, ensure_ascii=False) + "\n")


NAMES = {"kefm": "Klima-, Energi- og Forsyningsministeriet", "altinget": "Altinget", "dr": "DR"}


def ref(c: Candidate) -> dict:
    return {"id": c.id, "title": c.title, "url": c.url, "source": c.source, "source_name": NAMES[c.source],
            "published": iso(c.published)}


def event(eid: str, *cands: Candidate, updated: str = "2026-10-07T20:25:00Z", **kw) -> dict:
    data = {
        "id": eid,
        "date": eid[:10],
        "level": "milepael",
        "title": "Bred aftale om fælles model for affaldsgebyrer",
        "summary": "Regeringen og et flertal i Folketinget aftaler en fælles model for affaldsgebyrer.",
        "topics": ["gebyrer"],
        "places": [],
        "items": [ref(c) for c in cands],
        "updated": updated,
        "by": "claude-routine",
        "deleted": False,
    }
    data.update(kw)
    return data


def write(month: str, *lines: dict | str) -> None:
    path = paths.TIMELINE_DIR / f"{month}.jsonl"
    with path.open("a", encoding="utf-8") as f:
        for line in lines:
            f.write((line if isinstance(line, str) else json.dumps(line, ensure_ascii=False)) + "\n")


def validate(capsys, file: str | None = None, now: str = "2026-10-07T20:30:00Z") -> tuple[int, str]:
    code = timeline.main_validate_timeline(argparse.Namespace(file=file, now=now))
    return code, capsys.readouterr().out


def run_input(capsys, days: int | None = None, now: str = "2026-10-07T20:25:00Z") -> dict:
    assert timeline.main_timeline_input(argparse.Namespace(days=days, now=now)) == 0
    return json.loads(capsys.readouterr().out)


# ── model ───────────────────────────────────────────────────


def test_model_and_parse():
    c = cand("aftale", source="kefm")
    e = parse_timeline_line(json.dumps(event("2026-10-07-faelles-model", c)))
    assert isinstance(e, TimelineEvent) and e.date == date(2026, 10, 7) and e.deleted is False
    d = parse_timeline_line('{"id":"2026-10-07-faelles-model","deleted":true,"updated":"2026-10-08T20:00:00Z"}')
    assert isinstance(d, TimelineDeletion) and d.by == "claude-routine"
    # "deleted" kan udelades på en begivenhed
    raw = event("2026-10-07-faelles-model", c)
    del raw["deleted"], raw["by"]
    assert isinstance(parse_timeline_line(json.dumps(raw)), TimelineEvent)


@pytest.mark.parametrize(
    ("eid", "msg"),
    [
        ("2026-10-07-Stort-B", "små bogstaver"),
        ("2026-10-07--dobbelt", "små bogstaver"),
        ("2026-10-07", "små bogstaver"),
        ("2026-13-07-aftale", "ugyldig dato"),
        ("2026-10-07-" + "a" * 70, "højst 80 tegn"),
    ],
)
def test_bad_ids(eid, msg):
    with pytest.raises(ValidationError, match=msg):
        parse_timeline_line(json.dumps(event(eid, cand("x"))))


def test_items_topics_and_places_rules():
    c = cand("x")
    with pytest.raises(ValidationError, match="items"):
        TimelineEvent.model_validate(event("2026-10-07-tom"))
    with pytest.raises(ValidationError, match="flere gange"):
        TimelineEvent.model_validate(event("2026-10-07-dublet", c, c))
    many = [cand(f"x{i}") for i in range(9)]
    with pytest.raises(ValidationError, match="items"):
        TimelineEvent.model_validate(event("2026-10-07-mange", *many))
    with pytest.raises(ValidationError, match="topics"):
        TimelineEvent.model_validate(event("2026-10-07-x", c, topics=["gebyrer", "regler", "klima"]))
    with pytest.raises(ValidationError, match="mente du 'k:odense'"):
        TimelineEvent.model_validate(event("2026-10-07-x", c, places=["K:Odense"]))
    with pytest.raises(ValidationError, match="level"):
        TimelineEvent.model_validate(event("2026-10-07-x", c, level="stor"))
    bad_url = {**ref(c), "url": "javascript:alert(1)"}
    with pytest.raises(ValidationError, match="http"):
        TimelineEvent.model_validate({**event("2026-10-07-x", c), "items": [bad_url]})
    ok = TimelineEvent.model_validate(event("2026-10-07-x", c, places=["b:ullerslev", "k:nyborg"]))
    assert ok.places == ["k:nyborg", "b:ullerslev"]


# ── indlæsning ──────────────────────────────────────────────


def test_latest_line_wins_and_deletion(repo, caplog):
    a, b = cand("a"), cand("b")
    write("2026-09", event("2026-09-20-aftale", a, updated="2026-09-20T20:25:00Z"),
          event("2026-09-21-slettes", b, updated="2026-09-21T20:25:00Z"))
    write("2026-10", event("2026-09-20-aftale", a, b, updated="2026-10-01T20:25:00Z", title="Ny titel"),
          {"id": "2026-09-21-slettes", "deleted": True, "updated": "2026-10-02T20:25:00Z"}, "ikke json")
    events = timeline.load_events()
    assert list(events) == ["2026-09-20-aftale"]
    assert events["2026-09-20-aftale"].title == "Ny titel" and len(events["2026-09-20-aftale"].items) == 2
    assert "ugyldig linje i tidslinjen" in caplog.text


def test_week_label():
    assert timeline.week_label(date(2026, 10, 5)) == "uge 41 (5.-11. oktober 2026)"
    assert timeline.week_label(date(2026, 8, 31)) == "uge 36 (31. august-6. september 2026)"
    assert timeline.week_label(date(2026, 12, 28)) == "uge 53 (28. december 2026-3. januar 2027)"


# ── validate-timeline ───────────────────────────────────────


def test_valid_event(repo, capsys):
    c = cand("aftale", source="kefm")
    approve(c)
    write("2026-10", event("2026-10-06-faelles-model", c))
    code, out = validate(capsys)
    assert code == 0, out
    assert "validate-timeline: OK, 1 linjer i 1 filer, 1 begivenheder" in out


def test_no_files(repo, capsys):
    code, out = validate(capsys)
    assert code == 0 and "ingen tidslinjefiler" in out


def test_word_limits_and_dates(repo, capsys):
    c = cand("aftale", source="kefm")
    approve(c)
    write(
        "2026-10",
        event("2026-10-06-lang-titel", c, title=" ".join(["ord"] * 13)),
        event("2026-10-06-langt-resume", c, summary=" ".join(["ord"] * 41)),
        event("2026-10-08-fremtid", c),
        event("2026-10-06-sent", c, updated="2026-10-07T21:00:00Z"),
        event("2026-10-06-forkert-maaned", c, updated="2026-09-30T20:00:00Z"),
    )
    code, out = validate(capsys)
    assert code == 1
    assert "data/timeline/2026-10.jsonl:1: title har 13 ord (højst 12)" in out
    assert "2026-10.jsonl:2: summary har 41 ord (højst 40)" in out
    assert "2026-10.jsonl:3: date 2026-10-08 ligger i fremtiden" in out
    assert "2026-10.jsonl:4: updated 2026-10-07T21:00:00Z ligger i fremtiden" in out
    assert "2026-10.jsonl:5: updated er i 2026-09 i København; linjen hører til i data/timeline/2026-09.jsonl" in out


def test_items_must_be_approved_and_copied(repo, capsys):
    ok, rejected, unknown = cand("ok", source="kefm"), cand("afvist"), cand("ukendt")
    approve(ok)
    approve(rejected, relevant=False)
    store.save_candidates([unknown])
    wrong = {**ref(ok), "title": "Anden titel", "published": "2026-10-06T08:00:00Z"}
    write("2026-10", event("2026-10-06-a", rejected), event("2026-10-06-b", unknown),
          {**event("2026-10-06-c", ok), "items": [wrong]})
    code, out = validate(capsys)
    assert code == 1
    assert f"2026-10.jsonl:1: items: '{rejected.id}' er ikke et godkendt indslag" in out
    assert f"2026-10.jsonl:2: items: '{unknown.id}' er ikke et godkendt indslag" in out
    assert f"2026-10.jsonl:3: items: '{ok.id}' passer ikke med indslaget (title, published)" in out


def test_old_lines_and_kept_items_are_not_rechecked(repo, capsys):
    """Linjer skrevet for mere end 48 timer siden og indslag fra den forrige version tjekkes ikke igen."""
    gone, new = cand("forsvundet", days_ago=40), cand("ny", source="kefm")
    approve(new)  # gone er ikke (længere) godkendt
    write("2026-09", event("2026-08-28-gammel", gone, updated="2026-09-01T20:25:00Z"))
    write("2026-10", event("2026-08-28-gammel", gone, new, updated="2026-10-07T20:25:00Z"))
    code, out = validate(capsys)
    assert code == 0, out


def test_deletions(repo, capsys):
    c = cand("aftale", source="kefm")
    approve(c)
    write("2026-10", event("2026-10-06-aftale", c),
          {"id": "2026-10-06-aftale", "deleted": True, "updated": "2026-10-07T20:26:00Z"},
          {"id": "2026-10-06-aftale", "deleted": True, "updated": "2026-10-07T20:27:00Z"},
          {"id": "2026-10-05-findes-ikke", "deleted": True, "updated": "2026-10-07T20:27:00Z"})
    code, out = validate(capsys)
    assert code == 1
    assert "2026-10.jsonl:3: sletter '2026-10-06-aftale', som ikke findes eller allerede er slettet" in out
    assert "2026-10.jsonl:4: sletter '2026-10-05-findes-ikke'" in out
    assert "2026-10.jsonl:2:" not in out


def test_max_per_week(repo, capsys):
    cands = [cand(f"c{i}", source="kefm") for i in range(3)]
    approve(*cands)
    # uge 41: mandag 5. oktober. Den gamle begivenhed i ugen tæller med
    write("2026-10", event("2026-10-05-gammel", cands[0], updated="2026-10-05T20:25:00Z"))
    days = ["2026-10-06", "2026-10-07"]
    write("2026-10", *(event(f"{d}-ny-{i}", c) for i, (d, c) in enumerate(zip(days, cands[1:], strict=True))))
    code, out = validate(capsys)
    assert code == 1
    assert "2026-10.jsonl:2: uge 41 (5.-11. oktober 2026) har 3 begivenheder; højst 2" in out
    # En sletning af den mindst vigtige gør ugen gyldig igen
    write("2026-10", {"id": "2026-10-05-gammel", "deleted": True, "updated": "2026-10-07T20:28:00Z"})
    code, out = validate(capsys)
    assert code == 0, out


def test_unknown_place_is_a_warning(repo, capsys):
    c = cand("aftale", source="kefm")
    approve(c)
    write("2026-10", event("2026-10-06-aftale", c, places=["k:kobenhavn"]))
    code, out = validate(capsys)
    assert code == 0
    assert "ADVARSEL data/timeline/2026-10.jsonl:1: places: ukendt sted-id 'k:kobenhavn' (mente du 'k:koebenhavn'?)" in out


def test_schema_errors_and_file_name(repo, capsys):
    write("2026-10", '{"id":"2026-10-06-x","date":"2026-10-06"}', "ikke json")
    bad = paths.TIMELINE_DIR / "oktober.jsonl"
    bad.write_text("", encoding="utf-8")
    code, out = validate(capsys)
    assert code == 1
    assert "2026-10.jsonl:1: level: Field required" in out
    assert "2026-10.jsonl:2: ugyldig JSON" in out
    code, out = validate(capsys, file="data/timeline/oktober.jsonl")
    assert "data/timeline/oktober.jsonl:0: filnavnet skal være ÅÅÅÅ-MM.jsonl" in out


def test_file_option_uses_history_from_other_files(repo, capsys):
    c = cand("aftale", source="kefm", days_ago=10)
    approve(c)
    write("2026-09", event("2026-09-27-aftale", c, updated="2026-09-28T20:25:00Z"))
    write("2026-10", {"id": "2026-09-27-aftale", "deleted": True, "updated": "2026-10-07T20:25:00Z"})
    code, out = validate(capsys, file="data/timeline/2026-10.jsonl")
    assert code == 0, out
    assert "1 linjer i 1 filer, 0 begivenheder" in out


# ── timeline-input ──────────────────────────────────────────


def test_input_first_fill_uses_60_days(repo, capsys):
    old = cand("gammel", source="kefm", days_ago=50, title="Ny bekendtgørelse om affald er vedtaget")
    new = cand("ny", days_ago=1, title="Kommunerne får nye regler for affaldsgebyrer")
    copy = cand("ny-dr", source="dr", days_ago=0.9, title="Kommunerne får nye regler for affaldsgebyrer")
    approve(old, new, copy)
    approve(cand("afvist"), relevant=False)
    out = run_input(capsys)
    assert out["first_fill"] is True
    assert out["window"] == {"start": "2026-08-08T20:25:00Z", "end": "2026-10-07T20:25:00Z"}
    assert [s["id"] for s in out["stories"]] == [old.id, new.id]  # myndighed før fagmedie
    story = out["stories"][1]
    assert story["story_size"] == 2 and story["also"] == [ref(copy)]
    assert {k: story[k] for k in ("title", "url", "source", "source_name", "published")} == {
        k: v for k, v in ref(new).items() if k != "id"}
    assert story["in_events"] == []
    assert out["rules"]["max_per_week"] == 2 and out["rules"]["title_max_words"] == 12
    assert out["events"] == []
    assert out["weeks"][0]["monday"] == "2026-08-03" and out["weeks"][-1]["monday"] == "2026-10-05"


def test_input_with_events(repo, capsys):
    old = cand("gammel", source="kefm", days_ago=5)
    new = cand("ny", days_ago=1)
    approve(old, new)
    write("2026-10", event("2026-10-02-aftale", old, updated="2026-10-02T20:25:00Z"),
          event("2026-07-01-gammel", old, updated="2026-10-02T20:26:00Z", date="2026-07-01"))
    out = run_input(capsys)
    assert out["first_fill"] is False
    assert [s["id"] for s in out["stories"]] == [new.id]  # kun de sidste 3 dage
    assert [e["id"] for e in out["events"]] == ["2026-10-02-aftale"]  # kun de sidste 60 dage
    assert "by" not in out["events"][0] and "deleted" not in out["events"][0]
    # Vinduet starter søndag 4. oktober (uge 40); aftalen 2. oktober ligger i uge 40
    assert [(w["monday"], w["events"]) for w in out["weeks"]] == [("2026-09-28", 1), ("2026-10-05", 0)]
    out = run_input(capsys, days=6)
    by_id = {s["id"]: s for s in out["stories"]}
    assert by_id[old.id]["in_events"] == ["2026-07-01-gammel", "2026-10-02-aftale"]
    assert by_id[new.id]["in_events"] == []


# ── Opfyldning bagud (§7.3) ────────────────────────────────


def set_fill(repo, window_start: str = "2026-08-01", until: str = "2026-09", max_stories: int = 150) -> None:
    settings = repo / "config" / "settings.yaml"
    text = settings.read_text(encoding="utf-8")
    text = text.replace('fill_until: "2026-10"', f'fill_until: "{until}"').replace(
        "fill_max_stories: 150", f"fill_max_stories: {max_stories}")
    settings.write_text(text + f"window_start: {window_start}\n", encoding="utf-8")


def backfilled(*sids: str, failing: tuple[str, ...] = ()) -> None:
    states = {sid: SourceState(backfilled_from=date(2026, 8, 1), first_run_done=True) for sid in sids}
    states |= {sid: SourceState(fails=2, health="gul") for sid in failing}
    store.save_source_states(states)


def run_fill(capsys, now: str = "2026-10-07T20:25:00Z") -> dict:
    assert timeline.main_timeline_input(argparse.Namespace(days=None, fill=True, fill_done=None, now=now)) == 0
    return json.loads(capsys.readouterr().out)


def fill_done(capsys, month: str, now: str = "2026-10-07T20:40:00Z") -> tuple[int, str]:
    code = timeline.main_timeline_input(argparse.Namespace(days=None, fill=False, fill_done=month, now=now))
    return code, capsys.readouterr().out


def test_fill_months_and_month_bounds(repo):
    settings = load_config(paths.CONFIG_DIR).settings
    assert timeline.fill_months(settings) == []  # uden window_start
    settings = settings.model_copy(update={
        "window_start": date(2025, 11, 15),
        "timeline": settings.timeline.model_copy(update={"fill_until": "2026-02"}),
    })
    assert timeline.fill_months(settings) == ["2025-11", "2025-12", "2026-01", "2026-02"]
    start, end = timeline.month_bounds("2026-03")
    assert (iso(start), iso(end)) == ("2026-02-28T23:00:00Z", "2026-03-31T22:00:00Z")  # sommertid fra 29. marts
    assert iso(timeline.month_bounds("2026-12")[1]) == "2026-12-31T23:00:00Z"


def test_fill_waits_for_the_backfill_and_the_routine_and_goes_month_by_month(repo, capsys, caplog):
    set_fill(repo)
    found = NOW - timedelta(hours=2)  # fundet af bagudindsamlingen lige nu
    aug = cand("aug-aftale", source="kefm", days_ago=60, first_seen=found)
    sep = cand("sep-plan", source="kefm", days_ago=30, first_seen=found)
    store.save_candidates([aug, sep])
    out = run_fill(capsys)
    assert out["fill_month"] is None and out["months_left"] == ["2026-08", "2026-09"]
    assert out["status"] == "venter på bagudindsamlingen hos 3 kilder, fx altinget, dr, kefm"
    backfilled("kefm", "altinget", failing=("dr",))  # en kilde med fejl venter man ikke på
    out = run_fill(capsys)
    assert out["status"] == "venter på routinens vurdering af 1 indslag fra 2026-08"
    approve(aug)
    out = run_fill(capsys)
    assert out["fill_month"] == "2026-08" and out["first_fill"] is False
    assert list(out)[:4] == ["now", "first_fill", "fill_month", "window"]
    assert [s["id"] for s in out["stories"]] == [aug.id]
    assert out["window"] == {"start": "2026-07-31T22:00:00Z", "end": "2026-08-31T22:00:00Z"}
    assert out["weeks"][0]["monday"] == "2026-07-27" and out["weeks"][-1]["monday"] == "2026-08-31"

    code, text = fill_done(capsys, "2026-08")
    assert code == 0 and "2026-08 er markeret som fyldt; 1 måned tilbage" in text
    state = json.loads((paths.TIMELINE_DIR / "opfyldning.json").read_text(encoding="utf-8"))
    assert state == {"months": {"2026-08": "2026-10-07T20:40:00Z"}}
    assert run_fill(capsys)["status"] == "venter på routinens vurdering af 1 indslag fra 2026-09"
    approve(sep)
    assert run_fill(capsys)["fill_month"] == "2026-09"
    assert fill_done(capsys, "2026-09")[0] == 0
    out = run_fill(capsys)
    assert out["fill_month"] is None and out["status"] == "alle måneder er fyldt" and out["months_left"] == []
    assert fill_done(capsys, "2026-10")[0] == 1  # ikke en måned i opfyldningen
    assert "2026-10 er ikke en måned i opfyldningen (2026-08 til 2026-09)" in caplog.text


def test_fill_input_caps_stories_and_shows_events_around_the_month(repo, capsys):
    set_fill(repo, max_stories=2)
    backfilled("kefm", "altinget", "dr")
    a = cand("a", source="kefm", days_ago=60)
    b = cand("b", source="altinget", days_ago=59)
    c = cand("c", source="dr", days_ago=58)
    d = cand("d", source="kefm", days_ago=25)  # 12. september
    approve(a, b, c, d)
    write("2026-10",
          event("2026-07-28-foer", a), event("2026-09-05-efter", d),
          event("2026-07-01-for-tidligt", a), event("2026-09-20-for-sent", d))
    out = run_fill(capsys)
    assert out["fill_month"] == "2026-08"
    assert [s["id"] for s in out["stories"]] == [a.id, b.id]  # højst 2: myndighed før fagmedie før nyhedsmedie
    assert [e["id"] for e in out["events"]] == ["2026-09-05-efter", "2026-07-28-foer"]  # en uge til hver side


def test_validate_checks_the_fill_state(repo, capsys):
    c = cand("aftale", source="kefm")
    approve(c)
    write("2026-10", event("2026-10-06-faelles-model", c))
    (paths.TIMELINE_DIR / "opfyldning.json").write_text('{"months": {"2026-13": "x"}}', encoding="utf-8")
    code, out = validate(capsys)
    assert code == 1 and "data/timeline/opfyldning.json: skal være" in out
    (paths.TIMELINE_DIR / "opfyldning.json").write_text("{", encoding="utf-8")
    code, out = validate(capsys)
    assert code == 1 and "ikke gyldig JSON" in out


# ── eksport ─────────────────────────────────────────────────


def test_export_timeline(repo, tmp_path):
    a = cand("a", source="kefm", days_ago=3)
    b = cand("b", days_ago=2)
    gone = cand("gone", days_ago=90)
    approve(a, b)
    write("2026-10",
          event("2026-10-04-aftale", b, a, updated="2026-10-04T20:25:00Z", places=["k:nyborg", "k:findes-ikke"]),
          event("2026-07-01-gammel", gone, updated="2026-10-04T20:26:00Z", date="2026-07-01", level="vigtig"),
          event("2026-10-04-anden", b, updated="2026-10-04T20:27:00Z"),
          event("2026-10-03-slettet", b, updated="2026-10-04T20:28:00Z"),
          {"id": "2026-10-03-slettet", "deleted": True, "updated": "2026-10-04T20:29:00Z"})
    (paths.EXAMPLES_DIR / "timeline.sample.json").write_text('{"version":1}', encoding="utf-8")
    out = tmp_path / "_site"
    assert export.main_export(argparse.Namespace(out=str(out), now="2026-10-07T20:30:00Z")) == 0
    tl = json.loads((out / "data" / "timeline.json").read_text(encoding="utf-8"))
    TimelineFeed.model_validate(tl)
    assert (out / "data" / "timeline.sample.json").is_file()
    assert [e["id"] for e in tl["events"]] == ["2026-10-04-aftale", "2026-10-04-anden", "2026-07-01-gammel"]
    first = tl["events"][0]
    assert [r["id"] for r in first["items"]] == [a.id, b.id]  # ældste først
    assert first["places"] == ["k:nyborg"]  # ukendte steder udelades
    assert tl["places"] == [{"id": "k:nyborg", "navn": "Nyborg Kommune", "kort": "Nyborg"}]
    assert "by" not in first and "deleted" not in first
    assert first["story"] in (a.id, b.id)
    assert tl["events"][2]["story"] is None  # indslaget er ude af feedet
    assert {t["id"] for t in tl["topics"]} >= {"gebyrer", "regler"}


def test_export_without_timeline(repo, tmp_path):
    shutil.rmtree(paths.TIMELINE_DIR)
    out = tmp_path / "_site"
    assert export.main_export(argparse.Namespace(out=str(out), now="2026-10-07T20:30:00Z")) == 0
    tl = json.loads((out / "data" / "timeline.json").read_text(encoding="utf-8"))
    assert tl["events"] == [] and tl["places"] == []


# ── eksempelfilen ───────────────────────────────────────────


def test_sample_timeline_is_valid():
    tl = TimelineFeed.model_validate_json(
        (paths.EXAMPLES_DIR / "timeline.sample.json").read_text(encoding="utf-8"))
    events = tl.events
    assert len(events) >= 14
    months = {(e.date.year, e.date.month) for e in events}
    assert len(months) >= 14 and len({y for y, _ in months}) >= 2
    assert {e.level for e in events} == {"milepael", "vigtig"}
    assert [e.id for e in events] == [e.id for e in timeline.sort_events(events)]
    for e in events:
        assert timeline.word_count(e.title) <= timeline.TITLE_MAX_WORDS, e.id
        assert timeline.word_count(e.summary) <= timeline.SUMMARY_MAX_WORDS, e.id
        assert [r.id for r in e.items] == [r.id for r in sorted(e.items, key=timeline._ref_key)], e.id
    # Historien i feedet findes i eksempelfeedet
    feed = json.loads((paths.EXAMPLES_DIR / "feed.sample.json").read_text(encoding="utf-8"))
    stories = {it["story"] for it in feed["items"]}
    assert any(e.story for e in events)
    assert all(e.story in stories for e in events if e.story)
