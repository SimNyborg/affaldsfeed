"""Claude-routinens vurderinger: pending, validate-judgments, heartbeat og visningstilstand (KONTRAKTER §6.2-6.3)."""

from __future__ import annotations

import argparse
import json
import logging
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from affaldsfeed import paths, store
from affaldsfeed.config import Config, load_config, load_sources
from affaldsfeed.display import SourceInfo, item_time, known_sources, sort_newest_first
from affaldsfeed.models import Candidate, Heartbeat, Judgment, RoutineSettings, Source
from affaldsfeed.normalize import item_id
from affaldsfeed.timeutil import ensure_utc, iso, now_utc, to_cph

log = logging.getLogger(__name__)

JUDGMENT_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.jsonl$")
RECENT_APPROVED_HOURS = 72


# ── Indlæsning ──────────────────────────────────────────────


def rel(path: Path) -> str:
    """Sti relativt til repoets rod (til fejlbeskeder), ellers som den er."""
    try:
        return path.resolve().relative_to(paths.ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def judgment_files() -> list[Path]:
    """Vurderingsfiler (ÅÅÅÅ-MM-DD.jsonl) i datoorden."""
    d = paths.JUDGMENTS_DIR
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir() if p.is_file() and JUDGMENT_FILE_RE.match(p.name))


def _lines(path: Path) -> Iterator[tuple[int, str]]:
    with path.open(encoding="utf-8-sig") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if line:
                yield n, line


def format_errors(e: ValidationError) -> list[str]:
    """Korte, læsbare beskeder fra en pydantic-fejl."""
    out = []
    for err in e.errors():
        if err["type"] == "json_invalid":
            out.append(f"ugyldig JSON ({err['ctx'].get('error', '')})" if err.get("ctx") else "ugyldig JSON")
            continue
        loc = ".".join(str(x) for x in err["loc"]) or "linje"
        out.append(f"{loc}: {err['msg']}")
    return out


def _parse_all(warn: bool) -> list[Judgment]:
    out: list[Judgment] = []
    for path in judgment_files():
        for n, line in _lines(path):
            try:
                out.append(Judgment.model_validate_json(line))
            except ValidationError as e:
                if warn:
                    log.warning("%s:%d: ugyldig vurdering springes over (%s)", rel(path), n, format_errors(e)[0])
    return out


def load_judgment_list() -> list[Judgment]:
    """Alle gyldige vurderinger i fil- og linjeorden. Ugyldige linjer springes over med en advarsel."""
    return _parse_all(warn=True)


def load_judgments() -> dict[str, Judgment]:
    """Seneste vurdering pr. id."""
    latest: dict[str, Judgment] = {}
    for j in load_judgment_list():
        latest[j.id] = j
    return latest


def load_heartbeat() -> Heartbeat | None:
    p = paths.HEARTBEAT_FILE
    if not p.is_file():
        return None
    try:
        return Heartbeat.model_validate_json(p.read_text(encoding="utf-8-sig"))
    except (ValidationError, OSError) as e:
        log.warning("%s kan ikke læses: %s", rel(p), e)
        return None


def load_all_candidates(since: datetime | None = None) -> list[Candidate]:
    """Kandidater fra store, uden dubletter (første forekomst vinder)."""
    seen: set[str] = set()
    out: list[Candidate] = []
    for c in store.load_candidates(since):
        if c.id not in seen:
            seen.add(c.id)
            out.append(c)
    return out


# ── Visningstilstand (§6.3) ─────────────────────────────────


def last_scheduled_run(now: datetime, routine: RoutineSettings) -> datetime | None:
    """Seneste planlagte kørsel <= now (UTC), på formen HH:MM i rutinens timer og tidszone."""
    if not routine.hours:
        return None
    tz = ZoneInfo(routine.timezone)
    local = ensure_utc(now).astimezone(tz)
    hours = sorted(set(routine.hours), reverse=True)
    for back in range(8):
        day = local.date() - timedelta(days=back)
        for h in hours:
            slot = datetime(day.year, day.month, day.day, h, routine.minute, tzinfo=tz)
            if slot <= local:
                return slot.astimezone(UTC)
    return None


def display_mode(now: datetime, heartbeat: Heartbeat | None, routine: RoutineSettings) -> str:
    """Tilstand "claude" eller "fallback".

    En planlagt kørsel regnes først som misset, når grace_hours er gået siden dens tidspunkt.
    S* = seneste planlagte kørsel <= now - grace_hours. Fallback når heartbeat mangler eller
    last_run < S*. Så skifter feedet ikke til fallback hver morgen, før kl. 06:25-kørslen er nået.
    """
    if heartbeat is None:
        return "fallback"
    slot = last_scheduled_run(ensure_utc(now) - timedelta(hours=routine.grace_hours), routine)
    if slot is None:
        return "claude"
    if ensure_utc(heartbeat.last_run) < slot:
        return "fallback"
    return "claude"


