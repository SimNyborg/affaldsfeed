"""Visningslogik (KONTRAKTER §6.3): claude/fallback, ai:false, overrides, sweep-fund og since."""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timedelta

import pytest

from affaldsfeed.config import load_config
from affaldsfeed.display import (
    build_display_items,
    known_sources,
    source_category_map,
    split_ids,
    story_hints,
)
from affaldsfeed.models import Candidate, Geo, Judgment, Override, Publisher, Source, Why
from affaldsfeed.normalize import item_id
from affaldsfeed.timeutil import parse_iso

NOW = parse_iso("2026-10-07T10:00:00Z")
SINCE = NOW - timedelta(days=60)


def _src(id: str, category: str, **kw) -> Source:
    data = {
        "id": id,
        "name": id.upper(),
        "category": category,
        "homepage": f"https://{id}.dk",
        "feeds": [f"https://{id}.dk/rss"],
        "basis": "redaktionelt",
        "checked": date(2026, 10, 1),
    }
    data.update(kw)
    return Source(**data)


SOURCES = [
    _src("kefm", "myndighed"),
    _src("altinget", "fagmedie"),
    _src("dr", "nyhedsmedie", ai=False),
    _src("zwe", "eu_norden", lang="en"),
    _src("gnews", "nyhedsmedie", method="search", feeds=["https://news.google.com/rss/search?q={q}"]),
    _src("dakofa", "organisation", status="planlagt"),
]
PUBLISHERS = [Publisher(id="fyens", name="Fyens Stiftstidende", category="nyhedsmedie", domains=["fyens.dk"],
                        basis="redaktionelt")]


@pytest.fixture(scope="module")
def base_config():
    return dataclasses.replace(load_config(), publishers=PUBLISHERS, overrides=[])


def cand(slug: str, source: str = "altinget", decision: str = "vis", hours_ago: float = 2, **kw) -> Candidate:
    url = f"https://{source}.dk/{slug}"
    t = NOW - timedelta(hours=hours_ago)
    data = {
        "id": item_id(url),
        "url": url,
        "title": f"Titel om {slug}",
        "teaser": "Kort teaser om affald.",
        "source": source,
        "published": t,
        "date_quality": "kilde",
        "first_seen": t + timedelta(minutes=10),
        "topics": ["sortering"],
        "genre": "nyhed",
        "why": Why(filter="normal", score=4 if decision == "vis" else 2, decision=decision, hits=["titel: affald"]),
    }
    data.update(kw)
    return Candidate(**data)


def judge(c_or_id, relevant: bool = True, **kw) -> Judgment:
    jid = c_or_id if isinstance(c_or_id, str) else c_or_id.id
    data = {"id": jid, "relevant": relevant, "reason": "test", "judged_at": "2026-10-07T09:25:00Z"}
    data.update(kw)
    return Judgment.model_validate(data)


def build(config, candidates, judgments, mode="claude", since=SINCE):
    return build_display_items(config, SOURCES, candidates, {j.id: j for j in judgments}, mode, NOW, since)


def ids(items) -> set[str]:
    return {d.id for d in items}


def test_claude_mode_shows_only_relevant(base_config):
    a, b, c = cand("a"), cand("b"), cand("c")
    out = build(base_config, [a, b, c], [judge(a, True, reason="Nye regler"), judge(b, False)])
    assert ids(out) == {a.id}
    item = out[0]
    assert item.reviewed is True
    assert item.reason == "Nye regler"
    assert item.story == a.id


def test_fallback_shows_unjudged_vis_unreviewed(base_config):
    a, b, g, h = cand("a"), cand("b"), cand("g", decision="graa"), cand("h")
    out = build(base_config, [a, b, g, h], [judge(a, True), judge(h, False)], mode="fallback")
    by_id = {d.id: d for d in out}
    assert set(by_id) == {a.id, b.id}
    assert by_id[a.id].reviewed is True
    assert by_id[b.id].reviewed is False
    assert by_id[b.id].reason is None


def test_ai_false_source_uses_rules_only(base_config):
    v = cand("v", source="dr")
    g = cand("g", source="dr", decision="graa")
    out = build(base_config, [v, g], [judge(v, False), judge(g, True)])
    assert ids(out) == {v.id}
    assert out[0].reviewed is False


