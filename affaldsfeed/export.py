"""export-kommandoen: bygger _site/ med data/feed.json, data/status.json og data/timeline.json (KONTRAKTER §7.3 og §8-9)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from affaldsfeed import paths, store
from affaldsfeed.config import ConfigError, load_config, load_sources
from affaldsfeed.display import (
    build_display_items,
    item_time,
    known_sources,
    source_category_map,
    split_ids,
    story_hints,
)
from affaldsfeed.health import silent
from affaldsfeed.judgments import display_mode, load_all_candidates, load_heartbeat, load_judgment_list
from affaldsfeed.models import DisplayItem, Feed, Geo
from affaldsfeed.overview import PERIODS, load_overviews
from affaldsfeed.stories import build_stories
from affaldsfeed.timeline import export_timeline
from affaldsfeed.timeutil import ensure_utc, iso, now_utc

log = logging.getLogger(__name__)

FEED_VERSION = 1
REJECTED_DAYS = 30
SAMPLE_NAMES = ("feed.sample.json", "timeline.sample.json")


def dumps(obj: Any) -> str:
    """Deterministisk, kompakt JSON i UTF-8 (indent=None)."""
    return json.dumps(obj, ensure_ascii=False, indent=None, separators=(",", ":")) + "\n"


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _sort_items(items: list[DisplayItem]) -> list[DisplayItem]:
    """published faldende, derefter id; also efter published (stigende), derefter id."""
    out = []
    for d in items:
        also = sorted(d.also, key=lambda a: a.id)
        also.sort(key=lambda a: ensure_utc(a.published).timestamp() if a.published else float("inf"))
        out.append(d.model_copy(update={"also": also}))
    out.sort(key=lambda d: d.id)
    out.sort(key=item_time, reverse=True)
    return out


def geo_block(geo: Geo, items: list[DisplayItem]) -> dict[str, Any] | None:
    """geo i feed.json: alle regioner og kommuner, men kun byer, som indslagene nævner (inkl. also).

    None, når der ingen geografi er (config/geografi.yaml mangler).
    """
    if not geo.regioner:
        return None
    used = {p[2:] for d in items for p in d.places if p.startswith("b:")}
    return {
        "regioner": [{"id": r.id, "navn": r.navn, "kort": r.kort} for r in geo.regioner],
        "kommuner": [{"id": m.id, "navn": m.navn, "kort": m.kort, "region": m.region} for m in geo.kommuner],
        "byer": [
            {"id": t.id, "navn": t.navn, "kommune": t.kommune, "kommuner": list(t.kommuner or [t.kommune])}
            for t in sorted(geo.byer, key=lambda t: t.id)
            if t.id in used
        ],
    }


def build_all(now: datetime) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """(feed.json, status.json, timeline.json) som dicts."""
    now = ensure_utc(now)
    config = load_config(paths.CONFIG_DIR)
    sources = load_sources(paths.SOURCES_FILE)
    settings = config.settings
    since = now - timedelta(days=settings.window_days)

    candidates = [c for c in load_all_candidates(since - timedelta(days=1)) if item_time(c) >= since]
    judgment_list = load_judgment_list()
    judgments = {j.id: j for j in judgment_list}
    heartbeat = load_heartbeat()
    mode = display_mode(now, heartbeat, settings.routine)

    shown = build_display_items(config, sources, candidates, judgments, mode, now, since)
    heads = build_stories(
        shown,
        source_category_map(sources, config.publishers),
        story_hints(judgments),
        settings.story_title_window_days,
        settings.story_max_age_days,
        no_merge=split_ids(config, shown),
        # Dagsbundter kun i feedet; overblik og tidslinje ser dokumenterne hver for sig
        bundle_day={s.id for s in sources if s.bundle == "day"},
    )
    heads = _sort_items(heads)

    if heartbeat is not None:
        last_judgment = iso(heartbeat.last_run)
    elif judgment_list:
        last_judgment = iso(max(ensure_utc(j.judged_at) for j in judgment_list))
    else:
        last_judgment = None

    states = store.load_source_states()
    info = known_sources(sources, config.publishers)
    used = {d.source for d in heads} | {a.source for d in heads for a in d.also}
    feed_sources = []
    for sid in sorted(info):
        si = info[sid]
        if si.via_search and sid not in used:
            continue
        st = states.get(sid)
        health = "groen" if si.via_search else (st.health if st else "graa")
        feed_sources.append(
            {
                "id": si.id,
                "name": si.name,
                "category": si.category,
                "homepage": si.homepage,
                "lang": si.lang,
                "paywall": si.paywall,
                "owner": si.owner,
                "status": si.status,
                "health": health,
                "via_search": si.via_search,
            }
        )

    overviews = load_overviews()
    feed = {
        "version": FEED_VERSION,
        "generated": iso(now),
        "window_days": settings.window_days,
        "mode": mode,
        "last_judgment": last_judgment,
        "categories": [c.model_dump(mode="json") for c in config.categories],
        "topics": [
            {"id": t.id, "name": t.name, "short": t.short, "definition": t.definition} for t in config.topics
        ],
        "genres": [{"id": g.id, "label": g.label} for g in config.genres],
        "sources": feed_sources,
        "geo": geo_block(config.geo, heads),
        "overview": {p: (ov.model_dump(mode="json") if ov else None) for p, ov in overviews.items()},
        "items": [d.model_dump(mode="json") for d in heads],
    }
    Feed.model_validate(feed)  # kontrakten (KONTRAKTER §8); ValidationError giver exit 1

    status_sources = []
    for s in sorted(sources, key=lambda s: s.id):
        st = states.get(s.id)
        status_sources.append(
            {
                "id": s.id,
                "name": s.name,
                "category": s.category,
                "status": s.status,
                "health": st.health if st and s.status == "aktiv" else "graa",
                "last_ok": st.last_ok.isoformat() if st and st.last_ok else None,
                "fails": st.fails if st else 0,
                "last_error": st.last_error if st else None,
                "items_30d": st.items_30d if st else 0,
                "silent": bool(silent(st)) if st else False,
            }
        )
    status = {
        "generated": iso(now),
        "sources": status_sources,
        "counts": {
            "candidates_60d": len(candidates),
            "shown_60d": len(shown),
            "rejected_30d": len(store.load_rejected(now - timedelta(days=REJECTED_DAYS))),
        },
    }
    timeline = export_timeline(now, config, heads)
    return feed, status, timeline


def build_feed(now: datetime) -> dict[str, Any]:
    """feed.json som dict (KONTRAKTER §8)."""
    return build_all(now)[0]


def _resolve_out(out: str | None) -> Path:
    p = Path(out or "_site")
    return p if p.is_absolute() else paths.ROOT / p


def main_export(args: argparse.Namespace) -> int:
    now = now_utc(getattr(args, "now", None))
    out = _resolve_out(getattr(args, "out", None))
    site = paths.SITE_DIR.resolve()
    if out.resolve() == site or site in out.resolve().parents:
        log.error("--out må ikke ligge i site/: %s", out)
        return 1
    try:
        feed, status, timeline = build_all(now)
    except (ValidationError, ConfigError) as e:
        log.error("eksporten fejlede (skemafejl): %s", e)
        return 1

    try:
        out.mkdir(parents=True, exist_ok=True)
        if paths.SITE_DIR.is_dir():
            shutil.copytree(paths.SITE_DIR, out, dirs_exist_ok=True)
        else:
            log.warning("site/ findes ikke; kun data skrives")
        _write_text(out / "data" / "feed.json", dumps(feed))
        _write_text(out / "data" / "status.json", dumps(status))
        _write_text(out / "data" / "timeline.json", dumps(timeline))
        for name in SAMPLE_NAMES:
            sample = paths.EXAMPLES_DIR / name
            if sample.is_file():
                shutil.copyfile(sample, out / "data" / name)
    except OSError as e:
        log.error("kunne ikke skrive %s: %s", out, e)
        return 1

    n_also = sum(len(d["also"]) for d in feed["items"])
    n_places = sum(bool(d["places"]) for d in feed["items"])
    filled = [p for p in PERIODS if feed["overview"][p]]
    log.info(
        "eksport til %s: %d indslag (+%d i historier, %d med steder), tilstand %s, overblik: %s, tidslinje: %d",
        out, len(feed["items"]), n_also, n_places, feed["mode"], ", ".join(filled) or "intet",
        len(timeline["events"]),
    )
    return 0
