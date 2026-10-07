# Beslutninger

Korte, daterede noter om de vigtigste valg og fravalg. Nye beslutninger skrives nederst med dato. Ændres en beslutning, skrives en ny note, og den gamle bliver stående.

## 2026-10-07: Selvstændigt hobbyprojekt

Affaldsfeed er et hobbyprojekt i brugerens eget offentlige repo, `SimNyborg/affaldsfeed`, med eget navn og live på GitHub Pages. Konceptet er tænkt, så det kunne passe til affaldsviden, men der hentes intet fra og lægges intet på affaldsviden.info. Udtrykket er lånt som farveværdier og typografi, ikke som logo eller navn. Projektet bruger ingen kode eller data fra Affaldskort. Fravalgt: WordPress, login og et modul direkte på affaldsviden.info.

## 2026-10-07: Lean MVP som skelet

Af de tre koncepter fra researchen blev det enkleste valgt som skelet: konfiguration frem for kode, generiske hentemetoder og ingen kildespecifik kode. Fra det andet koncept kom blandt andet genreaksen, primærkildeordningen, datoreglerne og feltet `basis`. Fra det tredje kom filtre i URL'en, baseline for nye kilder, kort der ikke flyttes op ved ny dækning, og kompakt visning. Alt, der krævede ML, kurateringsflader eller flere sider, er skubbet til senere faser.

## 2026-10-07: Claude vurderer på abonnement kl. 06-23

Relevansen vurderes af en Claude cloud-routine på brugerens eget abonnement, en gang i timen kl. 06-23. Der er ingen API-nøgle i repoet og ingen anthropic-SDK i koden. Fravalgt: en `ANTHROPIC_API_KEY` som repo-secret med en lille model i GitHub Actions. Prisen for valget er 18 kørsler i døgnet af abonnementets kvote og ingen vurdering om natten. Om abonnementet tillader så mange routine-kørsler, bekræftes ved opsætningen. Gør det ikke, sættes antallet ned i `config/settings.yaml`. Forbruget følges på claude.ai/settings/usage.

## 2026-10-07: GitHub Actions til indsamling

Indsamlingen kører hver time døgnet rundt i GitHub Actions og bygger sitet til GitHub Pages. Begge dele er gratis for offentlige repos. Indsamlingen er ren Python uden AI og bruger derfor ikke af abonnementet. Actions skriver kun i `data/candidates/`, `data/rejected/` og `data/state/`, og routinen kun i `data/judgments/` og `data/overview/`, så de to aldrig skriver i de samme filer.

## 2026-10-07: Feedet viser kun godkendte indslag, med fallback

Et indslag kommer først i feedet, når Claude har godkendt det. Er routinen mere end 2 timer forsinket i dagtimerne, skifter feedet automatisk til regelbaseret visning, og indslag, der ikke er vurderet, får mærket "Ikke vurderet". Om natten venter nye indslag til kl. 06.25. Fallbacken er der, så feedet ikke går i stå, hvis kvoten er brugt eller routinen fejler.

## 2026-10-07: AI-overblik med fire perioder og hierarkisk input

Øverst på siden står et overblik over I dag, Ugen, Måneden og Året, skrevet af Claude. Dagen opdateres i hver kørsel, ugen to gange i døgnet, måneden dagligt og året hver mandag. Ugen bygger på historier, og måned og år bygger på de arkiverede overblik for de mindre perioder. Så holder token-forbruget sig nogenlunde fast, uanset hvor meget data der kommer. Hvert punkt skal pege på godkendte indslag, tal og datoer skal stå i dem, og en validator afviser resten.

## 2026-10-07: Søgemaskiner kun som finder

Google News og Bing News bruges til at finde artikler hos udgivere, der ikke har eget feed, fx lokalaviser. De er ikke selv kilder, og et indslag krediteres altid udgiveren. Kun udgivere i `sources.yaml` eller `config/medier.yaml` kommer i feedet. Ukendte udgivere bliver kildeforslag.

## 2026-10-07: Medier med AI-fravalg hentes af egen RSS-læser

DR, TV 2-regionerne, Politiken, Børsen, Ingeniøren og Energy Supply blokerer AI-agenter i robots.txt. Researchen foreslog at lade dem stå som kandidater, men brugeren besluttede, at feedets egen RSS-læser henter dem. Den er ikke en AI-crawler og følger robots.txt for `*`. Claude vurderer kun titel og RSS-uddrag og besøger aldrig mediernes sider. Feltet `ai: false` gør det muligt at lade en kilde vurdere kun efter regler, hvis beslutningen ændres.

## 2026-10-07: Ingen billeder

Kortene har ingen billeder. Det holder listen tæt, så første skærm kan vise mindst 6 indslag, også på mobil.

## 2026-10-07: Ingen ML-biblioteker

Relevans, temaer og genre klares med regler i `config/` og Claudes vurdering i routinen. Der bruges ikke scikit-learn, trafilatura, torch eller embeddings. Historier på niveau 3 i fase 3 kan tilføje rapidfuzz.

## 2026-10-07: Intet login

Siden er statisk og offentlig. Filtrene ligger i URL'en, så et delt link viser det samme for alle. localStorage bruges kun til det, der hører til den enkelte læser: sidste besøg, lys eller mørk tilstand, et skjult overblik og en lukket introlinje.

## 2026-10-07: Bred relevansprofil i MVP

Profilen i `config/relevansprofil.md` tager alt om affaldsområdet i Danmark med, som er relevant for kommuner. Udeladt er sager om industri- eller jordaffald uden kommunal vinkel, som Nordic Waste-sagen, samt atomaffald. Profilen skærpes, når stikprøverne viser, hvor der er støj.
