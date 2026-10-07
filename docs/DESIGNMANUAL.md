# Designmanual

Manualen beskriver, hvordan Affaldsfeed ser ud, og hvad der står på siden. Dataformatet, URL-parametrene og localStorage-nøglerne står i [KONTRAKTER.md](KONTRAKTER.md), afsnit 8 og 9. Kategoriernes navne, farver og ikoner står i `config/categories.yaml` og kommer til frontenden via `feed.json`.

## Principper

1. Afsenderen kommer først. Man skal kunne se, hvem der taler, før man læser titlen.
2. Én kolonne med det nyeste øverst, delt op pr. dag. Listen er kernen, og alt andet ligger rundt om den.
3. Farve bærer aldrig information alene. Ikon og tekst følges ad.
4. Siden er tæt, men der er luft nok til at læse. Der er ingen billeder, og titlerne må gerne stå tæt.
5. Udtrykket er lånt fra affaldsviden.info: farverne, Open Sans, afrundede hvide paneler på grå baggrund og pilleformede knapper. Logo og navn er ikke lånt, og intet hentes derfra. Farverne står som værdier i `site/assets/style.css`.
6. Siden er ærlig om data. Anslåede datoer, betalingsmure, forældede data, uvurderede indslag og tekst skrevet af Claude vises åbent.
7. Alt står skarpt. Rækker har fast højde, navne står på én linje, tal står i samme kolonne, og intet skifter bredde, når man vælger noget.

## Layout

- Demo-strimmel, header, indhold og footer deler én container: højst 68rem (1088 px) med 16 px sidemargen. Derfor står logoet på linje med sidepanelets venstrekant, og det sidste menupunkts tekst flugter med listepanelets højrekant.
- Fra 1024 px er der to kolonner: filterpanelet på 312 px og læsekolonnen på højst 720 px med 24 px imellem. Sidepanelet er sticky 16 px fra toppen, er højst skærmens højde minus 32 px og ruller selv.
- Fra 768 til 1023 px er containeren 47rem (752 px) med én kolonne på højst 720 px. Filtrene ligger i en skuffe fra højre bag knappen "Filtrér".
- Under 768 px går panelerne fra kant til kant uden radius, og al tekst står 16 px fra skærmkanten. Der er 8 px grå mellem panelerne. Filtrene ligger i et bundark.
- Brudpunkterne står i em (48em og 64em), så layoutet skifter tidligere, når brugeren har større grundskrift. Siden kan vises ved 320 px uden vandret scroll, også i tom-tilstanden, hvor knapperne må brydes over to linjer.
- Kan feedet ikke indlæses, står fejlen i læsekolonnen (også fra 1024 px, hvor sidepanelet så er skjult) uden listens hoved, fordi søgning, "Filtrér" og visning intet har at vise.
- Headeren er hvid, ikke sticky og har `box-shadow: 0 10px 15px rgba(0,0,0,.05)`. Fra 768 px er den én række på 64 px med logo (28 px) og ordmærket "Affaldsfeed" til venstre og navigationen til højre. Under 768 px står logo og ordmærke på én række (56 px) og navigationen på en række for sig (44 px). Der er ingen undertitel.
- Navigationen er Feed og Tidslinje. Om kilderne findes via footeren. Den aktive side har teksten i `--link` og en streg på 3 px i `--link` under teksten.
- Forsiden har denne rækkefølge: demo-strimmel (kun med `?demo=1`), header, sidepanel og læsekolonnen med meddelelser, AI-overblik og listepanelet. Listepanelet har listens hoved øverst og derefter dage og kort. "Vis flere" står under panelet.
- Afstande: 4, 8, 12, 16, 20, 24 og 32 px. Kort, listens hoved og overblik har 20 px vandret padding (16 px under 768 px). Optiske justeringer på 2, 3 og 6 px står ved de enkelte komponenter.
- Radius: 15 px på paneler (0 under 768 px), 8 px på felter, forslagslister og meddelelser, 999 px på knapper og aktive filtre.

| Højde | Mus fra 768 px | Berøring eller under 768 px | Bruges til |
|---|---|---|---|
| `--h-row` | 32 px | 44 px | filterrækker, forslag, "Flere filtre", rækker på Om kilderne |
| `--h-ctl` | 36 px | 44 px | søgefelter, "Filtrér", "Vis flere", primærknapper |
| `--h-chip` | 28 px | 32 px | aktive filtre og tekstknapper |
| `--h-day` | 40 px | 40 px | dagsoverskrifter |

## Typografi

Open Sans 400 og 600, hostet selv i `site/assets/fonts/` (latin, licensen står i `OFL.txt`). Reserven er `system-ui, -apple-system, "Segoe UI", sans-serif`. Siden henter ingen skrift fra andre domæner. Størrelserne står i rem. Der er ingen tekst under 13 px, ingen kursiv og ingen versaler.

| Token | Størrelse og linjehøjde | Vægt | Bruges til |
|---|---|---|---|
| `--t-xs` | 13/18 | 400, 600 | afsenderlinje, fodlinje, tider, tal, statuslinje, aktive filtre, tekstknapper, tekstvalg, overblikkets første linje og kildelinks, meddelelser og noter |
| `--t-s` | 14/20 | 400, 600 | filterrækker, forslag, gruppeoverskrifter og dagsoverskrifter (600) |
| `--t-m` | 15/22 | 400, 600 | brødtekst, teaser, knapper, overblikkets foldede hovedlinje og punkter, titler i kompakt visning (600) |
| `--t-in` | 15/22, ved berøring 16/24 | 400 | tekst i felter. 16 px forhindrer, at iOS zoomer ind |
| `--t-l` | 17/24 | 600 | korttitel, udfoldet hovedlinje i overblikket, "Filtre" |
| `--t-xl` | 20/28 | 600 | ordmærket og `h2` på Om kilderne |
| `--t-2xl` | 28/34 | 600 | `h1` på Om kilderne og Tidslinje |

