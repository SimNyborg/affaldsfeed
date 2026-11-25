"""Kontrol af resuméer mod kilden (KONTRAKTER §6.2b): routinen spørger for hvert resumé, om det nævner noget,
der ikke står i titlen eller teaseren. Et afvist resumé vises ikke, og indslaget står kun med titel."""

from __future__ import annotations

import argparse
import logging
import re
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from affaldsfeed import paths
from affaldsfeed.display import SourceInfo, item_time
from affaldsfeed.models import Candidate, Judgment, SummaryCheck, full_text, summary_sha
from affaldsfeed.timeutil import ensure_utc, to_cph

log = logging.getLogger(__name__)

CHECK_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.jsonl$")


# ── Indlæsning ──────────────────────────────────────────────


def check_files() -> list[Path]:
    """Kontrolfiler (ÅÅÅÅ-MM-DD.jsonl) i datoorden."""
    d = paths.SUMMARY_CHECKS_DIR
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir() if p.is_file() and CHECK_FILE_RE.match(p.name))


def _lines(path: Path) -> Iterator[tuple[int, str]]:
    with path.open(encoding="utf-8-sig") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if line:
                yield n, line


def load_checks() -> dict[tuple[str, str], SummaryCheck]:
    """Seneste gyldige kontrol pr. (id, summary_sha). Ugyldige linjer springes over med en advarsel."""
    out: dict[tuple[str, str], SummaryCheck] = {}
    for path in check_files():
        for n, line in _lines(path):
            try:
                c = SummaryCheck.model_validate_json(line)
            except ValidationError as e:
                log.warning("%s:%d: ugyldig kontrol springes over (%s)", path.name, n, e.errors()[0]["msg"])
                continue
            out[(c.id, c.summary_sha)] = c
    return out


def rejected_summaries(checks: dict[tuple[str, str], SummaryCheck]) -> set[tuple[str, str]]:
    """(id, summary_sha) for de resuméer, kontrollen har afvist. Et nyt resumé til samme id er ikke afvist."""
    return {key for key, c in checks.items() if not c.ok}


def check_counts(checks: dict[tuple[str, str], SummaryCheck]) -> dict[str, int]:
    """Antal kontrollerede og afviste resuméer i alt (status.json)."""
    return {"summaries_checked": len(checks), "summaries_rejected": len(rejected_summaries(checks))}


# ── Køen af resuméer, der ikke er kontrolleret ──────────────


def _source_text(
    iid: str, cand_by_id: dict[str, Candidate], judgments: dict[str, Judgment], info: dict[str, SourceInfo]
) -> tuple[dict[str, Any], datetime] | None:
    """Titel, teaser og afsender, som resuméet blev skrevet ud fra, og indslagets tidspunkt."""
    j = judgments.get(iid)
    if j is None or not j.relevant:
        return None
    c = cand_by_id.get(iid)
    if c is not None:
        src = info.get(c.source)
        if src is None or not full_text(src.ai):
            return None
        return {"title": c.title, "teaser": c.teaser, "source_name": src.name, "lang": c.lang}, item_time(c)
    ni = j.new_item
    if ni is None:
        return None
    src = info.get(ni.source)
    if src is None or not full_text(src.ai):
        return None
    when = ensure_utc(ni.published or j.judged_at)
    return {"title": ni.title, "teaser": ni.teaser, "source_name": src.name, "lang": src.lang}, when


def check_queue(
    info: dict[str, SourceInfo],
    candidates: list[Candidate],
    judgments: dict[str, Judgment],
    summaries: dict[str, str],
    checks: dict[tuple[str, str], SummaryCheck],
    since: datetime,
    limit: int,
) -> tuple[list[dict[str, Any]], int]:
    """Viste resuméer i feedets vindue uden kontrol af netop den tekst, nyeste først (højst limit), og antallet i alt.

    summaries: resuméet, feedet viser pr. id (summaries.effective_summaries).
    """
    cand_by_id = {c.id: c for c in candidates}
    rows: list[tuple[datetime, str, dict[str, Any]]] = []
    for iid, text in summaries.items():
        sha = summary_sha(text)
        if (iid, sha) in checks:
            continue
        found = _source_text(iid, cand_by_id, judgments, info)
        if found is None or found[1] < since:
            continue
        entry, when = found
        rows.append((when, iid, {"id": iid, **entry, "summary_da": text, "summary_sha": sha}))
    rows.sort(key=lambda r: r[1])
    rows.sort(key=lambda r: r[0], reverse=True)
    return [r[2] for r in rows[: max(0, limit)]], len(rows)


