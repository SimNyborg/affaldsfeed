"""Kildesundhed: hvornår en kilde er på tur, fejl i træk og statusfarve."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from affaldsfeed.models import Settings, Source, SourceState
from affaldsfeed.timeutil import ensure_utc, to_cph

# Kørslerne ligger ikke præcist en time fra hinanden (GitHub-cron forsinkes), så der er slæk
DUE_SLACK = timedelta(minutes=30)
RED_EVERY_HOURS = 24
SILENT_DAYS = 30


def is_due(source: Source, state: SourceState, now: datetime) -> bool:
    """Er kilden på tur? Røde kilder prøves kun én gang i døgnet."""
    if state.last_attempt is None:
        return True
    every = source.every_hours
    if state.health == "roed":
        every = max(every, RED_EVERY_HOURS)
    elapsed = ensure_utc(now) - ensure_utc(state.last_attempt)
    return elapsed >= timedelta(hours=every) - DUE_SLACK


def record_result(state: SourceState, ok: bool, error: str | None, now: datetime, settings: Settings) -> SourceState:
    """Ny state efter et forsøg. last_ok gemmes kun som dato (København)."""
    update: dict = {"last_attempt": ensure_utc(now)}
    if ok:
        today = to_cph(now).date()
        update.update(
            {
                "since": state.since or today,
                "last_ok": today,
                "fails": 0,
                "last_error": None,
                "first_run_done": True,
                "health": "groen",
            }
        )
    else:
        fails = state.fails + 1
        update.update(
            {
                "fails": fails,
                "last_error": (error or "ukendt fejl")[:300],
                "health": "roed" if fails >= settings.red_after_fails else "gul",
            }
        )
    return state.model_copy(update=update)


def silent(state: SourceState, today: date) -> bool:
    """Tavs kilde: den er fulgt i mindst 30 dage, svarer, men har ingen indslag de seneste 30 dage."""
    followed = state.since is not None and today - state.since >= timedelta(days=SILENT_DAYS)
    return followed and state.first_run_done and state.fails == 0 and state.items_30d == 0
