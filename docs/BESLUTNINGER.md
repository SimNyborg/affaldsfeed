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

Brugeren bad om en enklere side. Knappen til mørk tilstand er fjernet, så siden følger enhedens farvetema. Headeren har ingen undertitel, "Om kilderne" står kun i footeren, og linket "Om afsendertyperne" er væk. Menuen har foldbare grupper, og alle lister er afkrydset fra start, så et fjernet flueben skjuler. Hver gruppe undtagen Sted har én knap, der skifter mellem "Fravælg alle" og "Vælg alle" (Sted fik også knappen 8. oktober, se nedenfor). Kortene viser kun kildens navn, fx "Folketinget" i stedet for "Folketinget · Myndighed · Folketingssag". Afsendertype, ejer, genre, betalingsmur og "Ikke vurderet" står ikke på kortene, og linjen med sted og temaer under artiklerne er væk. Betalingsmure står på Om kilderne, og en forsinket vurdering står i en besked øverst på siden. Det koster lidt åbenhed på det enkelte kort, men brugeren foretrak den rene liste. AI-overblikket er mindre og kan foldes sammen. Grupperne Sprog, Historier og Periode er fjernet: historier er altid samlet, og perioden vælges over listen, hvor antallet af indslag stod. Perioden er senere afløst af en kalender (se nedenfor). Fravalgt: runde mærker ("piller") i menuerne.

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

## 2026-10-08: Nationale medier og lokalmedier er to afsendertyper

Med de mange nye lokalaviser rummede afsendertypen Nyhedsmedie over 90 kilder, og brugeren bad om at få nationale medier og lokalmedier delt op. Nyhedsmedie hedder nu Nationalt medie (landsdækkende medier og Ritzau), og den nye type Lokalmedie samler regionale dagblade, TV 2-regionerne, ugeaviser og lokale netaviser. Menuen, kildelisten og Om kilderne deler sig af sig selv, fordi de grupperer efter afsendertype.

Id'et `nyhedsmedie` er beholdt, så gemte filtre og data ikke skal flyttes. DR er et nationalt medie, selvom det har regionale redaktioner. De to typer deler farve, fordi en niende farve med mindst 20 i farveafstand til alle de andre kun findes som neongul eller næsten sort. Lokalmedie har i stedet sit eget ikon, en avis med kortnål, og `tools/check_colors.py` måler søskende med samme farve som én farve. De to typer har samme rang, når en historie har flere kilder.

## 2026-10-08: En kilde er først tavs efter 30 dage

Om kilderne viste "tavs i lang tid" ved de 61 lokalmedier, der kom til samme dag, fordi reglen kun så på, om en kilde havde haft indslag de seneste 30 dage. Kilden får nu en startdato (`since`) ved sin første vellykkede kørsel og kan først kaldes tavs, når den er fulgt i 30 dage. Feedet har kun kørt siden 7. oktober, så etiketten forsvinder også fra de ældre kilder og kommer først igen fra november.

## 2026-10-08: Vælg alle under Sted

Brugeren ville også have knappen "Vælg alle"/"Fravælg alle" under Sted. Den virker som i de andre grupper: "Fravælg alle" fjerner fluebenene ved regionerne og "Landsdækkende", og ét flueben viser derefter kun den region. "Vælg alle" viser alle steder igen og fjerner også de kommuner og byer, der er valgt i søgefeltet. Før havde Sted ingen knap, fordi et sted valgt i søgefeltet allerede viser kun det sted. Det gjorde Sted anderledes end de andre grupper.

## 2026-10-08: Kildernes afsendertyper er foldet sammen, og "Alle" er væk fra menuen

Med 153 aktive kilder var listen under Kilde lang. Brugeren bad om, at afsendertyperne starter foldet sammen, så man har overblik og selv folder dem ud. Søger man i "Find kilde", foldes de typer ud, der har et træf.

Brugeren bad også om at fjerne "Alle" fra gruppernes overskrifter, fordi pilen er nok til at vise, at man kan folde ud. En status står nu kun, når en gruppe eller en afsendertype er filtreret, fx "Ingen" eller "5 af 17". Så kan man stadig se et filter i en gruppe, der er foldet sammen.

## 2026-10-09: Ingeniøren, Videnskab.dk og Danwatch er fagmedier

