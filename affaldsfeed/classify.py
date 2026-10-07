"""Regelbaseret tema og genre (forslag; Claude har det sidste ord) samt opslag i overrides."""

from __future__ import annotations

import logging
import re
from urllib.parse import unquote, urlsplit

from .models import Genre, Override, Source, Topic
from .normalize import TRANSLIT, normalize_url
from .relevance import compile_patterns, find_hits

log = logging.getLogger(__name__)

MAX_TOPICS = 2
MIN_TOPIC_SCORE = 3
TITLE_POINTS = 3
TEASER_POINTS = 1
URL_POINTS = 1
SOURCE_POINTS = 1
RULE_GENRES = ("hoering", "folketing")  # giver altid temaet "regler"

# Bøjninger, der accepteres når en RSS-kategori sammenlignes med en genre ("Analyser", "Høringer")
_CATEGORY_SUFFIXES = ("", "r", "e", "er", "en", "ne", "erne", "s", "ter", "ker")
_CATEGORY_SPLIT_RE = re.compile(r"[,;/|>]+")
_SLUG_SPLIT_RE = re.compile(r"[\W_]+")
_TITLE_LEAD = " \t\"'«»„“”‘’"


def _url_path(url: str) -> str:
    try:
        return unquote(urlsplit(url or "").path)
    except ValueError:
        return ""


def _url_target(url: str) -> str:
    """Vært + sti (uden skema og query) til genrens URL-mønstre."""
    try:
        parts = urlsplit(url or "")
    except ValueError:
        return url or ""
    return (parts.netloc + unquote(parts.path)).lower()


def _compile_regex(pattern: str) -> re.Pattern:
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error:
        log.warning("ugyldigt URL-mønster %r; bruges som tekst", pattern)
        return re.compile(re.escape(pattern), re.IGNORECASE)


