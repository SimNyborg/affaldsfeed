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

## 2026-10-07: Stedfilter og tidslinje

Brugeren ønskede at kunne filtrere på sit område. Indslagene får derfor stedmærker for regioner, kommuner og byer ud fra geografien i `config/`, og "Landsdækkende" dækker indslag uden steder. Brugeren ønskede også en tidslinje over de vigtigste begivenheder. Den skrives af routinen kl. 22 ud fra godkendte indslag og ligger i `data/timeline/`, som routinen nu også må skrive i. Filerne er append-only, så en begivenhed kan rettes eller slettes med en ny linje.

## 2026-10-07: Enklere brugerflade

Brugeren bad om en enklere side. Knappen til mørk tilstand er fjernet, så siden følger enhedens farvetema. Headeren har ingen undertitel, "Om kilderne" står kun i footeren, og linket "Om afsendertyperne" er væk. Menuen har foldbare grupper, og alle lister er afkrydset fra start, så et fjernet flueben skjuler. Hver gruppe undtagen Sted har én knap, der skifter mellem "Fravælg alle" og "Vælg alle". Kortene viser kun kildens navn, fx "Folketinget" i stedet for "Folketinget · Myndighed · Folketingssag". Afsendertype, ejer, genre, betalingsmur og "Ikke vurderet" står ikke på kortene, og linjen med sted og temaer under artiklerne er væk. Betalingsmure står på Om kilderne, og en forsinket vurdering står i en besked øverst på siden. Det koster lidt åbenhed på det enkelte kort, men brugeren foretrak den rene liste. AI-overblikket er mindre og kan foldes sammen. Grupperne Sprog, Historier og Periode er fjernet: historier er altid samlet, og perioden vælges over listen, hvor antallet af indslag stod. Perioden er senere afløst af en kalender (se nedenfor). Fravalgt: runde mærker ("piller") i menuerne.

## 2026-10-07: Ingen Claude i sidens tekster

Sidens synlige tekster nævner ikke Claude. Overblik og tidslinje er mærket "AI" og "Kan indeholde fejl", så læserne ved, at teksten er skrevet af en maskine. Kode, docs og routinens instruks nævner stadig Claude, fordi de beskriver, hvordan systemet virker.

## 2026-10-07: Indsamlingen kører efter hvert byg

GitHubs tidsplan for `collect.yml` er ikke kommet i gang. Indsamlingen kører i stedet efter hvert byg af sitet (`workflow_run`), altså hver time i dagtimerne, når routinen har pushet. Det er accepteret, fordi intet alligevel vurderes om natten. Står routinen, står indsamlingen dog også, og så viser feedet advarslen om forældede data.

## 2026-10-07: Fase 3 uden niveau 3 og Via Ritzau

Historier på niveau 3 (rapidfuzz) er udskudt. En måling på feedets 60 kort fandt kun ét par om samme historie med forskellige titler, og det kom fra en kilde, Claude ikke vurderer (`ai: false`). En ny afhængighed og risikoen for forkerte sammenlægninger står ikke mål med det. Genovervej, når der er flere dubletter. Via Ritzau er også udskudt, fordi organisationerne bag pressemeddelelserne i forvejen hentes fra deres egne sider, så kanalen mest ville give dubletter.

## 2026-10-07: Webinar er ikke længere veto

Vetoet "webinar*" afviste også artikler om indholdet af et webinar, fx VANA's om afklaringer af producentansvaret. Relevansprofilen udelukker allerede webinarer og tilmeldinger, så annonceringer sorteres fra af Claude. "tilmeld*" er stadig veto. Samtidig er de kommunale affaldsselskaber med entydige navne (fx BOFA, Reno-Nord, AVØ og Revas) og enkelte private aktører kommet på navnelisten, så lokale nyheder om dem ikke afvises for mangel på affaldsord.

## 2026-10-07: Kalender i stedet for periode

Brugeren ville ikke have tidsvalget 7, 30 og 60 dage over listen. Tidsvalg hører til AI-overblikket, som beholder I dag, Ugen, Måneden og Året. Listen viser hele feedets vindue på 60 dage og bygges, efterhånden som man scroller, så "Vis flere" er væk. En lille kalenderknap over listen åbner en kalender, hvor man vælger første og sidste dag i et tidsrum. Det står i URL'en som `fra` og `til`. Kalenderen følger WAI-ARIA's mønster for datovælgere, så den også virker med tastatur og skærmlæser. Vil man længere tilbage end 60 dage, kræver det, at feedet deles op i månedsfiler. Det bygges først ved et konkret savn.

