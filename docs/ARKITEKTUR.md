# Arkitektur

Denne fil forklarer, hvordan data kommer fra kilderne ud på siden, og hvem der skriver hvad undervejs. Skemaer, felter, kommandoer og tærskler står i [KONTRAKTER.md](KONTRAKTER.md) og gentages ikke her.

## Dataflow

```
sources.yaml + config/*.yaml               (valideres med pydantic)
   │
   ├─ :05 hver time, døgnet rundt: GitHub Actions collect.yml
   │     python -m affaldsfeed run
   │       plan → hent (rss | search, fra fase 2 også sitemap | html | oda)
   │       → normalisér → løst forfilter → tema og genre efter regler → dedupe
   │       → data/candidates/, data/rejected/, data/state/
   │     python -m affaldsfeed export → commit af data/ → deploy til Pages
   │
   ├─ :25 hver time kl. 06-23 dansk tid: Claude-routinen (abonnement)
   │     følger routine/REDAKTOER.md
   │       pending → Claude vurderer → data/judgments/ÅÅÅÅ-MM-DD.jsonl
   │       → validate-judgments → heartbeat
   │       → overview-input → data/overview/<periode>.json → validate-overview --archive
   │       → git pull --rebase → push
   │     kl. 06.25 og 14.25 desuden et sweep med WebSearch
   │
   └─ ved push til data/judgments/** eller data/overview/**: GitHub Actions publish.yml
         python -m affaldsfeed export (fletter kandidater og vurderinger)
         → _site/data/feed.json + status.json → deploy til Pages

GitHub Pages: site/index.html henter data/feed.json én gang og filtrerer i browseren.
```

## Indsamlingsnettet i 5 lag

1. Direkte feeds. RSS og Atom i første version, sitemaps fra fase 2. Det dækker cirka 70 % af de kendte kilder pålideligt.
2. Nyhedssøgninger (`method: search`). Google News og Bing News på dansk med forespørgslerne i `config/search.yaml`. Søgemaskinen bruges kun til at finde artiklen, og indslaget krediteres altid udgiveren. Står udgiveren i `sources.yaml` eller `config/medier.yaml`, bliver artiklen en kandidat. Ukendte udgivere kommer ikke i feedet, men i `data/state/kildeforslag.md`. Bing-links opløses via `url`-parameteren, og dubletter fra Google fanges på normaliseret titel og udgiver.
3. Officielle kanaler. Høringsportalen, KEFM og EU-kilderne hentes som RSS fra første version. Folketingets ODA kommer i fase 2 og Retsinformation senere.
4. Claudes sweep kl. 06.25 og 14.25. Routinen søger med WebSearch efter vigtige danske affaldsnyheder fra de sidste 12-24 timer, som ikke er blandt kandidaterne. Fund fra kendte udgivere skrives som vurderinger med `new_item`. Ukendte udgivere havner i `data/judgments/kildeforslag-sweep.md`.
5. Kildesundhed og læring. Hver kilde har en status (grøn, gul, rød eller grå), som vises på "Om kilderne". Et svar med 200 og 0 indslag tæller som fejl, og kilder, der har været tavse længe, markeres. Listen over foreslåede kilder fra lag 2 og 4 gennemgås hver uge.

Indsamleren er høflig: ærlig User-Agent, robots.txt, mindst 2 sekunder mellem kald til samme vært, ETag og Last-Modified, et tidsbudget pr. kilde og automatisk pause efter gentagne fejl. Værdierne står i `config/settings.yaml`. Forfiltret er bevidst løst. Det fjerner det åbenlyst irrelevante og lader Claude vurdere resten (KONTRAKTER 5.4).

## Claude-routinen

Routinen er en Claude cloud-routine på projektejerens eget abonnement. Den bruger ingen API-nøgle, og koden har ingen anthropic-SDK. Routinen arbejder i en klon af repoet og følger instruksen i `routine/REDAKTOER.md`, som er versioneret her. Netværket i cloud-miljøet er ikke ændret: routinen skal kun bruge GitHub og PyPI, som er på standardlisten, og WebSearch, som er Claudes eget værktøj.

