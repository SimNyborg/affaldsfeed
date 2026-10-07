"""Læsning og atomisk skrivning af data/ (kandidater, afviste, state). Filer skrives kun ved ændring."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from affaldsfeed import paths
from affaldsfeed.models import Candidate, Rejected, SourceState
from affaldsfeed.timeutil import ensure_utc, iso, parse_iso, to_cph

log = logging.getLogger(__name__)

KILDEFORSLAG_TOP = 50


# ── Grundfunktioner ─────────────────────────────────────────


def _write_text(path: Path, text: str) -> bool:
    """Skriv atomisk (.tmp + os.replace), kun hvis indholdet er ændret."""
    data = text.encode("utf-8")
    try:
        if path.read_bytes() == data:
            return False
    except FileNotFoundError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return True


def _dumps_line(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


_M = TypeVar("_M", bound=BaseModel)


INVALID_LINES_LOGGED = 3  # så mange ugyldige linjer pr. fil logges enkeltvis; resten samles


def read_jsonl_counted(path: Path, model: type[_M]) -> tuple[list[_M], int]:
    """Læs én model pr. linje. Returnerer (poster, antal ugyldige linjer, der blev sprunget over)."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [], 0
    out: list[_M] = []
    skipped = 0
    for n, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            out.append(model.model_validate_json(line))
        except ValidationError as e:
            skipped += 1
            if skipped <= INVALID_LINES_LOGGED:
                err = e.errors()[0]
                loc = ".".join(str(x) for x in err.get("loc", ()))
                log.warning("%s linje %d er ugyldig og springes over: %s%s", path.name, n,
                            f"{loc}: " if loc else "", err.get("msg"))
    if skipped > INVALID_LINES_LOGGED:
        log.warning("%s: %d ugyldige linjer i alt sprunget over", path.name, skipped)
    return out, skipped


def read_jsonl(path: Path, model: type[_M]) -> list[_M]:
    """Læs én model pr. linje. Ugyldige linjer logges og springes over."""
    return read_jsonl_counted(path, model)[0]


def _keep_unreadable(path: Path, skipped: int, lost: list[str]) -> None:
    """En månedsfil med linjer, koden ikke kan læse, skrives aldrig om (KONTRAKTER §6)."""
    example = f" (fx {', '.join(lost[:3])})" if lost else ""
    log.error(
        "%s/%s: %d linjer kan ikke læses (fx felter fra en anden version af koden). Filen skrives ikke om, "
        "og %d nye eller ændrede poster for måneden gemmes ikke%s. Ret koden fremad, så den kan læse linjerne.",
        path.parent.name, path.name, skipped, len(lost), example,
    )


def write_jsonl(path: Path, records: list[BaseModel], sort_key: Callable[[Any], Any] | None = None) -> bool:
    """Skriv poster (sorteret) som JSONL. Returnerer True hvis filen blev ændret."""
    items = sorted(records, key=sort_key) if sort_key else list(records)
    text = "".join(_dumps_line(r.model_dump(mode="json")) + "\n" for r in items)
    return _write_text(path, text)


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        log.warning("%s kan ikke læses (%s); bruger standardværdi", path.name, e)
        return default


