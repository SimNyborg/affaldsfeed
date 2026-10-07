"""AI-overblikket: vinduer, overview-input og validate-overview (KONTRAKTER §7)."""

from __future__ import annotations

import argparse
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from affaldsfeed import paths
from affaldsfeed.config import Config, load_config, load_sources
from affaldsfeed.display import (
    SourceInfo,
    build_display_items,
    item_time,
    known_sources,
    sort_newest_first,
    split_ids,
    story_hints,
)
from affaldsfeed.judgments import format_errors, load_all_candidates, load_judgments, print_json, rel
from affaldsfeed.models import CATEGORY_RANK, Candidate, DisplayItem, Judgment, Overview, Source
from affaldsfeed.stories import group_stories
from affaldsfeed.timeutil import cph_day_bounds, ensure_utc, iso, now_utc, to_cph

log = logging.getLogger(__name__)

PERIODS = ("dag", "uge", "maaned", "aar")
HEADLINE_PREFIX = "Kort sagt:"
HEADLINE_MAX_WORDS = 25
BULLET_MAX_WORDS = 30
BULLET_LIMITS: dict[str, tuple[int, int]] = {"dag": (1, 5), "uge": (3, 5), "maaned": (5, 8), "aar": (5, 8)}
WINDOW_HOURS: dict[str, int] = {"uge": 7 * 24, "maaned": 30 * 24, "aar": 365 * 24}
MAX_LISTED: dict[str, int] = {"dag": 150, "uge": 120, "maaned": 40, "aar": 40}
LOWER_KIND: dict[str, str] = {"maaned": "uge", "aar": "maaned"}
ARCHIVE_RE = re.compile(r"^(dag|uge|maaned|aar)-(\d{4}-\d{2}-\d{2})\.json$")
FUTURE_SLACK = timedelta(minutes=10)


def window_for(period: str, now: datetime) -> tuple[datetime, datetime]:
    """Vinduet (UTC) for en periode: dag = kalenderdag i København til nu, ellers 7/30/365 × 24 t."""
    now = ensure_utc(now)
    if period == "dag":
        return cph_day_bounds(now)[0], now
    if period not in WINDOW_HOURS:
        raise ValueError(f"ukendt periode: {period}")
    return now - timedelta(hours=WINDOW_HOURS[period]), now


