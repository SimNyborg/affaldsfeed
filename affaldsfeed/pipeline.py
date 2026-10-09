"""run-kommandoen: plan → hent → normalisér → forfilter → klassificér → dedupe → gem."""

from __future__ import annotations

import argparse
import logging
import time
from collections import Counter
from collections.abc import Callable, Collection, Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import get_args

from affaldsfeed import paths, store
from affaldsfeed.classify import Classifier, Overrides
from affaldsfeed.collect import COLLECTORS, CollectContext, RawEntry, match_publisher
from affaldsfeed.collect.pages import expand_dates, remembered_sitemaps
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
from affaldsfeed.display import known_sources
from affaldsfeed.fetch import Fetcher
from affaldsfeed.health import is_due, record_result
from affaldsfeed.logos import logo_targets, refresh_logos
from affaldsfeed.models import Candidate, DateQuality, Rejected, Source, SourceState
from affaldsfeed.normalize import clean_text, item_id, normalize_title
from affaldsfeed.places import compile_places, rule_places
from affaldsfeed.relevance import Prefilter
from affaldsfeed.timeutil import cph_day_start, ensure_utc, iso, now_utc, parse_iso, to_cph

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
        self.places = compile_places(config.geo, config.settings.places)
        self.known_places = config.geo.place_ids()
        # Tidligere id'er (Source.replaces) -> kilden, der har overtaget dem
        self.replaced_by = {old: s for s in sources for old in s.replaces}
        self.overrides = Overrides(config.overrides)
        self.seen_ids: set[str] = set()
        self._synthetic: dict[str, Source] = {}

    def fixed_places(self, places: Iterable[str]) -> list[str]:
        """Afsenderens faste steder, der står i geografien. Ukendte id'er ignoreres (check fejler, run advarer)."""
        return [p for p in places if p in self.known_places]

    def source_places(self, source_id: str) -> list[str]:
        """Faste steder for en gemt kandidats afsender (kilde, udgiver eller kilden, der har overtaget id'et)."""
        src = self.sources_by_id.get(source_id) or self.replaced_by.get(source_id)
        if src is None:
            pub = self.publishers_by_id.get(source_id)
            return self.fixed_places(pub.places) if pub is not None else []
        return self.fixed_places(src.places)

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
                places=pub.places,
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

    def process(
        self,
        source: Source,
        entries: list[RawEntry],
        first_run: bool,
        check_mode: bool = False,
        since: date | None = None,
    ) -> SourceOutcome:
        """Regler for kildens indslag. `since` er bagudindsamlingens første dag (§5.8): ældre indslag er for gamle."""
        out = SourceOutcome()
        s = self.settings
        # Bagudindsamling: indslag ældre end det almindelige vindue, som forfiltret afviser, gemmes ikke som
        # afviste, ellers fylder et år med dagssitemaps data/rejected/ med titusindvis af poster
        quiet_before: datetime | None = None
        if since is not None:
            oldest = cph_day_start(since)
            quiet_before = self.now - timedelta(days=s.max_age_days_on_find)
        else:
            oldest = self.now - timedelta(days=s.baseline_days if first_run else s.max_age_days_on_find)
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
            too_old = dq != "fundet" and published < oldest

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
                if quiet_before is not None and not check_mode and dq != "fundet" and published < quiet_before:
                    out.skipped += 1
                    continue
                out.rejected.append(
                    Rejected(id=iid, url=url, title=title, source=e.source_id, first_seen=self.now, why=why)
                )
                continue

            genre = self.classifier.genre_for(title, url, e.categories, rsrc)
            topics = list(dict.fromkeys(self.classifier.topics_for(title, teaser, url, rsrc, genre=genre)))[:2]
            lang = e.lang if e.lang in ("da", "en", "sv") else rsrc.lang
            places = rule_places(title, teaser, lang, self.fixed_places(rsrc.places), self.places)
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
                places=places,
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


