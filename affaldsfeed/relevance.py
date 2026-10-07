"""Mønstermotor (KONTRAKTER §4) og det løse forfilter (§5.4)."""

from __future__ import annotations

import re
import unicodedata

from .models import Keywords, Source, Why

_FLAGS = re.IGNORECASE | re.UNICODE

TITLE_POINTS = 4
TEASER_POINTS = 2
TEASER_MAX = 6
WEAK_MAX = 2


def _pattern_regex(pattern: str, proper_noun: bool = False) -> str:
    """Oversæt et mønster til regex: uden * = helt ord, * = \\w*, mellemrum = frase.

    proper_noun: første bogstav skal stå med stort (egennavne), resten må have alle store/små bogstaver,
    så "Argo" og "ARGO" matcher, men det almindelige ord "kredsløb" ikke matcher selskabet "Kredsløb".
    """
    lead = pattern.startswith("*")
    trail = pattern.endswith("*")
    core = pattern.strip("*")
    segments = [r"\s+".join(re.escape(w) for w in seg.split()) for seg in core.split("*")]
    body = r"\w*".join(segments)
    if proper_noun and not lead and body[:1].isalpha():
        body = f"(?-i:{body[0]})" + body[1:]
    start = r"\w*" if lead else r"(?<!\w)"
    end = r"\w*" if trail else ""
    if not (lead and trail):
        end += r"(?!\w)"
    return start + body + end


def compile_patterns(patterns: list[str], proper_nouns: bool = False) -> list[tuple[str, re.Pattern]]:
    """Kompilér mønstre til (originalt mønster, regex). Tomme mønstre springes over.

    proper_nouns: mønstrene er egennavne og kræver stort begyndelsesbogstav (se _pattern_regex).
    """
    out: list[tuple[str, re.Pattern]] = []
    for p in patterns:
        p = unicodedata.normalize("NFC", (p or "").strip())
        if not p.strip("*").strip():
            continue
        out.append((p, re.compile(_pattern_regex(p, proper_nouns), _FLAGS)))
    return out


def find_hits(text: str, compiled: list[tuple[str, re.Pattern]]) -> list[str]:
    """De mønstre (originale strenge), der matcher teksten, i mønstrenes rækkefølge og uden dubletter."""
    if not text:
        return []
    t = unicodedata.normalize("NFC", text)
    hits: list[str] = []
    for orig, rx in compiled:
        if orig not in hits and rx.search(t):
            hits.append(orig)
    return hits


def _mask(text: str, compiled: list[tuple[str, re.Pattern]]) -> str:
    """Erstat alle match med mellemrum, så svage ord inde i stærke ord ikke tælles dobbelt."""
    t = unicodedata.normalize("NFC", text or "")
    for _, rx in compiled:
        t = rx.sub(" ", t)
    return t


def _merged(*lists: list[str]) -> list[str]:
    out: list[str] = []
    for lst in lists:
        out.extend(x for x in lst if x not in out)
    return out


class Prefilter:
    """Løst forfilter: sorterer det åbenlyst irrelevante fra. Claude vurderer resten."""

    def __init__(self, keywords: Keywords):
        # Alle sprog bruges for alle kilder (engelske ord optræder også i danske titler)
        self.strong = compile_patterns(_merged(*keywords.strong.values()))
        self.names = compile_patterns(keywords.names, proper_nouns=True)  # egennavne: stort begyndelsesbogstav
        self.weak = compile_patterns(_merged(*keywords.weak.values()))
        self.veto = compile_patterns(keywords.veto)
        self.service = compile_patterns(keywords.service)

    def score(self, title: str, teaser: str) -> tuple[int, list[str], bool]:
        """Point, hits og om der er et stærkt ord/navn i titlen."""
        title = title or ""
        teaser = teaser or ""
        t_strong = find_hits(title, self.strong)
        t_names = [n for n in find_hits(title, self.names) if n not in t_strong]
        s_strong = find_hits(teaser, self.strong)
        weak = _merged(
            find_hits(_mask(title, self.strong), self.weak),
            find_hits(_mask(teaser, self.strong), self.weak),
        )

        score = TITLE_POINTS * (len(t_strong) + len(t_names))
        score += min(TEASER_MAX, TEASER_POINTS * len(s_strong))
        others = len(t_strong) + len(t_names) + len(s_strong)
        weak_in_title = bool(find_hits(_mask(title, self.strong), self.weak))
        # Svage ord tæller kun sammen med et andet hit (stærkt ord, navn eller et andet svagt ord)
        # eller når det svage ord står i titlen (så "normal"-kilder giver gråzone, fx "handlingsplan for tekstiler")
        if weak and (others > 0 or len(weak) >= 2 or weak_in_title):
            score += min(WEAK_MAX, len(weak))

        hits = (
            [f"titel: {h}" for h in t_strong]
            + [f"navn: {h}" for h in t_names]
            + [f"teaser: {h}" for h in s_strong]
            + [f"svag: {h}" for h in weak]
        )
        return score, hits, bool(t_strong or t_names)

    def evaluate(self, title: str, teaser: str, source: Source) -> Why:
        level = source.filter
        score, hits, title_hit = self.score(title, teaser)

        veto = find_hits(title or "", self.veto)
        if veto:
            return Why(
                filter=level,
                score=score,
                decision="afvist",
                hits=[f"veto: {v}" for v in veto] + hits,
                reason=f"veto: {veto[0]}",
            )
        if source.category == "kommunal":
            service = find_hits(title or "", self.service)
            if service:
                return Why(
                    filter=level,
                    score=score,
                    decision="afvist",
                    hits=[f"service: {s}" for s in service] + hits,
                    reason=f"driftsbesked: {service[0]}",
                )

        reason: str | None = None
        if level == "none":
            decision = "vis"
        elif level == "normal":
            if score >= 4:
                decision = "vis"
            elif score >= 1:
                decision, reason = "graa", "gråzone: lav score"
            else:
                decision, reason = "afvist", "intet affaldsord"
        else:  # strict
            if score >= 4 and title_hit:
                decision = "vis"
            elif score >= 2 and not title_hit:
                decision, reason = "graa", "gråzone: intet affaldsord i titel"
            else:
                decision, reason = "afvist", "intet affaldsord" if score == 0 else "for få affaldsord"
        return Why(filter=level, score=score, decision=decision, hits=hits, reason=reason)