def test_claude_topics_and_genre_only_when_set(base_config):
    a = cand("a", topics=["gebyrer"], genre="debat")
    b = cand("b", topics=["gebyrer"], genre="debat")
    c = cand("c", topics=["gebyrer"])
    js = [
        judge(a),  # sætter hverken topics eller genre
        judge(b, topics=["regler", "udbud"], genre="analyse"),
        judge(c, topics=[]),  # bevidst uden tema
    ]
    by_id = {d.id: d for d in build(base_config, [a, b, c], js)}
    assert (by_id[a.id].topics, by_id[a.id].genre) == (["gebyrer"], "debat")
    assert (by_id[b.id].topics, by_id[b.id].genre) == (["regler", "udbud"], "analyse")
    assert by_id[c.id].topics == []


def test_summary_only_for_non_danish(base_config):
    en = cand("en", source="zwe", lang="en")
    da = cand("da")
    out = build(base_config, [en, da], [judge(en, summary_da="Dansk resumé"), judge(da, summary_da="Bør ignoreres")])
    by_id = {d.id: d for d in out}
    assert by_id[en.id].summary_da == "Dansk resumé"
    assert by_id[da.id].summary_da is None


def test_overrides(base_config):
    a, b, c, d = cand("a"), cand("b"), cand("c"), cand("pressemeddelelse-d")
    config = dataclasses.replace(
        base_config,
        overrides=[
            Override(match={"id": a.id}, action="skjul"),
            Override(match={"id": b.id}, action="vis"),
            Override(match={"id": c.id}, action="tema", value=["tekstiler", "klima"]),
            Override(match={"url_regex": r"pressemeddelelse-d$"}, action="genre", value="pressemeddelelse"),
        ],
    )
    # a er godkendt men skjules; b er uvurderet men vises (claude-tilstand)
    out = build(config, [a, b, c, d], [judge(a), judge(c), judge(d)])
    by_id = {x.id: x for x in out}
    assert set(by_id) == {b.id, c.id, d.id}
    assert by_id[b.id].reviewed is True
    assert by_id[c.id].topics == ["tekstiler", "klima"]
    assert by_id[d.id].genre == "pressemeddelelse"


def test_since_uses_published_then_first_seen(base_config):
    old = cand("old", hours_ago=24 * 61)
    undated = cand("undated", hours_ago=24 * 61, published=None, date_quality="fundet",
                   first_seen=NOW - timedelta(days=1))
    out = build(base_config, [old, undated], [judge(old), judge(undated)])
    assert ids(out) == {undated.id}


def test_unknown_and_inactive_sources_are_skipped(base_config):
    planned = cand("p", source="dakofa")
    gone = cand("g", source="findes-ikke")
    out = build(base_config, [planned, gone], [judge(planned), judge(gone)], mode="fallback")
    assert out == []


def test_sweep_items(base_config):
    url = "https://fyens.dk/artikel/ny-affaldsordning"
    ok = judge(item_id(url), new_item={"url": url, "title": "Ny affaldsordning i Odense", "source": "fyens",
                                       "published": "2026-10-07T06:00:00Z"})
    url2 = "https://ukendt.dk/x"
    unknown = judge(item_id(url2), new_item={"url": url2, "title": "X", "source": "ukendt"})
    url3 = "https://fyens.dk/fremtid"
    future = judge(item_id(url3), new_item={"url": url3, "title": "Fremtid", "source": "fyens",
                                            "published": "2026-10-09T06:00:00Z"})
    out = build(base_config, [], [ok, unknown, future])
    by_id = {d.id: d for d in out}
    assert set(by_id) == {ok.id, future.id}
    assert by_id[ok.id].source == "fyens"
    assert by_id[ok.id].date_quality == "kilde"
    assert by_id[ok.id].reviewed is True
    assert by_id[ok.id].why is None
    assert by_id[future.id].date_quality == "fundet"
    assert by_id[future.id].published == future.judged_at


def test_sorted_newest_first_then_id(base_config):
    a, b, c = cand("a", hours_ago=5), cand("b", hours_ago=1), cand("c", hours_ago=1)
    out = build(base_config, [a, b, c], [judge(a), judge(b), judge(c)])
    assert [d.id for d in out] == sorted([b.id, c.id]) + [a.id]


def test_teaser_is_shortened(base_config):
    long = cand("long", teaser="ord " * 120)
    out = build(base_config, [long], [judge(long)])
    assert len(out[0].teaser) <= base_config.settings.teaser_display_max
    assert out[0].teaser.endswith("…")