- `letter-spacing: 0.2px` på body og ingen anden spatiering.
- Tider, tal og tællere har `font-variant-numeric: tabular-nums`, så tallene står i kolonne.
- "kl. 14.17" og "5. okt." skrives med hårdt mellemrum, så de aldrig deles over to linjer.

## Farver

Farverne er CSS-variabler på `:root`.

| Token | Lys | Mørk | Brug |
|---|---|---|---|
| `--bg` | #DAE0E0 | #111614 | sidebaggrund |
| `--surface` | #FFFFFF | #1A201D | paneler, kort og felter |
| `--text` | #222222 | #E6EAE7 | brødtekst og titler (15,9:1 på hvid) |
| `--muted` | #565656 | #A9B3AE | metatekst, teaser, tal og rækker med 0 (7,34:1 på hvid) |
| `--line` | #DAE0E0 | #2C3531 | skillelinjer |
| `--link` | #0A602D | #7ED69B | links, afkrydsninger, valgt del i tekstvalg, primærknapper og fokusringe (7,71:1 på hvid) |
| `--link-hover` | #67952E | #A5E3B8 | hover på flader og kanter, aldrig som tekst (3,55:1) |
| `--accent` | #6E9612 | #95C41F | kun kanten på 3 px ved nye indslag og linjerne i "Her slap du sidst", aldrig tekst (3,5:1 på hvid og 8,0:1 på mørk flade; markeringen er en tilstand og skal have mindst 3:1) |
| `--tag-bg` | #E6F4EA | #1F3326 | kun aktive filtre (#0A602D på den giver 6,79:1) |
| `--warn-bg` | #FFF4CC | #3A3214 | meddelelsen om forældet feed og forældet overblik |
| `--footer` | #54595F | #0B0F0D | footer med hvid tekst |
| `--focus-on-dark` | #FFFFFF | #FFFFFF | fokusring på den mørke footer |

Felter har kanten `--field` og står kun på `--surface`, hvor kanten har mindst 3,4:1. `opacity` bruges aldrig til at vise en tilstand.

Mørk tilstand følger kun enhedens indstilling (`prefers-color-scheme: dark`). Der er ingen temavælger på siden. En gammel værdi i `af.theme` fra den tidligere vælger slettes ved indlæsning, så ingen sidder fast i et tema.

## Afsenderkategorier

Hver kategori har en farve, et ikon og et kort navn. Ikonet står i kategoriens farve og er 16 px i filterpanelet og forslagene, 14 px i kortets afsenderlinje og 20 px i overskrifterne på Om kilderne. Der er ingen prik. Panel, kort og aktive filtre bruger det korte navn. Det fulde navn står i filterrækkens `title` og på Om kilderne.

| Kategori | Kort navn | Lys | Mørk | Ikon-id | Motiv |
|---|---|---|---|---|---|
| Nyhedsmedie | Nyhedsmedie | #1862B5 | #68AAFE | `avis` | avis |
| Fagmedie | Fagmedie | #107C86 | #2CC4CB | `tidsskrift` | tidsskrift |
| Myndighed og Folketing | Myndighed | #5A3584 | #9B86C6 | `soejle` | søjlebygning |
| Kommune og affaldsselskab | Kommunal | #065F35 | #5EC587 | `raadhus` | rådhus |
| Organisation og branche | Organisation | #CA651B | #FFA350 | `personer` | to personer |
| Tænketank og NGO | Tænketank/NGO | #B8346C | #FF84BA | `paere` | pære |
| Forskning og universitet | Forskning | #7A5C0D | #AE9417 | `kolbe` | kolbe |
| EU og Norden | EU/Norden | #84241B | #DD7161 | `stjerner` | stjernekreds |

Ikonerne er egne inline SVG'er i `site/assets/ikoner.svg`. De bruger `currentColor`, og der er intet ikonbibliotek. `tools/check_colors.py` tjekker paletten: CIEDE2000 på mindst 20 mellem alle par, simulering af deutan og protan og kontrast på mindst 3:1 mod `--surface` i begge tilstande. Ændres en farve, skal tjekket være grønt igen. Den nuværende palet har mindst 22 mellem alle par i begge tilstande. Ved simuleret farveblindhed ligger enkelte par mellem 8,8 og 10, så farven står aldrig alene: ikon og navn følger altid med.

Temaerne har ingen egne farver og står som almindelig tekst på kortet. Panel, kort og aktive filtre bruger temaets korte navn (`topics[].short` i `feed.json`, ellers `name`).

## Komponenter

### Filterpanelet

Panelet er et `<search>` med overskriften "Filtre" og tekstknappen "Nulstil" til højre, når et filter er aktivt. Det bygges én gang. Et valg opdaterer tal og flueben på stedet, så fokus og scroll bliver, hvor de var.