def write_json(path: Path, obj: Any) -> bool:
    """Skriv JSON med indrykning (læsbare diffs). Returnerer True hvis filen blev ændret."""
    return _write_text(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def _month_key(dt: datetime) -> str:
    return ensure_utc(dt).strftime("%Y-%m")


def _month_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(p for p in directory.glob("*.jsonl") if len(p.stem) == 7 and p.stem[4] == "-")


# ── Kandidater ──────────────────────────────────────────────


def load_candidates(since: datetime | None = None) -> list[Candidate]:
    """Alle kandidater, eller kun dem med first_seen >= since. Sorteret efter fil (måned) og id."""
    out: list[Candidate] = []
    since_month = _month_key(since) if since else None
    for f in _month_files(paths.CANDIDATES_DIR):
        if since_month and f.stem < since_month:
            continue
        for c in read_jsonl(f, Candidate):
            if since is None or c.first_seen >= ensure_utc(since):
                out.append(c)
    return out


def save_candidates(records: list[Candidate]) -> int:
    """Flet nye og opdaterede kandidater ind i månedsfilerne (måned = first_seen, UTC).

    En månedsfil med linjer, der ikke kan læses, skrives ikke om; dens nye poster logges som fejl.
    Returnerer antallet af poster, der blev tilføjet eller ændret.
    """
    by_month: dict[str, list[Candidate]] = {}
    for r in records:
        by_month.setdefault(_month_key(r.first_seen), []).append(r)
    changed = 0
    for month, recs in sorted(by_month.items()):
        path = paths.CANDIDATES_DIR / f"{month}.jsonl"
        current, skipped = read_jsonl_counted(path, Candidate)
        existing = {c.id: c for c in current}
        fresh = [r for r in recs if existing.get(r.id) != r]
        if skipped:
            if fresh:
                _keep_unreadable(path, skipped, [r.url for r in fresh])
            continue
        changed += len(fresh)
        for r in recs:
            existing[r.id] = r
        write_jsonl(path, list(existing.values()), sort_key=lambda c: c.id)
    return changed


# ── Afviste ─────────────────────────────────────────────────


def load_rejected(since: datetime | None = None) -> list[Rejected]:
    out: list[Rejected] = []
    since_month = _month_key(since) if since else None
    for f in _month_files(paths.REJECTED_DIR):
        if since_month and f.stem < since_month:
            continue
        for r in read_jsonl(f, Rejected):
            if since is None or r.first_seen >= ensure_utc(since):
                out.append(r)
    return out


def save_rejected(records: list[Rejected], keep_days: int, now: datetime) -> int:
    """Flet afviste ind (første fund bevares) og ryd op efter keep_days. Returnerer antal nye poster."""
    cutoff = ensure_utc(now) - timedelta(days=keep_days)
    by_month: dict[str, list[Rejected]] = {}
    for r in records:
        by_month.setdefault(_month_key(r.first_seen), []).append(r)

    # Et id skal kun stå ét sted: find eksisterende på tværs af måneder
    files = _month_files(paths.REJECTED_DIR)
    existing_month: dict[str, str] = {}
    contents: dict[str, dict[str, Rejected]] = {}
    unreadable: dict[str, int] = {}  # måned -> antal linjer, der ikke kan læses (filen skrives ikke om)
    for f in files:
        current, skipped = read_jsonl_counted(f, Rejected)
        if skipped:
            unreadable[f.stem] = skipped
        recs = {r.id: r for r in current}
        contents[f.stem] = recs
        for rid in recs:
            existing_month[rid] = f.stem

    added = 0
    lost: dict[str, list[str]] = {}
    for month, recs in by_month.items():
        for r in recs:
            m = existing_month.get(r.id)
            if m is None:
                if month in unreadable:
                    lost.setdefault(month, []).append(r.url)
                    continue
                contents.setdefault(month, {})[r.id] = r
                existing_month[r.id] = month
                added += 1
            elif m not in unreadable:
                old = contents[m][r.id]
                # Bevar første fund; opdatér titel og begrundelse
                contents[m][r.id] = old.model_copy(update={"title": r.title, "why": r.why, "url": r.url})

    for month, recs in sorted(contents.items()):
        path = paths.REJECTED_DIR / f"{month}.jsonl"
        if month in unreadable:
            _keep_unreadable(path, unreadable[month], lost.get(month, []))
            continue
        kept = [r for r in recs.values() if r.first_seen >= cutoff]
        if not kept:
            if path.exists():
                path.unlink()
                log.info("Fjernede udløbet fil med afviste: %s", path.name)
            continue
        write_jsonl(path, kept, sort_key=lambda r: r.id)
    return added


# ── State ───────────────────────────────────────────────────


def load_source_states() -> dict[str, SourceState]:
    raw = read_json(paths.STATE_DIR / "sources.json", {})
    out: dict[str, SourceState] = {}
    if not isinstance(raw, dict):
        return out
    for sid, val in raw.items():
        try:
            out[sid] = SourceState.model_validate(val)
        except ValidationError as e:
            log.warning("state/sources.json: %s er ugyldig og nulstilles: %s", sid, e.errors()[0].get("msg"))
    return out


def save_source_states(states: dict[str, SourceState]) -> bool:
    obj = {sid: states[sid].model_dump(mode="json") for sid in sorted(states)}
    return write_json(paths.STATE_DIR / "sources.json", obj)


def _load_dict(name: str) -> dict:
    raw = read_json(paths.STATE_DIR / name, {})
    return raw if isinstance(raw, dict) else {}


def _save_dict(name: str, d: dict) -> bool:
    return write_json(paths.STATE_DIR / name, {k: d[k] for k in sorted(d)})


def load_http_cache() -> dict:
    return _load_dict("http.json")


def save_http_cache(d: dict) -> bool:
    return _save_dict("http.json", d)


def load_robots_cache() -> dict:
    return _load_dict("robots.json")


def save_robots_cache(d: dict) -> bool:
    return _save_dict("robots.json", d)


_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def load_seen() -> dict[str, dict[str, str]]:
    """state/seen.json: {kilde-id: {item-id: "ÅÅÅÅ-MM-DD"}} med dagen (København), URL'en sidst blev set."""
    out: dict[str, dict[str, str]] = {}
    for sid, entries in _load_dict("seen.json").items():
        if not isinstance(entries, dict):
            log.warning("state/seen.json: %s er ugyldig og nulstilles", sid)
            continue
        out[sid] = {k: v for k, v in entries.items() if isinstance(v, str) and _DAY_RE.match(v)}
    return out


def save_seen(
    seen: dict[str, dict[str, str]], now: datetime, source_ids: Iterable[str], keep_days: int
) -> bool:
    """Gem seen-state med sorterede nøgler. True hvis filen blev ændret.

    Poster, der ikke er observeret i keep_days, og kilder, der ikke længere står i sources.yaml, fjernes.
    Filen oprettes ikke, før der er noget at gemme.
    """
    cut = (to_cph(now).date() - timedelta(days=keep_days)).isoformat()
    known = set(source_ids)
    obj: dict[str, dict[str, str]] = {}
    for sid in sorted(seen):
        if sid not in known:
            continue
        kept = {iid: seen[sid][iid] for iid in sorted(seen[sid]) if seen[sid][iid] >= cut}
        if kept:
            obj[sid] = kept
    path = paths.STATE_DIR / "seen.json"
    if not obj and not path.exists():
        return False
    return write_json(path, obj)


def load_kildeforslag() -> dict:
    return _load_dict("kildeforslag.json")


def _md_escape(s: str) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def kildeforslag_md(d: dict) -> str:
    """Markdown-oversigt over ukendte udgivere (top 50 efter antal)."""
    rows = sorted(d.items(), key=lambda kv: (-int(kv[1].get("count", 0)), kv[0]))[:KILDEFORSLAG_TOP]
    lines = [
        "# Kildeforslag",
        "",
        "Udgivere, som nyhedssøgningen har fundet, men som ikke står i `sources.yaml` eller `config/medier.yaml`.",
        "Deres artikler kommer ikke i feedet. Er en udgiver troværdig, så tilføj den til `config/medier.yaml`.",
        "",
        f"Genereres automatisk af `python -m affaldsfeed run`. Viser top {KILDEFORSLAG_TOP} efter antal artikler.",
        "",
    ]
    if not rows:
        lines.append("Ingen forslag endnu.")
        return "\n".join(lines) + "\n"
    lines += ["| Domæne | Navn | Artikler | Senest set | Eksempler |", "|---|---|---:|---|---|"]
    for domain, info in rows:
        last = info.get("last_seen") or ""
        with contextlib.suppress(ValueError):
            last = to_cph(parse_iso(last)).strftime("%Y-%m-%d") if last else ""
        examples = " ".join(f"[{i + 1}]({_md_escape(u)})" for i, u in enumerate(info.get("examples") or []))
        lines.append(
            f"| {_md_escape(domain)} | {_md_escape(info.get('name') or '')} | {int(info.get('count', 0))} "
            f"| {last} | {examples} |"
        )
    return "\n".join(lines) + "\n"


def save_kildeforslag(d: dict) -> bool:
    """Gem kildeforslag.json og generér kildeforslag.md. True hvis noget blev ændret."""
    changed = _save_dict("kildeforslag.json", d)
    changed_md = _write_text(paths.STATE_DIR / "kildeforslag.md", kildeforslag_md(d))
    return changed or changed_md


def merge_kildeforslag(
    d: dict, unknown: list[tuple[str, str, str]], now: datetime, max_ids: int = 200
) -> int:
    """Tilføj ukendte udgivere. Hver artikel tælles kun én gang. Returnerer antal nye artikler."""
    from affaldsfeed.normalize import item_id

    added = 0
    stamp = iso(now)
    for domain, name, url in unknown:
        if not domain or not url:
            continue
        entry = d.setdefault(domain, {"name": name or domain, "count": 0, "last_seen": None, "examples": [], "ids": []})
        entry.setdefault("ids", [])
        entry.setdefault("examples", [])
        iid = item_id(url)
        if iid in entry["ids"]:
            continue
        entry["ids"] = (entry["ids"] + [iid])[-max_ids:]
        entry["count"] = int(entry.get("count", 0)) + 1
        entry["last_seen"] = stamp
        if name:
            entry["name"] = name
        if url not in entry["examples"]:
            entry["examples"] = ([url] + entry["examples"])[:3]
        added += 1
    return added
