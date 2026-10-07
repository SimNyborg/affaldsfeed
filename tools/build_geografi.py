"""Byg config/geografi.yaml (regioner, kommuner og byer) fra Danmarks Statistiks åbne API.

Kilder:
- FOLK1A: områdelisten med regioner og de 98 kommuner. Listen er ordnet, så hver region
  efterfølges af sine kommuner.
- BY3: byområder med kommunekode og folketal 1. januar (nyeste år).

Håndregler (navne, alias, ord der ikke må matche) står i config/geografi_regler.yaml.
Den genererede fil rettes ikke i hånden. Workflowet "Byg geografi" kører værktøjet, da
cloud-miljøet ikke kan nå api.statbank.dk.

Brug: python tools/build_geografi.py [--out config/geografi.yaml] [--report]
Exit 0 ved succes, 1 hvis data ikke ser ud som forventet (intet skrives).
"""

import argparse
import contextlib
import csv
import io
import re
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from affaldsfeed.paths import CONFIG_DIR  # noqa: E402

API = "https://api.statbank.dk/v1"
RULES_FILE = CONFIG_DIR / "geografi_regler.yaml"
OUT_FILE = CONFIG_DIR / "geografi.yaml"

# Forventet antal kommuner pr. region (kommunalreformen 2007). Afviger data, stopper værktøjet.
EXPECTED_PER_REGION = {"081": 11, "082": 19, "083": 22, "084": 29, "085": 17}

# BY3-koder: 01100 = Hovedstadsområdet, 99997 = uden fast bopæl, 99999 = landdistrikter
SKIP_TOWN_CODES = {"01100", "99997", "99999"}
TOWN_RE = re.compile(r"^(\d{3})-(\d{5}) (.+?)(?: \((?:del af [^)]*)\))?$")

GetJson = Callable[[str], Any]
PostText = Callable[[str, dict], str]


class GeoError(Exception):
    pass


# ── Hjælpere ────────────────────────────────────────────────


def slug(text: str) -> str:
    """'Høje-Taastrup' → 'hoeje-taastrup'."""
    s = text.lower()
    for a, b in (("æ", "ae"), ("ø", "oe"), ("å", "aa"), ("é", "e"), ("ü", "u"), ("ö", "oe"), ("ä", "ae")):
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def _variable(info: dict, pred: Callable[[dict], bool], what: str) -> dict:
    for var in info.get("variables") or []:
        if pred(var):
            return var
    raise GeoError(f"{info.get('id')}: fandt ikke variablen {what}")


# ── Regioner og kommuner (FOLK1A) ───────────────────────────


def parse_areas(info: dict, rules: dict) -> tuple[list[dict], list[dict]]:
    """Regioner og kommuner fra FOLK1A's områdeliste."""
    var = _variable(info, lambda v: v.get("id", "").upper() in ("OMRÅDE", "OMRADE"), "OMRÅDE")
    region_rules = rules["regioner"]
    regions: list[dict] = []
    municipalities: list[dict] = []
    current: str | None = None
    for value in var.get("values") or []:
        code, text = str(value["id"]), str(value["text"]).strip()
        if code in region_rules:
            rule = region_rules[code]
            expected = f"Region {rule['kort']}"
            if text != expected:
                raise GeoError(f"region {code} hedder {text!r}, forventede {expected!r}")
            current = code
            regions.append({"id": rule["id"], "kode": code, "navn": text, "kort": rule["kort"]})
            continue
        if not re.fullmatch(r"\d{3}", code) or code == "000" or code in rules.get("ikke_kommuner", []):
            continue
        if current is None:
            raise GeoError(f"kommune {code} {text} står før første region")
        municipalities.append({"kode": code, "kort": text, "region_kode": current})

    counts: dict[str, int] = {}
    for m in municipalities:
        counts[m["region_kode"]] = counts.get(m["region_kode"], 0) + 1
    if counts != EXPECTED_PER_REGION:
        raise GeoError(f"uventet antal kommuner pr. region: {counts}")

    region_id = {r["kode"]: r["id"] for r in regions}
    official = {str(k): v for k, v in (rules.get("officielle_navne") or {}).items()}
    extra = {str(k): v for k, v in (rules.get("ekstra_navne") or {}).items()}
    only_with = set(rules.get("kun_med_kommune") or [])
    known = {m["kode"] for m in municipalities}
    unknown = sorted((set(official) | set(extra)) - known)
    if unknown:
        raise GeoError(f"regler nævner ukendte kommunekoder: {unknown}")
    missing = sorted(only_with - {m["kort"] for m in municipalities})
    if missing:
        raise GeoError(f"kun_med_kommune nævner ukendte kommuner: {missing}")
    out: list[dict] = []
    for m in municipalities:
        kort = m["kort"]
        names = [kort, *[n for n in extra.get(m["kode"], []) if n != kort]]
        out.append(
            {
                "id": slug(kort),
                "kode": m["kode"],
                "navn": official.get(m["kode"], f"{kort} Kommune"),
                "kort": kort,
                "region": region_id[m["region_kode"]],
                "navne": names,
                "kun_med_kommune": kort in only_with,
            }
        )
    ids = [m["id"] for m in out]
    if len(set(ids)) != len(ids):
        raise GeoError("to kommuner har samme id")
    return regions, out