Brugeren bad om at flytte de tre fra Nationalt medie til Fagmedie. De er landsdækkende, men dækker hvert sit fagområde: teknik, videnskab og undersøgende journalistik om virksomheder og miljø. Reglen i KILDER.md siger nu, at et medie med et fagområde er et fagmedie, også når det er landsdækkende, og Fagmedies hjælpetekst nævner teknik, videnskab og miljø. Som fagmedier står de før de nationale medier, når flere kilder dækker samme historie.

## 2026-10-09: Kommunernes egne nyheder og alle otte universiteter

Brugeren savnede kommunernes egne hjemmesider og flere universiteter, fx DTU. Indtil nu hentede feedet kun de kommunale affaldsselskaber og ingen kommuner. Nu hentes 89 af de 98 kommuner, de fleste via sitemappet med et mønster for nyhederne. Oversigten står i [KOMMUNER.md](KOMMUNER.md).

Kommunerne skriver mest om andet end affald, så de har strengt filter, og indsamleren henter kun en nyhed, når adressen eller linkteksten har et affaldsord. Det holder antallet af kald nede, men en nyhed med en adresse uden affaldsord bliver ikke hentet. Søgningen og routinens søgning efter oversete nyheder dækker en del af det hul.

Ritzaus nyhedsrum (via.ritzau.dk) har et RSS-feed pr. afsender. Det bruges nu til DTU, Aalborg Universitet, IT-Universitetet og Esbjerg Kommune, fordi deres egne sider ikke kan hentes generisk. Den samlede Via Ritzau-kanal for alle pressemeddelelser er stadig udskudt. Her bruges kun nyhedsrummet for afsendere, hvis egen side ikke kan hentes, så det giver ingen dubletter.

Ni kommuner kan ikke hentes generisk. Tre har botbeskyttelse, to svarer ikke fra GitHub Actions, og fire har en nyhedsliste, der kræver JavaScript, eller ingen nyheder i sitemappet. De står som kandidater med en note.

## 2026-10-09: Sociale medier afventer

Brugeren bad om en kategori for sociale medier, der står i menuen, men ikke kan vælges. Den hedder Sociale medier og har `pending: true` i `config/categories.yaml`. Under Afsender har den en låst afkrydsning og "Afventer", hvor tallet ellers står. Under Kilde og på Om kilderne står den også med "Afventer". Den er ikke et valg, så "Vælg alle", "Fravælg alle" og status ser bort fra den, og `check` fejler, hvis en aktiv kilde får kategorien.

De fleste sociale medier kræver login og har intet åbent feed, og projektet omgår aldrig login. Bluesky, Mastodon og YouTube har åbne feeds og er de oplagte steder at begynde. Før kategorien tages i brug, skal to ting afgøres: om fx en kommunes opslag hører under Sociale medier eller under kommunen, og hvilken farve kategorien skal have. Paletten har ikke plads til en farve mere, der kan skelnes tydeligt fra de andre (se DESIGNMANUAL.md), så kategorien er grå indtil da. Den har den laveste rang for primærkilde, så et opslag aldrig står over en artikel om samme sag.

## 2026-10-09: De kommunale affaldsselskaber

Brugeren bad om de kommunale affaldsselskaber, der manglede, fx Kredsløb, Fors, Reno Djurs og BOFA. Udgangspunktet er medlemslisten hos brancheforeningen Cirkulær (tidligere Dansk Affaldsforening) med 63 medlemmer. De medlemmer, der ikke blev hentet i forvejen, og som hverken er kommuner eller færøske, er afprøvet fra GitHub Actions, og 34 selskaber er kommet til. Feedet henter nu 45 selskaber. Oversigten står i [AFFALDSSELSKABER.md](AFFALDSSELSKABER.md).

Selskaberne får deres ejerkommuner som faste steder, så deres nyheder kan findes med stedfiltret. Det gælder også de ni selskaber, der var med i forvejen, når ejerne er bekræftet. Rene affaldsselskaber har intet filter, forsyninger med vand, spildevand eller varme har normalt filter, og Fjernvarme Fyn har strengt filter, fordi selskabet mest skriver om fjernvarme. Ritzaus nyhedsrum bruges til Silkeborg Forsyning, DIN Forsyning, Assens Forsyning og Fors, fordi deres hjemmesider ikke har et feed eller et sitemap med datoer.

Fors, Norfors, Nomi4s og Energnist er gået fra kandidat eller fravalgt til aktiv. Kredsløb har stadig botbeskyttelse, Langeland Forsyning har en captcha, og Reno Djurs, BOFA, Motas, Deponi Syd og Ressourceindsamling har ingen nyheder på hjemmesiden. De står med en note og kan prøves igen senere.

