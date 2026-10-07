# Kontrakter (teknisk spec for udviklere)

Denne fil er den bindende tekniske kontrakt mellem modulerne. Ændres en kontrakt, opdateres denne fil i samme commit.

Alle tider gemmes som ISO 8601 i UTC med `Z` (fx `2026-10-07T07:14:00Z`). Visning sker i `Europe/Copenhagen`.
Alle JSON/JSONL-filer skrives UTF-8, `ensure_ascii=False`, nøgler i fast rækkefølge (pydantic-feltrækkefølge), én post pr. linje i JSONL, sorteret deterministisk (se den enkelte fil), afsluttet med linjeskift.

## 1. Pakke og CLI

Pakken hedder `affaldsfeed`. Alt køres fra repoets rod med `python -m affaldsfeed <kommando>`. Repo-roden findes som forælder til pakkemappen (`affaldsfeed/paths.py: ROOT`), så kommandoer virker uanset cwd.

| Kommando | Ejer-modul | Hvad den gør | Exit-kode |
|---|---|---|---|
| `check [--fetch ID] [--explain]` | `config.py` (+ `collect`) | Validerer `sources.yaml` og `config/*.yaml`. Med `--fetch ID` hentes én kilde live og det udskrives, hvad forfiltret beholder og hvorfor (ingen skrivning til `data/`). | 0 ok, 1 fejl |
| `run [--only ID[,ID]] [--dry-run] [--now ISO]` | `pipeline.py` | Indsamling: plan → hent → normalisér → forfilter → klassificér (regler) → dedupe → gem kandidater, afviste og state. `--dry-run` skriver intet. `--now` overstyrer "nu" (til test). | 0 (også når enkelte kilder fejler), 1 kun ved systemfejl eller > 50 % kildefejl |
| `export [--out _site] [--now ISO]` | `export.py` | Bygger `_site/` (kopi af `site/` + `data/feed.json` + `data/status.json`). | 0 / 1 ved skemafejl |
| `pending [--max 200] [--hours 72] [--now ISO]` | `judgments.py` | Udskriver JSON (stdout) med kandidater uden vurdering (se 6.1). | 0 |
| `validate-judgments [--file PATH]` | `judgments.py` | Validerer alle (eller én) vurderingsfiler. Udskriver fejl pr. linje. | 0 ok, 1 fejl |
| `heartbeat [--now ISO]` | `judgments.py` | Skriver `data/judgments/_heartbeat.json`. | 0 |
| `overview-input --period dag\|uge\|maaned\|aar [--now ISO]` | `overview.py` | Udskriver JSON-input til Claudes overblik (se 7.2). | 0 |
| `validate-overview [--period P] [--archive] [--now ISO]` | `overview.py` | Validerer `data/overview/<P>.json` (alle perioder uden `--period`). Med `--archive` kopieres gyldige filer til arkivet. | 0 ok, 1 fejl |
| `import FILE.csv [--replace]` | `tools/import_csv.py` via CLI | Brugerens kildeliste → nye poster med `status: kandidat` (fase 4). | 0 / 1 |
| `find-feed URL` | `tools/find_feed.py` via CLI | Finder RSS/Atom/sitemap for en hjemmeside (fase 4). | 0 / 1 |

CLI'en bygges med `argparse` i `affaldsfeed/__main__.py`, som kun importerer og kalder `main(args)`-funktioner i ejer-modulerne. Logning med `logging` på dansk, formatet `%(levelname)s %(name)s: %(message)s`.

## 2. Moduler og ejerskab