| Gruppe | Indhold |
|---|---|
| Sted | søgefelt med forslag, de valgte kommuner og byer som rækker, regionerne som faste rækker og en note |
| Afsender | 8 rækker med kategoriikon og linket "Om afsendertyperne" til `kilder.html#typer` |
| Tema | 13 rækker, en streg og "Uden tema" |
| Flere filtre | foldet `<details>` med Genre (6 rækker), Periode (7, 30 eller 60 dage) og rækkerne "Kun dansk" og "Saml historier" |
| Kilde | alle kilder med flueben, grupperet efter afsendertype, med et felt, der indsnævrer listen. Står sidst, fordi listen er lang |

- Hver gruppe er en `<fieldset>` med `<legend>` i 14/20 og vægt 600. Der er 20 px mellem grupperne og ingen streger.
- Valg inden for en gruppe kombineres med ELLER, og grupperne kombineres med OG.
- Sted, Afsender, Tema og Genre indsnævrer: intet valgt betyder alt, og vælger man noget, ser man kun det. Kilde er omvendt: alle kilder har flueben fra start, og fjernes et flueben, skjules kilden.
- "Flere filtre (1)" viser, hvor mange valg der afviger fra standard. Gruppen er foldet ud ved indlæsning, hvis der er valgt genre, periode 7 eller 30, "Kun dansk" eller "Saml historier" fra. Brugerens egne fold huskes ikke.
- Sted vises kun, når `feed.json` har `geo`. Uden `geo` læses `region`, `kommune` og `by` fra URL'en og skrives uændret tilbage, men de filtrerer ikke.

### Stedfiltret

Sted står øverst i panelet, fordi man typisk vælger sit område én gang og gemmer siden som bogmærke.

- Øverst er søgefeltet med nålen og pladsholderen "Kommune eller by". Forslagene går på tværs af kommuner, byer og regioner. En by har konteksten "by i Nyborg" i `--muted` efter navnet.
- Under feltet står de valgte kommuner og byer som rækker i den rækkefølge, de blev valgt. En fravalgt række bliver stående uden flueben resten af besøget (højst 6).
- Efter 8 px luft står regionerne som faste rækker i `geo`-rækkefølge. De er bygget ud fra data og aldrig skrevet ind i koden. Vælges en region i forslagene, sættes fluebenet i regionsrækken.
- Er et sted valgt, står noten "Landsdækkende nyheder vises ikke, når et sted er valgt." under regionerne (13/18, `--muted`), og feltet peger på den med `aria-describedby`.
- Hvert indslag får et udvidet sæt steder: en kommune giver også dens region, og en by giver sin primære kommune (`geo.byer[].kommune`) og dennes region. En by tæller ikke under de øvrige kommuner i `kommuner`, heller ikke når den ligger i flere. Et indslag passer, når det har et af de valgte steder i sættet. Derfor viser "Region Syddanmark" også indslag om Nyborg og Ullerslev, mens "Nyborg Kommune" ikke viser et indslag, der kun nævner Region Syddanmark. Hørsholm by (primær kommune Hørsholm, men også i Fredensborg og Rudersdal) tæller under Hørsholm Kommune og Region Hovedstaden, ikke under Fredensborg eller Rudersdal. Flere steder kombineres med ELLER.
- Tallet i en række og i et forslag er antallet af kort, stedet alene giver sammen med de øvrige filtre, efter samme regel for byer. De andre valgte steder tæller ikke med.
- Et id i URL'en, der ikke findes i `geo`, bliver stående, giver 0 og vises som id'et i mærket. Steder skrives sorteret i URL'en: regioner i `geo`-rækkefølge, kommuner og byer alfabetisk efter id. Uden `geo` skrives værdierne tilbage i den rækkefølge, de blev læst.
- Giver valgene 0 indslag, foreslår tom-tilstanden den ene ændring, der giver flest. Et sted foreslås udvidet til sin forælder (by til primær kommune, kommune til region), hvis det giver indslag, fx "Udvid til Nyborg Kommune (viser 4)". Ellers foreslås det fjernet.

### Kildelisten

Kilde viser alle kilder i `feed.json` som rækker med flueben, så man kan fravælge de kilder, man ikke vil se.

- Øverst er feltet "Find kilde" med lup. Det indsnævrer listen, mens man skriver, med samme foldning som søgningen (accenter, å/aa, æ/ae og ø/oe). Esc tømmer feltet. Passer ingen, står "Ingen kilde passer til "x"." (13/18, `--muted`) som status.
- Under feltet står "Alle 43 vises" eller "38 af 43 vises" til venstre og tekstknapperne "Vælg alle" og "Fravælg alle" til højre (13/18).
- Kilderne står i grupper efter afsendertype i konfigurationens rækkefølge. Hver gruppe har en lille overskrift med kategoriikonet (16 px) og det korte navn i 13/18, 600 og `--muted`. Inden for gruppen står kilderne alfabetisk. Overskriften er kun visuel (`aria-hidden`), fordi rækkens navn er nok.
- Rækkerne er filterrækker uden ikon. Tallet er antallet af kort, kilden giver med de andre filtre, også når kilden er fravalgt, så man kan se, hvad man går glip af.
- I URL'en står de fravalgte som `uden=` (fx `uden=avisen,altinget`). Er færre kilder valgt end fravalgt, skrives de valgte i stedet som `kilde=`, så linket bliver kort. Et link med `kilde=altinget` viser kun Altinget med flueben.
- Mærkerne over listen siger "Uden Avisen.dk" for hver fravalgt kilde og "Altinget" for hver valgt, når der er højst 3, ellers ét samlet mærke: "Uden 5 kilder" eller "13 kilder". "Filtrér (n)" tæller mærkerne. Giver valgene 0 indslag, kan tom-tilstanden foreslå "Vis Avisen.dk igen" eller "Vis alle kilder".

