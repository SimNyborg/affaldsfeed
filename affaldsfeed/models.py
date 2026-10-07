"""Pydantic-modeller: kontrakten fra docs/KONTRAKTER.md i kode."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


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
    lang: Lang = "da"
    paywall: Paywall = "nej"
    owner: str | None = None
    aliases: list[str] = Field(default_factory=list)
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


class Settings(_Strict):
    fetch: FetchSettings
    routine: RoutineSettings
    pages: PagesSettings = Field(default_factory=PagesSettings)
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
    why: Why
    baseline: bool = False
    found_via: FoundVia = "feed"
    categories: list[str] = Field(default_factory=list)


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
    genre: GenreId = "nyhed"
    summary_da: str | None = Field(default=None, max_length=160)
    story_hint: str | None = None
    judged_at: datetime
    by: str = "claude-routine"
    new_item: NewItem | None = None


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
    genre: GenreId = "nyhed"
    lang: Lang = "da"
    summary_da: str | None = None
    reviewed: bool = True
    reason: str | None = None
    also: list[AlsoRef] = Field(default_factory=list)
    why: Why | None = None
