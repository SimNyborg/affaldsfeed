# CLAUDE.md

Instrukser til Claude-sessioner i dette repo. Læs `docs/KONTRAKTER.md`, før du ændrer kode, og `docs/GAMEPLAN.md` for at se, hvor projektet står.

## Spilleregler

- Ingen kildespecifik kode. En kilde hentes med en generisk metode (`rss`, `sitemap`, `html`, `oda`, `search`), og alt om kilden står i `sources.yaml`. Kan en kilde ikke hentes generisk, får den `status: kandidat` eller `fravalgt` med en note.
- Konfiguration styrer. Ord, temaer, genrer, søgninger, udgivere, tærskler og tider står i `config/`. Nye lister og tal hører hjemme der, ikke i koden.
- Intet fra eller til affaldsviden.info. Pipeline, frontend og tests sender aldrig forespørgsler dertil, og intet lægges der.
- Intet fra Affaldskort. Ingen kode eller data kopieres derfra.
- Faste skrivegrænser i `data/`:
  - GitHub Actions (`collect.yml`) skriver kun i `data/candidates/`, `data/rejected/` og `data/state/`.
  - Claude-routinen skriver kun i `data/judgments/`, `data/overview/` og `data/timeline/`.
  - Udviklingssessioner committer ikke data, de selv har genereret lokalt.
- `docs/KONTRAKTER.md` er bindende. Ændres en kontrakt, opdateres filen i samme commit som koden. `affaldsfeed/models.py` er kontrakten i kode.
- Prosa-docs (README og `docs/*.md` undtagen KONTRAKTER) skrives gennem humanizer-skillet i embedded mode.
- Kodekommentarer og logbeskeder er på dansk og korte. Stier via `affaldsfeed/paths.py`, tider via `affaldsfeed/timeutil.py`: UTC på disk, København for dage og vinduer.
- Afhængigheder står i `requirements.txt`. Ingen ML-biblioteker og ingen anthropic-SDK. Claude vurderer i routinen, ikke i koden.
- Høflig hentning: UA og takt fra `config/settings.yaml`, robots.txt, ETag. Captcha, Cloudflare, ALTCHA og login omgås aldrig.
- Tests laver ingen netværkskald. Brug fixtures i `tests/fixtures/`.
- Nye idéer skrives i `docs/BESLUTNINGER.md` eller et issue. Fase 5 kræver et konkret savn.

## Kommandoer

Alle køres fra repoets rod.

```
python -m affaldsfeed check [--fetch ID] [--explain]
python -m affaldsfeed run [--only ID,ID] [--dry-run] [--now ISO]
python -m affaldsfeed export [--out _site] [--now ISO]
python -m affaldsfeed pending [--max 200] [--hours 72]
python -m affaldsfeed validate-judgments [--file PATH]
python -m affaldsfeed heartbeat
python -m affaldsfeed overview-input --period dag|uge|maaned|aar
python -m affaldsfeed validate-overview [--period P] [--archive]
python -m affaldsfeed timeline-input [--days 3]
python -m affaldsfeed validate-timeline [--file PATH]
python -m affaldsfeed import FILE.csv [--replace]     # fase 4
python -m affaldsfeed find-feed URL                   # fase 4
```

Frontend lokalt: `python -m http.server 8000` i roden og åbn `http://localhost:8000/site/index.html?demo=1`.

## Test

```
python -m pytest
python -m ruff check .
python -m affaldsfeed check
```

`ci.yml` kører de samme tre ved push og pull request.

## Fase-status

- Fase 0 og 1 er færdige, og feedet har været live siden 7. oktober 2026.
- Fase 2 er i gang: sitemap, html og ODA virker, og 153 kilder er aktive, heraf 81 regionale og lokale aviser (se `docs/LOKALMEDIER.md`). Lokalmedier, der ikke kan hentes direkte, står i `config/medier.yaml`. Efterprøvning af sweepet og 7 dages overvågning af sitemap og html mangler.
- Fase 3 er i gang (kompakt visning er færdig). Fase 4 venter på brugerens kildeliste.
- Se "Næste skridt for cloud-sessionen" i `docs/GAMEPLAN.md`.

## Arbejdsgang i cloud-sessionen

- Cloud-miljøet må ikke selv hente nyhedssider. Afprøv kilder fra GitHub Actions med `probe.yml`: skriv kilde-id'er eller `url <URL> [kB]` i `probe/request.txt` og push, så kommer svaret i `probe/result.md`.
- `gh pr create` fejler, fordi GraphQL er spærret. Opret pull requests med REST: `gh api repos/SimNyborg/affaldsfeed/pulls -f title=... -f head=<gren> -f base=main -F draft=true -F body=@fil.md`. Flet med `gh api -X PUT repos/SimNyborg/affaldsfeed/pulls/<nr>/merge -f merge_method=squash`, når CI er grøn.
- github.io kan ikke hentes herfra. Tjek udgivelsen med `gh api "repos/SimNyborg/affaldsfeed/deployments?environment=github-pages"` og status på den nyeste deployment.
- Frontenden testes lokalt med Playwright og den forudinstallerede Chromium mod `python -m http.server` og `?demo=1`: flere bredder (320, 375, 1280), tastatur og axe.

## Claude-routinen

Routinens instruks ligger i `routine/REDAKTOER.md` og er versioneret her i repoet. Routinen på claude.ai peger kun på filen. Vil du ændre, hvordan Claude vurderer eller skriver overblikket, så ret `routine/REDAKTOER.md` eller `config/relevansprofil.md`.
