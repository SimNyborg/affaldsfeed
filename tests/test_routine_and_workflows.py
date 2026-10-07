"""Routinens instruks (routine/REDAKTOER.md) og workflowet "Byg geografi" følger reglerne fra reviewet."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REDAKTOER = (ROOT / "routine" / "REDAKTOER.md").read_text(encoding="utf-8")


def test_routine_rules_for_places():
    text = " ".join(REDAKTOER.split())
    # En fejl i places må ikke koste hele vurderingen
    assert 'Er fejlen i `places`, så skriv `"places": null` i stedet for at slette linjen.' in text
    assert "Ved `relevant: false` er `places` altid `null`." in text
    # Gamle linjer (fx gjort ugyldige af en ny geografi) rettes ikke
    assert "Ret kun fejl i linjer, du selv har skrevet i denne kørsel" in text
    # Entydig regel for null mod []
    assert "`null` betyder, at `rule_places` er rigtige, også når listen er tom." in text
    assert "`[]` betyder, at nyheden er national, selvom reglerne fandt steder." in text
    assert "en by behøver ikke også sin kommune" not in text
    # Samme overskriftsstil som resten af filen (ingen fed overskrift)
    assert "**Steder.**" not in REDAKTOER


def test_routine_town_lookup_finds_aliases():
    m = re.search(r'`grep -n -i -B8 "([^"]+)" config/geografi\.yaml`', REDAKTOER)
    assert m, "opslagsopskriften mangler"
    assert 'grep -B1 "^  navn:' not in REDAKTOER  # fandt kun det officielle navn
    name = m.group(1)
    # Opskriften virker på den rigtige fil: aliasset findes, og id'et står i nærmeste "- id:" over træffet
    lines = (ROOT / "config" / "geografi.yaml").read_text(encoding="utf-8").splitlines()
    hit = next(i for i, ln in enumerate(lines) if name.lower() in ln.lower())
    assert "navn:" not in lines[hit]  # et alias under navne:, ikke det officielle navn
    found = next(ln for ln in reversed(lines[max(0, hit - 8) : hit]) if ln.startswith("- id: "))
    assert f"`b:{found.removeprefix('- id: ')}`" in REDAKTOER


def test_geography_workflow_commits_only_after_check():
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "geografi.yml").read_text(encoding="utf-8"))
    steps = wf["jobs"]["build"]["steps"]
    runs = [s.get("run", "") for s in steps]
    build = next(i for i, r in enumerate(runs) if "tools/build_geografi.py" in r)
    check = next(i for i, r in enumerate(runs) if "python -m affaldsfeed check" in r)
    assert check >= build and runs[check].index("affaldsfeed check") > runs[build].index("build_geografi.py")
    commit = next(i for i, r in enumerate(runs) if "git commit" in r)
    assert commit > check
    script = runs[commit]
    # Rapporten committes altid; geografi.yaml kun, når check er OK
    assert script.index("git add probe/geografi.md") < script.index('if [ "$CHECK_OK" = "true" ]')
    assert "git add config/geografi.yaml" in script.split('if [ "$CHECK_OK" = "true" ]', 1)[1].split("else")[0]
    assert steps[commit]["env"]["CHECK_OK"] == "${{ steps.build.outputs.check_ok }}"
    fail = steps[-1]
    assert fail["if"] == "steps.build.outputs.check_ok != 'true'" and "exit 1" in fail["run"]


def test_routine_timeline_step():
    text = " ".join(REDAKTOER.split())
    assert "Du skriver kun i `data/judgments/`, `data/overview/` og `data/timeline/`." in text
    assert "### 7. Tidslinje (kun når `TIME` er 22, eller når tidslinjen er tom)" in REDAKTOER
    assert ".venv/bin/python -m affaldsfeed timeline-input > /tmp/timeline.json" in REDAKTOER
    assert ".venv/bin/python -m affaldsfeed validate-timeline --file data/timeline/MÅNED.jsonl" in REDAKTOER
    # git add må ikke fejle, før tidslinjen findes
    assert "if [ -d data/timeline ]; then git add data/timeline; fi" in REDAKTOER
    assert "Tilføj aldrig andre stier end `data/judgments`, `data/overview` og `data/timeline`." in text
    # Eksemplet i instruksen er en gyldig linje
    from affaldsfeed.models import TimelineEvent

    line = next(ln.strip() for ln in REDAKTOER.splitlines() if ln.strip().startswith('{"id":"2026-10-07-faelles'))
    TimelineEvent.model_validate_json(line)


def test_publish_runs_on_timeline():
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8"))
    on = wf.get("on", wf.get(True))
    assert "data/timeline/**" in on["push"]["paths"]
    claude_md = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Claude-routinen skriver kun i `data/judgments/`, `data/overview/` og `data/timeline/`." in claude_md