# ── pending (§6.2) ──────────────────────────────────────────


def pending_candidates(
    info: dict[str, SourceInfo],
    candidates: list[Candidate],
    judgments: dict[str, Judgment],
    now: datetime,
    hours: float,
) -> list[Candidate]:
    """Uvurderede kandidater fundet inden for `hours`, ikke fra ai:false-kilder, nyeste først."""
    cutoff = ensure_utc(now) - timedelta(hours=hours)
    out = [
        c
        for c in candidates
        if c.id not in judgments
        and c.source in info
        and info[c.source].ai
        and ensure_utc(c.first_seen) >= cutoff
    ]
    return sort_newest_first(out)


def build_pending(
    config: Config,
    sources: list[Source],
    candidates: list[Candidate],
    judgments: dict[str, Judgment],
    now: datetime,
    hours: float,
    max_items: int,
) -> dict[str, Any]:
    info = known_sources(sources, config.publishers)
    pending = pending_candidates(info, candidates, judgments, now, hours)[: max(0, max_items)]

    cutoff = ensure_utc(now) - timedelta(hours=RECENT_APPROVED_HOURS)
    recent: list[dict[str, Any]] = []
    cand_ids = set()
    for c in candidates:
        cand_ids.add(c.id)
        j = judgments.get(c.id)
        if j is None or not j.relevant or c.source not in info:
            continue
        if item_time(c) >= cutoff or ensure_utc(c.first_seen) >= cutoff:
            recent.append(
                {"id": c.id, "title": c.title, "source_name": info[c.source].name, "published": item_time(c)}
            )
    for j in judgments.values():
        ni = j.new_item
        if ni is None or not j.relevant or j.id in cand_ids or ni.source not in info:
            continue
        when = ensure_utc(ni.published or j.judged_at)
        if when >= cutoff or ensure_utc(j.judged_at) >= cutoff:
            recent.append({"id": j.id, "title": ni.title, "source_name": info[ni.source].name, "published": when})
    recent.sort(key=lambda r: r["id"])
    recent.sort(key=lambda r: r["published"], reverse=True)
    for r in recent:
        r["published"] = iso(r["published"])

    return {
        "now": iso(now),
        "profile": config.profile,
        "topics": [{"id": t.id, "name": t.name, "definition": t.definition} for t in config.topics],
        "genres": [{"id": g.id, "label": g.label} for g in config.genres],
        "pending": [
            {
                "id": c.id,
                "url": c.url,
                "title": c.title,
                "teaser": c.teaser,
                "source_name": info[c.source].name,
                "category": info[c.source].category,
                "lang": c.lang,
                "published": iso(c.published),
                "rule_topics": list(c.topics),
                "rule_genre": c.genre,
                "prefilter": {"decision": c.why.decision, "score": c.why.score, "hits": list(c.why.hits)},
            }
            for c in pending
        ],
        "recent_approved": recent,
    }


def compact_json(obj: Any) -> str:
    """Kompakt men læsbar JSON til Claude: én linje pr. topnøgle og pr. listeelement."""

    def one(v: Any) -> str:
        return json.dumps(v, ensure_ascii=False, separators=(",", ":"))

    if not isinstance(obj, dict):
        return one(obj)
    parts: list[str] = []
    for k, v in obj.items():
        if isinstance(v, list) and v and isinstance(v[0], dict):
            body = ",\n  ".join(one(x) for x in v)
            parts.append(f"{one(k)}:[\n  {body}\n]")
        else:
            parts.append(f"{one(k)}:{one(v)}")
    return "{\n" + ",\n".join(parts) + "\n}"


def print_json(obj: Any) -> None:
    print(compact_json(obj))


def main_pending(args: argparse.Namespace) -> int:
    now = now_utc(getattr(args, "now", None))
    config = load_config(paths.CONFIG_DIR)
    sources = load_sources(paths.SOURCES_FILE)
    hours = args.hours if getattr(args, "hours", None) is not None else config.settings.pending_hours
    max_items = args.max if getattr(args, "max", None) is not None else 200
    out = build_pending(config, sources, load_all_candidates(), load_judgments(), now, hours, max_items)
    day = to_cph(now).date().isoformat()
    log.info(
        "%d uvurderede indslag; skriv vurderinger i data/judgments/%s.jsonl med judged_at %s",
        len(out["pending"]),
        day,
        out["now"],
    )
    print_json(out)
    return 0


# ── validate-judgments ──────────────────────────────────────


