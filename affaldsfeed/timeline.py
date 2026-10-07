"""Tidslinjen: de vigtigste begivenheder, valgt af Claude-routinen (KONTRAKTER §7.3).

timeline-input giver routinen nye historier og de nuværende begivenheder, validate-timeline tjekker
data/timeline/*.jsonl, og export_timeline bygger timeline.json til siden.
"""

from __future__ import annotations

import argparse
import logging
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from affaldsfeed import paths
from affaldsfeed.config import Config
from affaldsfeed.display import item_time, split_ids, story_hints
from affaldsfeed.judgments import format_errors, print_json, rel, unknown_places
from affaldsfeed.models import (
    CATEGORY_RANK,
    TIMELINE_ITEMS_MAX,
    DisplayItem,
    Geo,
    TimelineDeletion,
    TimelineEvent,
    TimelineFeed,
    TimelineRef,
    parse_timeline_line,
    sort_places,
)
from affaldsfeed.overview import Data, approved_items, load_data, word_count
from affaldsfeed.stories import group_stories
from affaldsfeed.timeutil import ensure_utc, iso, now_utc, to_cph

log = logging.getLogger(__name__)

FILE_RE = re.compile(r"^(\d{4}-\d{2})\.jsonl$")
TIMELINE_VERSION = 1
TITLE_MAX_WORDS = 12
SUMMARY_MAX_WORDS = 40
FUTURE_SLACK = timedelta(minutes=10)
EPOCH = datetime(2000, 1, 1, tzinfo=UTC)
MONTHS = ("januar", "februar", "marts", "april", "maj", "juni", "juli", "august", "september", "oktober",
          "november", "december")

LEVELS = {
    "milepael": "Ændrer rammerne for hele affaldsområdet: en lov eller bekendtgørelse vedtaget, en bred politisk "
    "aftale, en EU-regel vedtaget eller trådt i kraft.",
    "vigtig": "En stor beslutning, afgørelse, rapport eller hændelse med betydning ud over én kommune.",
}
INCLUDE = [
    "ny lov eller bekendtgørelse vedtaget",
    "politisk aftale",
    "EU-regel vedtaget eller trådt i kraft",
    "store afgørelser fra myndigheder",
    "store beslutninger i kommuner og affaldsselskaber, fx nyt anlæg, lukning eller fusion",
    "centrale rapporter og analyser fra myndigheder",
    "store hændelser, fx brande, konkurser og miljøsager",
]
EXCLUDE = [
    "enkeltstående lokale driftsnyheder",
    "debatindlæg",
    "arrangementer",
    "personnyt",
    "nyt om en begivenhed, der allerede står på tidslinjen (tilføj i stedet indslaget til den)",
]


# ── Indlæsning ──────────────────────────────────────────────


@dataclass(frozen=True)
class Line:
    path: Path
    n: int
    record: TimelineEvent | TimelineDeletion


def timeline_files() -> list[Path]:
    """Tidslinjefiler (ÅÅÅÅ-MM.jsonl) i datoorden."""
    d = paths.TIMELINE_DIR
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir() if p.is_file() and FILE_RE.match(p.name))


def _lines(path: Path) -> Iterator[tuple[int, str]]:
    with path.open(encoding="utf-8-sig") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if line:
                yield n, line


def read_lines(files: Iterable[Path]) -> tuple[list[Line], list[str]]:
    """Gyldige linjer i fil- og linjeorden og fejl for de ugyldige ("fil:linje: besked")."""
    lines: list[Line] = []
    errors: list[str] = []
    for path in files:
        for n, text in _lines(path):
            try:
                lines.append(Line(path, n, parse_timeline_line(text)))
            except ValidationError as e:
                errors.extend(f"{rel(path)}:{n}: {msg}" for msg in format_errors(e))
    return lines, errors


def current_events(lines: Iterable[Line]) -> dict[str, TimelineEvent]:
    """Den seneste linje pr. id vinder. En sletning fjerner begivenheden."""
    out: dict[str, TimelineEvent] = {}
    for ln in lines:
        r = ln.record
        if isinstance(r, TimelineDeletion):
            out.pop(r.id, None)
        else:
            out[r.id] = r
    return out


def load_events() -> dict[str, TimelineEvent]:
    """Nuværende begivenheder. Ugyldige linjer springes over med en advarsel."""
    lines, errors = read_lines(timeline_files())
    for msg in errors[:3]:
        log.warning("ugyldig linje i tidslinjen springes over: %s", msg)
    if len(errors) > 3:
        log.warning("... og %d ugyldige linjer mere i tidslinjen", len(errors) - 3)
    return current_events(lines)