# ── Byer (BY3) ──────────────────────────────────────────────


def by3_request(info: dict) -> tuple[dict, str]:
    """Byg dataforespørgslen: alle byområder, folketal, nyeste år."""
    towns = _variable(info, lambda v: v.get("id", "").upper() == "BYER", "BYER")
    time_var = _variable(info, lambda v: bool(v.get("time")), "tid")
    latest = str(time_var["values"][-1]["id"])
    variables = [{"code": towns["id"], "values": ["*"]}, {"code": time_var["id"], "values": [latest]}]
    for var in info.get("variables") or []:
        if var is towns or var is time_var:
            continue
        pick = [v for v in var.get("values") or [] if str(v.get("text", "")).lower().startswith("folketal")]
        if not pick:
            raise GeoError(f"BY3: variablen {var.get('id')} har ingen værdi for folketal")
        variables.append({"code": var["id"], "values": [str(pick[0]["id"])]})
    body = {
        "table": "BY3",
        "format": "CSV",
        "lang": "da",
        "valuePresentation": "Code",
        "delimiter": "Semicolon",
        "variables": variables,
    }
    return body, latest


def parse_population(text: str) -> dict[str, int]:
    """CSV med koder → {byområdekode: folketal}. Første kolonne er byområdet, sidste er tallet."""
    out: dict[str, int] = {}
    body = text.lstrip("﻿")
    first = body.split("\n", 1)[0]
    delimiter = max((";", "\t", ","), key=first.count)
    rows = list(csv.reader(io.StringIO(body), delimiter=delimiter))
    for row in rows[1:]:
        if len(row) < 2:
            continue
        raw = row[-1].strip().replace(".", "").replace(" ", "")
        if raw.isdigit():
            out[row[0].strip()] = int(raw)
    if not out:
        raise GeoError(f"BY3: ingen folketal i svaret: {body[:400]!r}")
    return out


def parse_towns(info: dict, population: dict[str, int], municipalities: list[dict], rules: dict) -> tuple[list[dict], list[str]]:
    """Byer med mindst min_indbyggere. Navne der findes flere steder, beholdes kun hvis én er klart størst."""
    towns_var = _variable(info, lambda v: v.get("id", "").upper() == "BYER", "BYER")
    by_code = {m["kode"]: m for m in municipalities}
    min_pop = int(rules.get("min_indbyggere", 1000))
    ignore = set(rules.get("ignorer_byer") or [])
    notes: list[str] = []

    # Saml dele af samme by (en by kan ligge i flere kommuner)
    towns: dict[str, dict] = {}
    for value in towns_var.get("values") or []:
        m = TOWN_RE.match(str(value["text"]).strip())
        if not m:
            continue
        kcode, tcode, name = m.groups()
        if tcode in SKIP_TOWN_CODES or kcode not in by_code:
            continue
        pop = population.get(str(value["id"]), 0)
        t = towns.setdefault(tcode, {"navn": name.strip(), "dele": {}})
        t["dele"][kcode] = t["dele"].get(kcode, 0) + pop

    kept: list[dict] = []
    for tcode, t in towns.items():
        total = sum(t["dele"].values())
        if total < min_pop:
            continue
        if t["navn"] in ignore:
            notes.append(f"ignoreret: {t['navn']}")
            continue
        main = max(t["dele"], key=lambda k: t["dele"][k])
        kept.append(
            {
                "kode": tcode,
                "navn": t["navn"],
                "kommune": by_code[main]["id"],
                "kommuner": sorted(by_code[k]["id"] for k in t["dele"] if t["dele"][k] > 0),
                "indbyggere": total,
            }
        )

    # Samme navn flere steder: behold den største, hvis den er mindst 5 gange større end nr. 2
    by_name: dict[str, list[dict]] = {}
    for t in kept:
        by_name.setdefault(t["navn"], []).append(t)
    out: list[dict] = []
    for name, group in by_name.items():
        group.sort(key=lambda t: -t["indbyggere"])
        if len(group) > 1:
            if group[0]["indbyggere"] >= 5 * group[1]["indbyggere"]:
                notes.append(f"flertydig, beholdt den største: {name} ({group[0]['kommune']})")
                group = group[:1]
            else:
                notes.append(f"flertydig, udeladt: {name} ({', '.join(t['kommune'] for t in group)})")
                continue
        out.extend(group)

    # Id: navnets slug; støder det på en anden by, tilføjes kommunen
    seen: set[str] = set()
    for t in sorted(out, key=lambda t: (-t["indbyggere"], t["kode"])):
        tid = slug(t["navn"])
        if tid in seen:
            tid = f"{tid}-{t['kommune']}"
        seen.add(tid)
        t["id"] = tid
    out.sort(key=lambda t: t["id"])
    return [
        {"id": t["id"], "navn": t["navn"], "kommune": t["kommune"], "kommuner": t["kommuner"], "indbyggere": t["indbyggere"]}
        for t in out
    ], notes