def validate_lines(
    files: list[Path],
    candidates: list[Candidate],
    info: dict[str, SourceInfo],
    known_ids: set[str],
) -> tuple[list[str], int]:
    """Validerer linjerne i `files`. Returnerer (fejl som "fil:linje: besked", antal linjer)."""
    cand_by_id = {c.id: c for c in candidates}
    errors: list[str] = []
    count = 0
    for path in files:
        name = rel(path)
        m = JUDGMENT_FILE_RE.match(path.name)
        if not m:
            errors.append(f"{name}:0: filnavnet skal være ÅÅÅÅ-MM-DD.jsonl")
        file_day = m.group(1) if m else None
        if not path.is_file():
            errors.append(f"{name}:0: filen findes ikke")
            continue
        for n, line in _lines(path):
            count += 1
            try:
                j = Judgment.model_validate_json(line)
            except ValidationError as e:
                errors.extend(f"{name}:{n}: {msg}" for msg in format_errors(e))
                continue
            errors.extend(f"{name}:{n}: {msg}" for msg in _check(j, cand_by_id, info, known_ids, file_day))
    return errors, count


def _check(
    j: Judgment,
    cand_by_id: dict[str, Candidate],
    info: dict[str, SourceInfo],
    known_ids: set[str],
    file_day: str | None,
) -> list[str]:
    msgs: list[str] = []
    lang: str | None = None
    if j.new_item is not None:
        expected = item_id(j.new_item.url)
        if j.id != expected:
            msgs.append(f"id skal være item_id(new_item.url) = {expected}")
        src = info.get(j.new_item.source)
        if src is None:
            msgs.append(
                f"new_item.source '{j.new_item.source}' er ukendt (skal være aktiv i sources.yaml "
                "eller stå i config/medier.yaml)"
            )
        else:
            lang = src.lang
        if not j.relevant:
            msgs.append("sweep-fund (new_item) skal have relevant=true")
    else:
        cand = cand_by_id.get(j.id)
        if cand is None:
            msgs.append(f"id '{j.id}' findes ikke blandt kandidaterne (og new_item mangler)")
        else:
            lang = cand.lang
    if j.summary_da is not None and lang == "da":
        msgs.append("summary_da skal være null, når indslaget er på dansk")
    if j.story_hint is not None:
        if j.story_hint == j.id:
            msgs.append("story_hint må ikke pege på indslaget selv")
        elif j.story_hint not in known_ids:
            msgs.append(f"story_hint '{j.story_hint}' er ikke et kendt indslag")
    if file_day is not None:
        day = to_cph(j.judged_at).date().isoformat()
        if day != file_day:
            msgs.append(f"judged_at er {day} i København; linjen hører til i data/judgments/{day}.jsonl")
    return msgs


def main_validate(args: argparse.Namespace) -> int:
    config = load_config(paths.CONFIG_DIR)
    sources = load_sources(paths.SOURCES_FILE)
    info = known_sources(sources, config.publishers)
    candidates = load_all_candidates()
    known_ids = {c.id for c in candidates} | {j.id for j in _parse_all(warn=False) if j.new_item is not None}
    file_arg = getattr(args, "file", None)
    if file_arg:
        p = Path(file_arg)
        # Relative stier regnes fra repoets rod (som export --out), ellers fra cwd
        files = [p if p.is_absolute() else (paths.ROOT / p)]
        if not files[0].exists() and not p.is_absolute():
            files = [Path.cwd() / p]
    else:
        files = judgment_files()
    errors, count = validate_lines(files, candidates, info, known_ids)
    for e in errors:
        print(e)
    if errors:
        print(f"validate-judgments: {len(errors)} fejl i {count} linjer ({len(files)} filer)")
        return 1
    print(f"validate-judgments: OK, {count} linjer i {len(files)} filer")
    return 0


# ── heartbeat ───────────────────────────────────────────────


def main_heartbeat(args: argparse.Namespace) -> int:
    now = now_utc(getattr(args, "now", None))
    prev = load_heartbeat()
    since = ensure_utc(prev.last_run) if prev else now - timedelta(hours=24)
    judged_now = [j for j in load_judgment_list() if ensure_utc(j.judged_at) > since]
    pending_after = 0
    try:
        config = load_config(paths.CONFIG_DIR)
        sources = load_sources(paths.SOURCES_FILE)
        info = known_sources(sources, config.publishers)
        pending_after = len(
            pending_candidates(info, load_all_candidates(), load_judgments(), now, config.settings.pending_hours)
        )
    except Exception as e:  # heartbeat skal skrives, selv om resten fejler
        log.warning("kunne ikke tælle uvurderede indslag: %s", e)
    judged = len({j.id for j in judged_now})
    swept = len({j.id for j in judged_now if j.new_item is not None})
    hb = Heartbeat(last_run=now, pending_before=pending_after + judged - swept, judged=judged)
    store.write_json(paths.HEARTBEAT_FILE, hb.model_dump(mode="json"))
    log.info("heartbeat %s: %d vurderet, %d ventede før kørslen", iso(now), hb.judged, hb.pending_before)
    return 0
