# Affaldsfeed

Affaldsfeed samler nyheder om affaldsområdet i Danmark på én side. Indslagene kommer fra nationale medier og lokalmedier, fagmedier, myndigheder, kommuner og affaldsselskaber, organisationer, tænketanke, forskning og EU og Norden. Det nyeste står øverst, og hver titel linker til den oprindelige artikel.

Feedet er skrevet til folk, der arbejder med affald i kommunerne og de kommunale affaldsselskaber. Man kan filtrere på sted, afsender, tema, kilde og genre. Listen går tilbage til 1. januar 2026, og en lille kalender viser nyhederne fra et bestemt tidsrum. Øverst ligger et kort AI-overblik med fanerne I dag, Ugen, Måneden og Året. Claude skriver det ud fra de indslag, der er godkendt til feedet, og hvert punkt linker til de artikler, det bygger på. Fanen Tidslinje samler de vigtigste begivenheder på området.

Live: https://simnyborg.github.io/affaldsfeed/

## Sådan virker det

1. GitHub Actions kører indsamlingen hver time i dagtimerne, lige efter at sitet er bygget. Den henter fra kilderne i `sources.yaml`, sorterer det åbenlyst irrelevante fra med et løst forfilter og foreslår tema og genre ud fra faste regler. Kandidaterne gemmes i `data/candidates/`, og sitet bygges og lægges på GitHub Pages.
2. En Claude-routine kører 25 minutter over hel fra kl. 06 til 23 dansk tid på projektejerens Claude-abonnement. Den læser instruksen i `routine/REDAKTOER.md`, vurderer de nye kandidater mod `config/relevansprofil.md` og skriver vurderingerne i `data/judgments/`. Derefter opdaterer den AI-overblikket i `data/overview/` og pusher.
3. Pushet starter et nyt byg, og GitHub Pages viser de godkendte indslag og det nye overblik.

Feedet viser kun indslag, Claude har godkendt. Er routinen mere end to timer forsinket i dagtimerne, fx fordi kvoten er brugt op, skifter feedet selv til regelbaseret visning, og en besked øverst på siden siger det. Om natten venter nye indslag til kørslen kl. 06.25. Hele forløbet er beskrevet i [docs/ARKITEKTUR.md](docs/ARKITEKTUR.md).

Indsamleren henter med User-Agent `Affaldsfeed/0.1 (+https://github.com/SimNyborg/affaldsfeed)`, følger robots.txt, holder mindst to sekunder mellem kald til samme vært og bruger ETag, så uændrede feeds ikke hentes igen. Ejer du en af kilderne og vil have den fjernet eller hentet sjældnere, så opret et issue.

## Sådan tilføjer du en kilde

Alle kilder står i `sources.yaml`. En ny RSS-kilde kræver ingen kode, kun en post som denne (Renosyd står allerede i registret og er bare brugt som eksempel):

```yaml
- id: renosyd
  name: Renosyd
  category: kommunal
  homepage: https://renosyd.dk
  feeds: https://renosyd.dk/feed
  filter: none
  basis: offentlig
  checked: 2026-10-07
```

Uden `method` og `status` bliver kilden hentet som RSS og sat til aktiv. Kør `python -m affaldsfeed check --fetch <id> --explain` før du committer. Så kan du se, hvad forfiltret beholder, og hvorfor. Felterne, kategorierne og kriterierne for at komme med står i [docs/KILDER.md](docs/KILDER.md).

## Lokalt

Projektet kræver Python 3.12.

```
pip install -r requirements-dev.txt
python -m affaldsfeed check      # validerer sources.yaml og config/
python -m affaldsfeed run        # henter fra kilderne og skriver i data/
python -m affaldsfeed export     # bygger _site/ med data/feed.json
python -m pytest
python -m ruff check .
```

`run --dry-run` henter uden at skrive noget. Data i `data/` skrives normalt af GitHub Actions og Claude-routinen, så lokale kørsler skal ikke committes.

Frontenden kan prøves med eksempeldata. Start serveren i repoets rod, fordi demo-tilstanden henter `../examples/feed.sample.json`:

```
python -m http.server 8000
```

Åbn derefter http://localhost:8000/site/index.html?demo=1. Vil du se rigtige data efter `export`, så kør `python -m http.server 8000 -d _site` og åbn http://localhost:8000/.

## Dokumentation

- [docs/GAMEPLAN.md](docs/GAMEPLAN.md): faser, status og næste skridt
- [docs/ARKITEKTUR.md](docs/ARKITEKTUR.md): dataflow, Claude-routinen, AI-overblikket og drift
- [docs/KILDER.md](docs/KILDER.md): kriterier for kilder, felterne i `sources.yaml` og import af en kildeliste
- [docs/DESIGNMANUAL.md](docs/DESIGNMANUAL.md): layout, farver, komponenter og mikrotekster
- [docs/BESLUTNINGER.md](docs/BESLUTNINGER.md): daterede beslutninger og fravalg
- [docs/KONTRAKTER.md](docs/KONTRAKTER.md): den bindende tekniske kontrakt mellem modulerne
- [CLAUDE.md](CLAUDE.md): spilleregler for Claude-sessioner i repoet

## Om projektet

Affaldsfeed er et uafhængigt hobbyprojekt af Simon Høg Nyborg. Det er ikke tilknyttet affaldsviden.info, og der hentes intet fra eller lægges intet på affaldsviden.info. Koden er MIT-licenseret, se [LICENSE](LICENSE). Titler og uddrag tilhører de oprindelige kilder.
