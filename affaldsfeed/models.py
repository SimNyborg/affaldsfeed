"""Pydantic-modeller: kontrakten fra docs/KONTRAKTER.md i kode."""

from __future__ import annotations

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
    "fagmedie",
    "myndighed",
    "kommunal",
    "organisation",
    "taenketank",
    "forskning",
    "eu_norden",
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


class PlaceSettings(_Strict):
    """Stedmærkning (places.py). Standarden passer til danske nyheder; kan overstyres i settings.yaml."""

    # Står et af ordene (eller et ord, der begynder med det) lige efter et stednavn, er navnet en del
    # af en institutions navn og tæller ikke som sted: "Aarhus Universitet", "Københavns Lufthavn".
    institution_words: list[str] = Field(default_factory=lambda: ["Universitet", "Lufthavn"])


class Settings(_Strict):
    fetch: FetchSettings
    routine: RoutineSettings
    pages: PagesSettings = Field(default_factory=PagesSettings)
    places: PlaceSettings = Field(default_factory=PlaceSettings)
    window_days: int = 60
    max_age_days_on_find: int = 14
    baseline_days: int = 14
    teaser_max: int = 300
    teaser_display_max: int = 240
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