## 2026-10-09: Hele 2026 i feedet

Brugeren bad om nyhederne fra alle kilder for hele 2026, dag for dag, og derefter de nye hver dag. Feedet rækker nu tilbage til 1. januar 2026. Datoen står som `window_start` i `config/settings.yaml`, og hver kilde hentes én gang bagud dertil (KONTRAKTER §5.8). Det afløser vinduet på 60 dage fra 2026-10-07 (Kalender i stedet for periode).

Bagudindsamlingen kører i de almindelige timekørsler. En kilde, der har mere, end der kan hentes i én kørsel, fortsætter hver time efter de andre kilder, så nye nyheder ikke venter på den. Sitemaps for afsluttede dage, uger og måneder læses kun én gang. Routinen vurderer de gamle indslag sammen med de nye, nyeste først, og har nu 14 dage til køen i stedet for 72 timer. Ellers kunne de ældste indslag nå at falde ud af køen, før de blev vurderet.

Hvor langt tilbage en kilde kan hentes, afhænger af kilden:
- Sitemaps med datoer går hele året tilbage. Det gælder de fleste kommuner, mange affaldsselskaber og de 18 aviser fra Jysk Fynske Medier, der har ét sitemap pr. dag. De gamle dagssitemaps er afprøvet fra GitHub Actions.
- Folketingets åbne data går hele året tilbage.
- RSS-feeds rummer kun de seneste 10 til 50 indslag, så de fleste nationale medier giver kun de seneste uger.
- Nyhedslister på hjemmesider giver kun det, der står på listens første side.
- Søgning hjælper ikke bagud. Google News blokerer indsamleren i robots.txt, og Bing News går kun omkring 30 dage tilbage og kan ikke søge i et tidsrum.

Januar til september bliver derfor tyndere for de nationale medier end for kommuner, affaldsselskaber og lokalaviser. Det kan ikke løses generisk uden at omgå en spærring, og det gør projektet ikke.

Artikler, som de første kørsler i oktober hentede og afviste som for gamle, står som sete. Ved kildens første bagudkørsel glemmes de sete adresser, der ikke blev til en kandidat, så de hentes igen. Gamle indslag, som forfiltret afviser, gemmes ikke i `data/rejected/`, for et års dagssitemaps ville ellers give flere titusinde poster dér.

`feed.json` er stadig én fil. Med et helt år bliver den større, anslået 2 til 3 MB. Komprimeret med gzip, som GitHub Pages bruger, fylder den omkring en femtedel, og listen viser kun 60 kort ad gangen. Bliver siden for langsom, deles feedet op i månedsfiler.

## 2026-10-09: Tidslinjen fyldes bagud til januar

Med hele 2026 i feedet skal tidslinjen også dække hele året. Den første fyldning den 7. oktober så kun 60 dage tilbage, og de daglige kørsler ser kun tre dage, så både januar til juli og de indslag fra august til oktober, som bagudindsamlingen finder nu, ville aldrig komme med.

Routinen fylder derfor tidslinjen bagud, én måned pr. kørsel fra januar til oktober (`timeline.fill_until`). En måned er først klar, når alle kilder uden fejl er hentet bagud, og routinen har vurderet månedens indslag. Ellers ville tidslinjen bygge på et halvt billede. Routinen markerer hver måned som fyldt med `timeline-input --fill-done`, også når den ikke fandt nogen store begivenheder, så den ikke tager den samme måned igen. Reglerne for, hvad der kommer på tidslinjen, er de samme som ellers. Det koster omkring ti ekstra trin i routinen i alt.

## 2026-10-09: Kommune/affaldsselskab i menuen

Brugeren bad om at omdøbe afsendertypen "Kommunal" til "Kommune/affaldsselskab". Det korte navn, som står i menuen, på mærkerne over listen og hos skærmlæsere, er nu "Kommune/affaldsselskab". Det fulde navn på "Om kilderne" er stadig "Kommune og affaldsselskab". Det følger de andre typer, der har "og" i det fulde navn og skråstreg i det korte, fx "Tænketank og NGO" og "Tænketank/NGO". Id'et `kommunal` er uændret, så links og data virker som før.

## 2026-10-09: Fanen Højdepunkter