### Filterrækken

Alle lister i panelet bruger samme række: en `<label>` med et ægte afkrydsningsfelt, eventuelt et ikon, navnet og tallet.

- Grid: afkrydsning (16 px, 20 px ved berøring), ikon (16 px), navn og en talkolonne på 40 px, med 8 px imellem. Højden er fast: 32 px med mus og 44 px ved berøring.
- Navnet står i 14/20 på én linje. Er det for langt, afkortes det med "…", og `title` har hele navnet. Ved normale størrelser brydes det aldrig.
- Stor skrift og tekstafstand (1.4.4 og 1.4.12): bliver panelet smalt i forhold til teksten, må rækker og forslag vokse, og navnet brydes i stedet for at blive afkortet. Det styres af en container query på panelet målt i `lh` (panelet har `line-height: 1`, så 1lh er skriftens størrelse): under 18lh med mus og 18,9lh ved berøring. Tekstafstand sætter `line-height` til 1,5 og udløser derfor også reglen. Ved normal skrift er sidepanelet 18,7lh (18,1lh med klassisk rullebjælke) og arket ved 320 px 19,2lh, så rækkerne er én linje i fast højde.
- Tallet står højrestillet i 13/18 og `--muted` med en skjult tekst " indslag". Tallet er antallet af kort, rækken giver sammen med de andre gruppers filtre.
- Et valg ændrer kun afkrydsningen. Navnet beholder vægt og farve, så intet flytter sig.
- En række med 0 har navnet i `--muted`, bliver stående og kan stadig vælges.
- Hover giver `--hover-bg` (kun med mus). Fokusringen sidder indvendigt på hele rækken, og rækkens felt har `scroll-margin-block: 12px`, så ringen ikke klippes, når panelet ruller ved Tab.
- Rækken har `padding: 0 8px; margin: 0 -8px`, så afkrydsningen flugter med overskriften og felterne, mens hover-fladen går 8 px ud.
- Sidepanelet har `scrollbar-gutter: stable`. Tager en klassisk scrollbar plads, trækkes dens bredde fra panelets højre polstring (højst ned til 8 px, så rækkernes hover-flade på 8 px ikke giver vandret scroll), så navnene stadig har plads. Det samme gælder arket.
- Skærmlæseren hører fx "Kommunal, 6 indslag". Kommaet står inline med nul størrelse (`.sr-punct`), fordi en skjult tekst med `position: absolute` giver "Kommunal , 6 indslag" i navnet.

### Søgefelt med forslag

Sted bruger et søgefelt med forslag (`assets/combobox.js`). Mønstret er WAI-ARIA's combobox med en listbox, hvor man kan vælge flere.

- Feltet er 36 px højt (44 px ved berøring) med nålen og pladsholderen "Kommune eller by". Klik i et tomt felt viser "Flest indslag lige nu" med de 8 kommuner og byer, der har flest indslag.
- Ved berøring rulles feltet op øverst i arket, når det får fokus, så forslagene står over tastaturet. Der rulles først, når trykket er landet som et klik i feltet, så trykket åbner listen.
- Når man skriver, viser listen højst 8 forslag. Søgningen ser bort fra store og små bogstaver og accenter, og å, æ og ø kan skrives som aa, ae og oe eller a, ae og o. Navne, der begynder med søgningen, står før navne, hvor et ord begynder med den. Er der flere end 8, står "Viser 8 af 23. Skriv mere for at indsnævre." under listen.
- Ved lige rang står kommuner før byer og byer før regioner. Tallene påvirker ikke rækkefølgen, så listen står stille, mens man filtrerer.
- Hvert forslag har fluebenskolonne, navn og tal i samme grid som filterrækken. Listen går 8 px ud i panelets polstring som rækkernes hover-flade (kant 1 px og 7 px polstring), så fluebenet står over afkrydsningerne, og navne og tal står i rækkernes kolonner. Det aktive forslag har `--hover-bg` og en indvendig ring i `--link`.
- Tekst uden bogstaver og tal (fx "...") giver beskeden "Ingen … passer til". En synlig besked forsvinder, når man klikker uden for feltet.
- Enter eller klik vælger stedet eller fravælger det, hvis det er valgt. Feltet tømmes, listen lukker, og fokus bliver i feltet. Skærmlæseren hører fx "Nyborg Kommune er valgt."
- Valgte kommuner og byer står som rækker under feltet. En fravalgt række bliver stående uden flueben resten af besøget, så et fejlklik kan fortrydes. Der står højst 6 fravalgte rækker, og den ældste forsvinder først. Kun den beskårne række fjernes fra DOM'en, så fokus bliver på den række, man lige har klikket.
- Skærmlæseren hører forslag og rækker med kontekst, fx "Ullerslev, by i Nyborg Kommune, 3 indslag" og "Nyborg Kommune, i Region Syddanmark, 12 indslag". Navnet kommer fra forslagets indhold (ingen `aria-label`), så den synlige tekst altid er en del af navnet.
- Listen ligger i flowet under feltet og skubber rækkerne ned, så panelets scroll aldrig klipper den. Kun én forslagsliste er åben ad gangen.

### Filterarket

Under 1024 px åbner "Filtrér" en modal `<dialog>`, og panelet flyttes ind i den. Under 768 px er det et bundark på 90 % af skærmens højde med radius 15 px foroven. Fra 768 px er det en skuffe på 400 px fra højre i fuld højde.

