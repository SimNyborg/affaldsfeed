"""Indlæsning og validering af sources.yaml og config/*.yaml, samt check-kommandoen."""

from __future__ import annotations

import argparse
import contextlib
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, get_args
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ValidationError

from affaldsfeed import paths
from affaldsfeed.models import (
    Category,
    CategoryId,
    Genre,
    GenreId,
    Geo,
    Keywords,
    Override,
    Publisher,
    SearchConfig,
    Settings,
    Source,
    Topic,
    TopicId,
)

log = logging.getLogger(__name__)

GEO_FILE = "geografi.yaml"
TOPIC_UI_MAX = 26  # højst så mange tegn i et temanavn i brugerfladen (short, ellers name)
# libyaml er meget hurtigere (geografi.yaml er stor); samme resultat som yaml.safe_load
_YAML_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


class ConfigError(Exception):
    """Fejl i sources.yaml eller config/. Beskeden nævner fil og post-id."""


@dataclass
class Config:
    settings: Settings
    categories: list[Category]
    topics: list[Topic]
    genres: list[Genre]
    keywords: Keywords
    search: SearchConfig
    publishers: list[Publisher]
    overrides: list[Override]
    profile: str
    geo: Geo = field(default_factory=Geo)
    # Fejl i geografi.yaml. Kun check fejler; ellers bruges en tom geografi (ingen stedmærkning)
    geo_errors: list[str] = field(default_factory=list)


# ── Hjælpere ─────────────────────────────────────────────────


