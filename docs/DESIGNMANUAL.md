# Designmanual

Manualen beskriver, hvordan Affaldsfeed ser ud, og hvad der står på siden. Dataformatet, URL-parametrene og localStorage-nøglerne står i [KONTRAKTER.md](KONTRAKTER.md), afsnit 8 og 9. Kategoriernes navne, farver og ikoner står i `config/categories.yaml` og kommer til frontenden via `feed.json`.

## Principper

1. Afsenderen kommer først. Man skal kunne se, hvem der taler, før man læser titlen.
2. Én kolonne med det nyeste øverst, delt op pr. dag. Listen er kernen, og alt andet ligger rundt om den.
3. Farve bærer aldrig information alene. Prik, ikon og tekst følges ad.
4. Siden er tæt, men der er luft nok til at læse. Der er ingen billeder, og titlerne må gerne stå tæt.
5. Udtrykket er lånt fra affaldsviden.info: farverne, Open Sans, afrundede hvide paneler på grå baggrund og pilleformede knapper. Logo og navn er ikke lånt, og intet hentes derfra. Farverne står som værdier i `site/assets/style.css`.
6. Siden er ærlig om data. Anslåede datoer, betalingsmure, forældede data, uvurderede indslag og tekst skrevet af Claude vises åbent.

## Layout

- Containeren er højst 1140 px bred og centreret på sidebaggrunden `--bg`.
- Headeren er hvid og 64 px høj med `box-shadow: 0 10px 15px rgba(0,0,0,.05)`. Den har ordmærket "Affaldsfeed" i `--link` (20 px, 600) med et eget simpelt ikon, en undertitel med antal kilder og opdateringstid og navigationen "Feed" og "Om kilderne".
- Fra 1024 px står filterpanelet til venstre: 264 px bredt, sticky, hvidt og med radius 15 px. Læsekolonnen til højre er højst 760 px. Øverst i den ligger AI-overblikket og under det listen, hver i sit hvide panel med radius 15 px.
- Mellem 768 og 1023 px er filtrene en sammenfoldelig bjælke over listen.
- Under 768 px er der én kolonne med 16 px sidemargen og ingen vandret scroll. Filtrene ligger bag knappen "Filtrér (2)", som åbner en `<dialog>` fra bunden. Trykflader er mindst 44×44 px.
- Afstande følger en 4 px-skala: 4, 8, 12, 16, 24 og 32. Kortet har padding 16 px 20 px og en skillelinje på 1 px i `--line`.
- Radius: 15 px på paneler, 999 px på chips og knapper, 8 px på søgefeltet.

## Typografi

Open Sans 400 og 600 fra Google Fonts med `system-ui, sans-serif` som reserve. Alle størrelser er i px.

| Element | Størrelse og linjehøjde | Vægt | Andet |
|---|---|---|---|
| Brødtekst og teaser | 15/22 | 400 | letter-spacing 0,2 px |
| Korttitel | 17/24 | 600 | |
| Overblikkets hovedlinje | 17/24 | 600 | |
| Overblikkets punkter | 15/22 | 400 | |
| Metatekst og kildelinks | 13/18 | 400 | farve `--muted` |
| Dagsoverskrift | 13/18 | 600 | versaler, letter-spacing 0,06 em |
| Genreetiket | 11/16 | 600 | versaler, letter-spacing 0,06 em |
| h1 på "Om kilderne" | 28/34 | 600 | |

## Farver

Farverne er CSS-variabler på `:root`.

| Token | Lys | Mørk | Brug |
|---|---|---|---|
| `--bg` | #DAE0E0 | #111614 | sidebaggrund |
| `--surface` | #FFFFFF | #1A201D | paneler og kort |
| `--text` | #222222 | #E6EAE7 | brødtekst og titler (15,9:1 på hvid) |
| `--muted` | #565656 | #A9B3AE | metatekst (7,34:1 på hvid) |
| `--line` | #DAE0E0 | #2C3531 | skillelinjer |
| `--link` | #0A602D | #7ED69B | links, aktive chips og faner, primærknapper (7,71:1 på hvid) |
| `--link-hover` | #67952E | #A5E3B8 | hover på flader og kanter, aldrig som tekst (3,55:1) |
| `--accent` | #95C41F | #95C41F | kun kanten på 3 px ved nye indslag, aldrig tekst |
| `--tag-bg` | #E6F4EA | #1F3326 | baggrund på temachips (#0A602D på den giver 6,79:1) |
| `--warn-bg` | #FFF4CC | #3A3214 | bjælken om forældet feed |
| `--footer` | #54595F | #0B0F0D | footer med hvid tekst |

Mørk tilstand følger `prefers-color-scheme: dark` under `:root:not([data-theme="light"])` og gentages under `:root[data-theme="dark"]`. En lille knap skifter mellem lys, mørk og auto, og valget gemmes i `af.theme`.

## Afsenderkategorier

Hver kategori har en farve, et ikon og et kort navn. Prikken er 8 px og ikonet 14 px.

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

Temaerne har ingen egne farver. Alle temachips bruger `--tag-bg` og `--link`.

## Komponenter