- Toppen (56 px) har overskriften "Filtre", "Nulstil" og lukkeknappen (44 × 44 px). Bunden har "Vis 23 indslag", som følger valgene, mens man vælger.
- Valg virker med det samme. Der er ingen "Anvend"-knap.
- Esc lukker det inderste først: en åben forslagsliste, så teksten i et søgefelt og til sidst arket. ×, Esc og klik uden for arket giver fokus tilbage til "Filtrér". "Vis 23 indslag" ruller listen frem og giver fokus til statuslinjen.
- Baggrunden ruller ikke, mens arket er åbent. En klassisk rullebjælkes bredde lægges til som polstring på siden, mens arket låser scroll, så siden ikke flytter sig, og skuffen står helt ude ved højrekanten. Bliver vinduet 1024 px eller bredere, lukker arket, og panelet står i sidepanelet med samme valg.
- I browsere uden `closedby` lukker et klik på baggrunden kun, når både tryk og slip var på baggrunden. Et træk, der begynder i arket, lukker ikke.

### Listens hoved

Øverst i listepanelet står tre rækker med 12 px imellem:

1. Søgefeltet "Søg i titler og kilder" med lup og en ryd-knap (×), som kun vises, når der er tekst. Under 1024 px står "Filtrér (2)" ved siden af. Tallet tæller valg inde i arket, men ikke søgningen.
2. De aktive filtre som mærker med × og til sidst "Nulstil". Rækken vises kun, når der er aktive filtre.
3. Statuslinjen til venstre og visningen "Normal | Kompakt" til højre.

- Søgningen slår igennem 180 ms efter sidste tast og straks ved Enter. Esc tømmer feltet. Klikker man på et filter, før de 180 ms er gået, anvendes søgningen først, så teksten ikke overskrives.
- Søgningen folder som forslagene: accenter fjernes, og å, æ og ø kan skrives som aa, ae og oe eller a, ae og o. "århus" finder "Aarhus".
- Mærket er 28 px højt med kant i `--link`, baggrund `--tag-bg` og teksten i 13/18. Et langt navn afkortes med "…" (højst 260 px fra 768 px). Mærker brydes mellem hinanden, aldrig inde i et mærke. Rækkefølgen er panelets.
- Statuslinjen siger "1.284 indslag" eller "23 af 1.284 indslag". Kendes sidste besøg, og er der nye indslag, følger tekstknappen "Vis 7 nye" ("Vis 1 ny"). Med `nye=1` står der "7 nye indslag · Vis alle" ("1 nyt indslag"). Skilletegnet hænger på teksten før det, så en linje aldrig begynder med "·".
- Med valg siger "Filtrér (2)" "Filtrér, 2 valgt" til skærmlæseren.
- "Nulstil" nulstiller filtre, søgning, `nye` og `story`, men beholder "Saml historier", visningen og overblikkets periode. Fokus går derefter til statuslinjen.

### Tekstvalg

Visning, Periode og overblikkets faner er diskrete tekstvalg: ord på række med 16 px imellem, uden kant, pille eller baggrund. Delene er 13/18 i vægt 600 i alle tilstande, så bredden aldrig skifter. Den, der ikke er valgt, står i `--muted` (`--text` ved hover med mus). Den valgte står i `--link` med en streg på 2 px lige under teksten, lavet som en kant, så den også ses med tvungne farver. Hver del er mindst 24 × 24 px, og ved berøring udvides klikfladen usynligt til 44 px uden at flytte noget. Første dels tekst flugter med indholdets venstrekant. Ved stor skrift må delene brydes mellem hinanden, men en del deles eller afkortes aldrig. Bag Visning og Periode ligger ægte radioknapper, så piletasterne flytter valget; overblikkets faner er `role="tab"`.

### Feed-kortet

```
[ikon] Altinget · Fagmedie · Delvis betalingsmur                        09.14
Kommunerne mangler tid til at indføre de nye regler
Kildens egen beskrivelse, højst 240 tegn og to linjer ...
Gebyrer og økonomi · Lovgivning, politik og EU             +2 andre kilder v
```

Kortet er en `<article>`, titlen en `<h3>` og tiden en `<time datetime>`. Padding er 16 px 20 px (12 px 16 px under 768 px), og der er en streg på 1 px i `--line` mellem kortene.

1. Afsenderlinjen (13/18, `--muted`): kategoriikon (14 px), kildens navn i 600 og `--text`, det korte kategorinavn, eventuelt ", udgivet af KL", genren (ikke Nyhed, og ikke når titlen selv begynder med den), "Betalingsmur" eller "Delvis betalingsmur" og "Ikke vurderet". Tiden står øverst til højre i en fast kolonne. Genre, betalingsmur og "Ikke vurderet" brydes aldrig midt i ("Delvis betalingsmur" står samlet). Skilletegnet er et skjult komma til skærmlæseren, hårdt mellemrum, "·" og et mellemrum, så en linje aldrig begynder med "·", og skærmlæseren holder en pause ("Fyens Stiftstidende, Nyhedsmedie").
2. Titlen (17/24, 600) linker til kilden i ny fane med den skjulte tekst "(åbner i nyt vindue)". Hover giver `--link` og understregning. Besøgte titler står i `--muted`. Titler på engelsk og svensk har `lang`.
3. Teaseren (15/22, `--muted`) er højst to linjer og afkortes ved et ord efter højst 240 tegn. Engelske og svenske indslag viser "Auto-resumé:" i 600 og derefter Claudes danske resumé.
4. Fodlinjen (13/18, `--muted`) har først stedet med en nål (14 px), derefter højst to temaer med korte navne og yderst til højre "+3 andre kilder" eller "+1 anden kilde". Har historien nye medlemmer, står der fx "+3 andre kilder, 2 nye". Linjen udelades, når den er tom.
   - Stedet er det mest præcise: en region udelades, når en kommune i den eller en by, hvis primære kommune ligger i den, også står på indslaget, og en kommune udelades, når den er primær kommune for en by på indslaget. `k:nyborg` og `b:ullerslev` viser "Ullerslev". Der står højst to navne og derefter fx "+2". Indslag uden steder viser intet, og steder vises ikke i kompakt visning.
   - To byer med samme navn får kommunens korte navn i parentes, fx "Ejby (Køge)".

