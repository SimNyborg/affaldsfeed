"""run-kommandoen: plan → hent → normalisér → forfilter → klassificér → dedupe → gem."""

from __future__ import annotations

import argparse
import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import get_args

from affaldsfeed import paths, store
from affaldsfeed.classify import Classifier, Overrides
from affaldsfeed.collect import COLLECTORS, CollectContext, RawEntry, match_publisher
from affaldsfeed.collect.pages import remembered_sitemaps
from affaldsfeed.collect.search import build_url
from affaldsfeed.config import (
    Config,
    ConfigError,
    cross_check,
    load_config,
    load_sources,
    publisher_lookup,
    source_hosts,
)
from affaldsfeed.fetch import Fetcher
from affaldsfeed.health import is_due, record_result
from affaldsfeed.models import Candidate, DateQuality, Rejected, Source, SourceState
from affaldsfeed.normalize import clean_text, item_id, normalize_title
from affaldsfeed.relevance import Prefilter
from affaldsfeed.timeutil import ensure_utc, iso, now_utc, parse_iso

log = logging.getLogger(__name__)

LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"
TITLE_MAX = 300
FUTURE_SLACK = timedelta(hours=2)
SEARCH_DEDUPE_DAYS = 7
MIN_DEDUPE_WORDS = 4
ITEMS_WINDOW_DAYS = 30
ROBOTS_KEEP_DAYS = 30
SLOW_EVERY_HOURS = 24
FILTER_ORDER = {"none": 0, "normal": 1, "strict": 2}
DATE_QUALITIES = set(get_args(DateQuality))


@dataclass
class SourceOutcome:
    new: list[Candidate] = field(default_factory=list)
    updated: list[Candidate] = field(default_factory=list)
    rejected: list[Rejected] = field(default_factory=list)
    skipped: int = 0