```
affaldsfeed/
  __init__.py        __version__ = "0.1.0"
  __main__.py        argparse-dispatcher
  paths.py           ROOT, CONFIG_DIR, DATA_DIR, SITE_DIR, SOURCES_FILE … (Path-konstanter)
  models.py          pydantic v2-modeller (denne kontrakt i kode) — DELT
  config.py          load_sources(), load_config() -> Config, validering, check-kommando
  timeutil.py        now_utc(override), to_cph(dt), cph_day_bounds(dt), iso(dt), parse_iso(s)
  fetch.py           Fetcher: UA, robots (protego), takt pr. vært, conditional GET, retry, backoff
  collect/__init__.py   COLLECTORS = {"rss": rss.collect, "search": search.collect, …}
  collect/rss.py     collect(source, fetcher, ctx) -> list[RawEntry]
  collect/search.py  collect(source, fetcher, ctx) -> list[RawEntry]   (Google News + Bing News)
  collect/pages.py   (fase 2) sitemap + html + sideudtræk
  collect/oda.py     (fase 2) Folketingets ODA
  normalize.py       normalize_url(), item_id(), clean_text(), normalize_title(), to_candidate()
  relevance.py       prefilter(raw, source, keywords) -> Why
  classify.py        rule_topics(), rule_genre()
  stories.py         build_stories(items, sources, hints) -> list[DisplayItem]  (primærkilde, also)
  store.py           read/write candidates, rejected, state (http, sources, seen), atomisk skrivning
  health.py          opdater kildesundhed, backoff, status-farve
  pipeline.py        run-kommandoen (orkestrerer ovenstående)
  judgments.py       pending, validate-judgments, heartbeat, load_judgments(), fallback-logik
  overview.py        overview-input, validate-overview, load_overviews()
  export.py          export-kommandoen, bygger feed.json + status.json + _site/
```

Reglen er: ingen kildespecifik kode. En kilde hentes med en generisk metode styret af `sources.yaml`.

## 3. Konfiguration

### 3.1 `sources.yaml` → `Source`
En YAML-liste. Felter (se `models.Source`):

| Felt | Type | Standard | Note |
|---|---|---|---|
| id | str `^[a-z0-9][a-z0-9-]*$` | påkrævet | unikt, ændres aldrig |
| name | str | påkrævet | |
| category | CategoryId | påkrævet | 8 værdier, se 3.2 |
| homepage | str (http/https) | påkrævet | værtsnavnet bruges til at matche søgeresultater |
| method | `rss`\|`sitemap`\|`html`\|`oda`\|`search` | `rss` | v1 implementerer `rss` og `search` |
| feeds | str \| list[str] | påkrævet | normaliseres til list |
| domains | list[str] | `[]` | ekstra værtsnavne til matchning (uden `www.`) |
| match | str \| None | None | regex for artikel-URL'er (sitemap/html) |
| select | str \| None | None | CSS-selektor (html) |
| filter | `none`\|`normal`\|`strict` | `normal` | forfiltrets strenghed |
| topics | list[TopicId] | `[]` | standardtema |
| genre | GenreId | `nyhed` | standardgenre |
| lang | `da`\|`en`\|`sv` | `da` | |
| paywall | `nej`\|`delvis`\|`ja` | `nej` | |
| owner | str \| None | None | udgiver hvis ikke afsender selv |
| aliases | list[str] | `[]` | |
| every | int \| None | None → rss 1, search 2, oda 3, sitemap/html 6 | timer mellem kørsler |
| bundle | `day` \| None | None | |
| ai | bool | true | false = Claude vurderer ikke kilden; den vurderes kun af regler |
| basis | `redaktionelt`\|`offentlig`\|`forskning`\|`organisation` \| None | None | påkrævet når status=aktiv |
| status | `aktiv`\|`planlagt`\|`kandidat`\|`pause`\|`fravalgt` | `aktiv` | |
| checked | date \| None | None | påkrævet når status=aktiv |
| note | str \| None | None | |

Søgekilder (`method: search`) har `category: nyhedsmedie` (ignoreres ved visning), `feeds` = URL-skabeloner med `{q}`, og vises aldrig selv som afsender. Deres indslag krediteres udgiveren (se 5.3).

