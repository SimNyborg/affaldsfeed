# Kildeliste for MVP

MVP'en bruger kun de mest relevante kilder i hver af de 8 afsenderkategorier. Det giver et feed med mindre støj og færre kilder at holde øje med, mens vi ser, hvordan relevansvurderingen fungerer. Listen udvides eller ændres senere, og brugerens egen kildeliste kan erstatte den helt (se [KILDER.md](KILDER.md) om import).

Kilderne står i [`sources.yaml`](../sources.yaml). MVP-kilderne har `status: aktiv`. Kilderne under "Senere" står med `status: planlagt` eller `kandidat` og kan slås til med én linje.

"Hentes via" betyder:

- RSS: kildens eget nyhedsfeed.
- Sitemap: kildens sitemap, hvor nye artikler findes ud fra adressen.
- Nyhedsside: kildens liste over nyheder, læst med en fast selektor.
- Søgning: Google News og Bing News på danske affaldsord.

Kilder, der kun kan hentes via sitemap eller nyhedsside, kræver indsamleren `collect/pages.py`. Den bliver derfor en del af MVP'en i stedet for fase 2, fordi flere af de vigtigste kilder ikke har RSS.

## Nyhedsmedie

| Kilde | Hvorfor med | Hentes via |
|---|---|---|
| DR Nyheder | Landsdækkende historier om affald, gebyrer og kommunale ordninger | RSS (strengt filter) |
| TV 2-regionerne | Lokale historier fra de 8 regionale stationer, fx nye ordninger, genbrugspladser og skraldebiler | RSS (strengt filter) |
| Avisen.dk (Ritzau) | Ritzau-telegrammer, som mange medier bygger på | RSS |
| Ingeniøren | Teknik bag forbrænding, CO2-fangst og genanvendelse | RSS (strengt filter) |
| Lokale og regionale aviser | Lokalaviser, som ikke har egne feeds i registret, fanges via nyhedssøgningen, når de skriver om affald | Søgning |

Senere: Politiken, Berlingske, Børsen, Jyllands-Posten, Information, B.T. og Mandag Morgen.

## Fagmedie

| Kilde | Hvorfor med | Hentes via |
|---|---|---|
| Altinget (Miljø, Forsyning, Kommunal) | Politik og regulering på affalds- og forsyningsområdet | RSS |
| Kommunen.dk | Nyheder fra kommunernes hverdag | RSS |
| Danske Kommuner | KL's magasin om kommunal drift og økonomi | Sitemap |
| Teknik & Miljø | Fagbladet for kommunernes tekniske forvaltninger | Sitemap |
| EmballageFOKUS | Emballage og udvidet producentansvar | RSS |

Senere: Dagens Byggeri, TekniskFOKUS, Energy Supply, BygTek og WasteTech.

## Myndighed og Folketing

| Kilde | Hvorfor med | Hentes via |
|---|---|---|
| Miljøstyrelsen | Nyheder og publikationer om affald, regler og vejledning | Sitemap |
| Klima-, Energi- og Forsyningsministeriet | Pressemeddelelser om politiske aftaler og regler | RSS |
| Forsyningstilsynet | Affaldsgebyrer, økonomisk regulering og benchmarking | Sitemap |
| Høringsportalen | Nye høringer om love og bekendtgørelser, filtreret på affald | RSS (strengt filter) |

Senere: Folketinget (ODA), Miljøministeriet, Klimarådet, Energistyrelsen, Konkurrence- og Forbrugerstyrelsen, Rigsrevisionen og Retsinformation.

## Kommune og affaldsselskab

| Kilde | Hvorfor med | Hentes via |
|---|---|---|
| ARC (Amager Ressourcecenter) | Stort fælleskommunalt selskab med forbrænding og genanvendelse | RSS |
| Vestforbrænding | Stort fælleskommunalt selskab med mange ejerkommuner | Sitemap |
| ARGO | Fælleskommunalt selskab på Sjælland | RSS |
| AffaldPlus | Fælleskommunalt selskab på Sydsjælland | RSS |
| Kredsløb | Aarhus Kommunes forsyningsselskab for affald | Sitemap |
| Renosyd | Fælleskommunalt selskab i Østjylland | RSS |

Senere: Odense Renovation, Nordværk, Fors, REFA, SONFOR, HOFOR, KLAR Forsyning, Norfors, Nomi4s og kommunernes egne nyhedssider.

## Organisation og branche

| Kilde | Hvorfor med | Hentes via |
|---|---|---|
| Brancheforeningen Cirkulær (tidligere Dansk Affaldsforening) | Forening for de kommunale affaldsselskaber | Sitemap |
| DAKOFA | Videnscenter og netværk for hele affaldsbranchen | Sitemap |
| KL | Kommunernes forhandlinger, høringssvar og nyheder om affald | Sitemap (strengt filter) |
| Dansk Producentansvar | Ordningerne for producentansvar på emballage, el og batterier | Sitemap |
| Dansk Retursystem | Pantsystemet for flasker og dåser | RSS |

Senere: VANA, Genvindingsindustrien, DI (ARI), Dansk Erhverv, Plastindustrien, Dansk Fjernvarme, Biogas Danmark, Gate 21 og Danske Regioner.

## Tænketank og NGO

| Kilde | Hvorfor med | Hentes via |
|---|---|---|
| CONCITO | Grøn tænketank med analyser af cirkulær økonomi og affald | Nyhedsside |
| Rådet for Grøn Omstilling | Grøn organisation med fokus på ressourcer og affald | RSS |
| Danmarks Naturfredningsforening | Holdninger til plast, affald og genbrug | Nyhedsside (strengt filter) |

Senere: Kraka, CEPOS og Tænketanken Europa.

## Forskning og universitet

| Kilde | Hvorfor med | Hentes via |
|---|---|---|
| Teknologisk Institut | Anvendt forskning i genanvendelse og plast | Nyhedsside (strengt filter) |
| Aarhus Universitet | Forskningsnyheder, filtreret på affald | RSS (strengt filter) |
| Københavns Universitet | Forskningsnyheder, filtreret på affald | RSS (strengt filter) |
| Syddansk Universitet | Forskningsnyheder, filtreret på affald | Nyhedsside (strengt filter) |

Senere: DTU (nyhederne vises med JavaScript og kræver en anden løsning), DCE, RUC og Uniavisen.

## EU og Norden

| Kilde | Hvorfor med | Hentes via |
|---|---|---|
| EU-Kommissionen, DG ENV | Nye EU-regler og forslag om affald, emballage og cirkulær økonomi | RSS (strengt filter) |
| Det Europæiske Miljøagentur (EEA) | Analyser og tal for affald i Europa | RSS |
| Europa-Parlamentets miljøudvalg (ENVI) | Behandlingen af EU-lovgivning om affald | RSS (strengt filter) |
| Avfall Sverige | Den svenske pendant til de kommunale affaldsselskabers forening | Nyhedsside |

Senere: Nordisk Ministerråd, Zero Waste Europe, ISWA, EEB, CEWEP, EXPRA, ACR+ og Municipal Waste Europe.

## Sådan ændrer du listen

Skriv i chatten, hvilke kilder der skal ind eller ud, eller ret `status` i `sources.yaml` direkte på GitHub. En kilde, der sættes til `aktiv`, bliver hentet ved næste time. Inden en ny kilde slås til, tjekkes den med `python -m affaldsfeed check --fetch <id> --explain`, så man kan se, hvad den bidrager med.
