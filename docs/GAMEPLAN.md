# Gameplan

Affaldsfeed bygges i seks faser. Fase 0 og 1 laves i den første lokale session og slutter med første push til GitHub. Derefter flyttes arbejdet til en cloud-session, som tager fase 2 og 3. Fase 4 venter på brugerens egen kildeliste, og fase 5 laves kun, hvis noget konkret mangler.

## Status

| Fase | Indhold | Status |
|---|---|---|
| 0 | Fundament: config, kilderegister, `check`, CI og docs | Færdig |
| 1 | Første live version: pipeline for RSS og søgning, site, workflows og Claude-routinen | Færdig, live 7. oktober 2026 |
| 2 | Kilder uden RSS, Folketingets ODA og Claudes sweep | I gang: sitemap, html og ODA virker, og 153 kilder er aktive. Sweepet er ikke efterprøvet |
| 3 | Kvalitet: "Hvorfor med?", bedre historier, kompakt visning | I gang: kompakt visning, dagsbundter og 150 testcases er færdige; niveau 3 og Via Ritzau er udskudt (se BESLUTNINGER) |
| 4 | Brugerens kildeliste | Venter på listen |
| 5 | Udvidelser | Kun ved konkret savn |

Opdatér tabellen, når en fase er færdig.

Ud over planen er der bygget et stedfilter (regioner, kommuner og byer ud fra `geo`), fanen Tidslinje med de vigtigste begivenheder (routinens trin 7 kl. 22) og en enklere brugerflade efter brugerens ønsker: et AI-overblik, der kan foldes sammen, foldbare grupper i menuen med alt afkrydset fra start og en kalender over listen.

## Fase 0: Fundament

Leverancer:
- git-repo med `config/*.yaml`, `config/relevansprofil.md` og `sources.yaml` med hele startlisten fra researchen
- `python -m affaldsfeed check`, `ci.yml` og `tests/cases.yaml`
- `docs/KONTRAKTER.md` som teknisk kontrakt
- README, CLAUDE.md, LICENSE og de fem docs på dansk, skrevet gennem humanizer-skillet

Færdig, når `check`, ruff og pytest er grønne lokalt og i CI.

## Fase 1: Første live version

Leverancer:
- modulerne fetch, collect/rss, collect/search, normalize, relevance (løst forfilter), classify, judgments, overview, stories (niveau 1 og 2), store, health og export
- hele `site/` efter designmanualen, med overbliksfeltet og alle fire faner
- `examples/feed.sample.json` med eksempler på overblik, så frontenden kan prøves med `?demo=1`
- `collect.yml` og `publish.yml`
- `routine/REDAKTOER.md` med instruks til vurdering, overblik og sweep

Opsætning, når koden er klar:
1. `gh repo create SimNyborg/affaldsfeed --public`
2. Push.
3. Slå GitHub Pages til med GitHub Actions som kilde.
4. Kør `collect.yml` med `workflow_dispatch` og følg den med `gh run watch`.
5. Opret Claude-routinen med `schedule`-skillet og test den med "Kør nu". Bekræft, om cron tager dansk tid eller UTC, og at abonnementet tillader 18 kørsler i døgnet. Tillader det færre, så sæt `routine.hours` i `config/settings.yaml` og routinens cron ned til det, der er plads til.

Færdig, når:
- `run` mod rigtige feeds henter fra mindst 30 kilder i mindst 7 kategorier, og fejlende kilder står i loggen
- `export` giver et `feed.json`, der validerer mod skemaet
- `collect.yml` er grøn, og Pages-adressen viser indslag
- routinen har skrevet `data/judgments/<dato>.jsonl` og `data/overview/dag.json` og pushet, og `publish.yml` har deployet resultatet
- frontenden er testet med demo-data og rigtige data: filtre og URL-tilstand, tom tilstand, nyt siden sidst, mørk tilstand, 375×812 uden vandret scroll, tastatur og en konsol uden fejl
- hvert punkt i et testoverblik er kontrolleret mod de artikler, det henviser til
- mindst 40 af de første 50 viste indslag er relevante ved manuel gennemgang

Til sidst: commit, push og `move_to_cloud` med en opsummering af fase 2-4.

## Fase 2: Kilder uden RSS (cloud)

Leverancer:
- `collect/pages.py` til sitemap og html med et fælles sideudtræk for titel, dato og teaser
- `collect/oda.py` til Folketingets ODA
- de planlagte kilder i `sources.yaml` slået til én ad gangen
- Claudes sweep kl. 06.25 og 14.25 i drift

Færdig, når mindst 60 kilder kører, alle 8 afsenderkategorier har mindst 3 aktive kilder, og ingen sitemap- eller html-kilde har fejlet i 7 dage.

## Fase 3: Kvalitet (cloud)

Leverancer:
- "Hvorfor med?" og "Rapportér" på kortet. "Rapportér" åbner en issue-skabelon og sender kun indslagets id med.
- historier på niveau 3 med rapidfuzz, som så bliver en ny afhængighed
- Via Ritzau, hvor udgiveren matches mod `aliases` i registret
- dagsbundter for ODA (færdig) og høringsfrist på indslag fra Høringsportalen
- kompakt visning
- `tests/cases.yaml` udvidet til 150 cases (færdig)

