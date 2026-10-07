"""Visningslogik: hvilke indslag vises, med hvilke temaer, og om Claude har vurderet dem (KONTRAKTER §6.3)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import get_args

from affaldsfeed.classify import Overrides
from affaldsfeed.config import Config
from affaldsfeed.models import (
    Candidate,
    DisplayItem,
    GenreId,
    Judgment,
    Override,
    Publisher,
    Source,
    TopicId,
)
from affaldsfeed.normalize import clean_text
from affaldsfeed.timeutil import ensure_utc

TOPIC_IDS: frozenset[str] = frozenset(get_args(TopicId))
GENRE_IDS: frozenset[str] = frozenset(get_args(GenreId))
FUTURE_TOLERANCE = timedelta(hours=2)


@dataclass(frozen=True)
class SourceInfo:
    """Det, visningen skal vide om en afsender (kilde fra sources.yaml eller udgiver fra medier.yaml)."""

    id: str
    name: str
    category: str
    lang: str
    ai: bool
    homepage: str | None
    paywall: str
    owner: str | None
    status: str
    via_search: bool


def known_sources(sources: list[Source], publishers: list[Publisher]) -> dict[str, SourceInfo]:
    """Kendte afsendere: aktive kilder (ikke søgekilder) først, derefter medier.yaml."""
    out: dict[str, SourceInfo] = {}
    for s in sources:
        if s.status != "aktiv" or s.method == "search":
            continue
        out[s.id] = SourceInfo(
            id=s.id,
            name=s.name,
            category=s.category,
            lang=s.lang,
            ai=s.ai,
            homepage=s.homepage,
            paywall=s.paywall,
            owner=s.owner,
            status=s.status,
            via_search=False,
        )
    for p in publishers:
        if p.id in out:
            continue
        out[p.id] = SourceInfo(
            id=p.id,
            name=p.name,
            category=p.category,
            lang=p.lang,
            ai=True,
            homepage=f"https://{p.domains[0]}" if p.domains else None,
            paywall=p.paywall,
            owner=None,
            status="aktiv",
            via_search=True,
        )
    return out


def item_time(x: Candidate | DisplayItem) -> datetime:
    """Tidspunktet et indslag sorteres og filtreres på: published, ellers first_seen."""
    return ensure_utc(x.published or x.first_seen)


def sort_newest_first[T: (Candidate, DisplayItem)](items: list[T]) -> list[T]:
    """Nyeste først, ved lighed efter id (deterministisk)."""
    return sorted(sorted(items, key=lambda x: x.id), key=item_time, reverse=True)


def source_category_map(sources: list[Source], publishers: list[Publisher]) -> dict[str, str]:
    """Afsender-id -> kategori for alle kendte afsendere."""
    return {sid: info.category for sid, info in known_sources(sources, publishers).items()}


def story_hints(judgments: dict[str, Judgment]) -> list[tuple[str, str]]:
    """Par (id, story_hint) fra de seneste vurderinger, sorteret."""
    return sorted(
        (j.id, j.story_hint) for j in judgments.values() if j.story_hint and j.story_hint != j.id
    )


def split_ids(config: Config, items: list[DisplayItem]) -> set[str]:
    """Id'er med override "split": de samles aldrig i en historie med andre."""
    overrides = Overrides(config.overrides)
    return {d.id for d in items if any(o.action == "split" for o in overrides.find(d.id, d.url))}


def _as_topics(value: str | list[str] | None) -> list[str]:
    vals = [value] if isinstance(value, str) else list(value or [])
    out: list[str] = []
    for v in vals:
        if v in TOPIC_IDS and v not in out:
            out.append(v)
    return out[:2]


@dataclass
class _Shown:
    show: bool
    reviewed: bool
    topics: list[str]
    genre: str


def _apply_overrides(found: list[Override], state: _Shown) -> _Shown:
    """Manuelle rettelser slår alt andet; de anvendes i filens rækkefølge."""
    for o in found:
        if o.action == "skjul":
            state.show = False
        elif o.action == "vis":
            state.show = True
            state.reviewed = True  # et menneske har valgt indslaget
        elif o.action == "tema":
            state.topics = _as_topics(o.value)
        elif o.action == "genre" and isinstance(o.value, str) and o.value in GENRE_IDS:
            state.genre = o.value
        # "split" bruges ved samling i historier (split_ids)
    return state


