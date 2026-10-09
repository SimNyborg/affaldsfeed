"""Pydantic-modeller: kontrakten fra docs/KONTRAKTER.md i kode."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PrivateAttr,
    field_validator,
    model_validator,
)

CategoryId = Literal[
    "nyhedsmedie",
    "lokalmedie",
    "fagmedie",
    "myndighed",
    "kommunal",
    "organisation",
    "taenketank",
    "forskning",
    "eu_norden",
    "sociale_medier",
]
TopicId = Literal[
    "sortering",
    "genbrugspladser",
    "gebyrer",
    "udbud",
    "forbraending",
    "klima",
    "genanvendelse",
    "producentansvar",
    "bioaffald",
    "tekstiler",
    "byg_farligt",
    "arbejdsmiljoe",
    "regler",
]
GenreId = Literal["nyhed", "debat", "pressemeddelelse", "analyse", "hoering", "folketing"]
Method = Literal["rss", "sitemap", "html", "oda", "search"]
FilterLevel = Literal["none", "normal", "strict"]
Lang = Literal["da", "en", "sv"]
Paywall = Literal["nej", "delvis", "ja"]
Basis = Literal["redaktionelt", "offentlig", "forskning", "organisation"]
Status = Literal["aktiv", "planlagt", "kandidat", "pause", "fravalgt"]
DateQuality = Literal["kilde", "url", "liste", "fundet"]
Decision = Literal["vis", "graa", "afvist"]
FoundVia = Literal["feed", "search", "sweep"]
Health = Literal["groen", "gul", "roed", "graa"]
Period = Literal["dag", "uge", "maaned", "aar"]

CATEGORY_RANK: dict[str, int] = {
    "myndighed": 0,
    "kommunal": 1,
    "organisation": 1,
    "taenketank": 1,
    "forskning": 1,
    "eu_norden": 1,
    "fagmedie": 2,
    "nyhedsmedie": 3,
    "lokalmedie": 3,
    "sociale_medier": 4,
}

DEFAULT_EVERY: dict[str, int] = {"rss": 1, "search": 2, "oda": 3, "sitemap": 6, "html": 6}

ID_PATTERN = r"^[a-z0-9][a-z0-9-]*$"
_ID_RE = re.compile(ID_PATTERN)

# Sted-id'er: r:<region>, k:<kommune>, b:<by> (KONTRAKTER §4.1)
MAX_PLACES = 8
PLACE_RANK: dict[str, int] = {"r": 0, "k": 1, "b": 2}
_PLACE_RE = re.compile(r"^[rkb]:[a-z0-9][a-z0-9-]*$")
PLACE_ID_HINT = "skriv r:<region>, k:<kommune> eller b:<by> med små bogstaver og æ→ae, ø→oe, å→aa (fx k:koebenhavn)"
_PLACE_LETTERS = (("æ", "ae"), ("ø", "oe"), ("å", "aa"), ("é", "e"), ("ü", "u"), ("ö", "oe"), ("ä", "ae"))
_PLACE_PREFIXES = {"region": "r", "kommune": "k", "by": "b"}


def sort_places(ids: Iterable[str], limit: int | None = MAX_PLACES) -> list[str]:
    """Unikke sted-id'er i fast rækkefølge: regioner, kommuner, byer, hver efter id. Højst `limit`."""
    out = sorted(set(ids), key=lambda p: (PLACE_RANK.get(p[:1], len(PLACE_RANK)), p))
    return out if limit is None else out[:limit]


def suggest_place_id(raw: str) -> str | None:
    """Et velformet bud på et forkert skrevet sted-id ("K:København" → "k:koebenhavn"), ellers None."""
    s = raw.strip().lower()
    for a, b in _PLACE_LETTERS:
        s = s.replace(a, b)
    prefix, sep, rest = s.partition(":")
    if not sep:
        return None
    prefix = _PLACE_PREFIXES.get(prefix.strip(), prefix.strip())
    out = f"{prefix}:{re.sub(r'[^a-z0-9]+', '-', rest).strip('-')}"
    return out if out != raw and _PLACE_RE.match(out) else None