Tider: minut 25 i timerne 6 til 23 dansk tid, som står i `config/settings.yaml` under `routine`. Cron er `25 6-23 * * *`, hvis routinen kan køre i dansk tid. Kan den kun køre i UTC, bruges `25 4-22 * * *`, som dækker kl. 06-23 både sommer og vinter og giver en ekstra kørsel uden for vinduet.

En kørsel:
1. `python -m affaldsfeed pending` udskriver kandidater uden vurdering, relevansprofilen, temaer, genrer og nyligt godkendte indslag.
2. Claude vurderer hvert indslag mod `config/relevansprofil.md`. Vurderingen består af relevant eller ej med en begrundelse på én linje, højst 2 temaer, genre, et dansk resumé for indslag på engelsk og svensk og et `story_hint`, hvis indslaget handler om samme historie som et andet. Claude ser kun titel, uddrag, kildenavn og kategori. Artikelsider hentes ikke.
3. Vurderingerne skrives i `data/judgments/ÅÅÅÅ-MM-DD.jsonl`, og `validate-judgments` tjekker dem. Ugyldige linjer afvises med en logbesked.
4. `heartbeat` skriver tidspunktet for kørslen i `data/judgments/_heartbeat.json`.
5. Overblikket opdateres for de perioder, der er på tur (se næste afsnit).
6. `git pull --rebase` og push. Pushet starter `publish.yml`.

Fallback: `export` bruger heartbeat til at vælge visning. Er seneste kørsel mere end 2 timer forsinket i forhold til den seneste planlagte kørsel, skifter feedet til regelbaseret visning. Godkendte indslag vises stadig, afviste er stadig skjult, og uvurderede kandidater, som forfiltret ville vise, kommer med mærket "Ikke vurderet". Om natten er der ingen planlagte kørsler, så nye indslag venter til kl. 06.25 uden at feedet skifter. Kilder med `ai: false` vurderes altid kun efter regler. Den præcise regel står i KONTRAKTER 6.3.

## AI-overblikket

Overblikket har fire perioder, og alle er rullende vinduer i dansk tid.

| Periode | Vindue | Opdateres | Bygges af |
|---|---|---|---|
| I dag (`dag`) | kalenderdagen indtil nu | i hver kørsel kl. 06-23 med nye godkendte indslag | dagens godkendte indslag |
| Ugen (`uge`) | seneste 7 døgn | kl. 06.25 og 14.25 | ugens indslag samlet i historier |
| Måneden (`maaned`) | seneste 30 døgn | dagligt kl. 06.25 | arkiverede ugeoverblik og de mest dækkede historier |
| Året (`aar`) | seneste 365 døgn | mandag kl. 06.25 | arkiverede månedsoverblik og årets største historier |

Inputtet er hierarkisk. Ugen bygger på historier frem for enkelte artikler, og måneden og året bygger på de overblik, der allerede er skrevet for de mindre perioder, plus højst 40 historier. Derfor vokser token-forbruget ikke, når der kommer mere data. Rækker data ikke hele vinduet tilbage, får overblikket feltet `since`, og siden skriver fx "Året (siden 7. oktober 2026)".

Præcisionsreglerne står i `routine/REDAKTOER.md`:
- Claude skriver kun ud fra godkendte indslag i perioden og bruger ingen viden udefra.
- Hvert punkt peger på mindst ét indslag via `item_ids`. Tal, datoer og frister skal stå i de indslag, punktet henviser til.
- Interessevaretagelse markeres, fx "ifølge Dansk Affaldsforening ...".
- Prioriteringen er betydning for kommuner (regler, økonomi, frister og større beslutninger), dernæst bredde i dækningen og nyhedsværdi.
- Sproget er neutralt og dansk uden salgssprog.