### 3.2 Faste id'er
- **CategoryId**: `nyhedsmedie`, `fagmedie`, `myndighed`, `kommunal`, `organisation`, `taenketank`, `forskning`, `eu_norden`.
- **TopicId**: `sortering`, `genbrugspladser`, `gebyrer`, `udbud`, `forbraending`, `klima`, `genanvendelse`, `producentansvar`, `bioaffald`, `tekstiler`, `byg_farligt`, `arbejdsmiljoe`, `regler`. ("Uden tema" = tom liste.)
- **GenreId**: `nyhed`, `debat`, `pressemeddelelse`, `analyse`, `hoering`, `folketing`.
- **Rang for primærkilde** (lav = først): `myndighed`=0; `kommunal`,`organisation`,`taenketank`,`forskning`,`eu_norden`=1; `fagmedie`=2; `nyhedsmedie`=3.

### 3.3 `config/`-filer
- `categories.yaml`: liste af `{id, name, short, color, color_dark, icon, help}`.
- `topics.yaml`: liste af `{id, name, definition, patterns: [..]}`. Mønstre: uden `*` = helt ord; `*` = vilkårlige bogstaver (`\w*`); ingen forskel på store/små bogstaver; mellemrum i mønster = præcis frase.
- `genres.yaml`: liste af `{id, label, url_patterns: [regex], title_prefixes: [str]}`.
- `keywords.yaml`: `{strong: {da,en,sv}, names: [..], weak: {da,en}, veto: [..], service: [..]}` (mønster-syntaks som topics).
- `search.yaml`: `{queries: [str], when: "2d"}` — forespørgsler med `OR`.
- `medier.yaml`: liste af `{id, name, category, domains: [..], basis, paywall, lang}` — troværdige udgivere, der kun findes via søgning (lokalaviser m.fl.). Id'er må ikke kollidere med `sources.yaml`.
- `settings.yaml`: se `models.Settings` (UA, takt, tærskler, vinduer, rutinetider, fallback).
- `overrides.yaml`: liste af `{match: {id|url_regex}, action: vis|skjul|tema|genre|split, value}`.
- `relevansprofil.md`: fritekst til Claude.

## 4. Mønstermotor (delt)
`relevance.py` eksporterer `compile_patterns(list[str]) -> list[re.Pattern]` og `find_hits(text, patterns) -> list[str]`. Et mønster `"affald*"` → `(?<!\w)affald\w*(?!\w)`, `"*affald*"` → `\w*affald\w*`, `"pant"` → `(?<!\w)pant(?!\w)`, alt `re.IGNORECASE | re.UNICODE`. Både `classify.py` og `relevance.py` bruger den.

## 5. Indsamling

### 5.1 `RawEntry` (internt, ikke gemt)
`{source_id, url, title, teaser, published: datetime|None, date_quality, lang, categories: list[str], publisher_name: str|None, publisher_domain: str|None, found_via: "feed"|"search"}`

### 5.2 Normalisering (`normalize.py`)
- `normalize_url(u)`: https, fjern `www.`, fragment, afsluttende `/` (ikke på rod), `utm_*`, `fbclid`, `gclid`, `ref`, `mc_cid`, `mc_eid`; sorter øvrige query-parametre.
- `item_id(url) = sha1(normalize_url(url)).hexdigest()[:12]`.
- `clean_text(s, max_len)`: fjern HTML, afkod entiteter, saml whitespace, afkort ved ord + "…".
- `normalize_title(t)`: små bogstaver, fjern tegnsætning og kildehaler (`" | Altinget"`, `" - DR"`), saml whitespace. Bruges til historier og dedupe af søgeresultater.

