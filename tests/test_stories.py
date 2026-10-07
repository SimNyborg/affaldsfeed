from __future__ import annotations

from datetime import UTC, datetime, timedelta

from affaldsfeed.models import DisplayItem
from affaldsfeed.stories import build_stories, group_stories

T0 = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
CATS = {
    "kefm": "myndighed",
    "arc": "kommunal",
    "altinget": "fagmedie",
    "avisen": "nyhedsmedie",
    "dr": "nyhedsmedie",
}
TITLE = "Kommuner skal sortere tekstiler fra nytår"


def item(iid: str, source: str, title: str = TITLE, hours: float = 0, published: bool = True) -> DisplayItem:
    when = T0 + timedelta(hours=hours)
    return DisplayItem(
        id=iid,
        story=iid,
        url=f"https://{source}.dk/{iid}",
        title=title,
        source=source,
        published=when if published else None,
        date_quality="kilde" if published else "fundet",
        first_seen=when,
    )


def groups(items, hints=(), window=3, max_age=7, **kw):
    return group_stories(list(items), CATS, list(hints), window, max_age, **kw)


def ids(gs):
    return [[it.id for it in g] for g in gs]


def test_same_title_within_window_is_one_story():
    gs = groups([item("a", "avisen", hours=0), item("b", "dr", hours=30)])
    assert ids(gs) == [["a", "b"]]


def test_title_tails_and_case_are_ignored():
    gs = groups(
        [item("a", "avisen", title=TITLE + " - Ritzau"), item("b", "dr", title=TITLE.upper() + " | DR")]
    )
    assert len(gs) == 1


def test_same_title_outside_window_is_separate():
    gs = groups([item("a", "avisen", hours=0), item("b", "dr", hours=24 * 3 + 1)])
    assert len(gs) == 2


def test_short_titles_are_not_merged():
    gs = groups([item("a", "arc", title="Ny affaldsplan"), item("b", "avisen", title="Ny affaldsplan")])
    assert len(gs) == 2


def test_duplicate_id_is_level_one():
    gs = groups([item("a", "avisen", title="Noget"), item("a", "avisen", title="Noget andet")])
    assert ids(gs) == [["a"]]
    assert gs[0][0].title == "Noget"


def test_main_is_lowest_rank_then_earliest():
    gs = groups(
        [
            item("med1", "avisen", hours=0),
            item("fag", "altinget", hours=1),
            item("kom", "arc", hours=5),
            item("myn", "kefm", hours=10),
            item("med2", "dr", hours=2),
        ]
    )
    assert ids(gs) == [["myn", "med1", "fag", "med2", "kom"]]


def test_equal_rank_earliest_wins():
    gs = groups([item("sen", "dr", hours=5), item("tidlig", "avisen", hours=1)])
    assert ids(gs)[0][0] == "tidlig"


def test_unknown_source_ranks_last():
    gs = groups([item("ukendt", "blog", hours=0), item("med", "avisen", hours=3)])
    assert ids(gs)[0][0] == "med"


def test_hints_join_different_titles():
    a = item("a", "kefm", title="Minister fremlægger ny affaldsreform for kommunerne")
    b = item("b", "avisen", title="Nu skal kommunerne sortere endnu mere", hours=4)
    c = item("c", "dr", title="Helt anden historie om vejret i dag", hours=4)
    gs = groups([a, b, c], hints=[("b", "a"), ("c", "ukendt-id")])
    assert sorted(ids(gs)) == [["a", "b"], ["c"]]


def test_hint_chain_is_transitive():
    a = item("a", "avisen", title="Første overskrift om affald i dag")
    b = item("b", "dr", title="Anden overskrift om samme affald", hours=1)
    c = item("c", "altinget", title="Tredje overskrift om affaldet her", hours=2)
    gs = groups([a, b, c], hints=[("a", "b"), ("b", "c")])
    assert ids(gs) == [["c", "a", "b"]]


def test_no_items_after_max_age():
    # hint binder et indslag 9 døgn senere til historien; det skal stå for sig selv
    a = item("a", "kefm", title="Ministeriet sender affaldsreformen i høring nu")
    b = item("b", "avisen", hours=24 * 9, title="Reformen af affaldssektoren er nu vedtaget")
    gs = groups([a, b], hints=[("a", "b")], max_age=7)
    assert sorted(ids(gs)) == [["a"], ["b"]]


def test_title_chain_cut_by_max_age():
    # samme titel hver 2,5 døgn: kæden må ikke vokse ud over 7 døgn fra hovedindslaget
    its = [item(f"i{n}", "avisen", hours=60 * n) for n in range(5)]  # 0, 2.5, 5, 7.5, 10 døgn
    gs = groups(its, window=3, max_age=7)
    first = next(g for g in gs if g[0].id == "i0")
    assert [it.id for it in first] == ["i0", "i1", "i2"]
    assert sum(len(g) for g in gs) == 5


def test_no_merge_keeps_item_alone():
    gs = groups([item("a", "avisen"), item("b", "dr", hours=1)], no_merge={"b"})
    assert len(gs) == 2