- Kun titlen og "+N andre kilder" kan klikkes. Kildenavn og temaer er tekst. Filtrering sker i panelet.
- "+N andre kilder" folder en liste ud under fodlinjen med en streg på 2 px til venstre. Knappen bliver stående ved højrekanten, når listen åbnes. Hvert medlem har afsenderlinje med tid og titlen som link (15/22, 600).
- Nye kort har en indvendig kant på 3 px i `--accent` til venstre og den skjulte tekst "Ny:" før titlen. Et kort er nyt, når et af dets indslag, der passer på filtrene, er nyt. Det er samme regel som "Vis 7 nye", så tallet og markeringerne altid stemmer.
- Tiden: under en dagsoverskrift kun klokkeslættet ("09.14"), under en ugeoverskrift datoen ("30. sep."). Er datoen anslået, står der "fundet 09.14". Indslag med kun en dato viser intet klokkeslæt under en dagsoverskrift.

### Kompakt visning

Fra 768 px er der én række pr. indslag i et grid med ikon (16 px), kilde i en fast kolonne på 9rem, titel og tid. Alle titler starter derfor samme sted. Under 768 px står ikon, kilde og tid på første linje og titlen på anden. Der er ingen teaser, fodlinje eller "+N andre kilder". Betalingsmur vises som en lås på 12 px efter titlen, og "Ikke vurderet" står efter titlen. Titlens sidste ord og låsen står i ét span uden ombrydning, så låsen aldrig står alene på en linje, og "· Ikke vurderet" aldrig begynder en linje.

### Dage og listen

- Overskrifterne er "I dag", "I går", "Mandag 5. oktober" for 2 til 6 dage siden og derefter uger som "Uge 40 · 28.–30. september". En ugegruppe nævner kun de dage, den faktisk dækker.
- Dagsoverskriften er en sticky `<h2>` på 40 px i 14/20 og 600 med streg over og under. Antallet står yderst til højre på samme højrekant som kortenes tider.
- "Her slap du sidst · i går kl. 08.14" står mellem nye og gamle indslag med linjer i `--accent`.
- Listen viser 50 kort ad gangen. "Vis flere (50)" står centreret under listepanelet, og fokus går derefter til den første nye titel.

### AI-overblikket

Overblikket ligger i et hvidt panel øverst i læsekolonnen over søgning og filtre, fordi det altid dækker hele feedet.

- Foldet (standard): første linje er "AI-overblik · I dag" i 13/18 og `--muted` med tekstknappen "Vis hele" til højre. Anden linje er hovedlinjen med "Kort sagt:" i 600, højst to linjer ved alle bredder. Panelet har 12 px lodret polstring, så det fylder 90 px.
- Udfoldet: knappen hedder "Vis mindre", og første linje er kun "AI-overblik", fordi fanerne viser perioden. 8 px under den står fanerne I dag, Ugen, Måneden og Året som tekstvalg, derefter "Opdateret kl. 14.24 · bygget på 23 indslag", hovedlinjen i 17/24, punkterne med kildelinks og bunden "Skrevet af Claude ud fra kilderne. Kan indeholde fejl."
- Fanerne er `role="tablist"`. Piletaster, Home og End skifter fane, og kun den aktive fane er i tabulatorrækkefølgen. Den valgte periode står i URL'en som `overblik=dag|uge|maaned|aar`.
- Under hvert punkt står kildelinks i 13/18, fx "Altinget, KEFM +2". Kildenavnene linker til artiklerne i ny fane og er 24 px høje mål (3 px polstring over og under, linjen bliver ikke højere). Den skjulte titel efter kildenavnet har `lang` på engelske og svenske titler. "+2" er en tekstknap på grundlinjen, der filtrerer feedet til historien med `story=<id>`; et usynligt `::before` giver den en klikflade på 24 × 24 px.
- Er overblikket forældet, står fx "· fra i går kl. 23.25" i første linje, og den udfoldede visning har en note på `--warn-bg`. Er der aktive filtre, står "Overblikket dækker hele feedet, ikke kun dine filtre." nederst.
- Valget huskes i `af.overviewHidden`: "0" betyder udfoldet, alt andet betyder foldet. Tilstanden holdes i siden, så knappen også virker, når localStorage ikke kan bruges.

### Demo-strimmel og meddelelser