## 2026-10-08: Kildernes logoer på kortene

Brugeren ville have mediernes egne små logoer på artiklerne, fx TV 2's. Indsamlingen henter hver kildes favicon efter kilderne i hver kørsel (højst 20 ad gangen) og tjekker dem igen hver 30. dag. Logoerne ligger i `data/state/logos/`, hvor indsamlingen i forvejen må skrive, og vises fra sitets eget domæne. Læserne sender derfor ingen forespørgsler til medierne. Kun rasterbilleder gemmes, aldrig SVG, fordi en SVG kan indeholde scripts. Har en kilde intet brugbart logo, står afsendertypens ikon som før. Fravalgt: at hente logoerne direkte fra medierne i læserens browser (sporing og ustabilt) og tjenester som Googles favicon-API (afhængighed og sporing).

Efter de første kørsler manglede Folketingets og HOFOR's logoer, og TV 2-regionernes var forkert. TV 2-regionerne samler otte stationer, så alle kortene viste TV2 Nords ikon. Nu får en kilde med `domains` på andre sites end forsiden et logo pr. site, og kortet vælger efter artiklens domæne. HOFOR's robots.txt forbyder mappen med deres ikoner, og de forbudte ikoner brugte alle tre forsøg, så `/favicon.ico` aldrig blev prøvet. Et forbudt ikon tæller nu ikke som forsøg. Folketingets forside er bag en Cloudflare-udfordring, som aldrig omgås, så Folketinget beholder afsendertypens ikon. Et forsøg med ikonet fra `oda.ft.dk`, hvor data i forvejen hentes, gav et generisk dokumentikon og er droppet igen. Derfor fjerner en varig fejl nu også et gammelt logo, så et forkert logo ikke hænger ved i 30 dage.

## 2026-10-08: Omdirigeringer tjekkes mod robots.txt

Hentningen fulgte omdirigeringer uden at tjekke målet mod robots.txt. Et link til en tilladt adresse kunne derfor ende på en side, robots.txt forbyder, fx når `/favicon.ico` sender videre til en forbudt mappe. Nu følger hentningen selv højst fem omdirigeringer, og hvert skridt skal være tilladt i sin værts robots.txt og overholde værtens takt. Er robots.txt på målet utilgængelig, springes værten over i kørslen, ligesom når den hentes direkte.

## 2026-10-08: Dækningen af affaldsnyheder

Brugeren spurgte, om feedet får alle relevante affaldsnyheder med, også fra brede medier som TV 2. Svaret var nej, og målingen viste fire huller.

Forfiltret afviste fem relevante artikler på et døgn, fx "Nu skal over 14.000 skraldespande skiftes ud" fra TV2 ØST og to artikler om strejker hos Marius Pedersen. Ordlisten kendte kun "skrald" som helt ord, og "genanvend*" ramte ikke sammensatte ord som "madrasgenanvendelse". Nu matcher `skrald*` og `*genanvend*`, og losseplads, renovatør, kluns, pantflasker, emballageforordningen og tøjindsamling er kommet på listen sammen med Marius Pedersen og Meldgaard. En simulering på alle afviste artikler fik de fem med uden at tage nye irrelevante med, og ingen kandidater faldt fra.

TV 2's feeds er udvalgte lister med 50 artikler fra op til en uge, ikke alt, hvad TV 2 udgiver. Der findes intet sitemap, og feeds for samfund, politik og krimi svarer 500. Business-feedet er tilføjet, fordi en artikel om affaldsgebyrer kun stod der. TV 2's sektionssider viser omkring 30 nye artikler hver og kunne give næsten fuld dækning, men TV 2's robots.txt spærrer for AI-robotter, så det afventer brugerens beslutning. Indtil da fanger nyhedssøgningen og sweepet resten.

DR's, TV 2-regionernes og Berlingskes feeds dækker det meste: hvert feed har de nyeste artikler, og kørslerne når dem, før de ryger ud af feedet. Af de 40 nyeste i TV 2 Fyns og Berlingskes nyhedssitemaps kendte indsamlingen 33 og 37. De manglende var for nye, sport eller forbrugerstof. DR's Viden- og Politik-feeds er tilføjet.