class Processor:
    """Gør RawEntry til Candidate/Rejected efter KONTRAKTER §5.4-5.5 og §6.1."""

    def __init__(
        self,
        config: Config,
        sources: list[Source],
        now: datetime,
        existing: dict[str, Candidate],
        recent_titles: set[tuple[str, str]],
    ):
        self.config = config
        self.settings = config.settings
        self.now = ensure_utc(now)
        self.sources_by_id = {s.id: s for s in sources}
        self.publishers_by_id = {p.id: p for p in config.publishers}
        self.existing = existing
        self.recent_titles = recent_titles
        self.prefilter = Prefilter(config.keywords)
        self.classifier = Classifier(config.topics, config.genres)
        self.overrides = Overrides(config.overrides)
        self.seen_ids: set[str] = set()
        self._synthetic: dict[str, Source] = {}

    def rule_source(self, collector_source: Source, source_id: str) -> Source:
        """Kilden som regler (forfilter, tema, genre) skal se. Søgefund bruger udgiverens kilde."""
        if source_id == collector_source.id:
            return collector_source
        src = self.sources_by_id.get(source_id) or self._synthetic.get(source_id)
        if src is None:
            pub = self.publishers_by_id.get(source_id)
            if pub is None:
                return collector_source
            src = Source(
                id=pub.id,
                name=pub.name,
                category=pub.category,
                homepage=f"https://{pub.domains[0]}" if pub.domains else "https://example.invalid",
                method="search",
                feeds=[],
                domains=pub.domains,
                lang=pub.lang,
                paywall=pub.paywall,
                basis=pub.basis,
                status="aktiv",
                checked=self.now.date(),
                filter=collector_source.filter,
            )
            self._synthetic[source_id] = src
        # Det strengeste filter af søgekilden og udgiveren gælder
        level = max(src.filter, collector_source.filter, key=lambda f: FILTER_ORDER[f])
        if level != src.filter:
            src = src.model_copy(update={"filter": level})
        return src

    def process(self, source: Source, entries: list[RawEntry], first_run: bool, check_mode: bool = False) -> SourceOutcome:
        out = SourceOutcome()
        s = self.settings
        max_age = timedelta(days=s.baseline_days if first_run else s.max_age_days_on_find)
        for e in entries:
            url = (e.url or "").strip()
            if not url.startswith(("http://", "https://")):
                out.skipped += 1
                continue
            iid = item_id(url)
            if iid in self.seen_ids:
                out.skipped += 1
                continue
            self.seen_ids.add(iid)
            title = clean_text(e.title, TITLE_MAX)
            if not title:
                out.skipped += 1
                continue
            teaser = clean_text(e.teaser, s.teaser_max)
            if teaser and normalize_title(teaser) == normalize_title(title):
                teaser = ""

            # Kendt id: opdatér kun titlen (published/first_seen bevares). Kun fra samme slags fund,
            # så et søgeresultat og kildens eget feed ikke skiftes til at overskrive hinanden.
            old = None if check_mode else self.existing.get(iid)
            if old is not None:
                if old.title != title and old.found_via == e.found_via:
                    upd = old.model_copy(update={"title": title})
                    self.existing[iid] = upd
                    out.updated.append(upd)
                else:
                    out.skipped += 1
                continue

            title_key = (normalize_title(title), e.source_id)
            # Søgefund dedupes altid på titel + udgiver. Feedindslag kun ved titler på mindst 4 ord,
            # fordi samme artikel kan ligge i flere sektionsfeeds med hver sin URL (fx Altinget).
            dedupe = e.found_via == "search" or len(title_key[0].split()) >= MIN_DEDUPE_WORDS
            if dedupe and not check_mode and title_key in self.recent_titles:
                out.skipped += 1
                continue

            # Datoregler (§5.5)
            published = ensure_utc(e.published) if e.published else None
            dq = e.date_quality if e.date_quality in DATE_QUALITIES and e.date_quality != "fundet" else "kilde"
            if published is not None and published > self.now + FUTURE_SLACK:
                published = None
            if published is None:
                if first_run and not check_mode:
                    out.skipped += 1  # udaterede springes over ved første kørsel
                    continue
                published, dq = self.now, "fundet"
            too_old = dq != "fundet" and published < self.now - max_age

            rsrc = self.rule_source(source, e.source_id)
            why = self.prefilter.evaluate(title, teaser, rsrc)
            forced = any(o.action == "vis" for o in self.overrides.find(iid, url))
            if forced and (why.decision == "afvist" or too_old):
                why = why.model_copy(update={"decision": "vis", "reason": "vist via overrides.yaml"})
            elif too_old:
                # Gamle indslag gemmes kun som afviste, hvis forfiltret ellers ville beholde dem og de er
                # nyere end rejected_keep_days. Ellers fylder arkiv-feeds med tusindvis af poster data/rejected/.
                keep_cut = self.now - timedelta(days=s.rejected_keep_days)
                if not check_mode and (why.decision == "afvist" or published < keep_cut):
                    out.skipped += 1
                    continue
                why = why.model_copy(update={"decision": "afvist", "reason": "for gammel"})

            if why.decision == "afvist":
                out.rejected.append(
                    Rejected(id=iid, url=url, title=title, source=e.source_id, first_seen=self.now, why=why)
                )
                continue

            genre = self.classifier.genre_for(title, url, e.categories, rsrc)
            topics = list(dict.fromkeys(self.classifier.topics_for(title, teaser, url, rsrc, genre=genre)))[:2]
            lang = e.lang if e.lang in ("da", "en", "sv") else rsrc.lang
            cand = Candidate(
                id=iid,
                url=url,
                title=title,
                teaser=teaser,
                source=e.source_id,
                published=published,
                date_quality=dq,
                first_seen=self.now,
                lang=lang,
                genre=genre,
                topics=topics,
                why=why,
                baseline=first_run and not check_mode,
                found_via=e.found_via if e.found_via in ("feed", "search", "sweep") else "feed",
                categories=list(e.categories),
            )
            out.new.append(cand)
            if not check_mode:
                self.existing[iid] = cand
                self.recent_titles.add(title_key)
        return out


