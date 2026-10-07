"""Samling af indslag om samme historie (KONTRAKTER §8): niveau 1 (id), niveau 2 (titel) og story_hint."""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from collections.abc import Iterable
from datetime import datetime, timedelta
from itertools import combinations

from .models import CATEGORY_RANK, AlsoRef, DisplayItem, sort_places
from .normalize import normalize_title
from .timeutil import ensure_utc

log = logging.getLogger(__name__)

# Korte, generiske titler ("Ny affaldsplan") samles ikke på titel alene
MIN_TITLE_WORDS = 4
_UNKNOWN_RANK = max(CATEGORY_RANK.values()) + 1


def _when(item: DisplayItem) -> datetime:
    return ensure_utc(item.published or item.first_seen)


def _component(start: str, adj: dict[str, set[str]], allowed: set[str]) -> set[str]:
    seen = {start}
    stack = [start]
    while stack:
        node = stack.pop()
        for nb in adj[node]:
            if nb in allowed and nb not in seen:
                seen.add(nb)
                stack.append(nb)
    return seen


def _components(nodes: Iterable[str], adj: dict[str, set[str]], order: dict[str, int]) -> list[set[str]]:
    allowed = set(nodes)
    out: list[set[str]] = []
    done: set[str] = set()
    for node in sorted(allowed, key=order.__getitem__):
        if node in done:
            continue
        comp = _component(node, adj, allowed)
        done |= comp
        out.append(comp)
    return out


def group_stories(
    items: list[DisplayItem],
    source_category: dict[str, str],
    hints: list[tuple[str, str]],
    title_window_days: int,
    max_age_days: int,
    *,
    no_merge: set[str] | None = None,
) -> list[list[DisplayItem]]:
    """Grupper indslag i historier. Hver gruppe har hovedindslaget først, derefter de øvrige efter tid.

    no_merge: id'er, der altid står alene (fx override "split").
    """
    # Niveau 1: samme id er samme indslag; første forekomst bruges
    unique: dict[str, DisplayItem] = {}
    for it in items:
        if it.id in unique:
            log.debug("dublet af id %s ignoreret", it.id)
            continue
        unique[it.id] = it
    order = {iid: i for i, iid in enumerate(unique)}
    adj: dict[str, set[str]] = {iid: set() for iid in unique}
    blocked = set(no_merge or ())

    def link(a: str, b: str) -> None:
        if a != b and a not in blocked and b not in blocked:
            adj[a].add(b)
            adj[b].add(a)

    # Niveau 2: samme normaliserede titel inden for ±title_window_days
    by_title: dict[str, list[str]] = defaultdict(list)
    for iid, it in unique.items():
        key = normalize_title(it.title)
        if len(key.split()) >= MIN_TITLE_WORDS:
            by_title[key].append(iid)
    window = timedelta(days=title_window_days)
    for ids in by_title.values():
        for a, b in combinations(ids, 2):
            if abs(_when(unique[a]) - _when(unique[b])) <= window:
                link(a, b)

    # story_hint-par fra Claudes vurderinger
    for a, b in hints:
        if a in adj and b in adj:
            link(a, b)

    def rank(it: DisplayItem) -> int:
        return CATEGORY_RANK.get(source_category.get(it.source, ""), _UNKNOWN_RANK)

    max_age = timedelta(days=max_age_days)
    groups: list[list[DisplayItem]] = []
    pending = deque(_components(unique, adj, order))
    while pending:
        comp = pending.popleft()
        members = [unique[i] for i in sorted(comp, key=order.__getitem__)]
        main = min(members, key=lambda it: (rank(it), _when(it), it.id))
        # Historien optager ikke indslag mere end max_age_days fra hovedindslaget
        in_time = {it.id for it in members if abs(_when(it) - _when(main)) <= max_age}
        story = _component(main.id, adj, in_time)
        others = sorted((unique[i] for i in story if i != main.id), key=lambda it: (_when(it), it.id))
        groups.append([main, *others])
        rest = comp - story
        if rest:
            pending.extend(_components(rest, adj, order))

    groups.sort(key=lambda g: (-_when(g[0]).timestamp(), g[0].id))
    return groups


def build_stories(
    items: list[DisplayItem],
    source_category: dict[str, str],
    hints: list[tuple[str, str]],
    title_window_days: int,
    max_age_days: int,
    *,
    no_merge: set[str] | None = None,
) -> list[DisplayItem]:
    """Hovedindslag med story og also udfyldt, sorteret efter published (faldende) og id.

    places bliver foreningen af alle indslagenes steder, så et lokalt indslag i en national
    historie kan findes med stedfiltret.
    """
    out: list[DisplayItem] = []
    for main, *others in group_stories(
        items, source_category, hints, title_window_days, max_age_days, no_merge=no_merge
    ):
        also = [
            AlsoRef(id=o.id, source=o.source, url=o.url, title=o.title, published=o.published) for o in others
        ]
        places = sort_places(p for it in (main, *others) for p in it.places)
        out.append(main.model_copy(update={"story": main.id, "also": also, "places": places}))
    out.sort(key=lambda it: (-_when(it).timestamp(), it.id))
    return out
