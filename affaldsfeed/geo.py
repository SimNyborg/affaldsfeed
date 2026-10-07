"""Stedgenkendelse (KONTRAKTER §8.1): regioner, kommuner og byer i titel og teaser."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import Any

from .models import GeoBy, GeoKommune, Geography, GeoRegion, Places

# (niveau, id); niveau er "region", "kommune" eller "by". None = ignore-mønster.
Ref = tuple[str, str]

# Genitiv: "Odenses", "Aarhus'", "Aarhus’"
_GENITIVE = r"(?:s|['’]s?)?"


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", (s or "").strip())


def pattern_regex(pattern: str) -> str:
    """Oversæt et stedmønster til regex.

    Hele ord og store/små bogstaver som skrevet; et lille første bogstav må også stå med
    stort (sætningsstart). Mellemrum = vilkårligt whitespace. * til sidst = \\w*, ellers
    må genitiv følge.
    """
    p = _nfc(pattern)
    wild = p.endswith("*")
    core = p.rstrip("*").strip()
    if not core:
        raise ValueError("tomt mønster")
    if "*" in core:
        raise ValueError("* må kun stå til sidst")
    first, rest = core[0], core[1:]
    head = f"[{re.escape(first)}{re.escape(first.upper())}]" if first.islower() else re.escape(first)
    body = r"\s+".join(re.escape(w) for w in re.split(r"\s+", rest))
    tail = r"\w*" if wild else _GENITIVE
    return rf"(?<!\w){head}{body}{tail}(?!\w)"


def pattern_key(pattern: str) -> str:
    """Nøgle til at finde dubletter: samme mønster uanset store/små bogstaver."""
    return _nfc(pattern).lower()


def place_patterns(place: GeoRegion | GeoKommune | GeoBy) -> list[str]:
    """Stedets mønstre; uden patterns bruges short (region, kommune) eller name (by)."""
    if place.patterns:
        return list(place.patterns)
    return [place.name if isinstance(place, GeoBy) else place.short]


def merge_places(items: Iterable[Places]) -> Places:
    """Foreningen af flere indslags steder (fx alle i en historie)."""
    r: set[str] = set()
    k: set[str] = set()
    b: set[str] = set()
    for p in items:
        r.update(p.regioner)
        k.update(p.kommuner)
        b.update(p.byer)
    return Places(regioner=sorted(r), kommuner=sorted(k), byer=sorted(b))


def feed_geo(geo: Geography) -> dict[str, Any]:
    """Opslaget i feed.json (§8): navne og forældre for alle steder i config-rækkefølge."""
    return {
        "regioner": [{"id": r.id, "name": r.name, "short": r.short} for r in geo.regioner],
        "kommuner": [{"id": k.id, "name": k.name, "short": k.short, "region": k.region} for k in geo.kommuner],
        "byer": [{"id": b.id, "name": b.name, "kommune": b.kommune} for b in geo.byer],
    }


class Gazetteer:
    """Finder steder i tekst. Ét samlet regex; ved overlap vinder det længste mønster."""

    def __init__(self, geo: Geography):
        self.regioner = {r.id: r for r in geo.regioner}
        self.kommuner = {k.id: k for k in geo.kommuner}
        self.byer = {b.id: b for b in geo.byer}
        entries: list[tuple[str, Ref | None]] = []
        for level, places in (("region", geo.regioner), ("kommune", geo.kommuner), ("by", geo.byer)):
            for place in places:
                entries.extend((p, (level, place.id)) for p in place_patterns(place))
        entries.extend((p, None) for p in geo.ignore)
        entries = [(p, ref) for p, ref in entries if _nfc(p).rstrip("*").strip()]
        # Længste først: regex-alternativer prøves i rækkefølge ved samme startposition
        entries.sort(key=lambda e: (-len(_nfc(e[0]).rstrip("*")), _nfc(e[0])))
        self._refs = [ref for _, ref in entries]
        alts = [f"(?P<p{i}>{pattern_regex(p)})" for i, (p, _) in enumerate(entries)]
        self._rx = re.compile("|".join(alts)) if alts else None

    def find(self, text: str | None) -> set[Ref]:
        """Steder nævnt i teksten (uden forældre)."""
        if not text or self._rx is None:
            return set()
        out: set[Ref] = set()
        for m in self._rx.finditer(unicodedata.normalize("NFC", text)):
            ref = self._refs[int((m.lastgroup or "p0")[1:])]
            if ref is not None:
                out.add(ref)
        return out

    def expand(self, refs: Iterable[Ref]) -> Places:
        """Tilføj forældre: en by giver sin kommune, en kommune sin region. Ukendte id'er droppes."""
        refs = set(refs)
        byer = {i for lvl, i in refs if lvl == "by" and i in self.byer}
        kommuner = {i for lvl, i in refs if lvl == "kommune" and i in self.kommuner}
        kommuner |= {self.byer[b].kommune for b in byer if self.byer[b].kommune in self.kommuner}
        regioner = {i for lvl, i in refs if lvl == "region" and i in self.regioner}
        regioner |= {self.kommuner[k].region for k in kommuner if self.kommuner[k].region in self.regioner}
        return Places(regioner=sorted(regioner), kommuner=sorted(kommuner), byer=sorted(byer))

    def places(self, *texts: str | None, fixed: Iterable[str] = ()) -> Places:
        """Steder i teksterne plus faste steder (kildens geo: kommune- eller region-id'er)."""
        refs: set[Ref] = set()
        for t in texts:
            refs |= self.find(t)
        for pid in fixed:
            if pid in self.kommuner:
                refs.add(("kommune", pid))
            elif pid in self.regioner:
                refs.add(("region", pid))
        return self.expand(refs)
