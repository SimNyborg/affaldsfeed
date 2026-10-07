"""Test af store.py: atomisk skrivning, kun ved ændring, månedsfiler, oprydning og kildeforslag."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from affaldsfeed import paths, store
from affaldsfeed.models import Candidate, Rejected, SourceState, Why

FIXTURES = Path(__file__).resolve().parent / "fixtures"
NOW = datetime(2026, 10, 7, 8, 5, tzinfo=UTC)


def _fakes():
    name = "affaldsfeed_test_fakes"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, FIXTURES / "fakes.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return sys.modules[name]


@pytest.fixture
def env(tmp_path, monkeypatch):
    return _fakes().setup_env(tmp_path, monkeypatch)


def _why(decision="vis", reason=None) -> Why:
    return Why(filter="normal", score=4, decision=decision, hits=["titel: affald*"], reason=reason)


def _cand(cid: str, first_seen: datetime, title: str = "Affald i kommunen") -> Candidate:
    return Candidate(
        id=cid,
        url=f"https://eksempel.dk/{cid}",
        title=title,
        source="testmedie",
        published=first_seen,
        date_quality="kilde",
        first_seen=first_seen,
        why=_why(),
    )


def _rej(rid: str, first_seen: datetime) -> Rejected:
    return Rejected(
        id=rid, url=f"https://eksempel.dk/{rid}", title="Fodbold", source="testmedie", first_seen=first_seen,
        why=_why("afvist", "intet affaldsord"),
    )


def test_write_jsonl_only_on_change_and_format(tmp_path):
    p = tmp_path / "sub" / "x.jsonl"
    recs = [_cand("bbbbbbbbbbbb", NOW, "Ærlig talt: æøå"), _cand("aaaaaaaaaaaa", NOW)]
    assert store.write_jsonl(p, recs, sort_key=lambda c: c.id) is True
    assert store.write_jsonl(p, recs, sort_key=lambda c: c.id) is False
    raw = p.read_bytes()
    assert raw.endswith(b"\n") and b"\r\n" not in raw
    lines = raw.decode("utf-8").splitlines()
    assert [json.loads(line)["id"] for line in lines] == ["aaaaaaaaaaaa", "bbbbbbbbbbbb"]
    assert "æøå" in lines[1]  # ensure_ascii=False
    assert '"first_seen":"2026-10-07T08:05:00Z"' in lines[0]
    assert not list(p.parent.glob("*.tmp"))
    assert [c.id for c in store.read_jsonl(p, Candidate)] == ["aaaaaaaaaaaa", "bbbbbbbbbbbb"]


def test_old_candidate_lines_without_places(env):
    # En linje skrevet før stedmærkningen (uden "places") kan stadig læses og får en tom liste
    old = _cand("aaaaaaaaaaaa", NOW).model_dump(mode="json")
    del old["places"]
    path = paths.CANDIDATES_DIR / "2026-10.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(old, ensure_ascii=False) + "\n", encoding="utf-8")
    [c] = store.load_candidates()
    assert c.places == [] and "places" not in c.model_fields_set
    # Gemmes den igen, står feltet der
    store.save_candidates([c.model_copy(update={"title": "Ny titel"})])
    assert json.loads(path.read_text(encoding="utf-8"))["places"] == []


def test_read_jsonl_skips_invalid_lines(tmp_path):
    p = tmp_path / "x.jsonl"
    good = json.dumps(_cand("aaaaaaaaaaaa", NOW).model_dump(mode="json"))
    p.write_text(good + "\n{ikke json\n\n" + '{"id": "mangler felter"}\n', encoding="utf-8")
    assert [c.id for c in store.read_jsonl(p, Candidate)] == ["aaaaaaaaaaaa"]
    assert store.read_jsonl(tmp_path / "findes-ikke.jsonl", Candidate) == []


def test_read_and_write_json(tmp_path):
    p = tmp_path / "a.json"
    assert store.read_json(p, {"x": 1}) == {"x": 1}
    assert store.write_json(p, {"b": "ø", "a": [1]}) is True
    assert store.write_json(p, {"b": "ø", "a": [1]}) is False
    assert store.read_json(p, None) == {"b": "ø", "a": [1]}
    p.write_text("{ødelagt", encoding="utf-8")
    assert store.read_json(p, "standard") == "standard"


def test_save_and_load_candidates_by_month(env):
    sep = datetime(2026, 9, 30, 23, 0, tzinfo=UTC)
    recs = [_cand("cccccccccccc", NOW), _cand("aaaaaaaaaaaa", NOW), _cand("bbbbbbbbbbbb", sep)]
    assert store.save_candidates(recs) == 3
    assert sorted(f.name for f in paths.CANDIDATES_DIR.iterdir()) == ["2026-09.jsonl", "2026-10.jsonl"]
    oct_ids = [json.loads(line)["id"] for line in (paths.CANDIDATES_DIR / "2026-10.jsonl").read_text().splitlines()]
    assert oct_ids == ["aaaaaaaaaaaa", "cccccccccccc"]

    # Samme post igen: ingen ændring. Ny titel: én ændring, stadig ét id
    assert store.save_candidates([_cand("aaaaaaaaaaaa", NOW)]) == 0
    assert store.save_candidates([_cand("aaaaaaaaaaaa", NOW, "Ny titel om affald")]) == 1
    all_c = store.load_candidates()
    assert [c.id for c in all_c].count("aaaaaaaaaaaa") == 1
    assert next(c for c in all_c if c.id == "aaaaaaaaaaaa").title == "Ny titel om affald"
    assert [c.id for c in store.load_candidates(since=datetime(2026, 10, 1, tzinfo=UTC))] == [
        "aaaaaaaaaaaa",
        "cccccccccccc",
    ]


def test_save_rejected_merges_and_prunes(env):
    old = datetime(2026, 6, 1, tzinfo=UTC)
    store.write_jsonl(paths.REJECTED_DIR / "2026-06.jsonl", [_rej("oooooooooooo", old)], sort_key=lambda r: r.id)
    first = datetime(2026, 10, 1, tzinfo=UTC)
    assert store.save_rejected([_rej("aaaaaaaaaaaa", first)], keep_days=90, now=NOW) == 1
    # Genfund senere: første fund bevares, og der kommer ingen dublet
    assert store.save_rejected([_rej("aaaaaaaaaaaa", NOW)], keep_days=90, now=NOW) == 0
    recs = store.load_rejected()
    assert [r.id for r in recs] == ["aaaaaaaaaaaa"]
    assert recs[0].first_seen == first
    assert not (paths.REJECTED_DIR / "2026-06.jsonl").exists()  # ældre end 90 dage


def test_source_states_roundtrip(env):
    st = SourceState(last_ok=date(2026, 10, 7), last_attempt=NOW, fails=0, items_30d=3, first_run_done=True, health="groen")
    assert store.save_source_states({"b": st, "a": SourceState()}) is True
    raw = json.loads((paths.STATE_DIR / "sources.json").read_text(encoding="utf-8"))
    assert list(raw) == ["a", "b"]
    assert raw["b"]["last_ok"] == "2026-10-07"
    assert raw["b"]["last_attempt"] == "2026-10-07T08:05:00Z"
    assert store.load_source_states()["b"] == st
    assert store.save_source_states({"b": st, "a": SourceState()}) is False


def test_http_and_robots_cache_sorted(env):
    store.save_http_cache({"https://b.dk/rss": {"etag": '"1"'}, "https://a.dk/rss": {"last_modified": "x"}})
    assert list(store.load_http_cache()) == ["https://a.dk/rss", "https://b.dk/rss"]
    store.save_robots_cache({"b.dk": {"fetched": "2026-10-07T08:00:00Z", "body": ""}})
    assert store.load_robots_cache()["b.dk"]["body"] == ""


def test_kildeforslag_counts_each_article_once(env):
    d = store.load_kildeforslag()
    unknown = [
        ("lokalavis.dk", "Lokalavisen", "https://lokalavis.dk/a"),
        ("lokalavis.dk", "Lokalavisen", "https://lokalavis.dk/a?utm_source=x"),  # samme artikel
        ("lokalavis.dk", "Lokalavisen", "https://lokalavis.dk/b"),
        ("blog.dk", "Blog", "https://blog.dk/x"),
    ]
    assert store.merge_kildeforslag(d, unknown, NOW) == 3
    assert store.merge_kildeforslag(d, unknown, NOW) == 0
    assert d["lokalavis.dk"]["count"] == 2
    assert d["lokalavis.dk"]["examples"] == ["https://lokalavis.dk/b", "https://lokalavis.dk/a"]
    assert d["lokalavis.dk"]["last_seen"] == "2026-10-07T08:05:00Z"
    assert store.save_kildeforslag(d) is True
    assert store.save_kildeforslag(d) is False
    md = (paths.STATE_DIR / "kildeforslag.md").read_text(encoding="utf-8")
    assert md.index("lokalavis.dk") < md.index("blog.dk")
    assert "| lokalavis.dk | Lokalavisen | 2 | 2026-10-07 |" in md
    assert store.load_kildeforslag()["blog.dk"]["count"] == 1
