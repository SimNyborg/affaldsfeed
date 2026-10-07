"""Stedmærkning: regioner, kommuner og byer i danske titler og teasere (KONTRAKTER §4.1).

Konservativ: hellere et sted for lidt end et forkert. Kun navne fra config/geografi.yaml tæller,
store og små bogstaver tæller (egennavne), og der gemmes kun det, der nævnes (ingen forældre).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field

from .models import Geo, PlaceSettings, sort_places

# "<navn> Kommune" skrives både med stort og lille k
_KOMMUNE = ("Kommune", "kommune")
_REGION = ("Region", "region")
# Ordet før et navn, evt. efterfulgt af initialer: "Lars Aagaard", "Lars C. Aagaard"
_WORD_BEFORE = re.compile(r"(\w+)\s+(?:[A-ZÆØÅ]\.\s*)*$")


@dataclass(frozen=True)
class PlaceMatcher:
    """Kompileret mønster for alle stednavne. Lav den med compile_places()."""

    pattern: re.Pattern[str] | None = None
    ids: dict[str, frozenset[str]] = field(default_factory=dict)  # navn som i teksten -> sted-id'er
    institution: re.Pattern[str] | None = None


def _norm(name: str) -> str:
    return " ".join(unicodedata.normalize("NFC", name).split())


def _genitive(name: str) -> str | None:
    """Ejefald med s ("Nyborgs"), men ikke når navnet ender på s eller ikke ender på et bogstav."""
    last = name[-1:]
    return name + "s" if last.isalpha() and last not in "sS" else None


def _lower_last_word(name: str) -> str:
    """"Københavns Kommune" -> "Københavns kommune"."""
    head, sep, last = name.rpartition(" ")
    return f"{head}{sep}{last[:1].lower()}{last[1:]}" if last else name


def place_names(geo: Geo) -> dict[str, set[str]]:
    """Alle navne (også ejefald og "Kommune"-former) -> sted-id'er."""
    out: dict[str, set[str]] = {}

    def add(name: str, pid: str) -> None:
        name = _norm(name)
        if not name:
            return
        for form in (name, _genitive(name)):
            if form:
                out.setdefault(form, set()).add(pid)

    for r in geo.regioner:
        for word in _REGION:
            add(f"{word} {r.kort}", f"r:{r.id}")
        add(r.navn, f"r:{r.id}")
    for name, region in geo.landsdele.items():
        add(name, f"r:{region}")
    for m in geo.kommuner:
        pid = f"k:{m.id}"
        for name in m.navne:
            if not m.kun_med_kommune:
                add(name, pid)
            for word in _KOMMUNE:
                add(f"{name} {word}", pid)
        # Officielt navn: "Københavns Kommune", "Bornholms Regionskommune"
        add(m.navn, pid)
        add(_lower_last_word(m.navn), pid)
    for t in geo.byer:
        for name in t.navne:
            add(name, f"b:{t.id}")
    return out


def _any_case_first(word: str) -> str:
    first = word[:1]
    return f"[{re.escape(first.upper())}{re.escape(first.lower())}]{re.escape(word[1:])}"


def compile_places(geo: Geo, settings: PlaceSettings | None = None) -> PlaceMatcher:
    """Byg mønstret. Længste navn vinder, så "Ikast-Brande" fanges før "Ikast"."""
    settings = settings or PlaceSettings()
    names = place_names(geo)
    if not names:
        return PlaceMatcher()
    alternatives = sorted(names, key=lambda n: (-len(n), n))
    body = "|".join(r"\s+".join(re.escape(w) for w in n.split(" ")) for n in alternatives)
    # Ordgrænse: intet bogstav eller ciffer lige før eller efter (bindestreg er en grænse)
    pattern = re.compile(rf"(?<!\w)(?:{body})(?!\w)")
    # Institutionsord som præfiks lige efter navnet, også efter bindestreg ("Aarhus-konventionen")
    words = [w.strip() for w in settings.institution_words if w.strip()]
    institution = (
        re.compile(r"[\s-]+(?:" + "|".join(_any_case_first(w) for w in words) + r")") if words else None
    )
    return PlaceMatcher(pattern, {n: frozenset(v) for n, v in names.items()}, institution)


def _after_person_name(text: str, start: int) -> bool:
    """Står et ord med stort begyndelsesbogstav (evt. med initialer efter) lige før? Så er bynavnet nok et
    efternavn ("Lars Aagaard", "Lars C. Aagaard")."""
    m = _WORD_BEFORE.search(text, 0, start)
    if m is None:
        return False
    word = m.group(1)
    return len(word) >= 2 and word[0].isupper() and word[1:].islower()


def match_places(text: str, matcher: PlaceMatcher) -> list[str]:
    """Sted-id'er nævnt i teksten, sorteret (regioner, kommuner, byer) og højst 8."""
    if not text or matcher.pattern is None:
        return []
    text = unicodedata.normalize("NFC", text)
    found: set[str] = set()
    for m in matcher.pattern.finditer(text):
        ids = matcher.ids.get(" ".join(m.group(0).split()))
        if not ids:
            continue
        # "Aarhus Universitet", "Københavns Vestegn", "Holbæk-motorvejen": et navn på noget andet end stedet
        if matcher.institution is not None and matcher.institution.match(text, m.end()):
            continue
        # Rene bynavne efter et fornavn er efternavne, fx "Lars Aagaard" og "Lars C. Aagaard" (byen Ågård)
        if all(p.startswith("b:") for p in ids) and _after_person_name(text, m.start()):
            continue
        found |= ids
    return sort_places(found)


def rule_places(
    title: str,
    teaser: str,
    lang: str,
    fixed: Iterable[str],
    matcher: PlaceMatcher | None,
) -> list[str]:
    """Regelmærker: afsenderens faste steder og steder nævnt i titel og teaser (kun danske tekster)."""
    found = set(fixed)
    if matcher is not None and lang == "da":
        for text in (title, teaser):
            found.update(match_places(text, matcher))
    return sort_places(found)