def sort_events(events: Iterable[TimelineEvent]) -> list[TimelineEvent]:
    """Nyeste dato først, derefter id."""
    return sorted(sorted(events, key=lambda e: e.id), key=lambda e: e.date, reverse=True)


def _ref_key(r: TimelineRef) -> tuple[float, str]:
    return (ensure_utc(r.published).timestamp() if r.published else float("inf"), r.id)


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def week_label(m: date) -> str:
    """'uge 41 (5.-11. oktober 2026)'."""
    s = m + timedelta(days=6)
    week = m.isocalendar().week
    if m.month == s.month:
        return f"uge {week} ({m.day}.-{s.day}. {MONTHS[s.month - 1]} {s.year})"
    first = f"{m.day}. {MONTHS[m.month - 1]}" + (f" {m.year}" if m.year != s.year else "")
    return f"uge {week} ({first}-{s.day}. {MONTHS[s.month - 1]} {s.year})"


def _ref(d: DisplayItem, names: dict[str, str]) -> dict[str, Any]:
    """Et indslag, som routinen kan kopiere direkte ind i items."""
    return {
        "id": d.id,
        "title": d.title,
        "url": d.url,
        "source": d.source,
        "source_name": names.get(d.source, d.source),
        "published": iso(item_time(d)),
    }


# ── timeline-input ──────────────────────────────────────────


def build_timeline_input(now: datetime, data: Data, days: int | None = None) -> dict[str, Any]:
    now = ensure_utc(now)
    settings = data.config.settings
    ts = settings.timeline
    events = load_events()
    first_fill = not events
    if days is None:
        days = ts.first_fill_days if first_fill else ts.input_days
    start = now - timedelta(days=days)
    info = data.info
    names = {sid: i.name for sid, i in info.items()}
    cat_map = {sid: i.category for sid, i in info.items()}

    approved = approved_items(data, now, start, now)
    groups = group_stories(
        approved,
        cat_map,
        story_hints(data.judgments),
        settings.story_title_window_days,
        settings.story_max_age_days,
        no_merge=split_ids(data.config, approved),
    )
    in_events: dict[str, set[str]] = defaultdict(set)
    for e in events.values():
        for r in e.items:
            in_events[r.id].add(e.id)

    stories: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    for g in groups:
        if not g:
            continue
        head = g[0]
        cat = cat_map.get(head.source)
        text = head.summary_da if head.lang != "da" and head.summary_da else head.teaser
        entry = {
            **_ref(head, names),
            "teaser_or_summary": text,
            "category": cat,
            "genre": head.genre,
            "topics": list(head.topics),
            "places": sort_places({p for d in g for p in d.places}, limit=None),
            "story_size": len(g),
            "also": [_ref(d, names) for d in g[1:]],
            "in_events": sorted({eid for d in g for eid in in_events.get(d.id, ())}),
        }
        key = (CATEGORY_RANK.get(cat or "", 9), -len(g), -item_time(head).timestamp(), head.id)
        stories.append((key, entry))
    stories.sort(key=lambda x: x[0])

    today = to_cph(now).date()
    recent = [e for e in sort_events(events.values()) if e.date >= today - timedelta(days=ts.events_days)]
    counts = Counter(monday(e.date) for e in events.values())
    weeks = []
    m = monday(to_cph(start).date())
    while m <= today:
        weeks.append({"week": week_label(m), "monday": m.isoformat(), "events": counts.get(m, 0)})
        m += timedelta(days=7)

    return {
        "now": iso(now),
        "first_fill": first_fill,
        "window": {"start": iso(start), "end": iso(now)},
        "rules": {
            "title_max_words": TITLE_MAX_WORDS,
            "summary_max_words": SUMMARY_MAX_WORDS,
            "topics_max": 2,
            "items_min": 1,
            "items_max": TIMELINE_ITEMS_MAX,
            "max_per_week": ts.max_per_week,
            "levels": LEVELS,
            "include": INCLUDE,
            "exclude": EXCLUDE,
        },
        "weeks": weeks,
        "stories": [entry for _, entry in stories],
        "events": [e.model_dump(mode="json", exclude={"by", "deleted"}) for e in recent],
    }


def main_timeline_input(args: argparse.Namespace) -> int:
    now = now_utc(getattr(args, "now", None))
    out = build_timeline_input(now, load_data(), getattr(args, "days", None))
    month = to_cph(now).strftime("%Y-%m")
    log.info(
        "tidslinje: %d historier og %d begivenheder i input%s; skriv nye linjer i data/timeline/%s.jsonl "
        "med updated %s",
        len(out["stories"]), len(out["events"]), " (første fyldning)" if out["first_fill"] else "", month,
        out["now"],
    )
    print_json(out)
    return 0