Færdig, når to stikprøver i træk viser mindst 45 relevante ud af 50.

## Fase 4: Brugerens kildeliste

Starter, når brugeren afleverer sin liste som regneark eller CSV med navn og URL, gerne også kategori og note.

1. `python -m affaldsfeed import liste.csv` laver poster med `status: kandidat`.
2. `python -m affaldsfeed find-feed <url>` finder RSS, Atom eller sitemap for hver kandidat.
3. `python -m affaldsfeed check --fetch <id> --explain` viser, hvad der hentes, og hvad forfiltret beholder. `filter`, `match` og `select` justeres ud fra det.
4. Kilderne sættes til aktiv. Med `--replace` sættes de kilder, der ikke står på brugerens liste, på pause. De slettes ikke.

Færdig, når alle kilder på listen er aktive eller fravalgt med en begrundelse, og `docs/KILDER.md` er opdateret. Detaljerne står i [KILDER.md](KILDER.md).

## Fase 5: Kun ved konkret savn

- overblikket som udgående RSS eller e-mail
- udgående RSS pr. tema
- Retsinformation som kilde
- kommunernes egne sitemaps

## Succeskriterier

- Efter fase 2 kører mindst 60 kilder, og alle 8 kategorier har mindst 3.
- Mindst 45 af 50 indslag i en stikprøve er relevante for en kommunal affaldsmedarbejder.
- Et nyt RSS-indslag står i feedet senest 2 timer efter udgivelse i dagtimerne.
- Feedet kører 30 dage i træk uden manuel indgriben.
- Første skærm viser mindst 6 indslag på både 1366×768 og 375×812.

## Næste skridt for cloud-sessionen

Start med at læse `CLAUDE.md`, `docs/KONTRAKTER.md` og denne fil. Tjek så, at driften kører: `gh run list` skal vise grønne kørsler af "Udgiv" og "Indsamling", og `data/judgments/_heartbeat.json` skal være fra seneste kørsel i dagtimerne. GitHubs tidsplan for `collect.yml` kører kun sporadisk: natten til 8. oktober 2026 kom 2 af omkring 8 planlagte kørsler. Indsamlingen kører derfor mest efter hvert byg (`workflow_run`), altså når routinen har pushet. Står routinen, står indsamlingen næsten også, og om natten går der op til fire timer mellem kørslerne.

Brugeren skal rette routinens prompt på claude.ai, så den siger "Du må kun skrive i data/judgments/, data/overview/ og data/timeline/." Indtil da fyldes tidslinjen ikke. Routinen er oprettet via API, så en session kan ikke selv rette den.

Fase 2, resten (lokale medier og ODA er færdige):
1. Følg de 45 sitemap- og 28 html-kilder og ODA i 7 dage. Fejler en, så ret `match`, `select` eller `filter`, eller sæt den på pause med en note.
2. Efterprøv sweepet kl. 06.25 og 14.25. Fund skal skrives som vurderinger med `new_item`, og ukendte udgivere skal havne i `data/judgments/kildeforslag-sweep.md`. Sweepet kl. 06.25 den 8. oktober gav ingen fund. Læs routinens session (`get_trigger` giver `last_run.session_id`, `list_events` viser forløbet) for at se, om det søgte, og hvad det fandt.
3. TV 2: afventer brugerens svar på, om indsamlingen må læse TV 2's sektionssider (HTML) for at få næsten fuld dækning (se BESLUTNINGER 2026-10-08, Dækningen af affaldsnyheder).
4. Følg de 81 regionale og lokale aviser, der kom til 2026-10-08 (BESLUTNINGER: Lokalaviserne hentes direkte og Ugeaviser og netaviser hentes direkte), i 7 dage. Tjek især dagssitemaps lige efter midnat, Sjællandske Mediers månedsskifte, forsiderne og de små RSS-feeds.
5. Lokalmedier: kortlægningen mangler målrettede søgninger i 65 kommuner (se `docs/LOKALMEDIER.md`, Huller i kortlægningen). Søg dem igennem i en ny tur, når søgebudgettet tillader det, og afprøv nye fund med `find-feed` via `probe.yml`. Ret tabellerne i `docs/LOKALMEDIER.md`, når en kilde kommer til eller falder fra.
6. Gennemgå `data/state/kildeforslag.md` hver uge. Troværdige udgivere flyttes til `config/medier.yaml` eller `sources.yaml`.

Fase 3:
1. "Hvorfor med?" bygger på feltet `why`, som allerede står i `feed.json`.
2. "Rapportér" med issue-skabelonerne `fejl-i-feed` og `ny-kilde`, som allerede findes.
3. Høringsfrist på indslag fra Høringsportalen, når der kommer en høring om affald at se formatet på.
4. Flere cases i `tests/cases.yaml`, især de indslag, stikprøverne har fundet forkerte.
5. Historier på niveau 3 og Via Ritzau er udskudt (se BESLUTNINGER). Tag dem op, hvis dubletterne bliver flere.

Fase 4, når brugerens liste kommer: følg trinnene under fase 4 ovenfor og i `docs/KILDER.md`.