class Classifier:
    """Tema og genre ud fra topics.yaml og genres.yaml. Overrides anvendes ikke her."""

    def __init__(self, topics: list[Topic], genres: list[Genre]):
        self.topic_ids = [t.id for t in topics]
        self._topic_patterns = {t.id: compile_patterns(t.patterns) for t in topics}
        # Til URL-slugs, hvor æøå er skrevet som ae/oe/aa
        self._topic_slug_patterns = {
            t.id: compile_patterns(sorted({p.translate(TRANSLIT) for p in t.patterns} - set(t.patterns)))
            for t in topics
        }
        self._genre_urls = [(g.id, [_compile_regex(p) for p in g.url_patterns]) for g in genres]
        self._genre_prefixes = [(g.id, [p.strip() for p in g.title_prefixes if p.strip()]) for g in genres]
        self._genre_words: list[tuple[str, set[str]]] = []
        for g in genres:
            if g.id == "nyhed":
                continue
            words = {g.id.casefold()}
            if g.label.strip():
                words.add(g.label.strip().casefold())
            words.update(p.strip().rstrip(":").strip().casefold() for p in g.title_prefixes if p.strip())
            self._genre_words.append((g.id, {w for w in words if w}))

    # ── Genre ──────────────────────────────────────────────

    def _genre_from_categories(self, categories: list[str]) -> str | None:
        parts = [
            p.strip().casefold() for c in categories or [] for p in _CATEGORY_SPLIT_RE.split(c) if p.strip()
        ]
        for genre_id, words in self._genre_words:
            for part in parts:
                for w in words:
                    if part.startswith(w) and part[len(w) :] in _CATEGORY_SUFFIXES:
                        return genre_id
        return None

    def _genre_from_title(self, title: str) -> str | None:
        t = (title or "").lstrip(_TITLE_LEAD).casefold()
        for genre_id, prefixes in self._genre_prefixes:
            for p in prefixes:
                pc = p.casefold()
                if not t.startswith(pc):
                    continue
                # "Høring over" må ikke ramme "Høring overvejes"
                if pc[-1].isalnum() and len(t) > len(pc) and t[len(pc)].isalnum():
                    continue
                return genre_id
        return None

    def genre_for(self, title: str, url: str, categories: list[str], source: Source) -> str:
        """Kildens genre (hvis ≠ nyhed) → URL-mønstre → RSS-kategorier → titelpræfikser → nyhed."""
        if source.genre != "nyhed":
            return source.genre
        target = _url_target(url)
        for genre_id, patterns in self._genre_urls:
            if any(rx.search(target) for rx in patterns):
                return genre_id
        return self._genre_from_categories(categories) or self._genre_from_title(title) or "nyhed"

    # ── Tema ───────────────────────────────────────────────

    def topic_scores(self, title: str, teaser: str, url: str, source: Source) -> dict[str, tuple[int, int]]:
        """Point pr. tema og længden af det mest specifikke mønster, der ramte (til lighed)."""
        slug = _SLUG_SPLIT_RE.sub(" ", _url_path(url))
        scores: dict[str, tuple[int, int]] = {}
        for tid in self.topic_ids:
            pats = self._topic_patterns[tid]
            t_hits = find_hits(title or "", pats)
            s_hits = find_hits(teaser or "", pats)
            score = TITLE_POINTS * len(t_hits) + TEASER_POINTS * len(s_hits)
            if slug.strip() and (find_hits(slug, pats) or find_hits(slug, self._topic_slug_patterns[tid])):
                score += URL_POINTS
            if tid in source.topics:
                score += SOURCE_POINTS
            if score:
                specific = max((len(h.strip("*")) for h in t_hits + s_hits), default=0)
                scores[tid] = (score, specific)
        return scores

    def topics_for(
        self, title: str, teaser: str, url: str, source: Source, *, genre: str | None = None
    ) -> list[str]:
        """Højst 2 temaer. genre kan gives, så RSS-kategorier tæller med; ellers beregnes den uden."""
        scores = self.topic_scores(title, teaser, url, source)
        order = {tid: i for i, tid in enumerate(self.topic_ids)}
        ranked = sorted(scores, key=lambda t: (-scores[t][0], -scores[t][1], order[t]))

        result: list[str] = []
        if ranked and scores[ranked[0]][0] >= MIN_TOPIC_SCORE:
            best = scores[ranked[0]][0]
            result.append(ranked[0])
            if len(ranked) > 1:
                second = scores[ranked[1]][0]
                if second >= MIN_TOPIC_SCORE and 2 * second >= best:
                    result.append(ranked[1])
        else:
            result = list(source.topics[:MAX_TOPICS])

        if genre is None:
            genre = self.genre_for(title, url, [], source)
        if genre in RULE_GENRES and "regler" not in result:
            result = [*result[: MAX_TOPICS - 1], "regler"]
        return result


class Overrides:
    """Manuelle rettelser fra overrides.yaml. Bruges af display.py."""

    _KEYS = {"id", "url_regex"}

    def __init__(self, overrides: list[Override]):
        self._items: list[tuple[Override, re.Pattern | None]] = []
        for ov in overrides:
            unknown = set(ov.match) - self._KEYS
            if unknown:
                log.warning("override med ukendte match-nøgler ignoreres: %s", ", ".join(sorted(unknown)))
            rx = None
            if "url_regex" in ov.match:
                try:
                    rx = re.compile(ov.match["url_regex"], re.IGNORECASE)
                except re.error:
                    log.warning("ugyldigt url_regex i override: %r", ov.match["url_regex"])
            self._items.append((ov, rx))

    def find(self, item_id: str, url: str) -> list[Override]:
        """Alle overrides, der passer på id og/eller URL, i filens rækkefølge."""
        found: list[Override] = []
        norm: str | None = None
        for ov, rx in self._items:
            m = ov.match
            if not (self._KEYS & set(m)):
                continue
            if "id" in m and m["id"] != item_id:
                continue
            if "url_regex" in m:
                if rx is None:
                    continue
                if norm is None:
                    norm = normalize_url(url)
                if not (rx.search(url or "") or rx.search(norm)):
                    continue
            found.append(ov)
        return found