Brugeren bad om at kalde tidslinjen Højdepunkter. Menupunktet, sidens titel og overskriften hedder nu Højdepunkter, og siden er stadig en tidslinje. Adressen `tidslinje.html` er den samme, så links, der allerede er delt, virker. Internt hedder den stadig tidslinjen: `data/timeline/`, `timeline-input` og routinens trin 7 og 7b.

## 2026-10-09: Sitemaps må være længere om at svare

Det daglige tjek viste, at Herning Kommunes sitemap gav timeout ved hver kørsel. Serveren danner sitemappet ved hver forespørgsel og var 24 sekunder om det første gang og 7 sekunder lige efter, mens indsamleren gav op efter 20 sekunder. Gribskov og Hedensted gav også timeout i drift, men svarede i afprøvningen. Sitemaps og listesider må derfor nu være 45 sekunder om at svare (`pages.doc_timeout_seconds`), mens artikelsider og feeds stadig har 20 sekunder. Det sker inden for kildens tidsbudget, så en langsom server kan ikke holde en kørsel hen.

## 2026-10-09: Dag for dag i listen

Brugeren ville ikke have ugegrupper som "Uge 40 · 28. september–2. oktober", når man går tilbage i tiden. Listen har nu én overskrift pr. dag hele vejen tilbage: "I dag", "I går" og derefter fx "Mandag 28. september". Dage fra et andet år får årstallet med. Under sin egen dags overskrift viser kortet kun klokkeslættet, også for gamle indslag. Med hele 2026 i feedet giver det mange overskrifter, men listen viser stadig kun 60 kort ad gangen.

## 2026-10-13: Routinen kører tre gange om dagen

Routinen stod stille fra 10. oktober kl. 00.25 til 13. oktober kl. 23.00, fordi abonnementets ugegrænse var nået. Hver kørsel blev afvist med "You've hit your weekly limit". Udviklingssessionen bruger af samme grænse, og den havde brugt meget i dagene før. En kørsel kostede omkring 0,46 dollar efter API-priser, og routinen kørte 19 gange i døgnet. Brugeren bad om kørsler kl. 7.30, 9.00 og 14.00. En routine kan kun køre på samme minut i hver time, så den kører nu kl. 07.25, 09.25 og 14.25 dansk tid (`CRON_TZ=Europe/Copenhagen 25 7,9,14 * * *`), og `routine.hours` er `[7, 9, 14]`. Sweepet kører kl. 07.25 og 14.25, og tidslinjen skrives kl. 14.25 i stedet for kl. 22. Prisen er, at en nyhed fundet om eftermiddagen først kommer på siden næste morgen. Routinen er oprettet på claude.ai, så kun brugeren kan ændre dens tidsplan. Derfor stopper en kørsel straks, når klokken ikke er 07, 09 eller 14 (trin 1). Det koster næsten intet og gør ændringen sikker, også før tidsplanen er rettet.

## 2026-10-13: Småtekst samlet bag en i-knap

Brugeren ville have en enklere side med al småtekst ét sted. Beskederne om forsinket vurdering og forældet feed, overblikkets note om forsinkelse, "bygget på N indslag" og teksten om AI under overblikket og på Højdepunkter er fjernet, og det samme er footeren. AI-overblikket hedder nu "Nyhedsoverblik senest opdateret fredag kl. 23.28". En diskret i-knap i headeren åbner "Om Affaldsfeed" med AI, opdatering og klager og sletning. Brugeren ville ikke have teksten om hobbyprojekt med, så den og linket til GitHub er væk, og linket til Om kilderne står i det første afsnit. Panelet siger også, at feedet aldrig omgår betalingsmure. Klager og ønsker om sletning går til jhn@jhn.dk, og opslag og kilder fjernes inden for 24 timer. Et opslag skjules med `config/overrides.yaml`, og en kilde tages af listen med `status: fravalgt` i `sources.yaml`.

AI-forordningens artikel 50, stk. 4, gælder fra 2. august 2026. Den kræver, at AI-genereret tekst, der skal informere offentligheden om forhold af offentlig interesse, er tydeligt mærket, medmindre et menneske har redaktionelt ansvar for den. Overblikket og højdepunkterne er AI-skrevne og ikke gennemlæst, og nu står det kun i i-panelet. Det er usikkert, om det er tydeligt nok. Et lille synligt "AI" ved overskriften vil fjerne tvivlen.

## 2026-10-14: Previews med egne ord

