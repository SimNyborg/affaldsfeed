# Kilder

Alle kilder står i `sources.yaml` i repoets rod. Her står, hvilke krav en kilde skal opfylde, og hvordan man tilføjer eller importerer kilder. Selve listen står kun i `sources.yaml`.

Startlisten er foreløbig. Den bygger på researchen fra 7. oktober 2026 og har godt 120 poster. Lidt over 40 er aktive RSS-kilder i første version, omkring 40 er planlagt til fase 2, og resten er kandidater eller fravalgt med en begrundelse. Dertil kommer de to søgekilder. Når brugerens egen liste kommer, importeres den som beskrevet nedenfor, og startlisten tilpasses.

## Troværdighedskriterier

En kilde kommer med, når alle fire krav er opfyldt.

1. Kendt afsender. En navngiven organisation, myndighed, institution eller et medie med ansvarlig redaktør eller kontaktperson. Anonyme sider, indholdsfarme og aggregatorer kommer ikke med.
2. Primærkilde. Afsenderen udgiver selv indholdet. Ritzau-telegrammer via Avisen.dk tæller med.
3. Kvalitetsgrundlag (`basis`). Mindst ét af disse: redaktionelt ansvar, offentlig myndighed eller kommunalt ejet selskab, forsknings- eller sektorforskningsinstitution, eller organisation med offentlig ledelse og oplyst finansiering. Virksomheders markedsføring kommer ikke med.
4. Relevant og høflig at hente. Kilden skriver mindst 4 gange om året om affald med betydning for kommuner. En central aktør kan komme med på færre. Den kan hentes uden login, captcha, ALTCHA eller Cloudflare-challenge og med ærlig User-Agent.

Fravalgte kilder bliver stående i registret med `status: fravalgt` og en note. "Om kilderne" viser dem under fravalg med begrundelse.

## De 8 afsenderkategorier

Kategorien hører til kilden og står i registret. Pipelinen gætter den aldrig ud fra teksten.

| id | Navn | Hvem hører til |
|---|---|---|
| `nyhedsmedie` | Nyhedsmedie | lands-, regional- og lokalmedier samt Ritzau-telegrammer |
| `fagmedie` | Fagmedie | fagblade og sektionsmedier om kommuner, forsyning, byggeri og emballage |
| `myndighed` | Myndighed og Folketing | ministerier, styrelser, tilsyn, råd, nævn, Høringsportalen og Folketinget |
| `kommunal` | Kommune og affaldsselskab | kommuner og kommunalt ejede affalds-, forbrændings- og forsyningsselskaber |
| `organisation` | Organisation og branche | interesse- og brancheorganisationer, herunder KL og Danske Regioner |
| `taenketank` | Tænketank og NGO | tænketanke og grønne organisationer |
| `forskning` | Forskning og universitet | universiteter, sektorforskning og godkendte teknologiske serviceinstitutter |
| `eu_norden` | EU og Norden | EU-institutioner og europæiske eller nordiske organisationer |

Regler for kategorierne:
- Hver kilde har præcis én kategori.
- Geografi går forud for type. Zero Waste Europe og CEWEP hører under EU og Norden, og typen står i `note`.
- KL er en organisation. KL's magasin Danske Kommuner er et fagmedie med `owner: KL`.
- Folketinget hører under Myndighed og Folketing. Genren `folketing` skiller sagerne ud.
- Virksomheder er ikke en kategori.

Når flere kilder dækker samme historie, står primærkilden først: myndighed og Folketing, så afsenderens egen kanal (kommunal, organisation, tænketank, forskning, EU og Norden), så fagmedie og til sidst nyhedsmedie.

## Felterne i sources.yaml

Feltnavnene er på engelsk, så de passer til koden. Valideringen sker med pydantic ved hver kørsel og i CI, og en fejl stopper med besked om kilde og felt. Den tekniske definition står i KONTRAKTER 3.1.