def bullet_limits(period: str, based_on: int) -> tuple[int, int]:
    """(min, max) antal punkter. dag: min 3 ved >= 6 indslag; andre: min sænkes ved tynde data."""
    lo, hi = BULLET_LIMITS[period]
    if period == "dag":
        return (3 if based_on >= 6 else 1), hi
    return min(lo, max(1, based_on // 3)), hi


def word_count(text: str) -> int:
    return len(text.split())


def overview_path(period: str) -> Path:
    return paths.OVERVIEW_DIR / f"{period}.json"


def _read_overview(path: Path) -> Overview | None:
    try:
        return Overview.model_validate_json(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValidationError) as e:
        log.warning("%s kan ikke læses: %s", rel(path), e)
        return None


def load_overviews() -> dict[str, Overview | None]:
    """Aktuelt overblik pr. periode (None når filen mangler eller er ugyldig)."""
    out: dict[str, Overview | None] = {}
    for p in PERIODS:
        path = overview_path(p)
        out[p] = _read_overview(path) if path.is_file() else None
    return out


# ── Fælles datagrundlag ─────────────────────────────────────


@dataclass
class Data:
    config: Config
    sources: list[Source]
    candidates: list[Candidate]
    judgments: dict[str, Judgment]

    @property
    def info(self) -> dict[str, SourceInfo]:
        return known_sources(self.sources, self.config.publishers)


def load_data() -> Data:
    return Data(
        config=load_config(paths.CONFIG_DIR),
        sources=load_sources(paths.SOURCES_FILE),
        candidates=load_all_candidates(),
        judgments=load_judgments(),
    )


def approved_items(data: Data, now: datetime, start: datetime, end: datetime) -> list[DisplayItem]:
    """Godkendte indslag (vurderet relevante eller vist manuelt) med tidspunkt i [start, end]."""
    items = build_display_items(data.config, data.sources, data.candidates, data.judgments, "claude", now, start)
    end = ensure_utc(end)
    return [d for d in items if d.reviewed and item_time(d) <= end]


def _data_start(data: Data) -> datetime | None:
    times = [item_time(c) for c in data.candidates]
    times += [ensure_utc(j.judged_at) for j in data.judgments.values() if j.new_item is not None]
    return min(times) if times else None


def _archived(kind: str) -> list[tuple[date, Path]]:
    d = paths.OVERVIEW_ARCHIVE_DIR
    if not d.is_dir():
        return []
    out = []
    for p in d.iterdir():
        m = ARCHIVE_RE.match(p.name)
        if m and m.group(1) == kind:
            out.append((date.fromisoformat(m.group(2)), p))
    return sorted(out)


def lower_overviews(period: str, start: datetime, end: datetime) -> list[Overview]:
    """maaned: arkiverede uge-overblik i vinduet (ét pr. dag). aar: arkiverede maaned-overblik (nyeste pr. måned)."""
    kind = LOWER_KIND.get(period)
    if kind is None:
        return []
    first, last = to_cph(start).date(), to_cph(end).date()
    chosen: dict[Any, Path] = {}
    for day, p in _archived(kind):
        if not first <= day <= last:
            continue
        key = day if kind == "uge" else (day.year, day.month)
        chosen[key] = p  # sorteret stigende, så den nyeste vinder
    out = []
    for key in sorted(chosen):
        ov = _read_overview(chosen[key])
        if ov is not None:
            out.append(ov)
    return out


# ── overview-input (§7.2) ───────────────────────────────────


def build_overview_input(period: str, now: datetime, data: Data) -> dict[str, Any]:
    start, end = window_for(period, now)
    info = data.info
    approved = approved_items(data, now, start, end)
    settings = data.config.settings
    cat_map = {sid: i.category for sid, i in info.items()}
    groups = group_stories(
        approved,
        cat_map,
        story_hints(data.judgments),
        settings.story_title_window_days,
        settings.story_max_age_days,
        no_merge=split_ids(data.config, approved),
    )
    size = {d.id: len(g) for g in groups for d in g}

    if period == "dag":
        listed = sort_newest_first(approved)[: MAX_LISTED[period]]
    else:
        heads = sort_newest_first([g[0] for g in groups if g])
        heads.sort(key=lambda d: (-size.get(d.id, 1), CATEGORY_RANK.get(cat_map.get(d.source, ""), 9)))
        listed = heads[: MAX_LISTED[period]]

    lower = lower_overviews(period, start, end)
    approved_ids = {d.id for d in approved}
    allowed = {d.id for d in listed}
    for ov in lower:
        for b in ov.bullets:
            allowed.update(x for x in b.item_ids if x in approved_ids)

    data_start = _data_start(data)
    since = to_cph(data_start).date() if data_start and data_start > start else None
    based_on = len(approved)
    lo, hi = bullet_limits(period, based_on)

    def entry(d: DisplayItem) -> dict[str, Any]:
        src = info.get(d.source)
        text = d.summary_da if d.lang != "da" and d.summary_da else d.teaser
        return {
            "id": d.id,
            "title": d.title,
            "teaser_or_summary": text,
            "source_name": src.name if src else d.source,
            "category": src.category if src else None,
            "genre": d.genre,
            "topics": list(d.topics),
            "published": iso(item_time(d)),
            "story_size": size.get(d.id, 1),
        }

    return {
        "period": period,
        "now": iso(now),
        "window": {"start": iso(start), "end": iso(end)},
        "since": since.isoformat() if since else None,
        "rules": {
            "headline_max_words": HEADLINE_MAX_WORDS,
            "bullet_max_words": BULLET_MAX_WORDS,
            "bullets_min": lo,
            "bullets_max": hi,
        },
        "items": [entry(d) for d in listed],
        "lower_overviews": [ov.model_dump(mode="json") for ov in lower],
        "allowed_item_ids": sorted(allowed),
        "based_on": based_on,
    }


def main_overview_input(args: argparse.Namespace) -> int:
    now = now_utc(getattr(args, "now", None))
    out = build_overview_input(args.period, now, load_data())
    log.info(
        "overblik %s: %d indslag i input, based_on %d, %d-%d punkter",
        args.period, len(out["items"]), out["based_on"], out["rules"]["bullets_min"],
        out["rules"]["bullets_max"],
    )
    print_json(out)
    return 0


# ── validate-overview ───────────────────────────────────────


def validate_overview(period: str, ov: Overview, data: Data, now: datetime) -> list[str]:
    """Indholdsregler ud over skemaet. Returnerer fejlbeskeder."""
    msgs: list[str] = []
    now = ensure_utc(now)
    if ov.period != period:
        msgs.append(f"period er '{ov.period}', men filen er {period}.json")
    if not ov.headline.strip().startswith(HEADLINE_PREFIX):
        msgs.append(f"headline skal begynde med '{HEADLINE_PREFIX}'")
    n = word_count(ov.headline)
    if n > HEADLINE_MAX_WORDS:
        msgs.append(f"headline har {n} ord (maks {HEADLINE_MAX_WORDS})")
    w_start, w_end = ensure_utc(ov.window.start), ensure_utc(ov.window.end)
    exp_start, _ = window_for(period, w_end)
    if w_start != exp_start:
        msgs.append(f"window.start skal være {iso(exp_start)} for {period} med window.end {iso(w_end)}")
    if w_end > now + FUTURE_SLACK:
        msgs.append(f"window.end {iso(w_end)} ligger i fremtiden")
    if ensure_utc(ov.generated) > now + FUTURE_SLACK:
        msgs.append(f"generated {iso(ov.generated)} ligger i fremtiden")

    approved = approved_items(data, now, w_start, w_end)
    approved_ids = {d.id for d in approved}
    cited: set[str] = set()
    for i, b in enumerate(ov.bullets, 1):
        if not b.text.strip():
            msgs.append(f"punkt {i} er tomt")
        n = word_count(b.text)
        if n > BULLET_MAX_WORDS:
            msgs.append(f"punkt {i} har {n} ord (maks {BULLET_MAX_WORDS})")
        for x in b.item_ids:
            cited.add(x)
            if x not in approved_ids:
                msgs.append(f"punkt {i}: item_id '{x}' er ikke et godkendt indslag i vinduet")

    if ov.based_on < len(cited):
        msgs.append(f"based_on er {ov.based_on}, men punkterne henviser til {len(cited)} forskellige indslag")
    if ov.based_on > len(approved):
        msgs.append(f"based_on er {ov.based_on}, men der er kun {len(approved)} godkendte indslag i vinduet")
    lo, hi = bullet_limits(period, ov.based_on)
    if not lo <= len(ov.bullets) <= hi:
        msgs.append(f"{len(ov.bullets)} punkter; tilladt er {lo}-{hi} (based_on {ov.based_on})")
    return msgs


def archive_path(period: str, ov: Overview) -> Path:
    day = to_cph(ov.window.end).date().isoformat()
    return paths.OVERVIEW_ARCHIVE_DIR / f"{period}-{day}.json"


def _archive(src: Path, dest: Path) -> bool:
    data = src.read_bytes()
    if dest.is_file() and dest.read_bytes() == data:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(dest)
    return True


def main_validate_overview(args: argparse.Namespace) -> int:
    now = now_utc(getattr(args, "now", None))
    period = getattr(args, "period", None)
    periods = [period] if period else [p for p in PERIODS if overview_path(p).is_file()]
    if not periods:
        print("validate-overview: ingen overblik at validere")
        return 0
    data = load_data()
    failed = 0
    for p in periods:
        path = overview_path(p)
        name = rel(path)
        if not path.is_file():
            print(f"{name}: filen findes ikke")
            failed += 1
            continue
        try:
            ov = Overview.model_validate_json(path.read_text(encoding="utf-8-sig"))
        except ValidationError as e:
            for msg in format_errors(e):
                print(f"{name}: {msg}")
            failed += 1
            continue
        msgs = validate_overview(p, ov, data, now)
        for msg in msgs:
            print(f"{name}: {msg}")
        if msgs:
            failed += 1
            continue
        note = ""
        if getattr(args, "archive", False):
            dest = archive_path(p, ov)
            _archive(path, dest)
            note = f" (arkiveret som {rel(dest)})"
        print(f"{name}: OK{note}")
    return 1 if failed else 0
