"""CLI: python -m affaldsfeed <kommando>. Importerer kun ejer-modulet for den valgte kommando (KONTRAKTER §1)."""

from __future__ import annotations

import argparse
import contextlib
import importlib
import importlib.util
import logging
import sys
from collections.abc import Callable

from affaldsfeed import __version__, paths

log = logging.getLogger("affaldsfeed")

PERIOD_CHOICES = ["dag", "uge", "maaned", "aar"]

# kommando -> (modul, funktion)
COMMANDS: dict[str, tuple[str, str]] = {
    "check": ("affaldsfeed.config", "main_check"),
    "run": ("affaldsfeed.pipeline", "main_run"),
    "export": ("affaldsfeed.export", "main_export"),
    "pending": ("affaldsfeed.judgments", "main_pending"),
    "validate-judgments": ("affaldsfeed.judgments", "main_validate"),
    "heartbeat": ("affaldsfeed.judgments", "main_heartbeat"),
    "overview-input": ("affaldsfeed.overview", "main_overview_input"),
    "validate-overview": ("affaldsfeed.overview", "main_validate_overview"),
    "timeline-input": ("affaldsfeed.timeline", "main_timeline_input"),
    "validate-timeline": ("affaldsfeed.timeline", "main_validate_timeline"),
}

# kommandoer, der videregives til et script i tools/ (main(argv) -> int)
TOOLS: dict[str, str] = {"import": "import_csv.py", "find-feed": "find_feed.py"}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m affaldsfeed", description="Affaldsfeed: indsamling og eksport.")
    p.add_argument("--version", action="version", version=f"affaldsfeed {__version__}")
    p.add_argument("-v", "--verbose", action="store_true", help="vis debug-log")
    sub = p.add_subparsers(dest="command", metavar="KOMMANDO")
    sub.required = True

    c = sub.add_parser("check", help="valider sources.yaml og config/")
    c.add_argument("--fetch", metavar="ID", help="hent én kilde live og vis forfiltrets afgørelser")
    c.add_argument("--explain", action="store_true", help="vis begrundelser for hvert indslag")

    r = sub.add_parser("run", help="indsamling: hent, filtrér og gem kandidater")
    r.add_argument("--only", metavar="ID[,ID]", help="kun disse kilder")
    r.add_argument("--dry-run", action="store_true", help="skriv intet til data/")
    r.add_argument("--now", metavar="ISO", help="overstyr nu (test)")

    e = sub.add_parser("export", help="byg _site/ med data/feed.json og data/status.json")
    e.add_argument("--out", default="_site", help="mappe (relativ til repoets rod), standard _site")
    e.add_argument("--now", metavar="ISO", help="overstyr nu (test)")

    pe = sub.add_parser("pending", help="JSON med uvurderede kandidater til Claude-routinen")
    pe.add_argument("--max", type=int, default=200, help="højst så mange indslag (standard 200)")
    pe.add_argument("--hours", type=float, default=None, help="kun fundet inden for så mange timer (standard settings.pending_hours, 336)")
    pe.add_argument("--now", metavar="ISO", help="overstyr nu (test)")

    vj = sub.add_parser("validate-judgments", help="valider data/judgments/*.jsonl")
    vj.add_argument("--file", metavar="PATH", help="kun denne fil")

    hb = sub.add_parser("heartbeat", help="skriv data/judgments/_heartbeat.json")
    hb.add_argument("--now", metavar="ISO", help="overstyr nu (test)")

    oi = sub.add_parser("overview-input", help="JSON-input til Claudes overblik")
    oi.add_argument("--period", required=True, choices=PERIOD_CHOICES)
    oi.add_argument("--now", metavar="ISO", help="overstyr nu (test)")

    vo = sub.add_parser("validate-overview", help="valider data/overview/<periode>.json")
    vo.add_argument("--period", choices=PERIOD_CHOICES, help="kun denne periode (ellers alle)")
    vo.add_argument("--archive", action="store_true", help="kopiér gyldige filer til data/overview/archive/")
    vo.add_argument("--now", metavar="ISO", help="overstyr nu (test)")

    ti = sub.add_parser("timeline-input", help="JSON-input til Claudes tidslinje")
    tg = ti.add_mutually_exclusive_group()
    tg.add_argument("--days", type=int, default=None, help="historier fra så mange dage (standard 3, tom tidslinje 60)")
    tg.add_argument("--fill", action="store_true", help="opfyldning: den næste måned, der er klar (KONTRAKTER §7.3)")
    tg.add_argument("--fill-done", metavar="ÅÅÅÅ-MM", help="markér en måned i opfyldningen som fyldt")
    ti.add_argument("--now", metavar="ISO", help="overstyr nu (test)")

    vt = sub.add_parser("validate-timeline", help="valider data/timeline/*.jsonl")
    vt.add_argument("--file", metavar="PATH", help="kun denne fil")
    vt.add_argument("--now", metavar="ISO", help="overstyr nu (test)")

    sub.add_parser("import", help="importér kildeliste fra CSV (tools/import_csv.py): import FILE.csv [--replace]")
    sub.add_parser("find-feed", help="find RSS/Atom/sitemap for en hjemmeside (tools/find_feed.py): find-feed URL")
    return p


def _setup_logging(verbose: bool) -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            with contextlib.suppress(ValueError, OSError):
                stream.reconfigure(encoding="utf-8")
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _load_tool(filename: str) -> Callable[[list[str]], int]:
    path = paths.ROOT / "tools" / filename
    if not path.is_file():
        raise FileNotFoundError(f"{path} findes ikke")
    spec = importlib.util.spec_from_file_location(f"affaldsfeed_tools_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"kan ikke indlæse {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    verbose = bool(argv) and argv[0] in ("-v", "--verbose")
    _setup_logging(verbose)

    # import og find-feed får resten af argumenterne uændret
    rest = argv[1:] if verbose else argv
    if rest and rest[0] in TOOLS:
        try:
            return int(_load_tool(TOOLS[rest[0]])(rest[1:]) or 0)
        except (FileNotFoundError, ImportError) as e:
            log.error("%s", e)
            return 1

    args = build_parser().parse_args(argv)
    module_name, func_name = COMMANDS[args.command]
    try:
        from affaldsfeed.config import ConfigError

        func = getattr(importlib.import_module(module_name), func_name)
    except (ImportError, AttributeError) as e:
        log.error("kommandoen %s er ikke tilgængelig: %s", args.command, e)
        return 1
    try:
        return int(func(args) or 0)
    except ConfigError as e:
        log.error("konfigurationsfejl: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