| Felt | Påkrævet | Standard | Betydning |
|---|---|---|---|
| `id` | ja | | Unikt id med små bogstaver, tal og bindestreg. Bruges i URL'er og data og ændres aldrig. |
| `name` | ja | | Navnet, der vises på kortet. |
| `category` | ja | | Et af de 8 kategori-id'er. |
| `homepage` | ja | | Kildens forside. Værtsnavnet bruges også til at genkende kilden i søgeresultater. |
| `method` | nej | `rss` | `rss` (også Atom), `sitemap`, `html`, `oda` eller `search`. Første version kan `rss` og `search`. |
| `feeds` | ja | | Én URL eller en liste af URL'er. |
| `domains` | nej | tom | Ekstra værtsnavne til genkendelse i søgeresultater, uden `www.`. |
| `match` | ved `sitemap` og `html` | | Regulært udtryk, som artikel-URL'er skal matche. |
| `select` | nej | | CSS-selektor for links på en html-liste. |
| `filter` | nej | `normal` | Forfiltrets strenghed: `none`, `normal` eller `strict` (se nedenfor). |
| `topics` | nej | tom | Standardtema, når teksten ikke giver et. |
| `genre` | nej | `nyhed` | Standardgenre, fx `hoering` for Høringsportalen. |
| `lang` | nej | `da` | `da`, `en` eller `sv`. |
| `paywall` | nej | `nej` | `nej`, `delvis` eller `ja`. Står på Om kilderne. |
| `owner` | nej | | Udgiveren, hvis det ikke er afsenderen selv, fx KL. |
| `aliases` | nej | tom | Andre navneformer, som bruges til Via Ritzau i fase 3. |
| `every` | nej | efter metode | Timer mellem kørsler. Uden værdi: `rss` 1, `search` 2, `oda` 3, `sitemap` og `html` 6. |
| `bundle` | nej | | `day` samler kildens indslag i ét kort pr. dag (fase 3, tænkt til ODA). |
| `ai` | nej | `true` | `false` betyder, at Claude ikke vurderer kilden. Den vurderes så kun efter regler. |
| `basis` | ved `aktiv` | | Kvalitetsgrundlaget: `redaktionelt`, `offentlig`, `forskning` eller `organisation`. |
| `status` | nej | `aktiv` | `aktiv`, `planlagt` (venter på metode eller test), `kandidat` (venter på beslutning), `pause` eller `fravalgt`. |
| `checked` | ved `aktiv` | | Datoen for seneste vurdering af kilden. |
| `note` | nej | | Fritekst, fx hvorfor kilden er med eller fravalgt. |

## Filterniveauer

Forfiltret giver point for affaldsord og kendte navne i titel og teaser. Ordene står i `config/keywords.yaml`. En veto-liste afviser fx atomaffald, jobopslag og tilmeldinger, og en serviceliste afviser driftsbeskeder fra kommunale kilder. Filtret er bevidst løst. Både de klare og de tvivlsomme indslag gemmes som kandidater, og Claude vurderer dem.

| Niveau | Bruges til | Bliver kandidat | Afvises |
|---|---|---|---|
| `none` | rene affaldskilder, fx affaldsselskaber og Dansk Retursystem | alt, der ikke rammes af veto eller service | veto og service |
| `normal` | fagmedier og organisationer med blandet stof | indslag med mindst 1 point | indslag med 0 point |
| `strict` | brede kilder som landsmedier, universiteter og Danske Regioner | indslag med mindst 2 point | resten |

De præcise point og grænser står i KONTRAKTER 5.4. Afviste indslag gemmes i 90 dage i `data/rejected/` med begrundelse, så filtret kan justeres. `python -m affaldsfeed check --fetch <id> --explain` viser for én kilde, hvad filtret beholder, og hvorfor.

## Sådan tilføjer du en kilde

1. Find kildens feed. `python -m affaldsfeed find-feed <url>` prøver de almindelige steder og rapporterer, hvad den finder. Man kan også selv kigge efter `<link rel="alternate">` i sidens kilde eller adresser som `/feed/`, `/rss` og `/rss.xml`.
2. Tjek kriterierne ovenfor.
3. Tilføj en post i `sources.yaml` under den rigtige kategori:

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

4. Kør `python -m affaldsfeed check --fetch <id> --explain` og justér `filter`, hvis der kommer for meget eller for lidt med.
5. Commit. Det kan også gøres direkte i GitHubs webeditor, så validerer CI posten. Kilden hentes ved næste timekørsel. Første gang gemmes indslag fra de seneste 60 dage som baseline, så de ikke markeres som nye.