### AI-overblikket

Overblikket ligger i et hvidt panel øverst i læsekolonnen, over listen.

- Fire segmenterede faner: I dag, Ugen, Måneden og Året. De er bygget som `role="tablist"` med `role="tab"` og `aria-selected`, og de skal kunne stå på én linje ved 375 px. Den aktive fane har baggrunden `--link` og hvid tekst. Den valgte fane står i URL'en som `overblik=dag|uge|maaned|aar`.
- Under fanerne står perioden i metatekst. Rækker data ikke hele vinduet tilbage, står startdatoen, fx "Året (siden 7. oktober 2026)".
- Hovedlinjen begynder med "Kort sagt:" og er højst 25 ord.
- Punkterne er en liste. I dag og Ugen har 3-5 punkter, Måneden og Året 5-8, og hvert punkt er højst 30 ord. Er der kun få indslag, kan der være færre punkter (reglerne står i KONTRAKTER 7.1).
- Under hvert punkt står små kildelinks i metatekst, fx "Altinget, KEFM +2". Kildenavnene linker til artiklerne i ny fane. "+2" filtrerer feedet til historien med `story=<id>`.
- Bunden af panelet: "Opdateret kl. 09.25 · bygget på 23 indslag · Skrevet af Claude ud fra kilderne nedenfor. Kan indeholde fejl."
- Knappen "Skjul overblik" folder panelet sammen til en linje med "Vis overblik". Valget huskes i `af.overviewHidden`.
- Overblikket dækker altid hele feedet. Er der aktive filtre, står det i en note.
- Før første kørsel: "Dagens overblik kommer efter kl. 06.25." Er opsummeringen forældet, står tidspunktet tydeligt, fx "Opdateret i går kl. 23.25".

### Feed-kortet

```
● [ikon] Altinget · Fagmedie · kl. 09.14                    Betalingsmur
DEBAT
Kommunerne mangler tid til at indføre de nye regler ↗
Kildens egen beskrivelse, højst 240 tegn og to linjer ...
[Gebyrer og økonomi] [Lovgivning, politik og EU]      +2 andre kilder ▾
```

Kortet er en `<article>`, titlen en `<h3>` og tiden en `<time datetime>`.

1. Afsenderlinje: prik og ikon, kildenavn (600), kort kategorinavn i `--muted`, eventuelt "udgivet af KL" eller "via Ritzau", og til sidst tiden. I dag og i går står tiden som "kl. 09.14", ellers som "7. okt.". Er datoen anslået, står der "fundet kl. 09.14". Højrestillet står mærkerne "Betalingsmur" med lås, "EN", "SV" og "Ikke vurderet".
2. Etiketlinje, kun når der er noget at vise: genren og fra fase 3 høringsfristen.
3. Titel: link til originalen i ny fane med `rel="noopener"` og ↗.
4. Teaser: kildens egen beskrivelse, højst 240 tegn, afkortet ved et ord og vist på højst to linjer. Engelske og svenske indslag viser i stedet Claudes danske resumé med mærket "Auto-resumé", og den originale teaser ligger i en `<details>`. Kompakt visning skjuler teaseren.
5. Fodlinje: op til 2 temachips og "+N andre kilder ▾", som folder en liste ud med kilde, kategori, tid og link.
6. Nye indslag har en venstrekant på 3 px i `--accent` og den skjulte tekst "Ny" til skærmlæsere. En historie med nye medlemmer får badget "+2 nye".

Der er ingen billeder. Kompakt visning er én linje pr. indslag med tid, prik, kilde og titel.

### Øvrige komponenter

- Kildebadge: prik, ikon, kildenavn og kort kategorinavn. Ved fokus og hover vises kategoriens forklaring fra `categories.yaml`. For organisationer står der "Afsenderen varetager medlemmernes interesser."
- Mærket "Ikke vurderet": en lille pille i `--muted` med tooltip "Vist efter regler, fordi Claudes vurdering er forsinket." Det vises kun på indslag med `reviewed: false`.
- Filterpanel: grupperne Afsender, Tema, Kilde og Flere filtre som `<fieldset>` med `<legend>` (13 px, versaler, `--muted`) og "Nulstil filtre" nederst. Kilde er en søgbar liste med afkrydsning, grupperet efter kategori og med tæller.
- Chip (`<button aria-pressed>`): pille, mindst 32 px høj på desktop og 44 px på mobil, med tæller i `--muted`. Aktiv: baggrund `--link` og hvid tekst. Valg med 0 nedtones, men bliver stående, så layoutet ikke hopper.
- Aktiv filterchip over listen: som en chip, men med × og fx `aria-label="Fjern filter Kommunal"`.
- Temachip på kortet: 13 px, `--tag-bg` og `--link`. Et klik tilføjer temaet som filter.
- Genreetiket: 11/16 i versaler og `--muted`.
- Datogruppe: `<h2>`, sticky under headeren, med tæller og en linje i `--line`. Overskrifterne er "I dag", "I går", ugedag og dato for resten af de seneste 7 dage og derefter uger.
- Statuslinje: 13 px med `aria-live="polite"`.
- "Vis flere": sekundær pilleknap med kant i `--link`. Listen viser 50 indslag ad gangen.
- Bjælke om forældet feed: `--warn-bg`, et ikon og et link til "Om kilderne". Vises, når feedet er over 6 timer gammelt.
- Søgefelt: radius 8 px og 1 px `--line`, som bliver `--link` ved fokus. Tasten `/` sætter fokus i feltet.
- Mobilfilter: `<dialog>` som bundark med radius 15 px foroven. Esc og knappen "Vis 48 indslag" lukker det.
- Introlinje ved første besøg, som kan lukkes. Valget huskes i `af.introClosed`.
- Footer: baggrund `--footer` og hvid tekst.