- Med `?demo=1` står en tynd strimmel i `--demo-bg` over headeren: "Demodata: opdigtede eksempler med links til example.org. Tiderne er rykket frem." og linket "Vis det rigtige feed", som aldrig brydes midt i. Den kan ikke lukkes. Interne links bevarer `?demo=1`; logoet på Om kilderne peger på `index.html?demo=1`.
- Meddelelser står øverst i læsekolonnen før overblikket i 13/18, mindst 40 px høje, med 8 px imellem. Forældet feed (over 6 timer) har `--warn-bg` og ikonet `advarsel`. Regelvisning har `--surface`, kant i `--line` og ikonet `info`. De har ingen lukkeknap og forsvinder, når årsagen forsvinder.

### Footer

Footeren har baggrund `--footer` og hvid tekst i 13/18: teksten om projektet og linkene "Om kilderne · Koden på GitHub". Skilletegnet hænger på linket før det, så en linje aldrig begynder med "·". Fokusringen er hvid. På Om kilderne har linket til siden selv `aria-current="page"`.

### Tidslinje

`tidslinje.html` viser de vigtigste begivenheder på affaldsområdet, valgt af Claude (KONTRAKTER 7.3). Siden har samme demo-strimmel, header, footer og læsekolonne som Om kilderne.