`validate-overview` afviser overblik med for lange tekster, forkert antal punkter eller `item_ids`, der ikke er godkendte indslag i vinduet. Med `--archive` kopieres gyldige overblik til `data/overview/archive/`. Arkivet er både input til måned og år og et spor, der gør det muligt at finde fejl bagefter. På siden står hvert punkt med kildelinks og noten "Kan indeholde fejl".

## Data og ejerskab

Hver mappe i `data/` har én skribent. Actions og routinen rører aldrig de samme filer, så de to kan pushe uden merge-konflikter, og begge laver `git pull --rebase` før push.

| Mappe | Skrives af | Indhold |
|---|---|---|
| `data/candidates/` | `collect.yml` | kandidater, én fil pr. fundmåned |
| `data/rejected/` | `collect.yml` | afviste indslag med begrundelse, gemt i 90 dage |
| `data/state/` | `collect.yml` | ETag, kildesundhed, robots-cache og kildeforslag fra søgninger |
| `data/judgments/` | Claude-routinen | vurderinger pr. dag, heartbeat og kildeforslag fra sweepet |
| `data/overview/` | Claude-routinen | aktuelle overblik pr. periode og arkivet |
| `_site/` | `export` | det byggede site, ikke i git |

Filerne skrives atomisk og kun, når indholdet faktisk ændrer sig, så git ikke får tomme commits. Formaterne står i KONTRAKTER afsnit 6.

## Workflows

- `collect.yml` kører hver time på minut 5 og kan startes med `workflow_dispatch`. Den kører `run` og `export`, committer `data/`, hvis noget er ændret, og deployer til Pages. Commits lavet med `GITHUB_TOKEN` starter ikke andre workflows, så `collect.yml` deployer selv.
- `publish.yml` starter ved push til `main` på `data/judgments/**`, `data/overview/**`, `site/**`, `config/**`, `sources.yaml` og `examples/**`, og kan også startes manuelt. Den kører `export` og deployer.
- `ci.yml` kører ruff, pytest og `python -m affaldsfeed check` ved push og pull request. Testene laver ingen netværkskald.

`collect.yml` og `publish.yml` deler `concurrency: pages`, så to deploys ikke kører samtidig.

## Drift og omkostning

- GitHub Actions og GitHub Pages er gratis for offentlige repos.
- Claude-routinen bruger 18 kørsler i døgnet af abonnementet (19, hvis cron skal stå i UTC). Forbruget følges på claude.ai/settings/usage. Bliver kvoten for stram, sættes `routine.hours` i `config/settings.yaml` og routinens cron ned, fx til hver anden time. Fallback dækker hullerne.
- Feedet rækker 60 dage tilbage.
- GitHub slår planlagte workflows fra efter 60 dage uden aktivitet i et offentligt repo. Datacommits holder repoet aktivt. Sker det alligevel, viser siden bjælken om forældet feed efter 6 timer.
- Driften kan følges i kildesundheden på "Om kilderne", i `data/judgments/_heartbeat.json` og i kørselsloggen i GitHub Actions.

## Kendte begrænsninger

- LinkedIn og Facebook kan ikke hentes.
- Bag betalingsmur får feedet kun overskrift og uddrag.
- Captcha, Cloudflare-challenges og ALTCHA omgås aldrig. Kilder bag dem sættes på pause eller fravælges med en note.
- Første version henter kun RSS og søgninger. Sitemap, html og ODA kommer i fase 2.
- Historier samles kun på ens URL og ens titel. Samme historie med forskellige overskrifter samles først fra fase 3.
- Claudes vurdering og overblikket afhænger af, at routinen kører, og af abonnementets kvote. Hvor mange routine-kørsler abonnementet tillader i døgnet, tjekkes ved opsætningen.
- Planlagte kørsler i GitHub Actions kan blive forsinket, når GitHub har travlt.
- AI-overblikket kan tage fejl. Kildelinks ved hvert punkt og arkivet gør det muligt at kontrollere det.
- Når en kilde ikke angiver dato, bruges fundtidspunktet, og kortet skriver "fundet kl. ...".
- Google News-links kan ikke altid opløses til artiklens egen adresse. Så linker indslaget via Google.