# ── Planlægning ─────────────────────────────────────────────


def _parse_only(val: object) -> set[str] | None:
    if not val:
        return None
    parts = val if isinstance(val, list | tuple) else [val]
    out = {p.strip() for item in parts for p in str(item).split(",") if p.strip()}
    return out or None


def plan_sources(
    sources: list[Source],
    states: dict[str, SourceState],
    now: datetime,
    only: set[str] | None,
    fetcher: Fetcher,
    max_crawl_delay: float,
) -> tuple[list[Source], list[str]]:
    """(kilder på tur, aktive kilder der venter på fase 2)."""
    by_id = {s.id: s for s in sources}
    if only:
        for sid in sorted(only - set(by_id)):
            log.warning("Ukendt kilde i --only: %s", sid)
        for sid in sorted(only & set(by_id)):
            if by_id[sid].status != "aktiv":
                log.warning("%s har status '%s' og køres ikke (brug check --fetch %s)", sid, by_id[sid].status, sid)
    pool = [s for s in sources if s.status == "aktiv" and (not only or s.id in only)]
    waiting = [s.id for s in pool if s.method not in COLLECTORS]
    due: list[Source] = []
    for s in pool:
        if s.method not in COLLECTORS:
            continue
        if only:
            due.append(s)
            continue
        eff = s
        if s.method != "search" and any(fetcher.cached_crawl_delay(f) > max_crawl_delay for f in s.feeds):
            eff = s.model_copy(update={"every": max(s.every_hours, SLOW_EVERY_HOURS)})
        if is_due(eff, states.get(s.id) or SourceState(), now):
            due.append(s)
    # Feeds først, så søgefund kan dedupes mod dem. Blandt feeds går de længst ventende først, så et brugt
    # tidsbudget for kørslen ikke rammer de samme kilder hver gang.
    never = datetime.min.replace(tzinfo=UTC)
    due.sort(key=lambda s: (s.method == "search", (states.get(s.id) or SourceState()).last_attempt or never, s.id))
    return due, waiting


def _valid_cache_urls(sources: list[Source], config: Config, http_cache: dict) -> set[str]:
    urls: set[str] = set()
    for s in sources:
        if s.status != "aktiv":
            continue
        if s.method == "search":
            urls.update(build_url(t, q, config.search.when) for t in s.feeds for q in config.search.queries)
        else:
            urls.update(s.feeds)
        if s.method == "sitemap":
            # Under-sitemaps fra et indeks hentes også betinget (KONTRAKTER §5.6)
            urls.update(remembered_sitemaps(http_cache, s.feeds))
    return urls


# ── run ─────────────────────────────────────────────────────