# ── Samlet ──────────────────────────────────────────────────


def build(get_json: GetJson, post_text: PostText, rules: dict, today: date) -> tuple[dict, list[str]]:
    folk1a = get_json(f"{API}/tableinfo/FOLK1A?lang=da&format=JSON")
    regions, municipalities = parse_areas(folk1a, rules)
    by3 = get_json(f"{API}/tableinfo/BY3?lang=da&format=JSON")
    body, year = by3_request(by3)
    population = parse_population(post_text(f"{API}/data", body))
    towns, notes = parse_towns(by3, population, municipalities, rules)

    region_ids = {r["id"] for r in regions}
    landsdele = rules.get("landsdele") or {}
    bad = sorted(v for v in landsdele.values() if v not in region_ids)
    if bad:
        raise GeoError(f"landsdele peger på ukendte regioner: {bad}")
    data = {
        "kilde": {
            "udgiver": "Danmarks Statistik (FOLK1A og BY3)",
            "folketal_aar": int(year) if str(year).isdigit() else str(year),
            "hentet": today.isoformat(),
            "min_indbyggere": int(rules.get("min_indbyggere", 1000)),
        },
        "regioner": [{k: r[k] for k in ("id", "kode", "navn", "kort")} for r in regions],
        "landsdele": dict(sorted(landsdele.items())),
        "kommuner": municipalities,
        "byer": towns,
    }
    return data, notes


HEADER = (
    "# Genereret af tools/build_geografi.py fra Danmarks Statistik. Ret ikke i hånden:\n"
    "# ret config/geografi_regler.yaml og kør workflowet \"Byg geografi\".\n"
)


def dump(data: dict) -> str:
    return HEADER + yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=120)


def _http(user_agent: str) -> tuple[GetJson, PostText]:
    session = requests.Session()
    session.headers["User-Agent"] = user_agent

    def get_json(url: str) -> Any:
        r = session.get(url, timeout=60)
        r.raise_for_status()
        return r.json()

    def post_text(url: str, body: dict) -> str:
        r = session.post(url, json=body, timeout=120)
        r.raise_for_status()
        r.encoding = r.encoding or "utf-8"
        return r.text

    return get_json, post_text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="build_geografi", description="Byg config/geografi.yaml fra Danmarks Statistik.")
    parser.add_argument("--out", type=Path, default=OUT_FILE)
    parser.add_argument("--report", action="store_true", help="udskriv optælling og noter")
    args = parser.parse_args(argv)
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(errors="replace")  # type: ignore[union-attr]

    rules = yaml.safe_load(RULES_FILE.read_text(encoding="utf-8"))
    settings = yaml.safe_load((CONFIG_DIR / "settings.yaml").read_text(encoding="utf-8"))
    get_json, post_text = _http(settings["fetch"]["user_agent"])
    try:
        data, notes = build(get_json, post_text, rules, date.today())
    except (GeoError, requests.RequestException, ValueError, KeyError) as exc:
        print(f"FEJL: {exc}", file=sys.stderr)
        return 1
    args.out.write_text(dump(data), encoding="utf-8")
    if args.report:
        print(f"{len(data['regioner'])} regioner, {len(data['kommuner'])} kommuner, {len(data['byer'])} byer")
        print(f"Folketal {data['kilde']['folketal_aar']}, mindst {data['kilde']['min_indbyggere']} indbyggere")
        for note in notes:
            print(f"  {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