def _check_places(v: list[str], limit: int | None = MAX_PLACES) -> list[str]:
    """Tjek formatet, fjern dubletter og normalisér rækkefølgen. Derefter højst `limit` forskellige steder."""
    bad = [p for p in v if not _PLACE_RE.match(p)]
    if bad:
        shown = ", ".join(f"{p!r} (mente du {s!r}?)" if (s := suggest_place_id(p)) else repr(p) for p in bad)
        what = "ugyldigt sted-id" if len(bad) == 1 else "ugyldige sted-id'er"
        raise ValueError(f"{what} {shown}: {PLACE_ID_HINT}")
    out = sort_places(v, limit=None)
    if limit is not None and len(out) > limit:
        raise ValueError(f"højst {limit} forskellige steder, her er der {len(out)}")
    return out


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ── Kilderegister ─────────────────────────────────────────────


class Source(_Strict):
    id: str
    name: str
    category: CategoryId
    homepage: str
    method: Method = "rss"
    feeds: list[str]
    domains: list[str] = Field(default_factory=list)
    match: str | None = None
    select: str | None = None
    filter: FilterLevel = "normal"
    topics: list[TopicId] = Field(default_factory=list)
    genre: GenreId = "nyhed"
    # Fast geografi for afsendere, der kun skriver om ét område (fx et kommunalt affaldsselskab). Højst 8.
    places: list[str] = Field(default_factory=list)
    lang: Lang = "da"
    paywall: Paywall = "nej"
    owner: str | None = None
    aliases: list[str] = Field(default_factory=list)
    # Tidligere id'er (fx en udgiver fra medier.yaml, der er blevet til en kilde), hvis indslag nu vises her
    replaces: list[str] = Field(default_factory=list)
    every: int | None = None
    bundle: Literal["day"] | None = None
    ai: bool = True
    basis: Basis | None = None
    status: Status = "aktiv"
    checked: date | None = None
    note: str | None = None

    @field_validator("id")
    @classmethod
    def _valid_id(cls, v: str) -> str:
        if not _ID_RE.match(v):
            raise ValueError("id skal bestå af små bogstaver, tal og bindestreg")
        return v

    @field_validator("places")
    @classmethod
    def _places(cls, v: list[str]) -> list[str]:
        return _check_places(v)

    @field_validator("feeds", mode="before")
    @classmethod
    def _feeds_list(cls, v: object) -> object:
        if isinstance(v, str):
            return [v]
        return v

    @field_validator("homepage")
    @classmethod
    def _http(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("homepage skal starte med http:// eller https://")
        return v

    @field_validator("select")
    @classmethod
    def _css(cls, v: str | None) -> str | None:
        if v:
            from cssselect import HTMLTranslator, SelectorError

            try:
                HTMLTranslator().css_to_xpath(v)  # samme oversætter som collect/pages.py
            except SelectorError as e:
                raise ValueError(f"ugyldig CSS-selektor: {e}") from e
        return v

    @model_validator(mode="after")
    def _active_requirements(self) -> Source:
        if self.status == "aktiv":
            missing = [f for f in ("basis", "checked") if getattr(self, f) is None]
            if missing:
                raise ValueError(f"aktiv kilde mangler: {', '.join(missing)}")
        if self.method in ("sitemap", "html") and self.status == "aktiv" and not self.match:
            raise ValueError("sitemap/html kræver 'match'")
        if self.match:
            re.compile(self.match)
        return self

    @property
    def every_hours(self) -> int:
        return self.every or DEFAULT_EVERY[self.method]


class Publisher(_Strict):
    """Troværdig udgiver, der kun findes via søgning (config/medier.yaml)."""

    id: str
    name: str
    category: CategoryId
    domains: list[str]
    basis: Basis
    paywall: Paywall = "nej"
    lang: Lang = "da"
    places: list[str] = Field(default_factory=list)  # højst 8

    @field_validator("places")
    @classmethod
    def _places(cls, v: list[str]) -> list[str]:
        return _check_places(v)


class Category(_Strict):
    id: CategoryId
    name: str
    short: str
    color: str
    color_dark: str
    icon: str
    help: str
    # Afventer: menuen viser kategorien uden at kunne vælge den, og den må ikke have aktive kilder
    pending: bool = False


class Topic(_Strict):
    id: TopicId
    name: str
    short: str | None = Field(default=None, min_length=1)  # kort navn til brugerfladen, ellers name
    definition: str
    patterns: list[str]


class Genre(_Strict):
    id: GenreId
    label: str
    url_patterns: list[str] = Field(default_factory=list)
    title_prefixes: list[str] = Field(default_factory=list)


class Keywords(_Strict):
    strong: dict[str, list[str]]
    names: list[str] = Field(default_factory=list)
    weak: dict[str, list[str]] = Field(default_factory=dict)
    veto: list[str] = Field(default_factory=list)
    service: list[str] = Field(default_factory=list)


class SearchConfig(_Strict):
    queries: list[str]
    when: str = "2d"


class Override(_Strict):
    match: dict[str, str]
    action: Literal["vis", "skjul", "tema", "genre", "split"]
    value: str | list[str] | None = None


class FetchSettings(_Strict):
    user_agent: str
    min_interval_seconds: float = 2.0
    timeout_seconds: float = 20.0
    source_budget_seconds: float = 60.0
    run_budget_seconds: float = Field(default=900.0, gt=0)  # samlet for feeds i én kørsel; resten venter
    max_crawl_delay_seconds: float = 30.0
    robots_cache_hours: int = 24
    max_response_mb: float = Field(default=50.0, gt=0)  # større svar afbrydes (også udpakket gzip)


class RoutineSettings(_Strict):
    hours: list[int]
    minute: int = 25
    grace_hours: float = 2.0
    timezone: str = "Europe/Copenhagen"


class PagesSettings(_Strict):
    """Sitemap- og html-kilder (KONTRAKTER §5.6)."""

    max_pages: int = 15  # nye sider pr. kilde pr. kørsel
    lastmod_days: int = 3  # sitemap: lastmod-vindue
    first_run_lastmod_days: int = 14  # ved kildens første kørsel (indtil baseline er komplet)
    max_sub_sitemaps: int = 5  # under-sitemaps fra et indeks
    max_sitemap_fetches: int = 6  # sitemap-hentninger pr. kilde pr. kørsel
    max_links: int = 30  # links pr. listeside
    max_page_mb: float = Field(default=5.0, gt=0)  # loft over en artikelside (sitemaps og lister: fetch)
    seen_refresh_days: int = 30  # seen.json: datoen fornyes, når den er ældre
    seen_keep_days: int = 120  # seen.json: fjernes, når den ikke er set så længe


class OdaSettings(_Strict):
    """Folketingets åbne data (KONTRAKTER §5.7)."""

    # Serverfilter: dokumenter, hvis titel indeholder et af ordene (store og små bogstaver er ligegyldige)
    words: list[str] = Field(default_factory=lambda: ["affald"])
    exclude_types: list[str] = Field(default_factory=list)  # dokumenttyper, der springes over (fx "Dagsorden")
    days: int = Field(default=3, gt=0)  # opdateringsvindue ved de almindelige kørsler
    first_run_days: int = Field(default=14, gt=0)  # ... ved kildens første kørsel
    max_pages: int = Field(default=5, gt=0)  # højst så mange sider à `top` dokumenter pr. kørsel
    top: int = Field(default=100, gt=0, le=100)  # dokumenter pr. side (ODA giver højst 100)


class PlaceSettings(_Strict):
    """Stedmærkning (places.py). Standarden passer til danske nyheder; kan overstyres i settings.yaml."""

    # Står et af ordene (eller et ord, der begynder med det) lige efter et stednavn, er navnet en del
    # af en institutions navn og tæller ikke som sted: "Aarhus Universitet", "Københavns Lufthavn".
    institution_words: list[str] = Field(default_factory=lambda: ["Universitet", "Lufthavn"])


class TimelineSettings(_Strict):
    """Tidslinjen (KONTRAKTER §7.3)."""

    input_days: int = Field(default=3, gt=0)  # timeline-input: godkendte historier fra så mange dage
    first_fill_days: int = Field(default=60, gt=0)  # ... når tidslinjen er tom
    events_days: int = Field(default=60, gt=0)  # eksisterende begivenheder i input (dubletter, nye indslag)
    max_per_week: int = Field(default=3, gt=0)  # højst så mange begivenheder med dato i samme uge
    recent_hours: int = Field(default=48, gt=0)  # linjer skrevet så nyligt tjekkes mod indslagene


class LogoSettings(_Strict):
    """Kildernes logoer (favicons) til kortene (KONTRAKTER §6.4)."""

    max_per_run: int = Field(default=20, ge=0)  # kilder pr. kørsel (0 = slået fra)
    refresh_days: int = Field(default=30, gt=0)  # et hentet logo tjekkes igen efter så mange dage
    retry_days: int = Field(default=7, gt=0)  # et mislykket forsøg prøves igen efter så mange dage
    max_kb: int = Field(default=200, gt=0)  # større billeder afvises
    budget_seconds: float = Field(default=120.0, gt=0)  # samlet tid til logoer i én kørsel


class Settings(_Strict):
    fetch: FetchSettings
    routine: RoutineSettings
    pages: PagesSettings = Field(default_factory=PagesSettings)
    oda: OdaSettings = Field(default_factory=OdaSettings)
    logos: LogoSettings = Field(default_factory=LogoSettings)
    places: PlaceSettings = Field(default_factory=PlaceSettings)
    timeline: TimelineSettings = Field(default_factory=TimelineSettings)
    window_days: int = 60
    max_age_days_on_find: int = 14
    baseline_days: int = 14
    teaser_max: int = 300
    teaser_display_max: int = 240
    title_prefixes: list[str] = Field(default_factory=list)  # fjernes fra titler i feedet (fx "Nyhed:")
    rejected_keep_days: int = 90
    pending_hours: int = 72
    stale_feed_hours: int = 6
    story_title_window_days: int = 3
    story_max_age_days: int = 7
    fail_run_ratio: float = 0.5
    red_after_fails: int = 5


# ── Indsamlede data ──────────────────────────────────────────


class Why(_Strict):
    filter: FilterLevel
    score: int
    decision: Decision
    hits: list[str] = Field(default_factory=list)
    reason: str | None = None


class Candidate(_Strict):
    id: str
    url: str
    title: str
    teaser: str = ""
    source: str
    published: datetime | None = None
    date_quality: DateQuality
    first_seen: datetime
    lang: Lang = "da"
    genre: GenreId = "nyhed"
    topics: list[TopicId] = Field(default_factory=list, max_length=2)
    places: list[str] = Field(default_factory=list)  # regelmærker, højst 8 (KONTRAKTER §4.1)
    why: Why
    baseline: bool = False
    found_via: FoundVia = "feed"
    categories: list[str] = Field(default_factory=list)

    @field_validator("places")
    @classmethod
    def _places(cls, v: list[str]) -> list[str]:
        return _check_places(v)


class Rejected(_Strict):
    id: str
    url: str
    title: str
    source: str
    first_seen: datetime
    why: Why


class SourceState(_Strict):
    last_ok: date | None = None
    last_attempt: datetime | None = None
    fails: int = 0
    last_error: str | None = None
    items_30d: int = 0
    first_run_done: bool = False
    health: Health = "graa"
    since: date | None = None  # første vellykkede kørsel (dato i København); None = ikke kendt endnu


# ── Claude-routinen ─────────────────────────────────────────


class NewItem(_Strict):
    url: str
    title: str = Field(max_length=300)
    teaser: str = Field(default="", max_length=300)
    source: str
    published: datetime | None = None


class Judgment(_Strict):
    id: str
    relevant: bool
    reason: str = Field(max_length=200)
    topics: list[TopicId] = Field(default_factory=list, max_length=2)
    # None = behold regelmærkerne; en liste (også tom) erstatter dem. Højst 8 forskellige.
    places: list[str] | None = None
    genre: GenreId = "nyhed"
    summary_da: str | None = Field(default=None, max_length=160)
    story_hint: str | None = None
    judged_at: datetime
    by: str = "claude-routine"
    new_item: NewItem | None = None

    @field_validator("places")
    @classmethod
    def _places(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else _check_places(v)


class Heartbeat(_Strict):
    last_run: datetime
    pending_before: int = 0
    judged: int = 0


class Window(_Strict):
    start: datetime
    end: datetime


class Bullet(_Strict):
    text: str
    item_ids: list[str] = Field(min_length=1)
    topics: list[TopicId] = Field(default_factory=list, max_length=2)


class Overview(_Strict):
    period: Period
    window: Window
    generated: datetime
    since: date | None = None
    headline: str
    bullets: list[Bullet] = Field(min_length=1)
    based_on: int


# ── Tidslinjen (KONTRAKTER §7.3) ─────────────────────────────

TimelineLevel = Literal["milepael", "vigtig"]
TIMELINE_ID_MAX = 80
TIMELINE_ITEMS_MAX = 8
_TIMELINE_ID_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-[a-z0-9]+(?:-[a-z0-9]+)*$")


def _check_timeline_id(v: str) -> str:
    m = _TIMELINE_ID_RE.match(v)
    if not m or len(v) > TIMELINE_ID_MAX:
        raise ValueError(
            f"id skal være ÅÅÅÅ-MM-DD-<slug> med små bogstaver, tal og enkelte bindestreger, højst {TIMELINE_ID_MAX} tegn"
        )
    try:
        date.fromisoformat(m.group(1))
    except ValueError:
        raise ValueError(f"id begynder med en ugyldig dato ({m.group(1)})") from None
    return v


class TimelineRef(_Strict):
    """Et indslag på tidslinjen: et øjebliksbillede, så det kan vises, når indslaget er ude af feedet."""

    id: str
    title: str = Field(min_length=1, max_length=300)
    url: str
    source: str
    source_name: str
    published: datetime | None = None

    @field_validator("url")
    @classmethod
    def _http(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("url skal starte med http:// eller https://")
        return v


class TimelineEntry(_Strict):
    """En begivenhed, som den står i timeline.json (uden by og deleted)."""

    id: str
    date: date
    level: TimelineLevel
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=600)
    topics: list[TopicId] = Field(default_factory=list, max_length=2)
    places: list[str] = Field(default_factory=list)
    items: list[TimelineRef] = Field(min_length=1, max_length=TIMELINE_ITEMS_MAX)
    updated: datetime

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        return _check_timeline_id(v)

    @field_validator("places")
    @classmethod
    def _places(cls, v: list[str]) -> list[str]:
        return _check_places(v)

    @field_validator("items")
    @classmethod
    def _unique_items(cls, v: list[TimelineRef]) -> list[TimelineRef]:
        ids = [r.id for r in v]
        if len(set(ids)) != len(ids):
            raise ValueError("samme indslag står flere gange i items")
        return v


class TimelineEvent(TimelineEntry):
    """Én linje i data/timeline/ÅÅÅÅ-MM.jsonl. En ny linje med samme id erstatter den forrige."""

    by: str = "claude-routine"
    deleted: Literal[False] = False


class TimelineDeletion(_Strict):
    """En linje, der sletter begivenheden med samme id."""

    id: str
    deleted: Literal[True]
    updated: datetime
    by: str = "claude-routine"

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        return _check_timeline_id(v)


def parse_timeline_line(line: str) -> TimelineEvent | TimelineDeletion:
    """En linje fra data/timeline/: en sletning, når "deleted" er true, ellers en begivenhed.

    Kaster ValidationError, også ved ugyldig JSON."""
    try:
        raw = json.loads(line)
    except ValueError:
        return TimelineEvent.model_validate_json(line)  # giver en ValidationError (json_invalid)
    if isinstance(raw, dict) and raw.get("deleted") is True:
        return TimelineDeletion.model_validate(raw)
    return TimelineEvent.model_validate(raw)


# ── Eksport ─────────────────────────────────────────────────


class AlsoRef(_Strict):
    id: str
    source: str
    url: str
    title: str
    published: datetime | None = None


class DisplayItem(_Strict):
    id: str
    story: str
    url: str
    title: str
    teaser: str = ""
    source: str
    published: datetime | None = None
    date_quality: DateQuality
    first_seen: datetime
    baseline: bool = False
    topics: list[TopicId] = Field(default_factory=list, max_length=2)
    # For en historie: foreningen af hovedindslagets og also-indslagenes steder (kan være flere end 8)
    places: list[str] = Field(default_factory=list)
    genre: GenreId = "nyhed"
    lang: Lang = "da"
    summary_da: str | None = None
    reviewed: bool = True
    reason: str | None = None
    also: list[AlsoRef] = Field(default_factory=list)
    why: Why | None = None

    @field_validator("places")
    @classmethod
    def _places(cls, v: list[str]) -> list[str]:
        return _check_places(v, limit=None)


# ── Geografi (config/geografi.yaml, genereret af tools/build_geografi.py) ──

# DST-koder er tekst ("083"); YAML kan læse dem som tal
GeoCode = Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, int) else v)]


