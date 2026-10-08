"""Importér brugerens kildeliste (CSV) som kandidater i sources.yaml (fase 4).

Brug: python tools/import_csv.py liste.csv [--replace] [--dry-run] [--kategori ID]
      python -m affaldsfeed import liste.csv [--replace]

CSV-kolonner: navn, url (påkrævet), kategori, note (valgfri). Skilletegn: komma, semikolon eller tab.
- Nye værter tilføjes nederst i sources.yaml med status: kandidat under kommentaren
  "# ── Importeret <dato> ──". Resten af filen omformateres ikke.
- Værter, der allerede står i sources.yaml, røres ikke, men rapporteres.
- --replace: aktive kilder, hvis vært ikke står i CSV'en, får status: pause
  (kun status-linjen ændres; søgekilder med method: search røres ikke).
- --dry-run viser ændringerne som diff og skriver intet.
"""

import argparse
import contextlib
import csv
import difflib
import io
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, NamedTuple, get_args
from urllib.parse import urlsplit

import yaml
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from affaldsfeed.models import CategoryId, Source  # noqa: E402
from affaldsfeed.paths import CONFIG_DIR, SOURCES_FILE  # noqa: E402
from affaldsfeed.timeutil import now_utc, to_cph  # noqa: E402

TRANSLIT = {"æ": "ae", "ø": "oe", "å": "aa", "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
SLUG_MAX = 40

COLUMN_ALIASES = {
    "navn": "navn",
    "name": "navn",
    "kilde": "navn",
    "url": "url",
    "link": "url",
    "hjemmeside": "url",
    "homepage": "url",
    "kategori": "kategori",
    "category": "kategori",
    "note": "note",
    "noter": "note",
    "bemaerkning": "note",
}

CATEGORY_SYNONYMS = {
    "medie": "nyhedsmedie",
    "avis": "nyhedsmedie",
    "nyheder": "nyhedsmedie",
    "lokalavis": "lokalmedie",
    "lokalaviser": "lokalmedie",
    "ugeavis": "lokalmedie",
    "ugeaviser": "lokalmedie",
    "netavis": "lokalmedie",
    "regionalavis": "lokalmedie",
    "fagblad": "fagmedie",
    "myndigheder": "myndighed",
    "ministerium": "myndighed",
    "styrelse": "myndighed",
    "folketing": "myndighed",
    "folketinget": "myndighed",
    "kommune": "kommunal",
    "kommuner": "kommunal",
    "affaldsselskab": "kommunal",
    "forsyning": "kommunal",
    "branche": "organisation",
    "forening": "organisation",
    "interesseorganisation": "organisation",
    "ngo": "taenketank",
    "taenketanke": "taenketank",
    "universitet": "forskning",
    "eu": "eu_norden",
    "norden": "eu_norden",
}


class CsvError(Exception):
    """Fejl i CSV-filen, der stopper importen."""


class Row(NamedTuple):
    line: int
    name: str
    url: str
    category_raw: str
    note: str


class Plan(NamedTuple):
    new_entries: list[dict]
    comments: dict[str, str]  # id -> kommentar på category-linjen
    existing: list[tuple[Row, list[str]]]  # række -> eksisterende id'er (med status)
    duplicates: list[tuple[Row, Row]]
    errors: list[str]
    notes: list[str]
    paused: list[str]
    kept_search: list[str]


# ── Hjælpere ────────────────────────────────────────────────


def slugify(name: str) -> str:
    """ASCII-id fra navn: æ→ae, ø→oe, å→aa, øvrige accenter fjernes, alt andet bliver bindestreg."""
    s = name.strip().lower()
    s = "".join(TRANSLIT.get(ch, ch) for ch in s)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if len(s) > SLUG_MAX:
        s = s[:SLUG_MAX].rsplit("-", 1)[0] if "-" in s[:SLUG_MAX] else s[:SLUG_MAX]
        s = s.strip("-")
    return s or "kilde"


def unique_id(base: str, taken: set[str]) -> str:
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


def with_scheme(url: str) -> str:
    url = url.strip()
    if url and "://" not in url:
        url = "https://" + url
    return url


def host_of(url: str) -> str:
    """Værtsnavn med små bogstaver, uden www. og port."""
    try:
        host = urlsplit(with_scheme(url)).hostname or ""
    except ValueError:
        return ""
    host = host.lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def category_table(config_dir: Path = CONFIG_DIR) -> dict[str, str]:
    """Slug af id, navn, kort navn og synonymer → CategoryId."""
    table = {slugify(cid): cid for cid in get_args(CategoryId)}
    path = config_dir / "categories.yaml"
    if path.exists():
        for row in yaml.safe_load(path.read_text(encoding="utf-8")) or []:
            for key in ("id", "name", "short"):
                if row.get(key):
                    table[slugify(str(row[key]))] = row["id"]
    for key, cid in CATEGORY_SYNONYMS.items():
        table.setdefault(key, cid)
    return table


def resolve_category(raw: str, table: dict[str, str]) -> str | None:
    if not raw.strip():
        return None
    s = slugify(raw)
    if s in table:
        return table[s]
    for part in s.split("-"):
        if part in table:
            return table[part]
    return None


# ── CSV ─────────────────────────────────────────────────────


def read_csv(path: Path) -> tuple[list[Row], list[str]]:
    """Læs rækker. Returnerer (rækker, advarsler). Kaster CsvError ved manglende kolonner."""
    warnings: list[str] = []
    data = path.read_bytes()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1252")
        warnings.append("filen er ikke UTF-8; læst som Windows-1252")
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    if not first:
        raise CsvError("filen er tom")
    delimiter = max([";", ",", "\t"], key=first.count)
    if first.count(delimiter) == 0:
        delimiter = ","
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    header = next(reader)
    columns: dict[str, int] = {}
    for i, col in enumerate(header):
        key = COLUMN_ALIASES.get(slugify(col).replace("-", ""))
        if key and key not in columns:
            columns[key] = i
    missing = [c for c in ("navn", "url") if c not in columns]
    if missing:
        raise CsvError(f"mangler kolonne: {', '.join(missing)} (fandt: {', '.join(header)})")

    def cell(values: list[str], key: str) -> str:
        i = columns.get(key)
        return values[i].strip() if i is not None and i < len(values) else ""

    rows = []
    for values in reader:
        if not any(v.strip() for v in values):
            continue
        rows.append(
            Row(
                reader.line_num,
                cell(values, "navn"),
                cell(values, "url"),
                cell(values, "kategori"),
                " ".join(cell(values, "note").split()),
            )
        )
    return rows, warnings


# ── Eksisterende register ───────────────────────────────────


def load_registry(text: str) -> list[dict]:
    data = yaml.safe_load(text) if text.strip() else []
    if data is None:
        data = []
    if not isinstance(data, list) or not all(isinstance(e, dict) for e in data):
        raise CsvError("sources.yaml skal være en liste af kilder")
    return data


def entry_hosts(entry: dict) -> set[str]:
    hosts = {host_of(str(entry.get("homepage") or ""))}
    for d in entry.get("domains") or []:
        hosts.add(host_of(str(d)))
    hosts.discard("")
    return hosts


def load_publishers(config_dir: Path = CONFIG_DIR) -> list[dict]:
    path = config_dir / "medier.yaml"
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return [p for p in data if isinstance(p, dict)]


# ── Plan ────────────────────────────────────────────────────


def plan_import(
    rows: list[Row],
    registry: list[dict],
    categories: dict[str, str],
    default_category: str,
    replace: bool,
    publishers: list[dict] | None = None,
) -> Plan:
    publishers = publishers or []
    by_host: dict[str, list[dict]] = {}
    for entry in registry:
        for h in entry_hosts(entry):
            by_host.setdefault(h, []).append(entry)
    pub_by_host = {host_of(str(d)): str(p.get("id")) for p in publishers for d in (p.get("domains") or [])}
    taken = {str(e.get("id")) for e in registry} | {str(p.get("id")) for p in publishers}

    plan = Plan([], {}, [], [], [], [], [], [])
    csv_hosts: set[str] = set()
    seen_rows: dict[str, Row] = {}
    for row in rows:
        if not row.name or not row.url:
            plan.errors.append(f"række {row.line}: {'navn' if not row.name else 'url'} mangler")
            continue
        homepage = with_scheme(row.url)
        host = host_of(homepage)
        if not host or "." not in host:
            plan.errors.append(f"række {row.line}: ugyldig url {row.url!r}")
            continue
        csv_hosts.add(host)
        if host in seen_rows:
            plan.duplicates.append((row, seen_rows[host]))
            continue
        seen_rows[host] = row
        if host in by_host:
            ids = [f"{e.get('id')} ({e.get('status', 'aktiv')})" for e in by_host[host]]
            plan.existing.append((row, ids))
            continue

        cid = resolve_category(row.category_raw, categories)
        comment = None
        if cid is None:
            if row.category_raw:
                safe = " ".join(row.category_raw.split()).replace("#", "")
                comment = f"ukendt kategori i CSV: {safe}"
            else:
                comment = "kategori mangler i CSV"
            cid = default_category
        new_id = unique_id(slugify(row.name), taken)
        entry: dict[str, Any] = {
            "id": new_id,
            "name": row.name,
            "category": cid,
            "homepage": homepage,
            "feeds": [],
            "status": "kandidat",
        }
        if row.note:
            entry["note"] = row.note
        try:
            Source.model_validate(entry)
        except ValidationError as exc:
            plan.errors.append(f"række {row.line}: {exc.errors()[0].get('msg', exc)}")
            continue
        taken.add(new_id)
        plan.new_entries.append(entry)
        if comment:
            plan.comments[new_id] = comment
        if host in pub_by_host:
            plan.notes.append(f"{new_id}: værten står også i medier.yaml som {pub_by_host[host]}")

    if replace:
        for entry in registry:
            if entry.get("status", "aktiv") != "aktiv":
                continue
            if entry.get("method", "rss") == "search":
                plan.kept_search.append(str(entry.get("id")))
                continue
            if not entry_hosts(entry) & csv_hosts:
                plan.paused.append(str(entry.get("id")))
    return plan


# ── Tekstuelle ændringer i sources.yaml ─────────────────────

_ITEM_RE = re.compile(r"^(?P<ind> *)-(?:(?P<sp> +)(?P<rest>.*))?$")
_KEY_RE = re.compile(r"^(?P<key>[A-Za-z_][\w-]*)\s*:(?:\s+(?P<val>.*))?$")
_STATUS_RE = re.compile(r"(?<![\w-])status\s*:\s*(?P<q>['\"]?)(?P<v>[A-Za-z]+)(?P=q)")


def _is_content(line: str) -> bool:
    s = line.strip()
    return bool(s) and not s.startswith("#")


def _scalar(val: str | None) -> str:
    if not val:
        return ""
    val = re.split(r"\s+#", val, maxsplit=1)[0].strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in "'\"":
        val = val[1:-1]
    return val


def _blocks(lines: list[str]) -> list[dict]:
    """Find listepunkterne på øverste niveau: id, linje for id og status, nøgle-indrykning."""
    root = None
    for line in lines:
        m = _ITEM_RE.match(line.rstrip("\r\n"))
        if m and _is_content(line):
            root = len(m["ind"])
            break
    if root is None:
        return []
    starts = []
    for i, line in enumerate(lines):
        m = _ITEM_RE.match(line.rstrip("\r\n"))
        if m and len(m["ind"]) == root:
            starts.append(i)
    blocks = []
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        m = _ITEM_RE.match(lines[start].rstrip("\r\n"))
        assert m is not None
        block: dict[str, Any] = {"start": start, "end": end, "id": None, "id_line": None, "status_line": None}
        if m["rest"] is not None and m["rest"].strip():
            key_ind = root + 1 + len(m["sp"])
            keyed = [(start, m["rest"])]
        else:
            nxt = next((i for i in range(start + 1, end) if _is_content(lines[i])), None)
            if nxt is None:
                continue
            key_ind = len(lines[nxt]) - len(lines[nxt].lstrip(" "))
            keyed = []
        for i in range(start + 1, end):
            raw = lines[i].rstrip("\r\n")
            if _is_content(raw) and len(raw) - len(raw.lstrip(" ")) == key_ind:
                keyed.append((i, raw[key_ind:]))
        block["key_ind"] = key_ind
        for i, text in keyed:
            km = _KEY_RE.match(text)
            if not km:
                continue
            if km["key"] == "id" and block["id"] is None:
                block["id"], block["id_line"] = _scalar(km["val"]), i
            elif km["key"] == "status" and block["status_line"] is None:
                block["status_line"] = i
        blocks.append(block)
    return blocks


def set_status(text: str, ids: list[str], status: str = "pause") -> tuple[str, list[str]]:
    """Sæt status for de givne id'er ved kun at ændre (eller indsætte) status-linjen.

    Returnerer (ny tekst, id'er der ikke kunne findes).
    """
    if not ids:
        return text, []
    lines = text.splitlines(keepends=True)
    nl = "\r\n" if "\r\n" in text else "\n"
    wanted = set(ids)
    inserts: list[tuple[int, str]] = []
    found: set[str] = set()
    for block in _blocks(lines):
        if block["id"] not in wanted:
            continue
        found.add(block["id"])
        if block["status_line"] is not None:
            i = block["status_line"]
            m = _STATUS_RE.search(lines[i])
            if m:
                lines[i] = lines[i][: m.start("v")] + status + lines[i][m.end("v") :]
                continue
        inserts.append((block["id_line"], " " * block["key_ind"] + f"status: {status}{nl}"))
    for i, new_line in sorted(inserts, reverse=True):
        if not lines[i].endswith(("\n", "\r")):
            lines[i] += nl
        lines.insert(i + 1, new_line)
    return "".join(lines), sorted(wanted - found)


def render_entries(entries: list[dict], comments: dict[str, str], indent: int, nl: str) -> str:
    out: list[str] = []
    for entry in entries:
        dumped = yaml.safe_dump(
            [entry], allow_unicode=True, sort_keys=False, default_flow_style=False, width=1000
        )
        lines = dumped.splitlines()
        if entry["id"] in comments:
            lines = [
                f"{ln}  # {comments[entry['id']]}" if ln.startswith("  category:") else ln for ln in lines
            ]
        if out:
            out.append("")
        out.extend(" " * indent + ln for ln in lines)
    return nl.join(out) + nl


def apply_plan(text: str, plan: Plan, date_str: str) -> tuple[str, list[str]]:
    """Ny tekst for sources.yaml. Returnerer (tekst, id'er der ikke kunne sættes på pause)."""
    nl = "\r\n" if "\r\n" in text else "\n"
    new_text, missing = set_status(text, plan.paused)
    if plan.new_entries:
        indent = 0
        for line in new_text.splitlines():
            m = _ITEM_RE.match(line)
            if m and _is_content(line):
                indent = len(m["ind"])
                break
        if new_text and not new_text.endswith("\n"):
            new_text += nl
        prefix = nl if new_text.strip() else ""
        new_text += f"{prefix}# ── Importeret {date_str} ──{nl}"
        new_text += render_entries(plan.new_entries, plan.comments, indent, nl)
    return new_text, missing


def verify(old_registry: list[dict], new_text: str, plan: Plan) -> None:
    """Tjek at den nye tekst kun indeholder de planlagte ændringer."""
    new_registry = load_registry(new_text)
    expected = []
    for entry in old_registry:
        e = dict(entry)
        if str(e.get("id")) in plan.paused:
            e["status"] = "pause"
        expected.append(e)
    expected.extend(plan.new_entries)
    if new_registry != expected:
        raise CsvError("ændringen af sources.yaml gav ikke det forventede resultat; intet skrevet")


def write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(tmp, path)


# ── Rapport og main ─────────────────────────────────────────


def print_plan(plan: Plan, csv_path: Path, n_rows: int) -> None:
    print(f"Import fra {csv_path.name}: {n_rows} rækker")
    print(f"  Nye kandidater: {len(plan.new_entries)}")
    for e in plan.new_entries:
        extra = f"  ({plan.comments[e['id']]})" if e["id"] in plan.comments else ""
        print(f"    + {e['id']}  {e['name']} [{e['category']}]  {e['homepage']}{extra}")
    if plan.existing:
        print(f"  Findes allerede, røres ikke: {len(plan.existing)}")
        for row, ids in plan.existing:
            print(f"    = {row.name} ({host_of(row.url)}) → {', '.join(ids)}")
    if plan.duplicates:
        print(f"  Dubletter i CSV, springes over: {len(plan.duplicates)}")
        for row, first in plan.duplicates:
            print(f"    række {row.line}: {row.name} har samme vært som række {first.line}")
    if plan.errors:
        print(f"  Fejl, springes over: {len(plan.errors)}")
        for msg in plan.errors:
            print(f"    {msg}")
    for msg in plan.notes:
        print(f"  Bemærk: {msg}")
    if plan.paused:
        print(f"  Sættes på pause (--replace): {len(plan.paused)}")
        for sid in plan.paused:
            print(f"    - {sid}")
    if plan.kept_search:
        print(f"  Søgekilder bevares: {', '.join(plan.kept_search)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="import", description="Importér en kildeliste (CSV) som kandidater."
    )
    parser.add_argument("file", type=Path, help="CSV med kolonnerne navn, url, kategori, note")
    parser.add_argument(
        "--replace", action="store_true", help="sæt aktive kilder, der ikke er på listen, på pause"
    )
    parser.add_argument("--dry-run", action="store_true", help="vis ændringer uden at skrive")
    parser.add_argument("--sources", type=Path, default=SOURCES_FILE, help="sti til sources.yaml")
    parser.add_argument(
        "--kategori",
        default="nyhedsmedie",
        choices=get_args(CategoryId),
        help="kategori når CSV'en ikke angiver en gyldig (markeres med kommentar)",
    )
    parser.add_argument("--now", default=None, help="ISO-tid til test (dato i kommentaren)")
    args = parser.parse_args(argv)
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(errors="replace")  # type: ignore[union-attr]

    try:
        rows, warnings = read_csv(args.file)
        text = ""
        if args.sources.exists():
            with open(args.sources, encoding="utf-8", newline="") as f:
                text = f.read()
        registry = load_registry(text)
        plan = plan_import(rows, registry, category_table(), args.kategori, args.replace, load_publishers())
        if args.replace and not any(r.name and r.url for r in rows):
            raise CsvError("--replace kræver mindst én gyldig række i CSV'en")
        date_str = to_cph(now_utc(args.now)).date().isoformat()
        new_text, missing = apply_plan(text, plan, date_str)
        if missing:
            raise CsvError(f"kunne ikke finde status for: {', '.join(missing)}")
        verify(registry, new_text, plan)
    except (OSError, CsvError, yaml.YAMLError, csv.Error, ValueError) as exc:
        print(f"FEJL: {exc}", file=sys.stderr)
        return 1

    for w in warnings:
        print(f"Advarsel: {w}")
    print_plan(plan, args.file, len(rows))
    if new_text == text:
        print("Ingen ændringer i sources.yaml.")
        return 0
    if args.dry_run:
        print()
        diff = difflib.unified_diff(
            text.splitlines(),
            new_text.splitlines(),
            fromfile=args.sources.name,
            tofile=f"{args.sources.name} (efter import)",
            lineterm="",
        )
        for line in diff:
            print(line)
        print()
        print("Tørkørsel: intet skrevet.")
        return 0
    write_atomic(args.sources, new_text)
    print(f"{args.sources.name} opdateret.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