Brugeren ville ikke have kildens tekst kopieret ordret på siden. Feedet viser derfor aldrig kildens egen teaser. Previewet under titlen er et kort resumé, som routinen skriver med egne ord ud fra titel og teaser og uden menneskelig indgriben. Nye indslag får det sammen med vurderingen (`summary_da`). De ældre indslag, omkring 480 ved skiftet, får det i portioner på 150 pr. kørsel fra `data/judgments/resumeer/`. Kontrollen i `validate-judgments` og `validate-summaries` afviser et resumé, der deler mere end fem ord i træk med teaseren, eller hvor over halvdelen af ordtrioerne står i den. Indtil et indslag har et resumé, vises kun titlen. Det gælder også kilder med `ai: false`, som Claude ikke læser.

To ting står tilbage. Kildernes egne teasere ligger stadig i `data/candidates/` i det offentlige repo, fordi routinen skal bruge dem. Og omformuleringen er netop den brug af AI, som 27 kilder har taget forbehold for (gennemgangen af kildernes vilkår 13. oktober). Brugeren bad om ikke at ændre kilderne ud fra gennemgangen, så det er uændret.

## 2026-10-14: Afsender og Kilde er én gruppe i menuen

Menuen havde to grupper, der viste det samme: Afsender med afsendertyperne og Kilde med kilderne delt op efter afsendertype. Brugeren bad om at slå dem sammen. Nu er der én gruppe, Kilde, med en række pr. afsendertype. Typens flueben vælger eller fravælger alle dens kilder, og en pil til højre folder typen ud, så man kan vælge enkelte kilder. Er kun nogle af kilderne valgt, er fluebenet halvt sat. Gruppen står lige under Sted, hvor Afsender stod.

URL'en er den samme, så gamle links virker: `afsender=` gælder hele typer og `kilde=` enkelte kilder, og en kilde vises, når begge viser den. Siden skriver den korteste form, fx `afsender=-kommunal` for alt undtagen kommuner og affaldsselskaber eller `kilde=dr-nyheder` for kun DR. Én slags valg har ingen kort form: næsten alt og kun én kilde fra en stor type, fx kun Nyborg Kommune fra Kommune/affaldsselskab. Det giver 133 fravalgte kilder i URL'en (omkring 2.300 tegn) og mærket "Uden 133 kilder". Linket virker. En ny parameter for "også denne kilde" ville gøre det kort, men den venter, til der er et konkret savn. Fravalgt: at et klik på typens navn folder den ud, fordi navnet i alle andre rækker sætter fluebenet.

## 2026-10-14: Resuméer til de ældre indslag skrevet på én gang

Brugeren ville have previews på de gamle artikler med det samme i stedet for at vente på routinens 150 pr. kørsel. Udviklingssessionen skrev derfor resuméer til alle 479 indslag i køen efter routinens regler og med samme kontrol mod kopiering. Linjerne har `by: "claude-udvikling"`, så de kan skelnes fra routinens. Det er en bevidst undtagelse fra reglen om, at udviklingssessioner ikke committer data, de selv har lavet.

20 af teaserne beskrev ikke artiklen. Det var fx sidens standardtekst, en omtale af afsenderen, en liste af stikord, et spørgsmål til læseren eller "Indlægget ... blev først udgivet på ...". Et resumé ud fra dem ville handle om noget andet end artiklen. De har fået `summary_da: null`, som er nyt i kontrakten (§6.2a): kun titlen vises, og indslaget kommer ikke i køen igen. Routinen bruger samme regel for nye indslag.

Efter skiftet har 404 af 711 kort et preview. De 307 andre viser kun titlen: 181 er fra de fire kilder med `ai: false` (CleanTech Watch, EnergiWatch, Kommunen og Teknik & Miljø), 106 har ingen eller en meget kort teaser, og 20 har en teaser uden indhold.

## 2026-10-14: Medier med forbehold vises kun med overskrift, og fem afventer

Gennemgangen af kildernes regler 13. oktober viste, at feedet stadig hentede fra alle 23 medier, der ifølge deres egne vilkår ikke må bruges sådan, og at Claude læste og omskrev tekst fra medier med forbehold mod AI og tekst- og datamining. Brugeren besluttede, at et medie kun udelukkes, når reglerne forbyder selve brugen. Hvor problemet er AI eller kopiering af tekst, bliver mediet med som overskrift og link.