## Tone og mikrotekster

Teksten er kort, saglig og dansk. Der er ingen udråbstegn og intet salgssprog. Tal har punktum som tusindtalsskilletegn (1.284). Klokkeslæt skrives "kl. 09.14", datoer "7. okt." eller "mandag 5. oktober".

Overblikket følger samme tone. Claude skriver neutralt og markerer, når en afsender varetager interesser ("ifølge Dansk Affaldsforening ...").

| Sted | Tekst |
|---|---|
| Undertitel | Nyheder om affald og ressourcer fra 72 kilder · opdateret kl. 14.17 |
| Introlinje | Nyheder om affald fra kommuner, myndigheder, medier, organisationer og forskning. Nyeste øverst. Brug filtrene til at vælge afsender, tema eller kilde. |
| Søgefelt | Søg i titler og kilder |
| Filtergrupper | Afsender · Tema · Kilde · Flere filtre |
| Mobilknap | Filtrér (2) |
| Nulstil | Nulstil filtre |
| Statuslinje | Viser 50 af 1.284 indslag · 7 nye siden i går kl. 08.14 · Vis kun nye |
| Skillelinje | Her slap du sidst · tirsdag kl. 14.32 |
| Anslået dato | fundet kl. 09.14 |
| Historie | +2 andre kilder |
| Betalingsmur | Betalingsmur |
| Resumé af EN/SV | Auto-resumé |
| Fallback | Ikke vurderet |
| Overblik, faner | I dag · Ugen · Måneden · Året |
| Overblik, hovedlinje | Kort sagt: ... |
| Overblik, kildelinks | Altinget, KEFM +2 |
| Overblik, bundlinje | Opdateret kl. 09.25 · bygget på 23 indslag · Skrevet af Claude ud fra kilderne nedenfor. Kan indeholde fejl. |
| Overblik, kort data | Året (siden 7. oktober 2026) |
| Overblik, før første kørsel | Dagens overblik kommer efter kl. 06.25. |
| Overblik, filternote | Overblikket dækker hele feedet, ikke kun dine filtre. |
| Overblik, knapper | Skjul overblik · Vis overblik |
| Filtre giver 0 | Ingen indslag passer til Kommunal + Tekstiler de seneste 60 dage. Fjern Kommunal (viser 23) · Nulstil filtre |
| Søgning giver 0 | Intet om "gebyrloft" de seneste 60 dage. |
| Kun nye, intet nyt | Intet nyt siden dit sidste besøg i går kl. 08.14. Vis alle |
| Intet i dag | Intet nyt endnu i dag. Sidst opdateret kl. 09.17. |
| feed.json fejler | Feedet kunne ikke indlæses. Prøv igen om lidt. Prøv igen |
| Forældet feed | Feedet blev sidst opdateret for 9 timer siden. Indsamlingen kører måske ikke. |
| Footer | Uafhængigt hobbyprojekt. Ikke tilknyttet affaldsviden.info. Alle overskrifter linker til den oprindelige kilde. |

## Tilgængelighed (WCAG 2.2 AA)

- Kontrast: mindst 4,5:1 for tekst og 3:1 for UI-grafik i begge tilstande. #95C41F og #67952E bruges aldrig som tekst.
- 1.4.1: farve står aldrig alene.
- Fokus: `:focus-visible` med en kontur på 2 px i `--link` og 2 px offset. `scroll-padding-top` svarer til headeren plus den sticky dagsoverskrift, så fokus ikke skjules (2.4.11).
- 2.5.8: trykflader er mindst 24×24 px, i praksis 32 px på desktop og 44 px på mobil.
- Tastatur: alt kan betjenes med tastatur. `/` giver søgning, Esc lukker dialogen, og fokus vender tilbage til knappen, der åbnede den. Overblikkets faner skiftes med piletasterne, og kun den aktive fane er i tab-rækkefølgen.
- Overblikket: hvert fanepanel har `role="tabpanel"` og `aria-labelledby`. "Skjul overblik" har `aria-expanded`.
- Struktur: h1 til h3, `<main>`, `<nav>` og `<article>`. Links, der åbner i nyt vindue, har den skjulte tekst "(åbner i nyt vindue)".
- Sprog: `lang="en"` eller `lang="sv"` på titler og teasere på engelsk og svensk.
- 1.4.10: siden kan reflowes ved 320 px.
- Bevægelse: `prefers-reduced-motion` slår animationer fra.
- Alle tidspunkter står i `<time datetime>`.
