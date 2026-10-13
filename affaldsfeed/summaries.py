"""Resuméer med egne ord (KONTRAKTER §6.2a): kontrol mod ordret kopiering, indlæsning, køen af ældre
indslag uden resumé og validate-summaries. Feedet viser resuméet i stedet for kildens teaser."""

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
from affaldsfeed.models import Candidate, Judgment, Summary, SummarySettings
from affaldsfeed.timeutil import ensure_utc, to_cph

log = logging.getLogger(__name__)

SUMMARY_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.jsonl$")
WORD_RE = re.compile(r"[^\W_]+")


# ── Kontrol mod ordret kopiering ────────────────────────────


def _words(text: str) -> list[str]:
    return WORD_RE.findall(text.lower())


def longest_shared_run(a: list[str], b: list[str]) -> list[str]:
    """Den længste række ord, der står i træk i både a og b."""
    best_len = best_end = 0
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for k in range(1, len(b) + 1):
            if a[i - 1] == b[k - 1]:
                cur[k] = prev[k - 1] + 1
                if cur[k] > best_len:
                    best_len, best_end = cur[k], i
        prev = cur
    return a[best_end - best_len : best_end]


def copy_problem(summary: str, source: str, cfg: SummarySettings) -> str | None:
    """Fejlbesked, hvis resuméet kopierer for meget af kildens teaser, ellers None."""
    s, t = _words(summary), _words(source)
    if not s or not t:
        return None
    run = longest_shared_run(s, t)
    if len(run) > cfg.max_shared_run:
        return (
            f"summary_da kopierer {len(run)} ord i træk fra kildens teaser ('{' '.join(run)}'); "
            f"højst {cfg.max_shared_run}, skriv med egne ord"
        )
    tri_s = {tuple(s[i : i + 3]) for i in range(len(s) - 2)}
    if len(tri_s) >= 4:
        tri_t = {tuple(t[i : i + 3]) for i in range(len(t) - 2)}
        share = len(tri_s & tri_t) / len(tri_s)
        if share > cfg.max_trigram_share:
            return f"summary_da ligner kildens teaser for meget ({share:.0%} af ordtrioerne står i den); skriv med egne ord"
    return None


# ── Indlæsning ──────────────────────────────────────────────


def summary_files() -> list[Path]:
    """Resuméfiler (ÅÅÅÅ-MM-DD.jsonl) i datoorden."""
    d = paths.SUMMARIES_DIR
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir() if p.is_file() and SUMMARY_FILE_RE.match(p.name))


def _lines(path: Path) -> Iterator[tuple[int, str]]:
    with path.open(encoding="utf-8-sig") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if line:
                yield n, line


def load_summaries() -> dict[str, Summary]:
    """Seneste gyldige resumélinje pr. id. Ugyldige linjer springes over med en advarsel."""
    out: dict[str, Summary] = {}
    for path in summary_files():
        for n, line in _lines(path):
            try:
                s = Summary.model_validate_json(line)
            except ValidationError as e:
                log.warning("%s:%d: ugyldigt resumé springes over (%s)", path.name, n, e.errors()[0]["msg"])
                continue
            out[s.id] = s
    return out


def effective_summaries(judgments: dict[str, Judgment], summaries: dict[str, Summary]) -> dict[str, str]:
    """Resuméet, der vises for hvert id: det nyeste af vurderingens summary_da og en resumélinje.
    En linje med summary_da null giver intet resumé."""
    best: dict[str, tuple[datetime, str]] = {}
    for j in judgments.values():
        if j.summary_da:
            best[j.id] = (ensure_utc(j.judged_at), j.summary_da)
    for s in summaries.values():
        if s.summary_da is None:
            continue
        t = ensure_utc(s.written_at)
        if s.id not in best or t >= best[s.id][0]:
            best[s.id] = (t, s.summary_da)
    return {k: v[1] for k, v in best.items()}


def summarized_ids(judgments: dict[str, Judgment], summaries: dict[str, Summary]) -> set[str]:
    """Id'er, der ikke skal i rewrite: de har et resumé, eller teaseren er erklæret uden indhold (null)."""
    return set(effective_summaries(judgments, summaries)) | set(summaries)


# ── Køen af ældre indslag uden resumé ───────────────────────