### 5.3 Søgning (`collect/search.py`)
- Google News: `https://news.google.com/rss/search?q={q}+when:{when}&hl=da&gl=DK&ceid=DK:da`. Udgiver fra `<source url="…">Navn</source>` (feedparser: `entry.source.href`/`entry.source.title`). Titlen har halen `" - Udgiver"`, som fjernes. Linket er en Google-redirect; prøv base64-afkodning af `/articles/<id>`; ellers beholdes linket.
- Bing News: `https://www.bing.com/news/search?q={q}&format=rss&setlang=da&cc=DK`. URL fra `url`-parameteren i `apiclick.aspx`. Udgiver fra `News:Source`.
- Udgiver → afsender: værtsnavn (uden `www.`) matches mod `homepage`-vært og `domains` i `sources.yaml` (status aktiv) og derefter `medier.yaml`. Match → `RawEntry.source_id = <id>`. Intet match → skrives til `data/state/kildeforslag.json` (`{domain: {name, count, last_seen, examples: [url ≤3]}}`), ikke kandidat. `data/state/kildeforslag.md` genereres fra JSON'en (top 50 efter count).
- Søgeresultater, hvis normaliserede titel + udgiver allerede findes blandt kandidater fra de sidste 7 dage, springes over.

### 5.4 Forfilter (`relevance.py: prefilter`) → `Why`
Score: 4 pr. stærkt ord/navn i titel; 2 pr. forskelligt stærkt ord i teaser (max 6); 1 pr. svagt ord (max 2, kun sammen med et andet hit). Veto i titel → `afvist`. Service (kun kategori `kommunal`) → `afvist`.

| filter | kandidat (`vis`) | kandidat (`graa`) | `afvist` |
|---|---|---|---|
| none | alt uden veto | – | veto/service |
| normal | score ≥ 4 | 1–3 | 0 |
| strict | score ≥ 4 og stærkt ord/navn i titel | score ≥ 2 uden titelhit | resten |

`vis` og `graa` gemmes som kandidater (Claude vurderer begge). `afvist` gemmes i `data/rejected/`. `Why = {filter, score, decision: "vis"|"graa"|"afvist", hits: ["titel: affaldsgebyr", …], reason: str|None}`.

### 5.5 Datoregler
published: feedets published → updated → (sideudtræk, fase 2) → ellers `first_seen` med `date_quality="fundet"`. Dato > 2 t i fremtiden → `first_seen`, `date_quality="fundet"`. Indslag ældre end 14 dage ved fund → afvist med reason `"for gammel"`. Første kørsel for en kilde (ingen state): indslag fra sidste 14 dage gemmes med `baseline: true`; udaterede springes over.

## 6. Data på disk

```
data/
  candidates/ÅÅÅÅ-MM.jsonl     Candidate pr. linje, måned = first_seen (UTC), sorteret efter id. Skrives KUN af run.
  rejected/ÅÅÅÅ-MM.jsonl       Rejected pr. linje (90 dage), sorteret efter id. Skrives KUN af run.
  judgments/ÅÅÅÅ-MM-DD.jsonl   Judgment pr. linje (dato = judged_at i København), rækkefølge som skrevet. Skrives KUN af Claude-routinen.
  judgments/_heartbeat.json    {"last_run": ISO, "pending_before": int, "judged": int}
  judgments/kildeforslag-sweep.md   ukendte udgivere fundet ved sweep (Claude)
  overview/{dag,uge,maaned,aar}.json   aktuelt Overview pr. periode. Skrives KUN af Claude-routinen.
  overview/archive/<periode>-ÅÅÅÅ-MM-DD.json   arkiv (validate-overview --archive)
  state/http.json              {url: {etag, last_modified}}
  state/sources.json           {source_id: SourceState}
  state/robots.json            {host: {fetched: ISO, body: str}}  (24 t cache)
  state/kildeforslag.json      se 5.3
  state/kildeforslag.md        genereret
```
Skrivning er atomisk (skriv `.tmp`, `os.replace`). Filer ændres kun, når indholdet faktisk ændres (så git ikke får tomme commits). `SourceState.last_ok` gemmes kun som dato.

### 6.1 `Candidate` (models.Candidate)
`{id, url, title, teaser, source, published, date_quality: "kilde"|"url"|"liste"|"fundet", first_seen, lang, genre, topics: [≤2], why: Why, baseline: bool, found_via: "feed"|"search", categories: [str]}`
- `title` ≤ 300 tegn, `teaser` ≤ 300 tegn (renset).
- Samme `id` gemmes aldrig to gange. Ved genfund med ny titel opdateres `title`, men `published`/`first_seen` bevares.