- **Afventer (5):** DR, Politiken, Din Avis, Folketidende og Dragør Nyt forbyder udtrykkeligt nyhedsoversigter for andre, en systematisk samling af links eller automatisk indsamling. De hentes ikke, deres gemte data slettes, og menuen viser dem låst nederst i deres type med "Afventer" (KONTRAKTER §3.4 og §9).
- **Kun overskrift (46):** de 18 aviser fra Jysk Fynske Medier, 22 medier med forbehold mod tekst- og datamining (fx Berlingske, TV 2, Ingeniøren, Altinget og CleanTech Watch), 5 medier, der kun spærrer AI-crawlere i robots.txt (fx Sjællandske Medier og Nordjyske), og WasteTech. Brugeren gav lov til, at Claude læser overskriften for at sortere, om den handler om affald. Alt andet fra artiklen bliver væk: ingen teaser i data, intet resumé, ingen begrundelse i `feed.json`, og indslagene indgår ikke i nyhedsoverblikket og højdepunkterne. Brugeren valgte bevidst Claude på overskriften frem for kun søgeord, også for JFM, hvis vilkår kræver en skriftlig aftale om tekst- og datamining. Uden Claude ville omkring 155 irrelevante kort komme med.
- **Bing-søgningen er fravalgt:** Microsofts vilkår (Services Agreement 14.f.i) tillader kun ikke-kommerciel, personlig brug af materiale fra Bing. Det kostede 11 kort, heraf to fra B.T. og Bygtek, som kun blev fundet via Bing.
- **WasteTech er med:** Danmarks eneste rene affaldsfagmedie stod som kandidat, fordi det ligger bag betalingsmur og fravælger AI. Afprøvningen 14. oktober viste, at sitemappet giver titel og dato, og at robots.txt tillader feedet. Teknologiens Mediehus tillader links.
- **CleanTech Watch** hentes nu kun fra sektionen Affald. Det brede `match` tog også sektionssiden med som et kort, og da Claude ikke læste kilden, var der ingen vurdering til at fange det. Kildens 224 artikler venter nu på Claudes vurdering af overskrifterne og forsvinder fra feedet, til den er sket.

Den gamle tekst i repoet er ryddet. Indsamlingen rydder `data/candidates/` og `data/rejected/` ved hver kørsel (`store.scrub_stored`). Udviklingssessionen fjernede én gang 22 vurderinger af indslag fra de fem medier, satte `summary_da` til `null` i 68 vurderinger og slettede 100 resumélinjer, heraf 83 fra sessionens egne resuméer 13. oktober. Det er en undtagelse fra reglen om, at kun routinen skriver i `data/judgments/`. Det, der ligger i repoets historik, er ikke fjernet, og overblik og højdepunkter skrevet før skiftet kan stadig nævne indslag med kun overskrift, til de bliver skrevet på ny.

Det er en vurdering ud fra kildernes egne regler, ikke juridisk rådgivning. Overskrift og link er det, medierne selv tillader, men en automatisk samling af avisoverskrifter kan stadig støde mod deres rettigheder. Newsbooster fik i 2002 fogedforbud mod systematisk at vise danske avisers overskrifter med dybe links, men den tjeneste var kommerciel og konkurrerede med aviserne. Kun en tilladelse gør det sikkert, så brugeren skriver til JFM og Teknologiens Mediehus.

## 2026-10-14: Fire institutter med affaldsforskning som egne kilder

Brugeren spurgte, om universiteternes institutter har nyheder, som de fælles nyhedslister ikke får med, fx et DTU-institut for miljø. Alle otte universiteter blev gennemgået (se KILDELISTE.md, "Universiteternes institutter"). Fire institutter kom med: DTU Sustain, DTU Kemiteknik, Københavns Universitets Institut for Fødevare- og Ressourceøkonomi (IFRO) og Aarhus Universitets Institut for Byggeri og Bygningsdesign. De har normalt filter, fordi de skriver om færre emner end universiteterne som helhed. Så er et svagt ord som plast eller ressource nok til, at Claude ser nyheden. DTU Kemiteknik skriver på engelsk og mest om andet end affald og har derfor strengt filter.