def rewrite_queue(
    info: dict[str, SourceInfo],
    candidates: list[Candidate],
    judgments: dict[str, Judgment],
    have: set[str],
    since: datetime,
    cfg: SummarySettings,
    limit: int,
) -> tuple[list[dict[str, Any]], int]:
    """Godkendte indslag i feedets vindue uden resumé, nyeste først (højst limit), og antallet i alt.

    Kun kilder, Claude må læse (ai), og kun indslag med en teaser på mindst cfg.min_teaser_chars tegn.
    """
    rows: list[tuple[datetime, str, dict[str, Any]]] = []
    cand_ids: set[str] = set()
    for c in candidates:
        cand_ids.add(c.id)
        j = judgments.get(c.id)
        src = info.get(c.source)
        if j is None or not j.relevant or src is None or not src.ai or c.id in have:
            continue
        if len(c.teaser.strip()) < cfg.min_teaser_chars or item_time(c) < since:
            continue
        entry = {"id": c.id, "title": c.title, "teaser": c.teaser, "source_name": src.name, "lang": c.lang}
        rows.append((item_time(c), c.id, entry))
    for j in judgments.values():
        ni = j.new_item
        if ni is None or not j.relevant or j.id in have or j.id in cand_ids:
            continue
        src = info.get(ni.source)
        if src is None or not src.ai or len(ni.teaser.strip()) < cfg.min_teaser_chars:
            continue
        when = ensure_utc(ni.published or j.judged_at)
        if when < since:
            continue
        rows.append((when, j.id, {"id": j.id, "title": ni.title, "teaser": ni.teaser, "source_name": src.name, "lang": src.lang}))
    rows.sort(key=lambda r: r[1])
    rows.sort(key=lambda r: r[0], reverse=True)
    return [r[2] for r in rows[: max(0, limit)]], len(rows)


# ── validate-summaries ──────────────────────────────────────


def check_summary(
    s: Summary,
    cand_by_id: dict[str, Candidate],
    judgments: dict[str, Judgment],
    cfg: SummarySettings,
    file_day: str | None,
) -> list[str]:
    msgs: list[str] = []
    j = judgments.get(s.id)
    if j is None or not j.relevant:
        msgs.append(f"id '{s.id}' er ikke et godkendt indslag")
    cand = cand_by_id.get(s.id)
    source = cand.teaser if cand is not None else (j.new_item.teaser if j is not None and j.new_item else "")
    problem = copy_problem(s.summary_da, source, cfg) if s.summary_da is not None else None
    if problem:
        msgs.append(problem)
    if file_day is not None:
        day = to_cph(s.written_at).date().isoformat()
        if day != file_day:
            msgs.append(f"written_at er {day} i København; linjen hører til i data/judgments/resumeer/{day}.jsonl")
    return msgs


def main_validate_summaries(args: argparse.Namespace) -> int:
    # Sent: judgments importerer dette modul
    from affaldsfeed.config import load_config
    from affaldsfeed.judgments import format_errors, load_all_candidates, load_judgments, rel

    cfg = load_config(paths.CONFIG_DIR).settings.summaries
    cand_by_id = {c.id: c for c in load_all_candidates()}
    judgments = load_judgments()
    file_arg = getattr(args, "file", None)
    if file_arg:
        p = Path(file_arg)
        files = [p if p.is_absolute() else (paths.ROOT / p)]
        if not files[0].exists() and not p.is_absolute():
            files = [Path.cwd() / p]
    else:
        files = summary_files()
    errors: list[str] = []
    count = 0
    for path in files:
        name = rel(path)
        m = SUMMARY_FILE_RE.match(path.name)
        if not m:
            errors.append(f"{name}:0: filnavnet skal være ÅÅÅÅ-MM-DD.jsonl")
        if not path.is_file():
            errors.append(f"{name}:0: filen findes ikke")
            continue
        for n, line in _lines(path):
            count += 1
            try:
                s = Summary.model_validate_json(line)
            except ValidationError as e:
                errors.extend(f"{name}:{n}: {msg}" for msg in format_errors(e))
                continue
            errors.extend(f"{name}:{n}: {msg}" for msg in check_summary(s, cand_by_id, judgments, cfg, m.group(1) if m else None))
    for e in errors:
        print(e)
    if errors:
        print(f"validate-summaries: {len(errors)} fejl i {count} linjer ({len(files)} filer)")
        return 1
    print(f"validate-summaries: OK, {count} linjer i {len(files)} filer")
    return 0