def refresh_places(proc: Processor, since: datetime) -> tuple[list[Candidate], int]:
    """Genberegn regelmærkerne for danske kandidater i vinduet med den aktuelle geografi (KONTRAKTER §6.1).

    Så dækker stedfiltret også indslag fundet før en ændring af geografien eller reglerne. Returnerer
    (kandidater, hvis steder ændrede sig, antal genberegnede); proc.existing opdateres. Uden geografi
    (filen mangler eller er ugyldig) ændres intet, så en fejl i geografi.yaml ikke sletter stederne.
    """
    if not proc.known_places:
        return [], 0
    since = ensure_utc(since)
    changed: list[Candidate] = []
    n = 0
    for iid, c in list(proc.existing.items()):
        if c.lang != "da" or ensure_utc(c.published or c.first_seen) < since:
            continue
        n += 1
        places = rule_places(c.title, c.teaser, c.lang, proc.source_places(c.source), proc.places)
        if places != c.places:
            upd = c.model_copy(update={"places": places})
            proc.existing[iid] = upd
            changed.append(upd)
    return changed, n


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
    needs_backfill: Callable[[SourceState], bool] | None = None,
) -> tuple[list[Source], list[str]]:
    """(kilder på tur, aktive kilder der venter på fase 2). En bagudindsamling med restkø er på tur hver time."""
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
        state = states.get(s.id) or SourceState()
        if s.method != "search" and any(fetcher.cached_crawl_delay(f) > max_crawl_delay for f in s.feeds):
            eff = s.model_copy(update={"every": max(s.every_hours, SLOW_EVERY_HOURS)})
        elif state.backfill_runs and needs_backfill is not None and needs_backfill(state):
            eff = s.model_copy(update={"every": 1})  # restkøen hentes hver time (§5.8)
        if is_due(eff, state, now):
            due.append(s)
    # Feeds først, så søgefund kan dedupes mod dem. Blandt feeds går de længst ventende først, så et brugt
    # tidsbudget for kørslen ikke rammer de samme kilder hver gang. En bagudindsamling med restkø venter, til de
    # andre kilder har kørt, så nye nyheder ikke forsinkes af den (§5.8).
    never = datetime.min.replace(tzinfo=UTC)

    def order(s: Source) -> tuple[bool, bool, datetime, str]:
        st = states.get(s.id) or SourceState()
        busy = bool(st.backfill_runs) and needs_backfill is not None and needs_backfill(st)
        return s.method == "search", busy, st.last_attempt or never, s.id

    due.sort(key=order)
    return due, waiting


def _valid_cache_urls(sources: list[Source], config: Config, http_cache: dict, now: datetime) -> set[str]:
    urls: set[str] = set()
    for s in sources:
        if s.status != "aktiv":
            continue
        if s.method == "search":
            urls.update(build_url(t, q, config.search.when) for t in s.feeds for q in config.search.queries)
        elif s.method == "sitemap":
            # {dato} giver dagens og gårsdagens sitemap; under-sitemaps fra et indeks hentes også betinget (§5.6)
            feeds = expand_dates(s.feeds, now)
            urls.update(feeds)
            urls.update(remembered_sitemaps(http_cache, feeds))
        else:
            urls.update(s.feeds)
    return urls


# ── run ─────────────────────────────────────────────────────