def test_published_none_uses_first_seen():
    gs = groups([item("a", "avisen", hours=0, published=False), item("b", "dr", hours=10)])
    assert ids(gs) == [["a", "b"]]


def test_groups_sorted_newest_first():
    gs = groups(
        [
            item("old", "avisen", title="Gammel historie om affald i kommunen", hours=0),
            item("new", "avisen", title="Ny historie om affald i kommunen her", hours=20),
        ]
    )
    assert ids(gs) == [["new"], ["old"]]


def test_build_stories_fills_story_and_also():
    its = [
        item("med", "avisen", hours=0),
        item("myn", "kefm", hours=6),
        item("fag", "altinget", hours=3),
        item("solo", "dr", title="En helt anden nyhed om genbrugspladser", hours=1),
    ]
    out = build_stories(its, CATS, [], 3, 7)
    assert [it.id for it in out] == ["myn", "solo"]
    main = out[0]
    assert main.story == "myn"
    assert [a.id for a in main.also] == ["med", "fag"]
    assert main.also[0].source == "avisen"
    assert main.also[0].url == "https://avisen.dk/med"
    assert main.also[0].published == T0
    assert out[1].also == []
    assert out[1].story == "solo"


def test_build_stories_does_not_mutate_input():
    its = [item("a", "avisen"), item("b", "kefm", hours=1)]
    build_stories(its, CATS, [], 3, 7)
    assert its[1].also == []


def test_build_stories_sort_ties_by_id():
    its = [
        item("b", "avisen", title="Første helt selvstændige nyhed om affald"),
        item("a", "dr", title="Anden helt selvstændige nyhed om affald"),
    ]
    assert [it.id for it in build_stories(its, CATS, [], 3, 7)] == ["a", "b"]


def test_build_stories_unites_places():
    # Kun et indslag i also er lokalt; historien kan alligevel findes med stedfiltret
    main = item("myn", "kefm", hours=0)
    local = item("lokal", "avisen", hours=2).model_copy(update={"places": ["k:nyborg", "b:ullerslev"]})
    other = item("fag", "altinget", hours=3).model_copy(update={"places": ["r:syddanmark", "k:nyborg"]})
    solo = item("solo", "dr", title="En helt anden nyhed om genbrugspladser", hours=1)
    out = {it.id: it for it in build_stories([main, local, other, solo], CATS, [], 3, 7)}
    assert out["myn"].places == ["r:syddanmark", "k:nyborg", "b:ullerslev"]
    assert out["solo"].places == []
    assert "places" not in out["myn"].also[0].model_dump()  # also-indslag arver hovedindslagets


def test_build_stories_places_are_not_cut_at_eight():
    # Foreningen skæres ikke: by=vojens skal finde historien, selv om den har 10 steder fordelt på 3 indslag
    main = item("myn", "kefm", hours=0).model_copy(update={"places": ["r:syddanmark", "k:aabenraa", "k:haderslev"]})
    a = item("a", "avisen", hours=1).model_copy(
        update={"places": ["k:soenderborg", "k:toender", "b:aabenraa", "b:haderslev"]})
    b = item("b", "altinget", hours=2).model_copy(update={"places": ["b:soenderborg", "b:toender", "b:vojens"]})
    [story] = build_stories([main, a, b], CATS, [], 3, 7)
    assert len(story.places) == 10
    assert story.places == ["r:syddanmark", "k:aabenraa", "k:haderslev", "k:soenderborg", "k:toender",
                            "b:aabenraa", "b:haderslev", "b:soenderborg", "b:toender", "b:vojens"]


# ── Dagsbundter (bundle: day) ──────────────────────────────


def test_day_bundle_groups_one_source_per_copenhagen_day():
    ft = [
        item("q1", "ft", title="Spm. om producentansvar for emballage", hours=1),
        item("q2", "ft", title="Spm. om asbest på genbrugsstationer", hours=3),
        item("q3", "ft", title="Svar om affaldsstatistik", hours=13),  # 23.00 dansk sommertid, samme dag
        item("q4", "ft", title="Spm. om pant på dåser", hours=15),  # 01.00 dansk sommertid, næste dag
        item("n1", "dr", title="Nyhed om noget helt andet", hours=2),
    ]
    gs = groups(ft, bundle_day={"ft"})
    assert sorted(ids(gs)) == sorted([["q1", "q2", "q3"], ["q4"], ["n1"]])  # hovedindslaget er det tidligste
    assert ids(groups(ft)) == [[i.id] for i in sorted(ft, key=lambda x: -x.first_seen.timestamp())]  # ellers hver for sig


def test_day_bundle_respects_no_merge_and_shows_also():
    ft = [item("q1", "ft", title="Spm. A om affald", hours=1), item("q2", "ft", title="Spm. B om affald", hours=2),
          item("q3", "ft", title="Spm. C om affald", hours=3)]
    assert sorted(ids(groups(ft, bundle_day={"ft"}, no_merge={"q2"}))) == sorted([["q1", "q3"], ["q2"]])
    heads = build_stories(ft, CATS, [], 3, 7, bundle_day={"ft"})
    assert len(heads) == 1 and heads[0].id == "q1"
    assert [a.id for a in heads[0].also] == ["q2", "q3"]