def main_summary_check_input(args: argparse.Namespace) -> int:
    # Sent: judgments importerer summaries, som display bruger
    from affaldsfeed.config import load_config, load_sources
    from affaldsfeed.display import known_sources
    from affaldsfeed.judgments import load_all_candidates, load_judgments, print_json
    from affaldsfeed.summaries import effective_summaries, load_summaries
    from affaldsfeed.timeutil import iso, now_utc

    now = now_utc(getattr(args, "now", None))
    config = load_config(paths.CONFIG_DIR)
    settings = config.settings
    limit = args.max if getattr(args, "max", None) is not None else settings.summaries.check_per_run
    judgments = load_judgments()
    items, total = check_queue(
        known_sources(load_sources(paths.SOURCES_FILE), config.publishers),
        load_all_candidates(),
        judgments,
        effective_summaries(judgments, load_summaries()),
        load_checks(),
        settings.window_since(now),
        limit,
    )
    day = to_cph(now).date().isoformat()
    log.info("%d af %d resuméer skal kontrolleres; skriv linjerne i data/judgments/kontrol/%s.jsonl", len(items), total, day)
    print_json({"now": iso(now), "items": items, "total": total})
    return 0


# ── validate-summary-checks ─────────────────────────────────


def written_shas(judgment_list: list[Judgment], summary_lines: list[tuple[str, str]]) -> dict[str, set[str]]:
    """Fingeraftryk af alle resuméer, der nogensinde er skrevet pr. id (vurderinger og resumélinjer)."""
    out: dict[str, set[str]] = {}
    for j in judgment_list:
        if j.summary_da:
            out.setdefault(j.id, set()).add(summary_sha(j.summary_da))
    for iid, text in summary_lines:
        out.setdefault(iid, set()).add(summary_sha(text))
    return out


def check_line(c: SummaryCheck, shas: dict[str, set[str]], file_day: str | None) -> list[str]:
    msgs: list[str] = []
    if c.summary_sha not in shas.get(c.id, set()):
        msgs.append(
            f"summary_sha '{c.summary_sha}' passer ikke med et resumé til '{c.id}'; kopiér id og summary_sha "
            "præcist fra summary-check-input"
        )
    if file_day is not None:
        day = to_cph(c.checked_at).date().isoformat()
        if day != file_day:
            msgs.append(f"checked_at er {day} i København; linjen hører til i data/judgments/kontrol/{day}.jsonl")
    return msgs


def _all_summary_lines() -> list[tuple[str, str]]:
    """(id, summary_da) for alle læsbare resumélinjer med tekst."""
    from affaldsfeed.models import Summary
    from affaldsfeed.summaries import summary_files

    out: list[tuple[str, str]] = []
    for path in summary_files():
        for _, line in _lines(path):
            try:
                s = Summary.model_validate_json(line)
            except ValidationError:
                continue
            if s.summary_da:
                out.append((s.id, s.summary_da))
    return out


def main_validate_summary_checks(args: argparse.Namespace) -> int:
    from affaldsfeed.judgments import format_errors, load_judgment_list, rel

    file_arg = getattr(args, "file", None)
    if file_arg:
        p = Path(file_arg)
        files = [p if p.is_absolute() else (paths.ROOT / p)]
        if not files[0].exists() and not p.is_absolute():
            files = [Path.cwd() / p]
    else:
        files = check_files()
    shas = written_shas(load_judgment_list(), _all_summary_lines())
    errors: list[str] = []
    count = 0
    for path in files:
        name = rel(path)
        m = CHECK_FILE_RE.match(path.name)
        if not m:
            errors.append(f"{name}:0: filnavnet skal være ÅÅÅÅ-MM-DD.jsonl")
        if not path.is_file():
            errors.append(f"{name}:0: filen findes ikke")
            continue
        for n, line in _lines(path):
            count += 1
            try:
                c = SummaryCheck.model_validate_json(line)
            except ValidationError as e:
                errors.extend(f"{name}:{n}: {msg}" for msg in format_errors(e))
                continue
            errors.extend(f"{name}:{n}: {msg}" for msg in check_line(c, shas, m.group(1) if m else None))
    for e in errors:
        print(e)
    if errors:
        print(f"validate-summary-checks: {len(errors)} fejl i {count} linjer ({len(files)} filer)")
        return 1
    print(f"validate-summary-checks: OK, {count} linjer i {len(files)} filer")
    return 0