class GeoRegion(_Strict):
    id: str = Field(pattern=ID_PATTERN)
    kode: GeoCode
    navn: str  # "Region Syddanmark"
    kort: str  # "Syddanmark"


class GeoMunicipality(_Strict):
    id: str = Field(pattern=ID_PATTERN)
    kode: GeoCode
    navn: str  # officielt navn: "Nyborg Kommune", "Københavns Kommune", "Bornholms Regionskommune"
    kort: str
    region: str = Field(pattern=ID_PATTERN)
    navne: list[str] = Field(default_factory=list)  # navne i tekst, fx ["Aarhus", "Århus"]
    kun_med_kommune: bool = False  # matches kun som "<navn> Kommune" (fx Vejen)


class GeoTown(_Strict):
    id: str = Field(pattern=ID_PATTERN)
    navn: str
    navne: list[str] = Field(default_factory=list)
    kommune: str = Field(pattern=ID_PATTERN)  # den primære kommune
    kommuner: list[str] = Field(default_factory=list)  # alle kommuner, byen ligger i
    indbyggere: int = 0


class Geo(_Strict):
    """Regioner, landsdele, kommuner og byer. Tom geografi betyder ingen stedmærkning."""

    kilde: dict[str, Any] = Field(default_factory=dict)
    regioner: list[GeoRegion] = Field(default_factory=list)
    landsdele: dict[str, str] = Field(default_factory=dict)  # navn -> region-id
    kommuner: list[GeoMunicipality] = Field(default_factory=list)
    byer: list[GeoTown] = Field(default_factory=list)

    _parents: dict[str, frozenset[str]] | None = PrivateAttr(default=None)

    def hierarchy(self) -> dict[str, frozenset[str]]:
        """Alle gyldige sted-id'er -> deres forældre: by → primær kommune → region, kommune → region.

        En by tæller kun under sin primære kommune (`kommune`), ikke under alle i `kommuner` (KONTRAKTER §9).
        """
        if self._parents is None:
            region_of = {m.id: m.region for m in self.kommuner}
            out: dict[str, frozenset[str]] = {f"r:{r.id}": frozenset() for r in self.regioner}
            for m in self.kommuner:
                out[f"k:{m.id}"] = frozenset({f"r:{m.region}"})
            for t in self.byer:
                ks = [t.kommune]
                out[f"b:{t.id}"] = frozenset(
                    {f"k:{k}" for k in ks} | {f"r:{region_of[k]}" for k in ks if k in region_of}
                )
            self._parents = out
        return self._parents

    def place_ids(self) -> set[str]:
        return set(self.hierarchy())

    def expand(self, place_id: str) -> set[str]:
        """Id'et og dets forældre (KONTRAKTER §9). Ukendte id'er udvides ikke."""
        return {place_id} | self.hierarchy().get(place_id, frozenset())