def main_run(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    try:
        return _run(args)
    except Exception:
        log.exception("Systemfejl under kørslen")
        return 1


def forget_seen(seen: dict[str, dict[str, str]], source_id: str, keep: Collection[str]) -> int:
    """Glem kildens sete URL'er, der ikke blev til en kandidat (fx afvist som for gamle), så bagudindsamlingen
    henter dem igen (KONTRAKTER §5.8). Returnerer antallet."""
    own = seen.get(source_id)
    if not own:
        return 0
    drop = [iid for iid in own if iid not in keep]
    for iid in drop:
        del own[iid]
    return len(drop)


def _run_note(first_run: bool, backfill: bool, backlog: bool) -> str:
    """Tillæg til kildens loglinje: baseline ved første kørsel, bagud ved bagudindsamling (§5.6 og §5.8)."""
    if not (first_run or backfill):
        return ""
    what = "bagudindsamling" if backfill else "baseline"
    return f", {what} (ikke komplet; fortsætter)" if backlog else f", {what}"


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
    for msg in xerrs:  # check fejler på dem; kørslen fortsætter
        note = "id'et ignoreres" if "ukendt sted-id" in msg else "kørslen fortsætter"
        log.warning("%s (check fejler; %s)", msg, note)
    for msg in xwarns:
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

    due, waiting = plan_sources(
        sources, states, now, only, fetcher, settings.fetch.max_crawl_delay_seconds, settings.needs_backfill
    )
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
        # Bagudindsamling til window_start (§5.8): én gang pr. kilde, som en første kørsel med et længere vindue
        backfill = settings.needs_backfill(state)
        ctx.conditional = not (first_run or backfill)
        ctx.first_run = first_run or backfill
        ctx.backfill_since = settings.window_start if backfill else None
        ctx.last_ok = state.last_ok
        fetcher.start_budget(settings.backfill.source_budget_seconds if backfill else settings.fetch.source_budget_seconds)
        if backfill and state.backfill_runs == 0:
            forgot = forget_seen(seen, s.id, proc.existing)
            if forgot:
                log.info("%s: bagudindsamling: %d URL'er fra seen uden kandidat hentes igen", s.id, forgot)
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
            out = proc.process(s, res.entries, first_run or backfill, since=ctx.backfill_since)
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
        if backfill and error is None:
            # Bagudindsamlingen er færdig uden restkø, ellers fortsætter den ved næste kørsel, dog højst max_runs
            # vellykkede kørsler, så en side med forbigående fejl ikke holder den i gang for altid (§5.8)
            runs = state.backfill_runs + 1
            if backlog and runs < settings.backfill.max_runs:
                update = {"backfill_runs": runs}
            else:
                if backlog:
                    log.warning("%s: bagudindsamlingen stopper efter %d kørsler med en restkø", s.id, runs)
                update = {"backfilled_from": settings.window_start, "backfill_runs": 0}
            states[s.id] = states[s.id].model_copy(update=update)
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
                _run_note(first_run, backfill, backlog),
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

    # Kildernes logoer (KONTRAKTER §6.4): efter kilderne og kun, når deres tidsbudget ikke er brugt op
    if not dry and settings.logos.max_per_run and not postponed:
        t_logo = time.monotonic()
        fetcher.start_budget(settings.logos.budget_seconds)
        cut = settings.window_since(now)
        in_feed = Counter(c.source for c in proc.existing.values() if (c.published or c.first_seen) >= cut)
        targets = logo_targets(known_sources(sources, config.publishers), sources)
        n = refresh_logos(
            [(t.key, t.homepage) for t in targets],
            fetcher,
            now,
            settings.logos,
            priority={t.key: in_feed[t.source] for t in targets},
            force={t.key for t in targets if t.source in only} if only else None,
        )
        fetcher.start_budget(None)
        log.info(
            "Logoer: %d hentet, %d mangler, %d venter (%.0f s)",
            n["hentet"], n["fejl"], n["venter"], time.monotonic() - t_logo,
        )

    # Regelmærkerne for steder følger den aktuelle geografi, også for indslag fundet før en ændring
    t_places = time.monotonic()
    window = settings.window_since(now)
    refreshed, n_refreshed = refresh_places(proc, window)
    log.info(
        "Steder genberegnet for %d danske kandidater i vinduet (fra %s): %d ændret (%.0f ms)",
        n_refreshed,
        to_cph(window).date().isoformat(),
        len(refreshed),
        (time.monotonic() - t_places) * 1000,
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
        changed = {c.id: c for c in [*new_c, *upd_c, *refreshed]}  # den seneste udgave vinder
        if changed:
            store.save_candidates(list(changed.values()))
        store.save_rejected(rejected, settings.rejected_keep_days, now)
        store.save_source_states(states)
        valid = _valid_cache_urls(sources, config, fetcher.http_cache, now)
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