def main_run(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    try:
        return _run(args)
    except Exception:
        log.exception("Systemfejl under kørslen")
        return 1


def _run(args: argparse.Namespace) -> int:
    now = now_utc(getattr(args, "now", None))
    dry = bool(getattr(args, "dry_run", False))
    only = _parse_only(getattr(args, "only", None))

    try:
        sources = load_sources(paths.SOURCES_FILE)
        config = load_config(paths.CONFIG_DIR)
    except ConfigError as e:
        log.error("Konfigurationen er ugyldig:\n%s", e)
        return 1
    xerrs, xwarns = cross_check(sources, config)
    for msg in xerrs + xwarns:
        log.warning(msg)
    settings = config.settings

    states = store.load_source_states()
    fetcher = Fetcher(settings.fetch, store.load_http_cache(), store.load_robots_cache(), now)
    kildeforslag = store.load_kildeforslag()
    seen = store.load_seen()
    all_candidates = store.load_candidates()
    existing = {c.id: c for c in all_candidates}
    recent_cut = now - timedelta(days=SEARCH_DEDUPE_DAYS)
    recent_titles = {(normalize_title(c.title), c.source) for c in all_candidates if c.first_seen >= recent_cut}

    due, waiting = plan_sources(sources, states, now, only, fetcher, settings.fetch.max_crawl_delay_seconds)
    if waiting:
        log.info("Venter på fase 2 (metode ikke implementeret): %s", ", ".join(sorted(waiting)))
    if only and not due:
        log.error("Ingen aktive kilder med en implementeret metode matcher --only %s", ",".join(sorted(only)))
        return 1
    log.info("Kørsel %s%s: %d kilder på tur", iso(now), " (dry-run)" if dry else "", len(due))

    ctx = CollectContext(
        config=config,
        sources=sources,
        now=now,
        publisher_lookup=publisher_lookup(sources, config.publishers),
        seen=seen,
    )
    proc = Processor(config, sources, now, existing, recent_titles)
    new_c: list[Candidate] = []
    upd_c: list[Candidate] = []
    rejected: list[Rejected] = []
    unknown: list[tuple[str, str, str]] = []
    failed: dict[str, str] = {}
    ok_count = 0
    run_t0 = time.monotonic()
    postponed: list[str] = []

    for s in due:
        # Kørslens tidsbudget: resten venter til næste kørsel. Søgekilder kører altid (de er hurtige, og
        # lokalmedier findes kun via søgning).
        if s.method != "search" and time.monotonic() - run_t0 > settings.fetch.run_budget_seconds:
            postponed.append(s.id)
            continue
        state = states.get(s.id) or SourceState()
        # Første kørsel: kilden har aldrig haft en vellykket kørsel (ingen state eller first_run_done false)
        first_run = not state.first_run_done
        ctx.conditional = not first_run
        ctx.first_run = first_run
        ctx.last_ok = state.last_ok
        fetcher.start_budget(settings.fetch.source_budget_seconds)
        cache_backup = dict(fetcher.http_cache)
        seen_backup = dict(seen.get(s.id, {}))
        t0 = time.monotonic()
        error: str | None = None
        n_entries = 0
        backlog = False
        out = SourceOutcome()
        try:
            res = COLLECTORS[s.method](s, fetcher, ctx)
            error = res.error
            n_entries = len(res.entries)
            backlog = res.backlog
            for line in res.diagnostics:
                log.debug("%s: %s", s.id, line)
            out = proc.process(s, res.entries, first_run)
            unknown.extend(res.unknown_publishers)
        except Exception as e:  # hver kilde er isoleret
            log.exception("%s: uventet fejl", s.id)
            error = f"{type(e).__name__}: {e}"[:300]
            fetcher.http_cache.clear()
            fetcher.http_cache.update(cache_backup)
            seen[s.id] = seen_backup  # sider markeret før fejlen er ikke behandlet
        new_c.extend(out.new)
        upd_c.extend(out.updated)
        rejected.extend(out.rejected)
        states[s.id] = record_result(state, error is None, error, now, settings)
        if first_run and backlog:
            # Baseline er ikke komplet (sider eller sitemaps venter): næste kørsel er også en første kørsel,
            # så restkøen hentes som baseline med 14-dages-vinduet (KONTRAKTER §5.6)
            states[s.id] = states[s.id].model_copy(update={"first_run_done": False})
        secs = time.monotonic() - t0
        if error:
            failed[s.id] = error
            log.warning("%s: FEJL %s (%.1f s)", s.id, error, secs)
        else:
            ok_count += 1
            vis = sum(c.why.decision == "vis" for c in out.new)
            log.info(
                "%s: %d indslag, %d nye (vis %d, graa %d), %d afviste, %d opdaterede%s (%.1f s)",
                s.id,
                n_entries,
                len(out.new),
                vis,
                len(out.new) - vis,
                len(out.rejected),
                len(out.updated),
                (", baseline (ikke komplet; fortsætter)" if backlog else ", baseline") if first_run else "",
                secs,
            )
        if dry:
            for c in out.new:
                log.info("  + [%s %d] %s: %s", c.why.decision, c.why.score, c.source, c.title)
    fetcher.start_budget(None)
    if postponed:
        log.warning(
            "Kørslens tidsbudget (%.0f s) er brugt: %d kilder venter til næste kørsel: %s",
            settings.fetch.run_budget_seconds,
            len(postponed),
            ", ".join(postponed),
        )

    # Antal indslag de seneste 30 dage pr. kilde
    cut30 = now - timedelta(days=ITEMS_WINDOW_DAYS)
    counts = Counter(c.source for c in proc.existing.values() if (c.published or c.first_seen) >= cut30)
    for sid, st in list(states.items()):
        if st.items_30d != counts.get(sid, 0):
            states[sid] = st.model_copy(update={"items_30d": counts.get(sid, 0)})

    # Ukendte udgivere → kildeforslag (kendte værter fra alle kilder, uanset status, springes over)
    known_hosts = {h: s.id for s in sources for h in source_hosts(s)}
    fresh_unknown = [u for u in unknown if match_publisher(u[0], known_hosts) is None]
    kf_added = store.merge_kildeforslag(kildeforslag, fresh_unknown, now)

    _log_summary(now, due, ok_count, failed, new_c, upd_c, rejected, kf_added, sources, config, waiting)

    if not dry:
        if new_c or upd_c:
            store.save_candidates(new_c + upd_c)
        store.save_rejected(rejected, settings.rejected_keep_days, now)
        store.save_source_states(states)
        valid = _valid_cache_urls(sources, config, fetcher.http_cache)
        store.save_http_cache({u: v for u, v in fetcher.http_cache.items() if u in valid})
        store.save_robots_cache(_prune_robots(fetcher.robots_cache, now))
        store.save_kildeforslag(kildeforslag)
        store.save_seen(seen, now, {s.id for s in sources}, settings.pages.seen_keep_days)
    else:
        log.info("Dry-run: intet er skrevet")

    attempted = len(due)
    if attempted and len(failed) / attempted > settings.fail_run_ratio:
        log.error("For mange kilder fejlede: %d af %d", len(failed), attempted)
        return 1
    return 0


def _prune_robots(cache: dict, now: datetime) -> dict:
    keep: dict = {}
    cut = now - timedelta(days=ROBOTS_KEEP_DAYS)
    for host, val in cache.items():
        try:
            if parse_iso(val.get("fetched", "")) >= cut:
                keep[host] = val
        except (ValueError, AttributeError):
            continue
    return keep


def _log_summary(
    now: datetime,
    due: list[Source],
    ok_count: int,
    failed: dict[str, str],
    new_c: list[Candidate],
    upd_c: list[Candidate],
    rejected: list[Rejected],
    kf_added: int,
    sources: list[Source],
    config: Config,
    waiting: list[str],
) -> None:
    cat = {s.id: s.category for s in sources}
    for p in config.publishers:
        cat.setdefault(p.id, p.category)
    vis = sum(c.why.decision == "vis" for c in new_c)
    log.info("== Opsummering %s ==", iso(now))
    log.info("Kilder: %d på tur, %d ok, %d fejl, %d venter på fase 2", len(due), ok_count, len(failed), len(waiting))
    for sid, err in sorted(failed.items()):
        log.info("  fejl %s: %s", sid, err)
    log.info(
        "Nye kandidater: %d (vis %d, graa %d). Opdaterede titler: %d. Afviste: %d. Nye kildeforslag-artikler: %d",
        len(new_c),
        vis,
        len(new_c) - vis,
        len(upd_c),
        len(rejected),
        kf_added,
    )
    per_cat = Counter(cat.get(c.source, "ukendt") for c in new_c)
    if per_cat:
        log.info("Nye pr. kategori: %s", ", ".join(f"{k} {v}" for k, v in sorted(per_cat.items())))
    per_reason = Counter(r.why.reason or "lav score" for r in rejected)
    if per_reason:
        log.info("Afvist pr. grund: %s", ", ".join(f"{k} {v}" for k, v in per_reason.most_common()))