- Øverst står "Tidslinje" (`h1`), linjen "De vigtigste begivenheder på affaldsområdet, udvalgt af Claude ud fra nyhederne i feedet. Kan indeholde fejl." og tekstvalget "Alle · Kun milepæle" (`niveau=milepael` i URL'en). Til højre står "Spring til 2026 · 2025", når begivenhederne spænder over mere end ét år. Antallet meldes til skærmlæsere, når niveauet skiftes.
- Begivenhederne står i ét panel grupperet efter måned. Månedsoverskriften er sticky som feedets dagsoverskrifter, i 17/24 med antallet til højre, og har et anker (`#2026-10`), så man kan linke til en måned.
- Hver begivenhed har datoen i en fast kolonne til venstre ("7. okt."), en markør på en lodret streg i `--line` og teksten til højre: "Milepæl" (13/18, 600, `--link`) ved milepæle, titlen (17/24, 600), resuméet (15/22, `--muted`), fodlinjen med steder og temaer som på kortet og "Læs 3 nyheder" (eller "Læs nyheden"). Markøren er en udfyldt cirkel på 12 px i `--link` ved milepæle og en ring ved de andre. Den er dekorativ (`aria-hidden`), fordi "Milepæl" står som tekst.
- "Læs 3 nyheder" folder indslagene ud med kilde (600), dato og titlen som link i ny fane. Er historien stadig i feedet, står "Vis i feedet" nederst og linker til `index.html?story=<id>`.
- Siden viser de 12 nyeste måneder med begivenheder. "Vis ældre" henter 12 måneder mere og giver fokus til den første nye måneds overskrift. "Spring til" og et anker i URL'en henter ældre måneder efter behov.
- Under 480 px står datoen over titlen, og stregen følger markøren i venstre side.
- Tom tidslinje: "Tidslinjen er tom endnu. Claude tilføjer de vigtigste begivenheder, efterhånden som nyhederne kommer." og linket "Gå til feedet". Ingen milepæle: "Der er ingen milepæle på tidslinjen endnu." og "Vis alle begivenheder".

### Om kilderne

Siden bruger samme demo-strimmel, header og footer og en læsekolonne på højst 720 px uden sidepanel. Fra 1024 px står læsekolonnen ved containerens venstrekant og flugter med logoet; under 1024 px står den som listepanelet på forsiden. Afsendertyperne står som rækker med ikon, det fulde navn og antal kilder (`id="typer"`), i to kolonner fra 560 px med 48 px imellem. Hver kategori har sin egen sektion med ikonet (20 px) i overskriften, kategoriens forklaring og kildelisten. Statusmærket står altid øverst til højre i kildens række. Tallene i "Status lige nu" står i 20/28 og vægt 600.

## Tone og mikrotekster

Teksten er kort, saglig og dansk. Der er ingen udråbstegn og intet salgssprog. Tal har punktum som tusindtalsskilletegn (1.284). Klokkeslæt skrives "kl. 09.14", datoer "7. okt." eller "mandag 5. oktober". Under en dagsoverskrift står kun klokkeslættet uden "kl.".

Overblikket følger samme tone. Claude skriver neutralt og markerer, når en afsender varetager interesser ("ifølge Dansk Affaldsforening ...").

| Sted | Tekst |
|---|---|
| Navigation | Feed · Tidslinje |
| Springlink | Gå til feedet |
| Søgefelt | Søg i titler og kilder · Ryd søgning |
| Filtrér-knap | Filtrér (2) |
| Panel og ark | Filtre · Nulstil · Luk filtre · Vis 23 indslag |
| Grupper | Sted · Afsender · Tema · Flere filtre (1) · Genre · Periode · Sprog og visning · Kilde |
| Afsender | Om afsendertyperne |
| Sted | Kommune eller by · Find kommune eller by · Flest indslag lige nu · Ingen steder har indslag lige nu. · by i Nyborg · Landsdækkende nyheder vises ikke, når et sted er valgt. |
| Kilde | Find kilde · Alle 43 vises · 38 af 43 vises · Vælg alle · Fravælg alle · Ingen kilde passer til "x". · Uden Avisen.dk · Uden 5 kilder · 13 kilder · Vis Avisen.dk igen · Vis alle kilder |
| Forslag | Viser 8 af 23. Skriv mere for at indsnævre. · Ingen kommune eller by passer til "xyz". Byer kommer med, når de er nævnt i et indslag. · Ingen kilde passer til "xyz". · Nyborg Kommune er valgt. · Nyborg Kommune er fravalgt. |
| Rækker | Uden tema · Kun dansk · Saml historier |
| Periode | 7 dage · 30 dage · 60 dage |
| Aktive filtre | Fjern filter: Nyborg Kommune · Region Syddanmark · Ullerslev · Seneste 7 dage · Kun dansk · Historie: ... |
| Statuslinje | 1.284 indslag · 23 af 1.284 indslag · Vis 7 nye · Vis 1 ny · 7 nye indslag · 1 nyt indslag · Vis alle |
| Visning | Normal · Kompakt |
| Kort | Betalingsmur · Delvis betalingsmur · Ikke vurderet · Auto-resumé: · udgivet af KL · fundet 09.14 · +3 andre kilder · +1 anden kilde · +3 andre kilder, 2 nye |
| Skillelinje | Her slap du sidst · i går kl. 08.14 |
| Overblik | AI-overblik · I dag · Ugen · Måneden · Året · Vis hele · Vis mindre · fra i går kl. 23.25 · Opdateret kl. 14.24 · bygget på 23 indslag · Skrevet af Claude ud fra kilderne. Kan indeholde fejl. |
| Overblik, kort data | Siden 7. oktober 2026 · opdateret kl. 09.25 |
| Overblik, før første kørsel | Dagens overblik kommer efter kl. 06.25. |
| Overblik, filternote | Overblikket dækker hele feedet, ikke kun dine filtre. |
| Filtre giver 0 | Ingen indslag passer til Nyborg Kommune + Tekstiler de seneste 60 dage. Landsdækkende nyheder vises ikke, når et sted er valgt. · Fjern Tekstiler (viser 23) · Udvid til Nyborg Kommune (viser 4) · Fjern historien (viser 2) · Nulstil filtre |
| Søgning giver 0 | Intet om "gebyrloft" de seneste 60 dage. · Ryd søgning (viser 1.284) |
| Kun nye, intet nyt | Intet nyt siden dit sidste besøg i går kl. 08.14. · Vis alle |
| Intet i dag | Intet nyt endnu i dag. Sidst opdateret kl. 09.17. |
| feed.json fejler (også data uden for kontrakten) | Feedet kunne ikke indlæses. Prøv igen om lidt. · Prøv igen |
| Forældet feed | Feedet blev sidst opdateret for 9 timer siden. Indsamlingen kører måske ikke. · Se kildernes status |
| Regelvisning | Claudes vurdering er forsinket. Nye indslag vises efter faste regler og er mærket "Ikke vurderet". |
| Demo | Demodata: opdigtede eksempler med links til example.org. Tiderne er rykket frem. · Vis det rigtige feed |
| Footer | Uafhængigt hobbyprojekt. Ikke tilknyttet affaldsviden.info. Alle overskrifter linker til den oprindelige kilde. · Om kilderne · Koden på GitHub |

## Tilgængelighed (WCAG 2.2 AA)

- Kontrast: mindst 4,5:1 for tekst og 3:1 for kanter, fokusringe og markeringer i begge tilstande. #95C41F, #6E9612 og #67952E bruges aldrig som tekst.
- 1.4.1: farve står aldrig alene.
- Fokus: `:focus-visible` med en kontur på 2 px i `--link` og 2 px offset. Rækker, forslag og menupunkter har ringen indvendigt, så den ikke klippes. Felter har ringen uden offset, og kanten bliver `--link`. På footeren er ringen hvid. `scroll-padding-top` svarer til dagsoverskriften plus 16 px, så fokus aldrig skjules under den (2.4.11).
- 2.5.8: alle mål er mindst 24 × 24 px, i praksis 28 til 36 px med mus og 44 px ved berøring.
- Tastatur: alt kan betjenes med tastatur. Der er ingen genveje på ét tegn. Søgefeltet med forslag følger WAI-ARIA's combobox-mønster med ↓, ↑, Alt + ↓, Alt + ↑, Enter, Esc og Tab. Filterarket er en modal dialog, og Esc lukker det inderste først. Overblikkets faner skiftes med piletasterne.
- Skærmlæser: tal i rækker og forslag læses med "indslag", mærker læses "Fjern filter: Kommunal", og valg i forslagslisten meldes ("Altinget er valgt."). Statuslinjen er en live-region, og arket har sin egen, fordi siden bag det er inert.
- Struktur: h1 til h3, `<main>`, `<nav>`, `<search>` og `<article>`. Forsidens skjulte h1 står i headeren, før sidepanelets h2 "Filtre". Links, der åbner i nyt vindue, har den skjulte tekst "(åbner i nyt vindue)".
- Sprog: `lang="en"` eller `lang="sv"` på titler og teasere på engelsk og svensk, også i overblikkets skjulte kildetekst.
- 1.4.4, 1.4.10 og 1.4.12: størrelser i rem og brudpunkter i em. Siden kan vises ved 320 px, og med grundskrift 20 eller 32 px eller med tekstafstand vokser rækkerne, og navnene brydes i stedet for at blive afkortet (se Filterrækken).
- Bevægelse: ark og skuffe glider ind på 200 ms. `prefers-reduced-motion` slår alle animationer fra.
- Tvungne farver: det aktive forslag får en ring i `Highlight`, valgte forslag kendes på fluebenet, nye kort får en kant i `CanvasText`, og arket har en kant, så det skiller sig fra siden bag det.
- Alle tidspunkter står i `<time datetime>`.