# ── validate-timeline ───────────────────────────────────────


@dataclass
class _Context:
    data: Data
    now: datetime
    recent_since: datetime
    place_ids: set[str] | None
    _approved: dict[str, DisplayItem] | None = None

    @property
    def approved(self) -> dict[str, DisplayItem]:
        if self._approved is None:
            self._approved = {d.id: d for d in approved_items(self.data, self.now, EPOCH, self.now)}
        return self._approved


def _check_ref(r: TimelineRef, ctx: _Context) -> str | None:
    d = ctx.approved.get(r.id)
    if d is None:
        return f"items: '{r.id}' er ikke et godkendt indslag"
    src = ctx.data.info.get(d.source)
    wrong = [
        name
        for name, ok in (
            ("url", r.url == d.url),
            ("title", r.title == d.title),
            ("source", r.source == d.source),
            ("source_name", src is None or r.source_name == src.name),
            ("published", iso(r.published) == iso(item_time(d))),
        )
        if not ok
    ]
    if wrong:
        return f"items: '{r.id}' passer ikke med indslaget ({', '.join(wrong)}); kopiér felterne fra timeline-input"
    return None


def _check_line(
    rec: TimelineEvent | TimelineDeletion,
    prev: TimelineEvent | None,
    file_month: str | None,
    ctx: _Context,
) -> tuple[list[str], list[str]]:
    """(fejl, advarsler) for én linje. prev er begivenheden, som den så ud før linjen."""
    errors: list[str] = []
    updated = ensure_utc(rec.updated)
    month = to_cph(updated).strftime("%Y-%m")
    if file_month is not None and month != file_month:
        errors.append(f"updated er i {month} i København; linjen hører til i data/timeline/{month}.jsonl")
    if updated > ctx.now + FUTURE_SLACK:
        errors.append(f"updated {iso(updated)} ligger i fremtiden")
    if isinstance(rec, TimelineDeletion):
        if prev is None:
            errors.append(f"sletter '{rec.id}', som ikke findes eller allerede er slettet")
        return errors, []

    today = to_cph(ctx.now).date()
    if rec.date > today:
        errors.append(f"date {rec.date.isoformat()} ligger i fremtiden")
    n = word_count(rec.title)
    if n > TITLE_MAX_WORDS:
        errors.append(f"title har {n} ord (højst {TITLE_MAX_WORDS})")
    n = word_count(rec.summary)
    if n > SUMMARY_MAX_WORDS:
        errors.append(f"summary har {n} ord (højst {SUMMARY_MAX_WORDS})")
    if updated >= ctx.recent_since:
        # Nye indslag skal være godkendte og kopieret præcist; dem fra den forrige version er tjekket før
        known = {r.id for r in prev.items} if prev else set()
        for r in rec.items:
            if r.id not in known and (msg := _check_ref(r, ctx)):
                errors.append(msg)
    return errors, unknown_places(rec.places, ctx.place_ids)


def validate_timeline(
    data: Data, now: datetime, targets: list[Path] | None = None
) -> tuple[list[str], list[str], int, int]:
    """Validerer tidslinjefilerne (alle eller `targets`). Returnerer (fejl, advarsler, linjer, begivenheder).

    Alle filer læses i datoorden, så en linje kendes i forhold til de tidligere versioner af samme id.
    """
    now = ensure_utc(now)
    ts = data.config.settings.timeline
    all_files = timeline_files()
    resolved = {p.resolve() for p in all_files}
    check_files = all_files if targets is None else targets
    check = {p.resolve() for p in check_files}
    order = all_files + [p for p in check_files if p.resolve() not in resolved]
    ctx = _Context(data, now, now - timedelta(hours=ts.recent_hours), data.config.geo.place_ids() or None)

    errors: list[str] = []
    warnings: list[str] = []
    count = 0
    state: dict[str, TimelineEvent] = {}
    weeks: dict[date, str] = {}  # mandag -> første nye linje i ugen
    for path in order:
        mine = path.resolve() in check
        name = rel(path)
        m = FILE_RE.match(path.name)
        if mine and not m:
            errors.append(f"{name}:0: filnavnet skal være ÅÅÅÅ-MM.jsonl")
        if not path.is_file():
            if mine:
                errors.append(f"{name}:0: filen findes ikke")
            continue
        for n, text in _lines(path):
            try:
                rec = parse_timeline_line(text)
            except ValidationError as e:
                if mine:
                    count += 1
                    errors.extend(f"{name}:{n}: {msg}" for msg in format_errors(e))
                continue
            prev = state.get(rec.id)
            if mine:
                count += 1
                errs, warns = _check_line(rec, prev, m.group(1) if m else None, ctx)
                errors.extend(f"{name}:{n}: {msg}" for msg in errs)
                warnings.extend(f"{name}:{n}: {msg}" for msg in warns)
                if isinstance(rec, TimelineEvent) and ensure_utc(rec.updated) >= ctx.recent_since:
                    weeks.setdefault(monday(rec.date), f"{name}:{n}")
            if isinstance(rec, TimelineDeletion):
                state.pop(rec.id, None)
            else:
                state[rec.id] = rec

    # Højst max_per_week begivenheder pr. uge; tjekkes for uger med nye linjer
    per_week = Counter(monday(e.date) for e in state.values())
    for m_day, where in sorted(weeks.items()):
        if per_week[m_day] > ts.max_per_week:
            errors.append(
                f"{where}: {week_label(m_day)} har {per_week[m_day]} begivenheder; højst {ts.max_per_week}. "
                "Lad den mindst vigtige ude, eller slet den med en sletningslinje"
            )
    return errors, warnings, count, len(state)