### 6.2 `Judgment` (models.Judgment) — én linje i `data/judgments/*.jsonl`
```json
{"id":"3f9a1c0b7e21","relevant":true,"reason":"Nye regler for affaldsgebyrer i kommunerne","topics":["gebyrer","regler"],"genre":"nyhed","summary_da":null,"story_hint":null,"judged_at":"2026-10-07T07:25:41Z","by":"claude-routine","new_item":null}
```
- `reason` ≤ 200 tegn. `topics` ≤ 2 fra TopicId. `genre` fra GenreId. `summary_da` ≤ 160 tegn, kun når kandidatens `lang` ≠ `da` (ellers null). `story_hint` = id på et andet indslag om samme historie eller null.
- **Sweep-fund** har `new_item = {url, title, teaser, source, published}` hvor `source` er et kendt id (sources.yaml aktiv eller medier.yaml); `id` = `item_id(url)`; `relevant` skal være true.
- Den seneste vurdering af et id vinder (filer læses i datoorden, linjer i rækkefølge).
- `pending` udskriver: `{"now": ISO, "profile": "<relevansprofil.md>", "topics": [{id,name,definition}], "genres": [{id,label}], "pending": [{id,url,title,teaser,source_name,category,lang,published,rule_topics,rule_genre,prefilter:{decision,score,hits}}], "recent_approved": [{id,title,source_name,published}]}`. `pending` = kandidater uden vurdering, `first_seen` inden for `--hours`, ikke fra kilder med `ai: false`, nyeste først, maks `--max`. `recent_approved` = godkendte fra sidste 72 t (til `story_hint`).

### 6.3 Fallback (judgments.py: `display_mode(now, heartbeat, settings) -> "claude"|"fallback"`)
Rutinen kører kl. `settings.routine.minute` i timerne `settings.routine.hours` (København). Seneste planlagte kørsel `S` = seneste tidspunkt ≤ now på formen HH:MM i vinduet. Tilstand er `fallback`, når heartbeat mangler, eller `last_run < S - settings.routine.grace_hours` (standard 2). Ellers `claude`.
- `claude`: vis kandidater med `relevant: true`-vurdering; skjul `relevant: false`; uvurderede vises ikke (venter).
- `fallback`: som `claude`, men uvurderede kandidater med `why.decision == "vis"` vises også med `reviewed: false`.
- Kilder med `ai: false` vurderes altid af regler: vises når `why.decision == "vis"`, `reviewed: false`.

## 7. Overblik

### 7.1 `Overview` (models.Overview) — `data/overview/<periode>.json`
```json
{"period":"dag","window":{"start":"2026-10-06T22:00:00Z","end":"2026-10-07T07:25:00Z"},"generated":"2026-10-07T07:26:10Z","since":null,"headline":"Kort sagt: …","bullets":[{"text":"…","item_ids":["3f9a1c0b7e21"],"topics":["gebyrer"]}],"based_on":23}
```
- `headline` ≤ 25 ord. Hvert `bullets[].text` ≤ 30 ord. `item_ids` ≥ 1, alle skal være godkendte (relevant) indslag med `published`/`first_seen` inden for vinduet (for `maaned`/`aar`: inden for vinduet). `topics` ≤ 2.
- Antal punkter: `dag` 1–5 (min 3 hvis `based_on` ≥ 6), `uge` 3–5, `maaned` 5–8, `aar` 5–8 (minimum sænkes til `max(1, based_on//3)` når data er tynde).
- `since` = første dato med data, hvis vinduet går længere tilbage end data.
- Vinduer (København): `dag` = kalenderdag til nu; `uge` = 7×24 t; `maaned` = 30×24 t; `aar` = 365×24 t.

