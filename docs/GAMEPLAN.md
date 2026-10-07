# Gameplan

Affaldsfeed bygges i seks faser. Fase 0 og 1 laves i den første lokale session og slutter med første push til GitHub. Derefter flyttes arbejdet til en cloud-session, som tager fase 2 og 3. Fase 4 venter på brugerens egen kildeliste, og fase 5 laves kun, hvis noget konkret mangler.

## Status

| Fase | Indhold | Status |
|---|---|---|
| 0 | Fundament: config, kilderegister, `check`, CI og docs | Færdig |
| 1 | Første live version: pipeline for RSS og søgning, site, workflows og Claude-routinen | Færdig, live 7. oktober 2026 |
| 2 | Kilder uden RSS, Folketingets ODA og Claudes sweep | I gang: sitemap og html virker, og 71 kilder er aktive. ODA mangler, og sweepet er ikke efterprøvet |
| 3 | Kvalitet: "Hvorfor med?", bedre historier, kompakt visning | I gang: kompakt visning er færdig |
| 4 | Brugerens kildeliste | Venter på listen |
| 5 | Udvidelser | Kun ved konkret savn |

Opdatér tabellen, når en fase er færdig.

Ud over planen er der bygget et stedfilter (regioner, kommuner og byer ud fra `geo`), fanen Tidslinje med de vigtigste begivenheder (routinens trin 7 kl. 22) og en enklere brugerflade efter brugerens ønsker: et AI-overblik, der kan foldes sammen, foldbare grupper i menuen med alt afkrydset fra start og periodevalget over listen.

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
- dagsbundter for ODA og høringsfrist på indslag fra Høringsportalen
- kompakt visning
- `tests/cases.yaml` udvidet til 150 cases

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

Start med at læse `CLAUDE.md`, `docs/KONTRAKTER.md` og denne fil. Tjek så, at driften kører: `gh run list` skal vise grønne kørsler af "Udgiv" og "Indsamling", og `data/judgments/_heartbeat.json` skal være fra seneste kørsel i dagtimerne. GitHubs tidsplan for `collect.yml` var ikke kommet i gang pr. 7. oktober 2026. Indsamlingen kører i stedet efter hvert byg (`workflow_run`), altså når routinen har pushet. Står routinen, står indsamlingen derfor også.

Brugeren skal rette routinens prompt på claude.ai, så den siger "Du må kun skrive i data/judgments/, data/overview/ og data/timeline/." Indtil da fyldes tidslinjen ikke. Routinen er oprettet via API, så en session kan ikke selv rette den.

Fase 2, resten:
1. Lokale medier i `config/medier.yaml`: ugeaviserne fra Ugeavispuljen, medlemmerne af Danske Lokalaviser og andre lokale nyhedssider med redaktionelt ansvar. Domæner under et fælles domæne (fx `sn.dk`, `ugeavisen.dk`, `dinavis.dk`) står én gang.
2. Følg de 19 sitemap- og 10 html-kilder i 7 dage. Fejler en, så ret `match`, `select` eller `filter`, eller sæt den på pause med en note.
3. Byg `collect/oda.py`. Søg på affaldsordene i `config/keywords.yaml`, giv indslagene genren `folketing` og brug `bundle: day`.
4. Efterprøv sweepet kl. 06.25 og 14.25. Fund skal skrives som vurderinger med `new_item`, og ukendte udgivere skal havne i `data/judgments/kildeforslag-sweep.md`.
5. Gennemgå `data/state/kildeforslag.md` hver uge. Troværdige udgivere flyttes til `config/medier.yaml` eller `sources.yaml`.

Fase 3:
1. "Hvorfor med?" bygger på feltet `why`, som allerede står i `feed.json`.
2. "Rapportér" med issue-skabelonerne `fejl-i-feed` og `ny-kilde`, som allerede findes.
3. Historier på niveau 3 med rapidfuzz. Tærsklen skal være høj, fordi en forkert sammenlægning skjuler en nyhed.
4. Via Ritzau med `aliases`, dagsbundter for ODA og høringsfrist.
5. Flere cases i `tests/cases.yaml`, især de indslag, stikprøverne har fundet forkerte.

Fase 4, når brugerens liste kommer: følg trinnene under fase 4 ovenfor og i `docs/KILDER.md`.