def main_validate_timeline(args: argparse.Namespace) -> int:
    now = now_utc(getattr(args, "now", None))
    file_arg = getattr(args, "file", None)
    targets = None
    if file_arg:
        p = Path(file_arg)
        # Relative stier regnes fra repoets rod (som validate-judgments), ellers fra cwd
        targets = [p if p.is_absolute() else (paths.ROOT / p)]
        if not targets[0].exists() and not p.is_absolute():
            targets = [Path.cwd() / p]
    files = targets if targets is not None else timeline_files()
    if not files:
        print("validate-timeline: ingen tidslinjefiler at validere")
        return 0
    errors, warnings, count, n_events = validate_timeline(load_data(), now, targets)
    for w in warnings:
        print(f"ADVARSEL {w}")
    for e in errors:
        print(e)
    advarsler = f", {len(warnings)} {'advarsel' if len(warnings) == 1 else 'advarsler'}" if warnings else ""
    if errors:
        print(f"validate-timeline: {len(errors)} fejl i {count} linjer ({len(files)} filer){advarsler}")
        return 1
    print(f"validate-timeline: OK, {count} linjer i {len(files)} filer, {n_events} begivenheder{advarsler}")
    return 0


# ── export (timeline.json) ──────────────────────────────────


def place_names(geo: Geo) -> dict[str, tuple[str, str]]:
    """Sted-id -> (navn, kort) for alle steder i geografien."""
    out: dict[str, tuple[str, str]] = {f"r:{r.id}": (r.navn, r.kort) for r in geo.regioner}
    out.update({f"k:{m.id}": (m.navn, m.kort) for m in geo.kommuner})
    out.update({f"b:{t.id}": (t.navn, t.navn) for t in geo.byer})
    return out


def export_timeline(now: datetime, config: Config, heads: list[DisplayItem]) -> dict[str, Any]:
    """timeline.json som dict, valideret mod models.TimelineFeed.

    heads er feedets historier (feed.json items). En begivenhed får story = den historie, der har et af
    dens indslag, så siden kan linke til den i feedet. Steder, der ikke står i geografien, udelades.
    """
    story_of: dict[str, str] = {}
    for d in heads:
        story_of.setdefault(d.id, d.story)
        for a in d.also:
            story_of.setdefault(a.id, d.story)
    names = place_names(config.geo)
    used: set[str] = set()
    events = []
    for e in sort_events(load_events().values()):
        items = sorted(e.items, key=_ref_key)
        places = [p for p in e.places if p in names]
        used.update(places)
        events.append(
            {
                **e.model_dump(mode="json", exclude={"by", "deleted"}),
                "places": places,
                "items": [r.model_dump(mode="json") for r in items],
                "story": next((story_of[r.id] for r in items if r.id in story_of), None),
            }
        )
    out = {
        "version": TIMELINE_VERSION,
        "generated": iso(now),
        "topics": [{"id": t.id, "name": t.name, "short": t.short, "definition": t.definition} for t in config.topics],
        "places": [{"id": p, "navn": names[p][0], "kort": names[p][1]} for p in sort_places(used, limit=None)],
        "events": events,
    }
    TimelineFeed.model_validate(out)  # kontrakten (KONTRAKTER §7.3); ValidationError giver exit 1
    return out