### 7.2 `overview-input` udskriver
`{"period","now","window":{start,end},"since","rules":{"headline_max_words":25,"bullet_max_words":30,"bullets_min","bullets_max"},"items":[{id,title,teaser_or_summary,source_name,category,genre,topics,published,story_size}],"lower_overviews":[Overview…],"allowed_item_ids":[…]}`
- `dag`: alle godkendte indslag i vinduet (maks 150).
- `uge`: godkendte i vinduet grupperet i historier, sorteret efter story_size og rang (maks 120 historier; kun hovedindslag + story_size).
- `maaned`: `lower_overviews` = arkiverede `uge`-overblik fra vinduet (højst ét pr. dag, nyeste pr. dag) + top 40 historier efter story_size.
- `aar`: `lower_overviews` = arkiverede `maaned`-overblik (nyeste pr. kalendermåned) + top 40 historier.

## 8. `feed.json` (export → `_site/data/feed.json`)
```json
{
  "version": 1,
  "generated": "ISO",
  "window_days": 60,
  "mode": "claude|fallback",
  "last_judgment": "ISO|null",
  "categories": [{"id","name","short","color","color_dark","icon","help"}],
  "topics": [{"id","name","definition"}],
  "genres": [{"id","label"}],
  "sources": [{"id","name","category","homepage","lang","paywall","owner","status","health","via_search": false}],
  "overview": {"dag": Overview|null, "uge": …, "maaned": …, "aar": …},
  "items": [DisplayItem]
}
```
`DisplayItem`:
`{id, story, url, title, teaser, source, published, date_quality, first_seen, baseline, topics, genre, lang, summary_da, reviewed, reason, also: [{id, source, url, title, published}], why}`
- `items` sorteret efter `published` (faldende), derefter `id`. Kun hovedindslag for historier står i `items`; øvrige ligger i `also` (sorteret efter published).
- `sources` indeholder alle aktive kilder fra `sources.yaml` (undtagen `method: search`) + `medier.yaml`-udgivere, der optræder i items (`via_search: true`).
- `health`: `groen`|`gul`|`roed`|`graa`.
- `status.json`: `{generated, sources: [{id, name, category, status, health, last_ok, fails, last_error, items_30d, silent}], counts: {candidates_60d, shown_60d, rejected_30d}}`.

Historier (`stories.py`): niveau 1 = samme id; niveau 2 = samme `normalize_title` inden for ±3 døgn; niveau 3 (fase 3) = rapidfuzz. Desuden forenes `story_hint`-par fra vurderinger. Hovedindslag = laveste kategori-rang, ved lighed tidligst publiceret. `story` = hovedindslagets id. En historie optager ikke indslag mere end 7 døgn efter hovedindslaget.

## 9. Frontend-kontrakt
- `site/` er statisk (ingen build). `index.html` og `kilder.html` henter `data/feed.json` (relativt). Med `?demo=1` hentes `../examples/feed.sample.json` lokalt eller `data/feed.sample.json` på Pages (export kopierer eksempelfilen dertil).
- URL-parametre: `afsender`, `tema`, `kilde`, `genre` (kommaseparerede id'er), `periode` (7|30|60), `sprog=da`, `q`, `nye=1`, `saml=0`, `vis=kompakt`, `story=<id>`, `overblik=dag|uge|maaned|aar`.
- localStorage-nøgler (alle i try/catch): `af.lastVisit`, `af.theme`, `af.overviewHidden`, `af.introClosed`.

## 10. Workflows
- `collect.yml`: cron `5 * * * *` + `workflow_dispatch`. `run` → `export` → commit `data/` hvis ændret (`git pull --rebase` før push) → deploy Pages. `concurrency: pages`.
- `publish.yml`: `push` til `main` på `data/judgments/**`, `data/overview/**`, `site/**`, `config/**`, `sources.yaml`, `examples/**` + `workflow_dispatch` → `export` → deploy Pages. `concurrency: pages`.
- `ci.yml`: push/PR → `ruff check`, `pytest`, `python -m affaldsfeed check`. Ingen netværkskald i tests.