def _from_candidate(
    c: Candidate,
    info: SourceInfo,
    judgment: Judgment | None,
    mode: str,
    overrides: Overrides,
    teaser_max: int,
) -> DisplayItem | None:
    reason: str | None = None
    summary: str | None = None
    state = _Shown(show=False, reviewed=True, topics=list(c.topics), genre=c.genre)
    if not info.ai:
        # kilden vurderes kun af regler
        state.show = c.why.decision == "vis"
        state.reviewed = False
    elif judgment is not None:
        state.show = judgment.relevant
        reason = judgment.reason
        if "topics" in judgment.model_fields_set:
            state.topics = list(judgment.topics)
        if "genre" in judgment.model_fields_set:
            state.genre = judgment.genre
        summary = judgment.summary_da
    elif mode == "fallback":
        state.show = c.why.decision == "vis"
        state.reviewed = False
    # ellers: uvurderet i claude-tilstand venter
    state = _apply_overrides(overrides.find(c.id, c.url), state)
    if not state.show:
        return None
    return DisplayItem(
        id=c.id,
        story=c.id,
        url=c.url,
        title=c.title,
        teaser=clean_text(c.teaser, teaser_max),
        source=c.source,
        published=ensure_utc(c.published) if c.published else None,
        date_quality=c.date_quality,
        first_seen=ensure_utc(c.first_seen),
        baseline=c.baseline,
        topics=state.topics[:2],
        genre=state.genre,
        lang=c.lang,
        summary_da=summary if c.lang != "da" else None,
        reviewed=state.reviewed,
        reason=reason,
        why=c.why,
    )


def _from_sweep(
    j: Judgment,
    info: SourceInfo,
    overrides: Overrides,
    now: datetime,
    teaser_max: int,
) -> DisplayItem | None:
    ni = j.new_item
    if ni is None or not info.ai:
        return None
    state = _Shown(show=j.relevant, reviewed=True, topics=list(j.topics), genre=j.genre)
    state = _apply_overrides(overrides.find(j.id, ni.url), state)
    if not state.show:
        return None
    found = ensure_utc(j.judged_at)
    published = ensure_utc(ni.published) if ni.published else None
    date_quality = "kilde"
    if published is None or published > now + FUTURE_TOLERANCE:
        published, date_quality = found, "fundet"
    return DisplayItem(
        id=j.id,
        story=j.id,
        url=ni.url,
        title=ni.title,
        teaser=clean_text(ni.teaser, teaser_max),
        source=ni.source,
        published=published,
        date_quality=date_quality,
        first_seen=found,
        baseline=False,
        topics=state.topics[:2],
        genre=state.genre,
        lang=info.lang,
        summary_da=j.summary_da if info.lang != "da" else None,
        reviewed=state.reviewed,
        reason=j.reason,
        why=None,
    )


def build_display_items(
    config: Config,
    sources: list[Source],
    candidates: list[Candidate],
    judgments: dict[str, Judgment],
    mode: str,
    now: datetime,
    since: datetime,
) -> list[DisplayItem]:
    """Alle indslag, der skal vises (før samling i historier), nyeste først.

    mode er "claude" eller "fallback" (judgments.display_mode). Kun indslag med
    published (ellers first_seen) >= since kommer med.
    """
    now = ensure_utc(now)
    since = ensure_utc(since)
    info = known_sources(sources, config.publishers)
    overrides = Overrides(config.overrides)
    teaser_max = config.settings.teaser_display_max

    out: dict[str, DisplayItem] = {}
    cand_ids: set[str] = set()
    for c in candidates:
        if c.id in cand_ids:
            continue
        cand_ids.add(c.id)
        src = info.get(c.source)
        if src is None or item_time(c) < since:
            continue
        item = _from_candidate(c, src, judgments.get(c.id), mode, overrides, teaser_max)
        if item is not None:
            out[item.id] = item

    # sweep-fund fra Claude, som ikke (endnu) er kandidater
    for j in judgments.values():
        if j.new_item is None or j.id in cand_ids:
            continue
        src = info.get(j.new_item.source)
        if src is None:
            continue
        item = _from_sweep(j, src, overrides, now, teaser_max)
        if item is not None and item_time(item) >= since:
            out[item.id] = item

    return sort_newest_first(list(out.values()))
