# Kontrakter (teknisk spec for udviklere)

Denne fil er den bindende tekniske kontrakt mellem modulerne. Ændres en kontrakt, opdateres denne fil i samme commit.

Alle tider gemmes som ISO 8601 i UTC med `Z` (fx `2026-10-07T07:14:00Z`). Visning sker i `Europe/Copenhagen`.
Alle JSON/JSONL-filer skrives UTF-8, `ensure_ascii=False`, nøgler i fast rækkefølge (pydantic-feltrækkefølge), én post pr. linje i JSONL, sorteret deterministisk (se den enkelte fil), afsluttet med linjeskift.

## 1. Pakke og CLI

Pakken hedder `affaldsfeed`. Alt køres fra repoets rod med `python -m affaldsfeed <kommando>`. Repo-roden findes som forælder til pakkemappen (`affaldsfeed/paths.py: ROOT`), så kommandoer virker uanset cwd.

| Kommando | Ejer-modul | Hvad den gør | Exit-kode |
|---|---|---|---|
| `check [--fetch ID] [--explain]` | `config.py` (+ `collect`) | Validerer `sources.yaml` og `config/*.yaml`. Med `--fetch ID` hentes én kilde live som ved dens første kørsel (tom seen-state), og det udskrives, hvad forfiltret beholder og hvorfor (ingen skrivning til `data/`). `--explain` viser også indsamlerens diagnose (sitemap/html, se 5.6). | 0 ok, 1 fejl |
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
  fetch.py           Fetcher: UA, robots (protego), takt pr. vært, conditional GET, retry, backoff, loft over svarstørrelse
  collect/__init__.py   COLLECTORS = {"rss": rss.collect, "search": search.collect, …}
  collect/rss.py     collect(source, fetcher, ctx) -> list[RawEntry]
  collect/search.py  collect(source, fetcher, ctx) -> list[RawEntry]   (Google News + Bing News)
  collect/pages.py   collect_sitemap / collect_html (-> CollectResult) + extract_page (sideudtræk), se 5.6
  collect/oda.py     (fase 2) Folketingets ODA
  normalize.py       normalize_url(), item_id(), clean_text(), normalize_title(), to_candidate()
  relevance.py       prefilter(raw, source, keywords) -> Why
  classify.py        rule_topics(), rule_genre()
  places.py          compile_places(geo, settings) -> PlaceMatcher, match_places(), rule_places()  (se 4.1)
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
| method | `rss`\|`sitemap`\|`html`\|`oda`\|`search` | `rss` | `rss`, `search`, `sitemap` og `html` er implementeret; `oda` følger |
| feeds | str \| list[str] | påkrævet | normaliseres til list; sitemap: sitemap- eller indeks-URL'er; html: listesider |
| domains | list[str] | `[]` | ekstra værtsnavne til matchning (uden `www.`) |
| match | str \| None | None | regex for artikel-URL'er (sitemap/html; `re.search` på hele URL'en); påkrævet når aktiv |
| select | str \| None | None | CSS-selektor for links (html; standard `a[href]`); valideres af modellen |
| filter | `none`\|`normal`\|`strict` | `normal` | forfiltrets strenghed |
| topics | list[TopicId] | `[]` | standardtema |
| genre | GenreId | `nyhed` | standardgenre |
| places | list[str] | `[]` | faste steder (sted-id'er, se 4.1), højst 8. Kun til afsendere med fast geografi, fx et kommunalt affaldsselskab. Nyhedsmedier, også lokalaviser, får ingen `places` (check advarer) |
| lang | `da`\|`en`\|`sv` | `da` | |
| paywall | `nej`\|`delvis`\|`ja` | `nej` | |
| owner | str \| None | None | udgiver hvis ikke afsender selv |
| aliases | list[str] | `[]` | |
| replaces | list[str] | `[]` | tidligere id'er (fx en udgiver fra `medier.yaml`, der er blevet til en kilde), hvis gemte indslag nu vises under denne kilde. Id'erne må ikke findes i `sources.yaml` eller `medier.yaml` (`check` fejler). |
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
- `topics.yaml`: liste af `{id, name, short?, definition, patterns: [..]}`. Mønstre: uden `*` = helt ord; `*` = vilkårlige bogstaver (`\w*`); ingen forskel på store/små bogstaver; mellemrum i mønster = præcis frase. `short` er valgfrit: et kort navn til brugerfladen, når `name` er for langt. Navnet i brugerfladen (`short`, ellers `name`) har højst 26 tegn; `check` advarer (fejler ikke) ved flere.
- `genres.yaml`: liste af `{id, label, url_patterns: [regex], title_prefixes: [str]}`.
- `keywords.yaml`: `{strong: {da,en,sv}, names: [..], weak: {da,en}, veto: [..], service: [..]}` (mønster-syntaks som topics).
- `search.yaml`: `{queries: [str], when: "2d"}` — forespørgsler med `OR`.
- `medier.yaml`: liste af `{id, name, category, domains: [..], basis, paywall, lang, places?}` — troværdige udgivere, der kun findes via søgning (lokalaviser m.fl.). Id'er må ikke kollidere med `sources.yaml`. `places` som i 3.1 (lokalaviser får ingen).
- `settings.yaml`: se `models.Settings` (UA, takt, tærskler, vinduer, rutinetider, fallback). Blokken `pages` (`models.PagesSettings`) har grænserne for sitemap og html (5.6) og for `state/seen.json` (6). `places.institution_words` (valgfri, standard `["Universitet", "Lufthavn"]`) bruges af stedmærkningen (4.1).
- `geografi.yaml`: genereres af `tools/build_geografi.py` fra Danmarks Statistik og rettes aldrig i hånden. `{kilde, regioner: [{id, kode, navn, kort}], landsdele: {navn: region-id}, kommuner: [{id, kode, navn, kort, region, navne, kun_med_kommune}], byer: [{id, navn, navne, kommune, kommuner, indbyggere}]}` → `models.Geo`. `navn` er det officielle navn ("Region Syddanmark", "Nyborg Kommune", "Københavns Kommune", "Bornholms Regionskommune"), `kort` det korte. `byer.kommune` er byens primære kommune, `byer.kommuner` alle kommuner, byen ligger i. Mangler filen, er geografien tom: ingen stedmærkning og en advarsel i `check`. `check` fejler ved dublet-id'er, når `kommune.region`, `by.kommune` eller `by.kommuner` ikke findes, når `by.kommune` ikke står i `by.kommuner`, og når en landsdel peger på en ukendt region. Sted-id'er i `sources.yaml` og `medier.yaml` skal findes i geografien.
- `geografi_regler.yaml`: håndregler til `tools/build_geografi.py` (officielle navne, ekstra navne, `kun_med_kommune`, byer der ikke må matche, landsdele). Ret her og kør workflowet "Byg geografi".
- `overrides.yaml`: liste af `{match: {id|url_regex}, action: vis|skjul|tema|genre|split, value}`.
- `relevansprofil.md`: fritekst til Claude.

## 4. Mønstermotor (delt)
`relevance.py` eksporterer `compile_patterns(list[str], proper_nouns=False) -> list[re.Pattern]` og `find_hits(text, patterns) -> list[str]`. Med `proper_nouns=True` (bruges til `keywords.names` i forfiltret) skal første bogstav stå med stort, mens resten matcher uanset store/små bogstaver: "Argo" og "ARGO" giver træf på `ARGO`, men "kredsløb" giver ikke træf på `Kredsløb`. Et mønster `"affald*"` → `(?<!\w)affald\w*(?!\w)`, `"*affald*"` → `\w*affald\w*`, `"pant"` → `(?<!\w)pant(?!\w)`, alt `re.IGNORECASE | re.UNICODE`. Både `classify.py` og `relevance.py` bruger den.

### 4.1 Stedmærkning (`places.py`)
- **Sted-id'er:** `r:<region>`, `k:<kommune>`, `b:<by>` med id'er fra `geografi.yaml` (fx `r:syddanmark`, `k:nyborg`, `b:ullerslev`). Et `places`-felt er en liste uden dubletter, sorteret: regioner, kommuner, byer, hver alfabetisk efter id (`models.sort_places`). Højst 8; er der flere, skæres der efter sorteringen. Formatet tjekkes af modellerne.
- `compile_places(geo, settings.places) -> PlaceMatcher` og `match_places(text, matcher) -> list[str]`. `rule_places(title, teaser, lang, fixed, matcher)` giver regelmærkerne: afsenderens faste `places` plus steder nævnt i titel og teaser (matchet hver for sig). Tekster matches kun, når `lang == "da"`.
- **Matchning:** store og små bogstaver tæller (egennavne). Ordgrænse: intet bogstav eller ciffer lige før eller efter; bindestreg er en grænse ("Aarhus-firma" giver Aarhus). Længste navn vinder ("Ikast-Brande" før "Ikast", "Nykøbing Falster" før landsdelen "Falster"). Ejefald: navn + "s", når navnet ikke ender på s ("Nyborgs", "Københavns").
  - Kommuner: hvert navn i `navne` → `k:<id>`; desuden "<navn> Kommune(s)" (også med lille k) og det officielle navn ("Københavns Kommune", "Bornholms Regionskommune"). Har kommunen `kun_med_kommune: true` (Vejen), matches den kun med "Kommune"-endelsen.
  - Byer: hvert navn i `navne` → `b:<id>`. Har byen samme navn som en kommune (Nyborg), giver et træf både `k:` og `b:`; "<navn> Kommune" giver kun `k:`.
  - Regioner: "Region <kort>" og "Region <kort>s" (også "region") → `r:<id>`. Landsdele ("Fyn", "Sønderjylland") → `r:<region>`.
  - Ingen implicitte forældre: kun det nævnte gemmes. Hierarkiet (`Geo.expand`: by → kommuner → regioner) bruges ved filtrering (§9).
  - Konservativt, hellere et sted for lidt end et forkert: står et ord fra `settings.places.institution_words` (eller et ord, der begynder med det) lige efter navnet, tæller navnet ikke ("Aarhus Universitet", "Københavns Lufthavn"). Et rent bynavn lige efter et ord på mindst to bogstaver med stort begyndelsesbogstav tæller ikke, fordi det er et efternavn ("Lars Aagaard", byen Ågård; "I Ullerslev" tæller); navne, der også er en kommune, en region eller en landsdel, tæller stadig.

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
- Bing News: `https://www.bing.com/news/search?q={q}&format=rss&setlang=da-DK&cc=DK&qft=sortbydate%3d%221%22` (uden `sortbydate` og med `setlang=da` giver Bing 0 resultater for OR-forespørgsler). URL fra `url`-parameteren i `apiclick.aspx`. Udgiver fra `News:Source`.
- Udgiver → afsender: værtsnavn (uden `www.`) matches mod `homepage`-vært og `domains` i `sources.yaml` (status aktiv) og derefter `medier.yaml`. Match → `RawEntry.source_id = <id>`. Intet match → skrives til `data/state/kildeforslag.json` (`{domain: {name, count, last_seen, examples: [url ≤3]}}`), ikke kandidat. `data/state/kildeforslag.md` genereres fra JSON'en (top 50 efter count).
- Søgeresultater, hvis normaliserede titel + udgiver allerede findes blandt kandidater fra de sidste 7 dage, springes over. Det samme gælder feedindslag med en normaliseret titel på mindst 4 ord (samme artikel i flere sektionsfeeds med hver sin URL).

### 5.4 Forfilter (`relevance.py: prefilter`) → `Why`
Score: 4 pr. stærkt ord/navn i titel; 2 pr. forskelligt stærkt ord i teaser (max 6); 1 pr. svagt ord (max 2, kun sammen med et andet hit, eller når et svagt ord står i titlen — så giver et svagt titelord alene `graa` ved `normal`). Veto i titel → `afvist`. Service (kun kategori `kommunal`) → `afvist`.

| filter | kandidat (`vis`) | kandidat (`graa`) | `afvist` |
|---|---|---|---|
| none | alt uden veto | – | veto/service |
| normal | score ≥ 4 | 1–3 | 0 |
| strict | score ≥ 4 og stærkt ord/navn i titel | score ≥ 2 uden titelhit | resten |

`vis` og `graa` gemmes som kandidater (Claude vurderer begge). `afvist` gemmes i `data/rejected/`. `Why = {filter, score, decision: "vis"|"graa"|"afvist", hits: ["titel: affaldsgebyr", …], reason: str|None}`.

### 5.5 Datoregler
published: feedets published → updated (rss/search); for sitemap og html sidens egen dato efter sideudtrækket i 5.6, ellers listens dato ved linket (html) → ellers `first_seen` med `date_quality="fundet"`. Sitemappets `lastmod` er aldrig en dato. Dato > 2 t i fremtiden → `first_seen`, `date_quality="fundet"`. Indslag ældre end 14 dage ved fund → afvist med reason `"for gammel"`. Første kørsel for en kilde (ingen vellykket kørsel endnu: ingen state eller `first_run_done: false`; `CollectContext.first_run`): indslag fra de sidste `settings.baseline_days` dage (60, samme som `window_days`, så feedet er fyldt fra start) gemmes med `baseline: true`; udaterede springes over. For sitemap og html varer første kørsel, indtil kilden har en komplet baseline (5.6).

`date_quality`: `kilde` = dato med klokkeslæt fra kilden (feed, artikelside eller Google News-sitemap); `url` = dato fra URL'en; `liste` = dato uden klokkeslæt fra kildens egne sider (listen ved linket, artiklens metadata eller tekst), så den vises som dato uden "kl. 00.00"; `fundet` = tidspunktet for fundet. Alle tider gemmes i UTC. For sitemap og html er en tid uden tidszone dansk tid, og en dato uden tid er starten af dagen i København.

Datoformater for sitemap og html (`collect/pages.py: parse_date`). Kun eksplicitte formater læses, og der gættes aldrig på dag-først:
- ISO 8601 og varianter med år først, altid som år-måned-dag: `2026-10-07`, `2026/10/07`, `20261007`, evt. med tid (`T` eller mellemrum) og tidszone (`Z`, `+0200`, `+02:00`, også efter et mellemrum, `UTC`, `GMT`, `GMT+2`, `CET`, `CEST` o.l.).
- RFC 822 (`Wed, 07 Oct 2026 10:00:00 GMT`), uanset kildens sprog.
- Danske datoer: `7. oktober 2026`, `7. okt. 2026`, `07.10.2026` (dag først), evt. efterfulgt af `kl. 14.32`.
- Engelske månedsnavne (`October 7, 2026`, `7 October 2026`) kun for kilder med `lang: en`.
- En ukendt eller ugyldig tidszone (fx `+24:00`) eller dato giver ingen dato og aldrig en undtagelse; så prøves næste kilde til en dato.

### 5.6 Sitemap, html og sideudtræk (`collect/pages.py`)
Kilder uden RSS. Tallene er standardværdierne i `settings.yaml: pages` (`models.PagesSettings`).

**sitemap** (`feeds` = sitemap- eller indeks-URL'er)
- gzip genkendes på de magiske bytes `1f 8b` (eller `.gz`) og pakkes ud med loft på `fetch.max_response_mb` (50 MB). XML parses med lxml uden DTD, entitetsopløsning og netværk (XXE og "billion laughs" virker ikke; et dokument, libxml2 stopper pga. entiteter, afvises). Elementer findes på local-name, så navnerummets præfiks er ligegyldigt; CDATA og whitespace i `<loc>` håndteres, et `&`, der ikke indleder en entitet (`?id=1&lang=da`), bevares, og relative URL'er gøres absolutte.
- Indeks: de 5 under-sitemaps med nyeste `lastmod` følges (uden lastmod, eller ved samme lastmod: de sidste i dokumentet, det sidste først), dybde først. Kun under-sitemaps på kildens egne værter (homepage eller `domains`) følges. Højst ét indlejret indeks mere og højst 6 sitemap-hentninger pr. kilde pr. kørsel; samme sitemap hentes højst én gang pr. kørsel.
- urlset: en URL er ny, når den ligger på kildens vært (homepage eller `domains`, også underdomæner), matcher `match` (`re.search`; uden `match` alle), har `lastmod` fra starten af dagen (København) for 3 dage siden (14 ved kildens første kørsel; har kilden været nede, fra dagen før dens sidste vellykkede kørsel, `CollectContext.last_ok`, dog højst 14 dage) og ikke står i seen-state. Uden `lastmod`: ved første kørsel registreres URL'en i seen som baseline uden at blive hentet; senere er den ny, hvis den ikke står i seen. Samme URL i flere sitemaps tælles én gang (`item_id`).
- Google News-sitemap (`news:news` med `news:title` og `news:publication_date`): titel og dato bruges direkte (`kilde`; uden klokkeslæt `liste`), teaser er tom, og artikelsiden hentes ikke. Posterne behandles som RSS-indslag og markeres ikke i seen. Et tomt Google News-sitemap (navnerummet er erklæret) er ikke en fejl: det viser kun de seneste 48 timer.

**html** (`feeds` = listesider)
- Kun første listeside hentes (ingen paginering). Links findes med `select` (CSS via lxml.cssselect, standard `a[href]`; er det valgte element ikke et link, bruges første `a[href]` indeni eller nærmeste udenom), gøres absolutte med `urljoin` (`<base href>` respekteres), fragmentet fjernes, og kun links på kildens vært/domains, der matcher `match`, beholdes. Kildens egne listesider (`feeds`) er aldrig artikler. Dubletter fjernes; højst 30 pr. listeside i dokumentets rækkefølge. Linkteksten er den længste blandt de links til samme URL (et billedlink giver højst sin alt-tekst).
- Står der en dato ved linket (`<time datetime>` eller dansk dato i linkets nærmeste container, højst 5 niveauer op og aldrig i en container med andre artikellinks), bruges den som reservedato med `date_quality: "liste"`, hvis siden selv ingen dato har.

**Fælles**
- Kun URL'er, der ikke står i seen, hentes: højst 15 sider pr. kilde pr. kørsel, for sitemap nyeste `lastmod` først (uden lastmod sidst), for html i listens rækkefølge. Resten tages ved næste kørsel og markeres ikke; er der en restkø (loft, tidsbudget, forbigående sidefejl), glemmes sitemappernes/listens ETag, så en 304 ikke skjuler den.
- Første kørsel varer, indtil kilden har en komplet baseline. Ender en første kørsel med en restkø, eller kunne et sitemap eller en liste ikke læses pga. en forbigående fejl eller tidsbudgettet (`CollectResult.backlog`), sætter `run` ikke `first_run_done`. Næste kørsel er så også en første kørsel: 14-dages-vinduet gælder, så restkøen faktisk hentes, URL'er uden lastmod registreres som baseline, og indslagene gemmes med `baseline: true` (5.5). En varig fejl (fx 404 på et under-sitemap) holder ikke kilden i første kørsel.
- `filter: strict`: slug'en (stien med `-` og `_` som mellemrum, procentkodning afkodet) eller linkteksten (html) skal indeholde et stærkt ord eller navn fra `keywords.yaml`, også med æøå skrevet som ae/oe/aa. Ellers hentes siden ikke.
- Al hentning går gennem `Fetcher.get` (UA, robots.txt, takt, ETag, tidsbudget). Sitemaps og lister hentes med conditional GET efter første kørsel, også under-sitemaps fra et indeks: deres ETags gemmes i `state/http.json`, og indeksets post husker de fulgte under-sitemaps (`sitemaps`, se 6). Artikelsider hentes altid ubetinget. Sider, robots.txt forbyder, springes over (uden at tælle med i loftet); når tidsbudgettet er brugt, stoppes der, og resten venter.
- 304: et uændret urlset eller en uændret liste læses ikke. Et indeks, der svarer 304, betyder ikke "intet nyt": de under-sitemaps, det pegede på sidst, hentes stadig med deres egne betingede forespørgsler. Først når indekset og de valgte under-sitemaps svarer 304, er der intet nyt.
- Størrelse: `Fetcher` læser svaret i bidder og afbryder over `fetch.max_response_mb` (50 MB; artikelsider `pages.max_page_mb`, 5 MB), også når Content-Length er for stor, og efter udpakning af gzip/deflate, så gzip-bomber og enorme svar aldrig ligger i hukommelsen. robots.txt læses kun til 500 kB.
- Seen-state (6): en URL markeres, når siden er hentet og udtrukket (også hvis den ikke er HTML, mangler titel, ikke kunne udtrækkes eller afvises af forfiltret bagefter), når hentningen fejlede varigt (4xx undtagen 408, 425 og 429, robots.txt-forbud eller svar over loftet), eller når den er registreret som baseline. Forbigående fejl (5xx, timeout, 429, netværk) markeres ikke og prøves igen ved næste kørsel. URL'er, der står i sitemappet eller på listen og allerede er i seen, tæller som observeret; et 304-svar på et urlset eller en liste tæller som observation af alle kildens kendte URL'er.
- Fejl (`CollectResult.error`, giver gul/rød sundhed): indeks eller listeside kunne ikke hentes eller er ikke et sitemap/HTML; ingen under-sitemaps kunne hentes; et indeks gav ingen brugbare under-sitemaps (tomt, alle på fremmede værter, for dybt indlejret); et almindeligt sitemap er tomt ("tomt sitemap"); 0 URL'er/links matcher `match`/`select` (mønster eller selektor er sandsynligvis forældet); eller alle forsøgte sidehentninger fejlede (også når robots.txt blokerede dem alle). Var nogle sitemaps eller lister uændrede (304), er 0 matchende eller et tomt sitemap blandt de læste ikke en fejl, for de uændrede kan rumme URL'erne. En kilde uden nye artikler er ikke en fejl. Delvise fejl logges som advarsel. Ved en fejl i et dokuments indhold glemmes dets ETag (ved en kildefejl alle sitemaps' og listers), så det hentes helt ved næste kørsel, og fejlen bliver stående i sundheden, til den er rettet.
- Diagnose (`CollectResult.diagnostics`, internt; udskrives af `check --fetch ID --explain` og logges på debug-niveau af `python -m affaldsfeed -v run`): valgte under-sitemaps med lastmod; antal URL'er i alt, matchende, med lastmod i vinduet, uden lastmod (og registreret som baseline), fra Google News, nye og sprunget over pga. strict; sider hentet, ok, fejlede, med varig fejl, blokeret, ikke HTML og uden titel; op til 10 jævnt fordelte eksempler på URL'er, der matcher, og på URL'er, der ikke matcher; for html antal links på siden, valgt af `select` og matchende samt op til 20 eksempler (href | linktekst) af alle links og af de matchende; og om baseline er komplet ved første kørsel. Formålet er at sætte `match` og `select` for nye kilder ud fra en probe fra GitHub Actions.

**Sideudtræk** (`extract_page(content, url, content_type, *, now, names, lang) -> Page(title, published, date_quality, teaser) | None`, ren funktion, der aldrig rejser en undtagelse for sidens indhold; `lang` er kildens sprog, se datoformater i 5.5)
- Kun HTML: content-type med `html` eller ingen content-type. PDF og andet giver `None`. Tegnsættet findes som BOM → Content-Type → `<meta charset>` → utf-8, hvis bytes er gyldig utf-8 → windows-1252. Et erklæret tegnsæt bruges med `errors="replace"`, også når enkelte bytes er ugyldige; windows-1252 er kun sidste udvej, når intet er erklæret, og bytes ikke er gyldig utf-8. Kun tekst-tegnsæt accepteres (ikke base64, hex, rot13, zip, idna o.l.). Som i browsere læses latin-1/ascii som windows-1252 og utf-16/32 uden BOM som utf-8. Erklærer siden latin-1/windows-1252, men er den gyldig utf-8 med æøå, læses den som utf-8.
- Hovedindholdet er det `<article>` eller `<main>`, der rummer sidens `<h1>`, ellers første `<article>` uden for aside/nav/footer, ellers `<main>`/`[role=main]`. Står `<h1>` direkte i `<main>`, og rummer main præcis ét `<article>` uden egne overskrifter, er det artiklens brødtekst og ikke en anden artikel.
- Titel: `og:title` → første `<h1>` (helst i hovedindholdet) → `<title>`. En kildehale (" | Navn", " - Navn", " – Navn") fjernes, når den er kort og ligner et navn, eller når den er kildens navn, alias eller vært (`names`). En kandidat, der kun er kildens navn, springes over.
- Dato, første brugbare: JSON-LD `datePublished` (også i `@graph`, lister og indlejrede objekter; artikeltyper før fx WebPage) → meta `article:published_time` (også `itemprop="datePublished"`) → `<time datetime>` (hovedindholdets egne først; aldrig i aside/nav/footer eller i andre artikler, fx relaterede) → meta `publication-date`/`date`/`DC.date` (og `pubdate`, `dcterms.date` m.fl.) → dato i URL'en (`/2026/10/07/` eller `2026-10-07`; `url`) → dato i de første 1.500 tegn af hovedindholdets tekst ("7. oktober 2026", "7. okt. 2026", "07.10.2026", evt. efterfulgt af "kl. 14.32"; engelske månedsnavne for `lang: en`): en dato efter "Publiceret", "Udgivet", "Dato" o.l. vinder, ellers den seneste (tidligere datoer i teksten er typisk henvisninger). Datoer mere end 2 t i fremtiden og før år 2000 ignoreres, og så prøves den næste dato eller kilde til en dato. Samme regel gælder datoen ved et link på en liste.
- Teaser: `og:description` → meta `description`, rå (renses senere af `clean_text`).

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
  state/http.json              {url: {etag, last_modified, sitemaps?}}  sitemaps: de under-sitemaps, et indeks pegede på sidst (5.6)
  state/sources.json           {source_id: SourceState}
  state/robots.json            {host: {fetched: ISO, body: str}}  (24 t cache)
  state/kildeforslag.json      se 5.3
  state/kildeforslag.md        genereret
  state/seen.json              {source_id: {item_id(url): "ÅÅÅÅ-MM-DD"}}  sitemap/html: kendte artikel-URL'er (5.6)
```
Skrivning er atomisk (skriv `.tmp`, `os.replace`). Filer ændres kun, når indholdet faktisk ændres (så git ikke får tomme commits). `SourceState.last_ok` gemmes kun som dato.

`state/seen.json` (`store.load_seen`/`save_seen`): datoen er dagen (København), hvor URL'en sidst blev observeret i kildens sitemap eller på dens liste. Den fornyes kun, når den er ældre end `pages.seen_refresh_days` (30), så filen ikke ændres hver time. Poster, der ikke er observeret i `pages.seen_keep_days` (120), og kilder, der ikke længere står i `sources.yaml`, fjernes ved skrivning. Sider med en varig fejl står der også, så de ikke prøves ved hver kørsel (5.6). Nøglerne er sorteret, og filen oprettes først, når der er noget i den. `run` læser og skriver den; `run --dry-run` og `check --fetch` skriver den ikke. Fejler en kilde med en undtagelse, rulles dens poster fra kørslen tilbage.

### 6.1 `Candidate` (models.Candidate)
`{id, url, title, teaser, source, published, date_quality: "kilde"|"url"|"liste"|"fundet", first_seen, lang, genre, topics: [≤2], places: [≤8], why: Why, baseline: bool, found_via: "feed"|"search", categories: [str]}`
- `title` ≤ 300 tegn, `teaser` ≤ 300 tegn (renset).
- `places`: regelmærker (4.1), sat af `run` ved klassificering ud fra titel, teaser og afsenderens `places` (for søgefund udgiverens). Linjer fra før feltet fandtes, læses som `[]`.
- Samme `id` gemmes aldrig to gange. Ved genfund med ny titel opdateres `title`, men `published`/`first_seen` bevares (ligesom `topics` og `places`).

### 6.2 `Judgment` (models.Judgment) — én linje i `data/judgments/*.jsonl`
```json
{"id":"3f9a1c0b7e21","relevant":true,"reason":"Nye regler for affaldsgebyrer i kommunerne","topics":["gebyrer","regler"],"places":null,"genre":"nyhed","summary_da":null,"story_hint":null,"judged_at":"2026-10-07T07:25:41Z","by":"claude-routine","new_item":null}
```
- `reason` ≤ 200 tegn. `topics` ≤ 2 fra TopicId. `genre` fra GenreId. `summary_da` ≤ 160 tegn, kun når kandidatens `lang` ≠ `da` (ellers null). `story_hint` = id på et andet indslag om samme historie eller null.
- `places`: `null` eller udeladt = behold regelmærkerne (kandidatens `places`); en liste, også `[]` (landsdækkende), erstatter dem. Højst 8 sted-id'er (4.1); rækkefølgen normaliseres. `validate-judgments` melder ukendte id'er (ikke i `geografi.yaml`) som fejl med linjenummer. Gælder ikke kilder med `ai: false`, som kun vurderes af regler.
- **Sweep-fund** har `new_item = {url, title, teaser, source, published}` hvor `source` er et kendt id (sources.yaml aktiv eller medier.yaml); `id` = `item_id(url)`; `relevant` skal være true. Uden `places` får fundet regelmærker ud fra `new_item.title`, `teaser` og afsenderens `places`.
- Den seneste vurdering af et id vinder (filer læses i datoorden, linjer i rækkefølge).
- `pending` udskriver: `{"now": ISO, "profile": "<relevansprofil.md>", "topics": [{id,name,definition}], "genres": [{id,label}], "places_help": {"format": "r:<region>, k:<kommune>, b:<by>", "regioner": [{id,navn}], "kommuner": [{id,navn}]}, "pending": [{id,url,title,teaser,source_name,category,lang,published,rule_topics,rule_genre,rule_places,prefilter:{decision,score,hits}}], "recent_approved": [{id,title,source_name,published}]}`. `pending` = kandidater uden vurdering, `first_seen` inden for `--hours`, ikke fra kilder med `ai: false`, nyeste først, maks `--max`. `rule_places` = kandidatens `places`. `places_help` har alle regioner og kommuner, men ingen byer (routinen slår byer op i `config/geografi.yaml`). `recent_approved` = godkendte fra sidste 72 t (til `story_hint`).

### 6.3 Fallback (judgments.py: `display_mode(now, heartbeat, settings) -> "claude"|"fallback"`)
Rutinen kører kl. `settings.routine.minute` i timerne `settings.routine.hours` (København). En planlagt kørsel regnes først som misset, når `settings.routine.grace_hours` (standard 2) er gået siden dens tidspunkt: `S*` = seneste tidspunkt ≤ `now - grace_hours` på formen HH:MM i vinduet. Tilstand er `fallback`, når heartbeat mangler, eller `last_run < S*`. Ellers `claude`.
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
  "topics": [{"id","name","short","definition"}],
  "genres": [{"id","label"}],
  "sources": [{"id","name","category","homepage","lang","paywall","owner","status","health","via_search": false}],
  "geo": {"regioner": [{"id","navn","kort"}], "kommuner": [{"id","navn","kort","region"}], "byer": [{"id","navn","kommune","kommuner"}]} | null,
  "overview": {"dag": Overview|null, "uge": …, "maaned": …, "aar": …},
  "items": [DisplayItem]
}
```
`DisplayItem`:
`{id, story, url, title, teaser, source, published, date_quality, first_seen, baseline, topics, places, genre, lang, summary_da, reviewed, reason, also: [{id, source, url, title, published}], why}`
- `items` sorteret efter `published` (faldende), derefter `id`. Kun hovedindslag for historier står i `items`; øvrige ligger i `also` (sorteret efter published).
- `topics[].short`: kort navn til brugerfladen, `null` når temaet ikke har et (brug så `name`).
- `places`: sted-id'er (4.1), sorteret, højst 8. Vurderingens `places`, hvis den ikke er `null`, ellers kandidatens regelmærker. Id'er, der ikke står i geografien, udelades. For en historie er `places` foreningen af hovedindslagets og also-indslagenes steder, så et lokalt indslag i en national historie kan findes med stedfiltret; indslag i `also` har intet felt og arver hovedindslagets. Tom liste = landsdækkende.
- `geo`: alle regioner og alle kommuner i `geografi.yaml`s rækkefølge, men kun de byer, der optræder i `items[].places` (inkl. also, sorteret efter id). `navn` er det fulde navn ("Region Syddanmark", "Nyborg Kommune", "Ullerslev"), `kort` det korte; `byer[].kommune` er den primære kommune, `byer[].kommuner` alle kommuner, byen ligger i. `null`, når `geografi.yaml` mangler.
- `sources` indeholder alle aktive kilder fra `sources.yaml` (undtagen `method: search`) + `medier.yaml`-udgivere, der optræder i items (`via_search: true`).
- `health`: `groen`|`gul`|`roed`|`graa`.
- `feed.json` valideres mod `models.Feed` før skrivning (fejl giver exit 1). `examples/feed.sample.json` følger samme kontrakt (`tests/test_sample.py`).
- `status.json`: `{generated, sources: [{id, name, category, status, health, last_ok, fails, last_error, items_30d, silent}], counts: {candidates_60d, shown_60d, rejected_30d}}`.

Historier (`stories.py`): niveau 1 = samme id; niveau 2 = samme `normalize_title` inden for ±3 døgn; niveau 3 (fase 3) = rapidfuzz. Desuden forenes `story_hint`-par fra vurderinger. Hovedindslag = laveste kategori-rang, ved lighed tidligst publiceret. `story` = hovedindslagets id. En historie optager ikke indslag mere end 7 døgn efter hovedindslaget.

## 9. Frontend-kontrakt
- `site/` er statisk (ingen build). `index.html` og `kilder.html` henter `data/feed.json` (relativt). Med `?demo=1` hentes `../examples/feed.sample.json` lokalt eller `data/feed.sample.json` på Pages (export kopierer eksempelfilen dertil).
- URL-parametre: `afsender`, `tema`, `kilde`, `genre` (kommaseparerede id'er), `region`, `kommune`, `by` (kommaseparerede id'er uden præfiks, fx `region=syddanmark&kommune=nyborg&by=ullerslev`), `periode` (7|30|60), `sprog=da`, `q`, `nye=1`, `saml=0`, `vis=kompakt`, `story=<id>`, `overblik=dag|uge|maaned|aar`.
- Rækkefølge i URL'en: `demo, afsender, tema, kilde, genre, region, kommune, by, periode, sprog, q, nye, saml, vis, story, overblik`. Regioner skrives i `geo`-rækkefølge, kommuner og byer alfabetisk efter id, så samme valg giver samme link.
- **Stedfiltret** (`region`, `kommune`, `by`): hvert indslag får et udvidet sæt nøgler E ud fra `places` og `geo`:

  | Id i `places` | Tilføjes til E |
  |---|---|
  | `r:X` | `r:X` |
  | `k:Y` | `k:Y` og `r:<region for Y>` |
  | `b:Z` | `b:Z`, og for hver kommune K i `Z.kommuner`: `k:K` og `r:<region for K>` |
  | id, der ikke findes i `geo` | kun id'et selv |

  De valgte steder er ét sæt V af præfiksede nøgler (`region=X` → `r:X`, `kommune=Y` → `k:Y`, `by=Z` → `b:Z`). Et indslag passer, når E og V har mindst én nøgle til fælles. Altså: `region=X` viser indslag med `r:X`, en kommune i X eller en by, hvis `kommuner` indeholder en kommune i X; `kommune=Y` viser indslag med `k:Y` eller en by, hvis `kommuner` indeholder Y; `by=Z` viser kun indslag med `b:Z`. Et indslag med kun `r:X` vises ikke under en kommune i X. Flere valgte steder kombineres med ELLER inden for stedfiltret og med OG mod de andre filtre. Indslag uden steder (landsdækkende) vises ikke, når et sted er valgt. En historie passer, når ét af dens indslag passer (hovedindslagets `places` er allerede foreningen). Et id i URL'en, der ikke findes i `geo`, beholdes og matcher intet. Er `geo` `null`, filtrerer parametrene ikke, men skrives uændret tilbage.
- localStorage-nøgler (alle i try/catch): `af.lastVisit`, `af.theme`, `af.overviewHidden` (`"0"` = AI-overblikket er udfoldet; alt andet, også en manglende nøgle og den gamle værdi `"1"`, = foldet), `af.introClosed` (bruges ikke længere; reserveret og må ikke genbruges). Ingen andre nøgler.

## 10. Workflows
- `collect.yml`: cron `17 * * * *` + `workflow_run` efter hver kørsel af `publish.yml` ("Udgiv") + `workflow_dispatch`. GitHubs tidsplan kan falde ud, så `workflow_run` sikrer en kørsel, hver gang routinen har pushet vurderinger. `run` → `export` → commit `data/` hvis ændret (`git pull --rebase` før push) → deploy Pages. `concurrency: pages`. `run` starter ikke flere feed-, sitemap- og html-kilder, når `fetch.run_budget_seconds` (900 s) er brugt; de venter til næste kørsel og kommer først i køen, fordi kilderne køres med den længst ventende først. Søgekilder kører altid til sidst. Jobbets `timeout-minutes` er 30.
- `publish.yml`: `push` til `main` på `data/judgments/**`, `data/overview/**`, `site/**`, `config/**`, `sources.yaml`, `examples/**` + `workflow_dispatch` → `export` → deploy Pages. `concurrency: pages`.
- `ci.yml`: push/PR → `ruff check`, `pytest`, `python -m affaldsfeed check`. Ingen netværkskald i tests.