- **DTU:** Nyhedslisterne hentes med JavaScript, men institutternes forsider viser de nyeste nyheder som almindelige links. Feedet læser forsiden og får derfor kun de nyheder, der står der, når den hentes. Bagudindsamlingen når kun de fire nyeste fra DTU Sustain og de to nyeste fra DTU Kemiteknik. DTU's robots.txt beder om 10 sekunder mellem kald, og det overholder indsamleren.
- **Delt vært:** IFRO ligger på www.ku.dk ligesom Københavns Universitets nye hjemmeside. `check` advarer, når to aktive kilder deler vært, fordi søgeresultater og sweep-fund kun kan gå til én af dem. Advarslen gælder ikke længere, når den ene kildes `owner` er den andens navn, eller når de har samme `owner` (KONTRAKTER §3.1). Fund på www.ku.dk går til Københavns Universitet, som står først i filen.
- **Madspild:** "madspild*" er nu et svagt ord i forfiltret. IFRO's nyhed om madspild i butikker fik 0 point, selv om temaet Mad- og bioaffald nævner madspild. Ordet ramte kun ét afvist indslag i oktober, så det giver næppe mere støj.
- **CBS' artikler:** CBS' institut for ledelse, samfund og kommunikation (MSC), hvor forskningen i bæredygtighed og cirkulær økonomi hører til, viser CBS' fælles nyheder. Sitemappet rummer også CBS' artikler (forskningsbaserede tekster). De kom med under samme strenge filter som nyhederne.
- **Ikke med:** Aalborg Universitets institutter, bl.a. DCEA, er relevante, men deres nyhedslister hentes med JavaScript fra et API. De står som kandidater sammen med to institutter, hvis RSS virker, men som ikke har skrevet om affald i flere år.

## 2026-10-14: Højdepunkterne fyldes bagud uden at vente på medier med kun overskrift

Brugeren så kun højdepunkter fra de seneste to måneder. Opfyldningen bagud havde ikke taget en eneste måned, fordi den ventede på bagudindsamlingen hos 16 aviser fra Jysk Fynske Medier. Deres daglige sitemaps hentes et par uger ad gangen, så det ville tage flere dage endnu. Ventetiden var spildt: aviserne vises kun med overskrift, og deres indslag kommer aldrig på tidslinjen.

- **Kun kilder med `ai: true` tæller:** Opfyldningen venter kun på bagudindsamlingen og routinens vurderinger hos de kilder, hvis indslag kan komme på tidslinjen (KONTRAKTER §7.3).
- **Op til fire måneder pr. kørsel:** Hver måned er 20-70 kB input til routinen. Med én måned pr. kørsel og tre kørsler om dagen ville januar til oktober tage over tre dage. Med fire er de fyldt i løbet af et døgn.
- **Routinens prompt:** Prompten på claude.ai giver routinen lov til kun at skrive i `data/judgments/` og `data/overview/`, selv om instruksen også beder den skrive tidslinjen. Routinen skrev alligevel tidslinjen 7. og 8. oktober, men modstriden kan få den til at springe trinnet over. Brugeren retter prompten, så den også nævner `data/timeline/`, og tidsplanen fra hver time til kl. 7.25, 9.25 og 14.25, hvor routinen alligevel kun arbejder. En udviklingssession kan ikke ændre en routine, som brugeren har oprettet.

## 2026-10-14: Siden Om kilderne er fjernet

Brugeren ville ikke have, at man kan se siden med kilderne. `kilder.html` og dens kode og styling er fjernet, i-dialogen henviser ikke længere til den, og issue-skabelonens link til den er væk. Kilderne står stadig i menuen, fordi man filtrerer på dem, og medier, der afventer tilladelse, står stadig låst nederst i deres type. Kildernes sundhed kan følges i `data/status.json`, som eksporten stadig skriver, og i `data/state/sources.json`.

## 2026-10-14: Højdepunkterne for januar til september skrevet på én gang

Brugeren ville have højdepunkter for hele 2026 med det samme og ikke vente på, at routinen fyldte månederne bagud over det næste døgn. Udviklingssessionen gennemgik derfor de 506 godkendte historier fra januar til oktober efter routinens regler (REDAKTOER.md, trin 7) og skrev 21 nye begivenheder, så Højdepunkter nu har 24. Juli har ingen, og oktober havde allerede sine. Linjerne har `by: claude-udvikling`, alle ti måneder er markeret som fyldt i `data/timeline/opfyldning.json`, og `validate-timeline` er grøn. Det er en undtagelse fra reglen om, at kun routinen skriver i `data/timeline/`, ligesom resuméerne til de ældre indslag. Fremover skriver routinen nye højdepunkter som før.