Nyhedssøgningen er tynd. Google News er spærret af sin robots.txt, og Bing giver omkring 25 resultater pr. runde for alle søgninger tilsammen, hvoraf hvert fjerde handler om affald. Bing fandt dog seks TV 2-artikler, som TV 2's egne feeds ikke havde. To nye søgninger dækker ordene, der manglede. Berlingskes RSS-links har `?referrer=RSS`, så samme artikel fik to id'er alt efter, om den kom fra feedet eller søgningen. Parameteren fjernes nu i `normalize_url`.

## 2026-10-08: Lokalaviserne hentes direkte

Brugeren savnede lokalmedier som Vejle Amts Folkeblad og Horsens Folkeblad og bad om en gennemgang af alle kommuner. Aviserne stod i `config/medier.yaml`, men blev kun fundet via Bing-søgningen, som giver omkring 25 resultater pr. runde for hele landet. Derfor kom deres artikler næsten aldrig med.

Nu hentes 20 regionale og lokale aviser direkte: 13 dagblade fra Jysk Fynske Medier via deres dagssitemaps, Nordjyske via ugesitemaps, Sjællandske Medier (sn.dk) og Lolland-Falsters Folketidende via deres sitemaps, Bornholms Tidende via RSS og Herning Folkeblad, Midtjyllands Avis og Skive Folkeblad via forsiden. En prøvekørsel fandt straks 15 artikler med affaldsord fra de seneste to uger, som feedet ikke havde, fx "14.000 skraldespande fik for mange bank" (Sjællandske Medier), fire om Refa og skraldebiler (Folketidende) og en om Nordværk (Nordjyske). Claude vurderer dem som alle andre.

Indsamleren er udvidet generelt: `{dato}` i en sitemap-URL henter dagens og gårsdagens sitemap, et indeks uden lastmod sorteres efter datoen i URL'en, perioder før vinduet springes over, og procentkodede URL'er afkodes. De fleste aviser fravælger AI-træning i robots.txt, men ikke almindelige læsere, så samme princip som for DR og TV 2 gælder: Indsamleren er ikke en AI-crawler, og Claude ser kun titel og uddrag. Aviserne får ingen faste steder, fordi de dækker flere kommuner. Stederne kommer fra titlen og Claudes vurdering.

Endnu ikke dækket direkte: Jysk Fynske Mediers ugeaviser på `ugeavisen.dk` og Din Avis (`dinavis.dk`) har hverken feed eller brugbart sitemap. De findes stadig via søgningen. (Løst samme dag, se næste afsnit.)

## 2026-10-08: Ugeaviser og netaviser hentes direkte

Efter dagbladene blev ugeaviser og netaviser kortlagt for alle 98 kommuner. Kortlægningen fandt 184 lokale og regionale medier, og alle med et kendt domæne blev afprøvet fra GitHub Actions med `find-feed`, sitemap og forside. Før i dag blev ingen af de 184 hentet direkte, og efter dagbladene var det 56. Nu er det 157. Ti findes stadig kun via søgningen, og 17 dækkes ikke. Oversigten pr. kommune og grundene står i `docs/LOKALMEDIER.md`.

Der er 61 nye kilder: 36 via RSS, 10 via sitemaps og 15 via forsiden. To fund dækker mange titler på én gang. Jysk Fynske Mediers ugeaviser ligger alle på `ugeavisen.dk`, som har samme dagssitemap som dagbladene, og Din Avis har ét RSS-feed for alle sine lokalaviser. LIV-aviserne i København har annoncørbetalt indhold i sitemappet, så deres `match` udelukker `/annoncorbetaltindhold/`. Dagbladenes sitemaps havde intet af den slags i stikprøven.

Troværdighedskravene gælder stadig. Netaviser, hvor kortlægningen ikke kunne finde en navngiven redaktør eller en henvisning til Pressenævnet, er ikke med, og det gælder også et net af syv netaviser, der ser ud til at dele indhold. To poster i `medier.yaml` var ikke aviser: thisted-dagblad.dk samler annoncørbetalte indlæg, og aars.dk er en foreningsside. De er fravalgt med en note.

Kortlægningen er ikke komplet. Loftet på 200 websøgninger pr. tur blev nået, så i 65 kommuner er der kun søgt efter de store mediehuses titler. Uafhængige netaviser kan mangle der.

Probe-workflowet tabte et resultat, fordi to kørsler skrev `probe/result.md` samtidig og fik en konflikt ved `git pull --rebase`. Commit-trinnet lægger nu resultatet oven på grenens nyeste udgave i stedet.