def _host(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _clean_domain(d: str) -> str:
    d = d.strip().lower()
    if "://" in d:
        d = urlsplit(d).hostname or ""
    d = d.split("/")[0]
    return d[4:] if d.startswith("www.") else d


def _read_yaml(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise ConfigError(f"{path.name}: filen findes ikke") from e
    try:
        return yaml.load(text, Loader=_YAML_LOADER)  # sikker loader (SafeLoader eller CSafeLoader)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f" (linje {mark.line + 1})" if mark is not None else ""
        raise ConfigError(f"{path.name}: YAML-fejl{where}: {getattr(e, 'problem', e)}") from e


def _fmt_validation(fname: str, ident: str, err: ValidationError) -> list[str]:
    out = []
    for e in err.errors():
        loc = ".".join(str(x) for x in e.get("loc", ())) or "-"
        msg = str(e.get("msg"))
        if e.get("type") == "value_error":
            msg = msg.removeprefix("Value error, ")  # vores egne beskeder er på dansk
        out.append(f"{fname}: {ident}: {loc}: {msg}")
    return out


def _validate_list(data: Any, model: type[BaseModel], fname: str) -> tuple[list[Any], list[str]]:
    """Validér en YAML-liste post for post, så alle fejl kommer med."""
    if data is None:
        return [], []
    if not isinstance(data, list):
        return [], [f"{fname}: skal være en liste"]
    items: list[Any] = []
    errors: list[str] = []
    for i, raw in enumerate(data):
        ident = str(raw.get("id")) if isinstance(raw, dict) and raw.get("id") else f"post #{i + 1}"
        try:
            items.append(model.model_validate(raw))
        except ValidationError as e:
            errors.extend(_fmt_validation(fname, ident, e))
        except re.error as e:
            errors.append(f"{fname}: {ident}: ugyldigt regex: {e}")
    return items, errors


def _validate_obj(data: Any, model: type[BaseModel], fname: str) -> tuple[Any, list[str]]:
    try:
        return model.model_validate(data if data is not None else {}), []
    except ValidationError as e:
        return None, _fmt_validation(fname, "-", e)


def _duplicates(ids: list[str]) -> list[str]:
    seen: set[str] = set()
    dup: list[str] = []
    for i in ids:
        if i in seen and i not in dup:
            dup.append(i)
        seen.add(i)
    return dup


# ── Indlæsning ───────────────────────────────────────────────


def _load_sources(path: Path) -> tuple[list[Source], list[str]]:
    data = _read_yaml(path)
    sources, errors = _validate_list(data, Source, path.name)
    for d in _duplicates([s.id for s in sources]):
        errors.append(f"{path.name}: {d}: id findes flere gange")
    return sources, errors


def load_sources(path: Path | None = None) -> list[Source]:
    """Læs og validér kilderegistret. Rejser ConfigError med alle fejl."""
    path = path or paths.SOURCES_FILE
    sources, errors = _load_sources(path)
    if errors:
        raise ConfigError("\n".join(errors))
    return sources


def _load_config(config_dir: Path) -> tuple[Config | None, list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    def read(name: str, optional: bool = False) -> Any:
        p = config_dir / name
        if optional and not p.exists():
            warnings.append(f"{name}: filen findes ikke (bruger tom liste)")
            return None
        try:
            return _read_yaml(p)
        except ConfigError as e:
            errors.append(str(e))
            return None

    settings, e1 = _validate_obj(read("settings.yaml"), Settings, "settings.yaml")
    categories, e2 = _validate_list(read("categories.yaml"), Category, "categories.yaml")
    topics, e3 = _validate_list(read("topics.yaml"), Topic, "topics.yaml")
    genres, e4 = _validate_list(read("genres.yaml"), Genre, "genres.yaml")
    keywords, e5 = _validate_obj(read("keywords.yaml"), Keywords, "keywords.yaml")
    search, e6 = _validate_obj(read("search.yaml"), SearchConfig, "search.yaml")
    publishers, e7 = _validate_list(read("medier.yaml", optional=True), Publisher, "medier.yaml")
    overrides, e8 = _validate_list(read("overrides.yaml"), Override, "overrides.yaml")
    for e in (e1, e2, e3, e4, e5, e6, e7, e8):
        errors.extend(e)

    # Faste id-lister skal være komplette og unikke
    for fname, items, allowed in (
        ("categories.yaml", categories, get_args(CategoryId)),
        ("topics.yaml", topics, get_args(TopicId)),
        ("genres.yaml", genres, get_args(GenreId)),
    ):
        ids = [x.id for x in items]
        for d in _duplicates(ids):
            errors.append(f"{fname}: {d}: id findes flere gange")
        if not any(fname in e for e in errors):
            missing = [a for a in allowed if a not in ids]
            if missing:
                errors.append(f"{fname}: mangler id'er: {', '.join(missing)}")

    for d in _duplicates([p.id for p in publishers]):
        errors.append(f"medier.yaml: {d}: id findes flere gange")
    for p in publishers:
        if not p.domains:
            errors.append(f"medier.yaml: {p.id}: domains må ikke være tom")

    # Geografi (KONTRAKTER §3.3): fejl gør kun check rød; ellers tom geografi. Steder tjekkes i cross_check.
    geo, geo_errors, geo_warnings = _load_geo(config_dir)
    warnings.extend(geo_warnings)

    for t in topics:
        ui_name = t.short or t.name
        if len(ui_name) > TOPIC_UI_MAX:
            warnings.append(
                f"topics.yaml: {t.id}: navnet i brugerfladen er {len(ui_name)} tegn (højst {TOPIC_UI_MAX}), "
                f"tilføj eller forkort short: {ui_name}"
            )

    # Regex og mønstre
    for g in genres:
        for pat in g.url_patterns:
            try:
                re.compile(pat)
            except re.error as e:
                errors.append(f"genres.yaml: {g.id}: ugyldigt regex {pat!r}: {e}")
    errors.extend(_check_patterns(topics, keywords))

    topic_ids = set(get_args(TopicId))
    genre_ids = set(get_args(GenreId))
    for i, o in enumerate(overrides):
        ident = o.match.get("id") or o.match.get("url_regex") or f"post #{i + 1}"
        if not ({"id", "url_regex"} & set(o.match)):
            errors.append(f"overrides.yaml: {ident}: match skal have id eller url_regex")
        if "url_regex" in o.match:
            try:
                re.compile(o.match["url_regex"])
            except re.error as e:
                errors.append(f"overrides.yaml: {ident}: ugyldigt url_regex: {e}")
        if o.action == "tema":
            vals = o.value if isinstance(o.value, list) else [o.value] if o.value else []
            bad = [v for v in vals if v not in topic_ids]
            if bad or not vals:
                errors.append(f"overrides.yaml: {ident}: ukendt tema-id: {', '.join(map(str, bad)) or '(tom)'}")
        if o.action == "genre" and o.value not in genre_ids:
            errors.append(f"overrides.yaml: {ident}: ukendt genre-id: {o.value}")

    profile_path = config_dir / "relevansprofil.md"
    try:
        profile = profile_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        errors.append("relevansprofil.md: filen findes ikke")
        profile = ""

    if errors:
        return None, errors, warnings
    cfg = Config(
        settings=settings,
        categories=categories,
        topics=topics,
        genres=genres,
        keywords=keywords,
        search=search,
        publishers=publishers,
        overrides=overrides,
        profile=profile,
        geo=geo,
        geo_errors=geo_errors,
    )
    return cfg, errors, warnings


_NEWS_PLACES = "places bruges kun til afsendere med fast geografi, ikke til nationale medier og lokalmedier"


def _unknown_places(fname: str, ident: str, places: list[str], known: set[str]) -> list[str]:
    return [
        f"{fname}: {ident}: places: ukendt sted-id {p} (se config/{GEO_FILE})" for p in places if p not in known
    ]


def _load_geo(config_dir: Path) -> tuple[Geo, list[str], list[str]]:
    """Læs og tjek geografi.yaml. Mangler filen, er geografien tom (ingen stedmærkning)."""
    path = config_dir / GEO_FILE
    if not path.exists():
        return Geo(), [], [f"{GEO_FILE}: filen findes ikke (ingen stedmærkning)"]
    try:
        data = _read_yaml(path)
    except ConfigError as e:
        return Geo(), [str(e)], []
    geo, errors = _validate_obj(data, Geo, GEO_FILE)
    if geo is None:
        return Geo(), errors, []
    errors = check_geo(geo)
    return (Geo() if errors else geo), errors, []


def check_geo(geo: Geo) -> list[str]:
    """Unikke id'er, og at by → kommune(r) → region og landsdele peger på noget, der findes."""
    f = GEO_FILE
    errors: list[str] = []
    for kind, ids in (
        ("regioner", [r.id for r in geo.regioner]),
        ("kommuner", [m.id for m in geo.kommuner]),
        ("byer", [t.id for t in geo.byer]),
    ):
        errors.extend(f"{f}: {kind}: {d}: id findes flere gange" for d in _duplicates(ids))
    regions = {r.id for r in geo.regioner}
    municipalities = {m.id for m in geo.kommuner}
    for m in geo.kommuner:
        if m.region not in regions:
            errors.append(f"{f}: kommuner: {m.id}: ukendt region {m.region}")
    for t in geo.byer:
        for k in dict.fromkeys([t.kommune, *t.kommuner]):
            if k not in municipalities:
                errors.append(f"{f}: byer: {t.id}: ukendt kommune {k}")
        if t.kommuner and t.kommune not in t.kommuner:
            errors.append(f"{f}: byer: {t.id}: kommune {t.kommune} står ikke i kommuner")
    for name, region in geo.landsdele.items():
        if region not in regions:
            errors.append(f"{f}: landsdele: {name}: ukendt region {region}")
    return errors


def _check_patterns(topics: list[Topic], keywords: Keywords | None) -> list[str]:
    """Mønstrene skal kunne oversættes af mønstermotoren i relevance.py."""
    try:
        from affaldsfeed.relevance import compile_patterns
    except ImportError:  # pragma: no cover - relevance.py findes altid i drift
        return []
    errors: list[str] = []

    def check(fname: str, ident: str, pats: list[str]) -> None:
        try:
            compile_patterns(pats)
        except Exception as e:
            errors.append(f"{fname}: {ident}: ugyldigt mønster: {e}")

    for t in topics:
        check("topics.yaml", t.id, t.patterns)
    if keywords is not None:
        for lang, pats in keywords.strong.items():
            check("keywords.yaml", f"strong.{lang}", pats)
        for lang, pats in keywords.weak.items():
            check("keywords.yaml", f"weak.{lang}", pats)
        check("keywords.yaml", "names", keywords.names)
        check("keywords.yaml", "veto", keywords.veto)
        check("keywords.yaml", "service", keywords.service)
    return errors


def load_config(config_dir: Path | None = None) -> Config:
    """Læs og validér alle filer i config/. Rejser ConfigError med alle fejl.

    En fejl i geografi.yaml stopper ikke kommandoerne: den logges, og geografien er tom (ingen stedmærkning),
    til filen er rettet. Kun check fejler (KONTRAKTER §3.3).
    """
    config_dir = config_dir or paths.CONFIG_DIR
    cfg, errors, warnings = _load_config(config_dir)
    for w in warnings:
        log.warning(w)
    if errors or cfg is None:
        raise ConfigError("\n".join(errors))
    if cfg.geo_errors:
        log.error(
            "%s er ugyldig, så stedmærkningen er slået fra, til filen er rettet (se python -m affaldsfeed check):\n%s",
            GEO_FILE, "\n".join(cfg.geo_errors),
        )
    return cfg


def source_hosts(source: Source) -> list[str]:
    """Værtsnavne (uden www.) som en kilde kendes på: homepage + domains."""
    hosts = [_host(source.homepage)] + [_clean_domain(d) for d in source.domains]
    out: list[str] = []
    for h in hosts:
        if h and h not in out:
            out.append(h)
    return out


def publisher_lookup(sources: list[Source], publishers: list[Publisher]) -> dict[str, str]:
    """Vært -> afsender-id. Aktive kilder (ikke søgekilder) først, derefter medier.yaml."""
    lookup: dict[str, str] = {}
    for s in sources:
        if s.status != "aktiv" or s.method == "search":
            continue
        for h in source_hosts(s):
            lookup.setdefault(h, s.id)
    for p in publishers:
        for d in p.domains:
            h = _clean_domain(d)
            if h:
                lookup.setdefault(h, p.id)
    return lookup


def cross_check(sources: list[Source], config: Config, today: date | None = None) -> tuple[list[str], list[str]]:
    """Tjek på tværs af filer. Returnerer (fejl, advarsler)."""
    errors: list[str] = []
    warnings: list[str] = []
    source_ids = {s.id for s in sources}
    for p in config.publishers:
        if p.id in source_ids:
            errors.append(f"medier.yaml: {p.id}: id findes også i sources.yaml")

    # replaces: gamle id'er må ikke stadig findes, og to kilder må ikke overtage det samme id
    publisher_ids = {p.id for p in config.publishers}
    taken: dict[str, str] = {}
    for s in sources:
        for old in s.replaces:
            if old in source_ids or old in publisher_ids:
                where = "sources.yaml" if old in source_ids else "medier.yaml"
                errors.append(f"sources.yaml: {s.id}: replaces nævner {old}, som stadig findes i {where}")
            if old in taken and taken[old] != s.id:
                errors.append(f"sources.yaml: {s.id}: replaces nævner {old}, som {taken[old]} allerede overtager")
            taken.setdefault(old, s.id)

    # Samme vært hos to forskellige aktive afsendere
    owner: dict[str, str] = {}
    for s in sources:
        if s.status != "aktiv" or s.method == "search":
            continue
        for h in source_hosts(s):
            if h in owner and owner[h] != s.id:
                warnings.append(f"sources.yaml: {s.id}: værten {h} bruges også af {owner[h]}")
            owner.setdefault(h, s.id)
    for p in config.publishers:
        for d in p.domains:
            h = _clean_domain(d)
            if h in owner and owner[h] != p.id:
                warnings.append(f"medier.yaml: {p.id}: domænet {h} tilhører allerede {owner[h]}")
            owner.setdefault(h, p.id)

    for s in sources:
        if s.method == "search":
            for f in s.feeds:
                if "{q}" not in f:
                    errors.append(f"sources.yaml: {s.id}: søgeskabelonen mangler {{q}}: {f}")
        if s.method != "sitemap":
            for f in s.feeds:
                if "{dato}" in f:
                    errors.append(f"sources.yaml: {s.id}: {{dato}} virker kun med method: sitemap: {f}")
        if s.status == "aktiv" and s.checked and today and s.checked < today - timedelta(days=365):
            warnings.append(f"sources.yaml: {s.id}: checked er over 12 måneder gammel ({s.checked})")

    # Faste steder (KONTRAKTER §3.1). Uden geografi (mangler eller er ugyldig) kan id'erne ikke tjekkes.
    # run logger fejlene som advarsler og ignorerer de ukendte id'er.
    known_places = config.geo.place_ids()
    for fname, senders in (("sources.yaml", sources), ("medier.yaml", config.publishers)):
        for x in senders:
            if known_places:
                errors.extend(_unknown_places(fname, x.id, x.places, known_places))
            if x.places and x.category in ("nyhedsmedie", "lokalmedie"):
                warnings.append(f"{fname}: {x.id}: {_NEWS_PLACES}")
    return errors, warnings


# ── check-kommandoen ─────────────────────────────────────────


def _print(s: str = "") -> None:
    print(s)


def main_check(args: argparse.Namespace) -> int:
    """Validér sources.yaml og config/. Med --fetch ID hentes én kilde live (skriver intet)."""
    if hasattr(sys.stdout, "reconfigure"):
        with contextlib.suppress(ValueError, OSError):
            sys.stdout.reconfigure(errors="replace")

    errors: list[str] = []
    warnings: list[str] = []
    sources: list[Source] = []
    try:
        sources, errs = _load_sources(paths.SOURCES_FILE)
        errors.extend(errs)
    except ConfigError as e:
        errors.append(str(e))
    try:
        cfg, errs, warns = _load_config(paths.CONFIG_DIR)
    except ConfigError as e:  # pragma: no cover - _load_config samler selv fejl
        cfg, errs, warns = None, [str(e)], []
    errors.extend(errs)
    warnings.extend(warns)
    if cfg is not None:
        errors.extend(cfg.geo_errors)  # kun check fejler ved en ugyldig geografi
    if cfg is not None and not errors:
        from affaldsfeed.timeutil import now_utc, to_cph

        e2, w2 = cross_check(sources, cfg, to_cph(now_utc()).date())
        errors.extend(e2)
        warnings.extend(w2)

    for w in warnings:
        _print(f"ADVARSEL {w}")
    if errors:
        for e in errors:
            _print(f"FEJL {e}")
        _print(f"{len(errors)} fejl fundet.")
        return 1

    active = [s for s in sources if s.status == "aktiv"]
    geo = cfg.geo
    _print(
        f"OK: {len(sources)} kilder ({len(active)} aktive), {len(cfg.publishers)} udgivere i medier.yaml, "
        f"{len(cfg.topics)} temaer, {len(cfg.genres)} genrer, {len(cfg.search.queries)} søgninger, "
        f"geografi: {len(geo.regioner)} regioner, {len(geo.kommuner)} kommuner, {len(geo.byer)} byer."
    )

    fetch_id = getattr(args, "fetch", None)
    if fetch_id:
        return _check_fetch(fetch_id, sources, cfg, explain=bool(getattr(args, "explain", False)))
    return 0


def _check_fetch(source_id: str, sources: list[Source], cfg: Config, explain: bool) -> int:
    """Hent én kilde live og vis forfiltrets afgørelser. Skriver intet til data/."""
    from affaldsfeed import store
    from affaldsfeed.collect import COLLECTORS, CollectContext
    from affaldsfeed.fetch import Fetcher
    from affaldsfeed.pipeline import Processor
    from affaldsfeed.timeutil import iso, now_utc

    source = next((s for s in sources if s.id == source_id), None)
    if source is None:
        _print(f"FEJL ukendt kilde: {source_id}")
        return 1
    collector = COLLECTORS.get(source.method)
    if collector is None:
        _print(f"FEJL metoden '{source.method}' er ikke implementeret endnu (fase 2)")
        return 1

    now = now_utc()
    fetcher = Fetcher(cfg.settings.fetch, {}, store.load_robots_cache(), now)
    fetcher.start_budget(max(cfg.settings.fetch.source_budget_seconds, 120.0))
    # Som kildens første kørsel med tom seen-state; intet gemmes
    ctx = CollectContext(
        config=cfg,
        sources=sources,
        now=now,
        publisher_lookup=publisher_lookup(sources, cfg.publishers),
        conditional=False,
        first_run=True,
        seen={},
    )
    _print(f"\nHenter {source.id} ({source.name}, {source.category}, metode {source.method}, filter {source.filter}) …")
    result = collector(source, fetcher, ctx)
    if result.error:
        _print(f"FEJL {result.error}")
    proc = Processor(cfg, sources, now, existing={}, recent_titles=set())
    out = proc.process(source, result.entries, first_run=False, check_mode=True)

    kept = out.new
    _print(
        f"{len(result.entries)} indslag hentet. Beholdt {len(kept)} "
        f"(vis {sum(c.why.decision == 'vis' for c in kept)}, graa {sum(c.why.decision == 'graa' for c in kept)}), "
        f"afvist {len(out.rejected)}, sprunget over {out.skipped}."
    )
    if kept:
        _print("\nBEHOLDT")
        for c in sorted(kept, key=lambda c: (c.published or c.first_seen), reverse=True):
            _print(f"  [{c.why.decision}] score {c.why.score:>2}  {(iso(c.published) or '')[:10]}  {c.source}: {c.title}")
            _print(f"      {c.url}")
            hits = "; ".join(c.why.hits) or "-"
            _print(
                f"      hits: {hits} | tema: {', '.join(c.topics) or '-'} | genre: {c.genre}"
                f" | steder: {', '.join(c.places) or '-'}"
            )
    if out.rejected:
        _print("\nAFVIST")
        for r in out.rejected:
            reason = f" ({r.why.reason})" if r.why.reason else ""
            _print(f"  [afvist] score {r.why.score:>2}{reason}  {r.source}: {r.title}")
            if explain:
                _print(f"      {r.url}")
                _print(f"      hits: {'; '.join(r.why.hits) or '-'}")
    if result.unknown_publishers:
        _print("\nUKENDTE UDGIVERE (ville blive kildeforslag)")
        for domain, name, url in result.unknown_publishers:
            _print(f"  {domain} ({name}): {url}")
    if explain and result.diagnostics:
        # Til sidst, så den står med, når en probe kun gemmer halen af udskriften
        _print("\nDIAGNOSE")
        for line in result.diagnostics:
            _print(f"  {line}")
    return 1 if result.error and not result.entries else 0