def test_source_maps_and_hints():
    info = known_sources(SOURCES, PUBLISHERS)
    assert set(info) == {"kefm", "altinget", "dr", "zwe", "fyens"}
    assert info["fyens"].via_search is True
    assert info["dr"].ai is False
    cats = source_category_map(SOURCES, PUBLISHERS)
    assert cats["kefm"] == "myndighed" and cats["fyens"] == "nyhedsmedie"
    js = {
        "a": judge("a", story_hint="b"),
        "c": judge("c"),
        "d": judge("d", story_hint="d"),
    }
    assert story_hints(js) == [("a", "b")]


def test_split_ids(base_config):
    a, b = cand("a"), cand("b")
    config = dataclasses.replace(base_config, overrides=[Override(match={"id": a.id}, action="split")])
    items = build(config, [a, b], [judge(a), judge(b)])
    assert split_ids(config, items) == {a.id}


def test_places_from_judgment_or_rules(base_config):
    rules = ["k:nyborg", "b:ullerslev"]
    keep, none_, clear, replace = (cand(s, places=rules) for s in ("keep", "none", "clear", "replace"))
    js = [
        judge(keep),  # places mangler: behold regelmærkerne
        judge(none_, places=None),
        judge(clear, places=[]),  # nationalt
        judge(replace, places=["r:syddanmark", "b:ullerslev"]),
    ]
    by_id = {d.id: d for d in build(base_config, [keep, none_, clear, replace], js)}
    assert by_id[keep.id].places == rules
    assert by_id[none_.id].places == rules
    assert by_id[clear.id].places == []
    assert by_id[replace.id].places == ["r:syddanmark", "b:ullerslev"]


def test_places_rules_only_and_fallback(base_config):
    rules_only = cand("dr", source="dr", places=["k:aarhus"])
    unjudged = cand("venter", places=["k:odense"])
    out = build(base_config, [rules_only, unjudged], [judge(rules_only, places=[])], mode="fallback")
    by_id = {d.id: d for d in out}
    assert by_id[rules_only.id].places == ["k:aarhus"]  # ai:false ser bort fra vurderingen
    assert by_id[unjudged.id].places == ["k:odense"]


def test_unknown_place_ids_are_dropped(base_config):
    a = cand("a", places=["k:nyborg", "b:findes-ikke"])
    assert build(base_config, [a], [judge(a)])[0].places == ["k:nyborg"]
    no_geo = dataclasses.replace(base_config, geo=Geo())
    assert build(no_geo, [a], [judge(a)])[0].places == []


def test_sweep_places(base_config):
    url = "https://fyens.dk/artikel/ullerslev"
    rules = judge(item_id(url), new_item={"url": url, "title": "Ny genbrugsplads i Ullerslev",
                                          "teaser": "Nyborg Kommune bygger pladsen.", "source": "fyens"})
    url2 = "https://fyens.dk/artikel/odense"
    given = judge(item_id(url2), places=["k:odense"],
                  new_item={"url": url2, "title": "Ny genbrugsplads i Ullerslev", "source": "fyens"})
    by_id = {d.id: d for d in build(base_config, [], [rules, given])}
    assert by_id[rules.id].places == ["k:nyborg", "b:ullerslev"]
    assert by_id[given.id].places == ["k:odense"]


def test_datetimes_are_utc(base_config):
    a = cand("a", published=datetime.fromisoformat("2026-10-07T11:00:00+02:00"))
    out = build(base_config, [a], [judge(a)])
    assert out[0].model_dump(mode="json")["published"] == "2026-10-07T09:00:00Z"


def test_items_under_a_replaced_id_follow_the_new_source(base_config):
    """En udgiver fra medier.yaml er blevet til en kilde: gemte indslag vises under kilden (Source.replaces)."""
    sources = [*SOURCES, _src("tv2-nyheder", "nyhedsmedie", replaces=["tv2-dk"])]
    old = cand("gammel", source="tv2-dk")
    out = build_display_items(base_config, sources, [old], {old.id: judge(old)}, "claude", NOW, SINCE)
    assert [d.source for d in out] == ["tv2-nyheder"]
    info = known_sources(sources, base_config.publishers)
    assert info["tv2-dk"].id == "tv2-nyheder"
    # Uden replaces forsvinder indslaget (ukendt afsender)
    assert build(base_config, [old], [judge(old)]) == []