Kan kilden ikke hentes med en af de generiske metoder, skrives der ingen specialkode. Den får `status: kandidat` eller `fravalgt` og en note.

## Brugerens egen kildeliste (fase 4)

Listen kan være et regneark eller en CSV med navn og URL, gerne også kategori og note.

1. `python -m affaldsfeed import liste.csv` laver poster med `status: kandidat`. Poster med samme værtsnavn som en eksisterende kilde slås sammen med den.
2. `python -m affaldsfeed find-feed <url>` prøver `<link rel="alternate">`, så `/feed/`, `/rss` og `/rss.xml` og til sidst sitemaps fra robots.txt og `/sitemap.xml`. Den henter én gang og skriver en rapport med antal indslag, nyeste dato og robots-status.
3. `python -m affaldsfeed check --fetch <id> --explain` viser, hvad der hentes, og hvad forfiltret beholder. `filter`, `match` og `select` justeres ud fra det.
4. Kandidaterne sættes til `aktiv` med `basis` og `checked`. Kører man `import` med `--replace`, sættes de kilder, der ikke står på brugerens liste, på pause. Ingen kilder slettes.
5. Denne fil opdateres, og startlisten markeres ikke længere som foreløbig.

## Søgekilder og medier.yaml

Søgekilderne er poster i `sources.yaml` med `method: search`. Deres `feeds` er URL-skabeloner til Google News og Bing News med `{q}`, hvor forespørgslerne fra `config/search.yaml` sættes ind. De står med `category: nyhedsmedie`, men vises aldrig selv som afsender. Hvert fund krediteres udgiveren.

Udgiveren findes ud fra værtsnavnet. Først sammenlignes med `homepage` og `domains` for de aktive kilder i `sources.yaml`, derefter med `config/medier.yaml`. Den fil rummer troværdige udgivere, som kun findes via søgning, fx lokalaviser. Lokalmedierne er samlet ud fra Slots- og Kulturstyrelsens Ugeavispulje og Innovationspulje, medlemmerne af Danske Lokalaviser og lokale netaviser med en navngiven redaktør eller en henvisning til Pressenævnet. Ugeaviser under et fælles domæne, fx `ugeavisen.dk` og `dinavis.dk`, står som én post. De regionale dagblade hentes derimod direkte fra deres sitemaps eller forsider (se nedenfor), fordi søgningen kun finder en lille del af deres artikler. Hver post har `id`, `name`, `category`, `domains`, `basis`, `paywall` og `lang`, og id'erne må ikke gå igen i `sources.yaml`. Samme troværdighedskriterier gælder.

Finder søgningen en ukendt udgiver, bliver artiklen ikke vist. Udgiveren skrives i stedet i `data/state/kildeforslag.md` med antal fund og eksempler. Claudes sweep gør det samme i `data/judgments/kildeforslag-sweep.md`. Listerne gennemgås hver uge, og gode udgivere flyttes til `medier.yaml` eller `sources.yaml`.

## Kilder med AI-fravalg i robots.txt

Nogle medier, fx DR, TV 2-regionerne, Politiken, Børsen, Ingeniøren og Energy Supply, blokerer AI-agenter i robots.txt, men ikke almindelige læsere. Brugeren har besluttet, at de hentes af feedets egen RSS-læser. Den er ikke en AI-crawler, har sin egen User-Agent og følger robots.txt for `*`. Claude vurderer kun titlen og RSS-uddraget, som allerede ligger i data, og henter aldrig noget fra mediets sider. Ombestemmer brugeren sig, sættes `ai: false` på kilden, og så vurderes den kun efter regler.

Samme princip gælder de regionale og lokale aviser, som brugeren 2026-10-08 bad om at få med for alle kommuner. De fleste fravælger AI-træning i robots.txt, men ikke almindelige læsere. Jysk Fynske Medier og Nordjyske har dags- eller ugesitemaps med titel og dato, så indsamleren henter aldrig selve artiklen. Hos Sjællandske Medier og Lolland-Falsters Folketidende hentes kun artikler med et affaldsord i URL'en, og hos Midtjyske Medier kun artikler, hvis linktekst på forsiden har et affaldsord. Claude ser kun titlen og uddraget.
