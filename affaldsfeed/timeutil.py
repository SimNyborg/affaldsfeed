"""Tidshjælpere. Alt gemmes i UTC; dage og vinduer regnes i København."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

CPH = ZoneInfo("Europe/Copenhagen")


def now_utc(override: str | None = None) -> datetime:
    """Nu i UTC, eller et fast tidspunkt fra --now (til test)."""
    if override:
        return parse_iso(override)
    return datetime.now(UTC).replace(microsecond=0)


def parse_iso(s: str) -> datetime:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def to_cph(dt: datetime) -> datetime:
    return ensure_utc(dt).astimezone(CPH)


def cph_day_bounds(dt: datetime) -> tuple[datetime, datetime]:
    """Start og slut (UTC) for den københavnske kalenderdag, som dt ligger i."""
    local = to_cph(dt)
    start_local = datetime.combine(local.date(), time.min, tzinfo=CPH)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def cph_day_start(d: date) -> datetime:
    """Starten (UTC) af den københavnske kalenderdag d."""
    return datetime.combine(d, time.min, tzinfo=CPH).astimezone(UTC)
