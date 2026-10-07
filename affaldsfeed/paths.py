"""Faste stier i repoet. Alt regnes ud fra repoets rod, så kommandoer virker uanset cwd."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
SITE_DIR = ROOT / "site"
EXAMPLES_DIR = ROOT / "examples"
SOURCES_FILE = ROOT / "sources.yaml"

CANDIDATES_DIR = DATA_DIR / "candidates"
REJECTED_DIR = DATA_DIR / "rejected"
JUDGMENTS_DIR = DATA_DIR / "judgments"
OVERVIEW_DIR = DATA_DIR / "overview"
OVERVIEW_ARCHIVE_DIR = OVERVIEW_DIR / "archive"
STATE_DIR = DATA_DIR / "state"

HEARTBEAT_FILE = JUDGMENTS_DIR / "_heartbeat.json"