# ── feed.json (export, KONTRAKTER §8) ───────────────────────


class FeedTopic(_Strict):
    id: TopicId
    name: str
    short: str | None = None
    definition: str


class FeedGenre(_Strict):
    id: GenreId
    label: str


class FeedSource(_Strict):
    id: str
    name: str
    category: CategoryId
    homepage: str | None = None
    lang: Lang
    paywall: Paywall
    owner: str | None = None
    status: Status
    health: Health
    via_search: bool = False
    logo: str | None = None  # "logos/<id>.<ext>" relativt til sitet, når kilden har et logo (§6.4)
    domain_logos: dict[str, str] = Field(default_factory=dict)  # domæne -> logo for kildens andre sites (§6.4)


class FeedGeoRegion(_Strict):
    id: str
    navn: str
    kort: str


class FeedGeoMunicipality(_Strict):
    id: str
    navn: str
    kort: str
    region: str


class FeedGeoTown(_Strict):
    id: str
    navn: str
    kommune: str
    kommuner: list[str]


class FeedGeo(_Strict):
    regioner: list[FeedGeoRegion]
    kommuner: list[FeedGeoMunicipality]
    byer: list[FeedGeoTown]  # kun byer, som indslagene nævner


class Feed(_Strict):
    version: int
    generated: datetime
    window_days: int
    mode: Literal["claude", "fallback"]
    last_judgment: datetime | None = None
    categories: list[Category]
    topics: list[FeedTopic]
    genres: list[FeedGenre]
    sources: list[FeedSource]
    geo: FeedGeo | None = None  # None når config/geografi.yaml mangler
    overview: dict[Period, Overview | None]
    items: list[DisplayItem]

    @model_validator(mode="after")
    def _places_in_geo(self) -> Feed:
        if self.geo is None:
            return self
        known = (
            {f"r:{r.id}" for r in self.geo.regioner}
            | {f"k:{m.id}" for m in self.geo.kommuner}
            | {f"b:{t.id}" for t in self.geo.byer}
        )
        used = {p for it in self.items for p in it.places}
        unknown = sorted(used - known)
        if unknown:
            raise ValueError(f"items bruger sted-id'er, der ikke står i geo: {', '.join(unknown[:5])}")
        unused = sorted({f"b:{t.id}" for t in self.geo.byer} - used)
        if unused:
            raise ValueError(f"geo.byer har byer, som intet indslag nævner: {', '.join(unused[:5])}")
        return self


# ── timeline.json (export, KONTRAKTER §7.3) ─────────────────


class TimelinePublicEvent(TimelineEntry):
    # Historien i feed.json med et af begivenhedens indslag (til "Vis i feedet"), ellers None
    story: str | None = None


class TimelinePlace(_Strict):
    id: str  # med præfiks, fx k:nyborg
    navn: str
    kort: str


class TimelineFeed(_Strict):
    version: int
    generated: datetime
    topics: list[FeedTopic]
    places: list[TimelinePlace]  # navne på de steder, begivenhederne bruger
    events: list[TimelinePublicEvent]

    @model_validator(mode="after")
    def _places_named(self) -> TimelineFeed:
        named = {p.id for p in self.places}
        missing = sorted({p for e in self.events for p in e.places} - named)
        if missing:
            raise ValueError(f"events bruger steder uden navn i places: {', '.join(missing[:5])}")
        return self
