# Kildeliste for MVP

MVP'en bruger kun de mest relevante kilder i hver afsenderkategori. Det giver et feed med mindre støj og færre kilder at holde øje med, mens vi ser, hvordan relevansvurderingen fungerer. Listen udvides eller ændres senere, og brugerens egen kildeliste kan erstatte den helt (se [KILDER.md](KILDER.md) om import).

Kilderne står i [`sources.yaml`](../sources.yaml). MVP-kilderne har `status: aktiv`. Kilderne under "Senere" står med `status: planlagt` eller `kandidat` og kan slås til med én linje.

"Hentes via" betyder:

- RSS: kildens eget nyhedsfeed.
- Sitemap: kildens sitemap, hvor nye artikler findes ud fra adressen.
- Nyhedsside: kildens liste over nyheder, læst med en fast selektor.
- Søgning: Bing News på danske affaldsord indtil 14. oktober 2026. Den er fravalgt, fordi Bings vilkår kun tillader personlig brug, og Google News forbyder automatisk hentning i robots.txt. Claude-routinens daglige søgning efter oversete nyheder dækker en del af hullet.

Kilder, der kun kan hentes via sitemap eller nyhedsside, kræver indsamleren `collect/pages.py`. Den bliver derfor en del af MVP'en i stedet for fase 2, fordi flere af de vigtigste kilder ikke har RSS.

## Nationalt medie

| Kilde | Hvorfor med | Hentes via |
|---|---|---|
| DR Nyheder | Landsdækkende historier om affald, gebyrer og kommunale ordninger | RSS (strengt filter) |
| Avisen.dk (Ritzau) | Ritzau-telegrammer, som mange medier bygger på | RSS |

Senere: Politiken, Berlingske, Børsen, Jyllands-Posten, Information, B.T. og Mandag Morgen.

## Lokalmedie

| Kilde | Hvorfor med | Hentes via |
|---|---|---|
| TV 2-regionerne | Lokale historier fra de 8 regionale stationer, fx nye ordninger, genbrugspladser og skraldebiler | RSS (strengt filter) |
| Regionale og lokale aviser | 81 dagblade, ugeaviser og netaviser, der dækker alle kommuner med et lokalmedie. Se [LOKALMEDIER.md](LOKALMEDIER.md) | RSS, sitemap eller forside (strengt filter) |
| Øvrige lokalmedier | Lokalmedier, der ikke kan hentes direkte, blev fanget via nyhedssøgningen, når de skrev om affald. Søgningen er fravalgt fra 14. oktober 2026 | Søgning |

## Fagmedie

| Kilde | Hvorfor med | Hentes via |
|---|---|---|
| Altinget (Miljø, Forsyning, Kommunal) | Politik og regulering på affalds- og forsyningsområdet | RSS |
| Kommunen.dk | Nyheder fra kommunernes hverdag | RSS |
| Danske Kommuner | KL's magasin om kommunal drift og økonomi | Sitemap |
| Teknik & Miljø | Fagbladet for kommunernes tekniske forvaltninger | Sitemap |
| EmballageFOKUS | Emballage og udvidet producentansvar | RSS |
| Ingeniøren | Teknik bag forbrænding, CO2-fangst og genanvendelse | RSS (strengt filter) |

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
| DTU, Aalborg Universitet og IT-Universitetet | Pressemeddelelser, filtreret på affald | RSS via Ritzau (strengt filter) |
| Roskilde Universitet og CBS | Nyheder, filtreret på affald | Sitemap (strengt filter) |
| DTU Sustain | Miljø- og ressourceteknologi, også affald og restprodukter | Forside med de fire nyeste nyheder |
| DTU Kemiteknik | Forbrænding, pyrolyse og kemisk genanvendelse af plast | Forside med de to nyeste nyheder (strengt filter, engelsk) |
| Københavns Universitet, Fødevare- og Ressourceøkonomi | Ressourceøkonomi, fx madspild og plastpolitik | Nyhedsside |
| Aarhus Universitet, Byggeri og Bygningsdesign | Byggematerialer og genbrug i byggeriet | RSS |

Senere: DCE og Uniavisen.

### Universiteternes institutter

Universiteternes fælles nyhedslister rummer kun en del af institutternes nyheder. Den 14. oktober 2026 blev institutter og centre med forskning i affald, ressourcer, miljø og byggeri gennemgået ved alle otte universiteter. Et institut kom med, når dets nyheder kan hentes på en generisk måde, og når de seneste nyheder rummer noget om affald. Institutter med en relevant nyhedsliste, der ikke kan hentes, står i `sources.yaml` som kandidater med en note.

| Universitet | Med i feedet | Gennemgået, men ikke med |
|---|---|---|
| DTU | DTU Sustain og DTU Kemiteknik | DTU Construct (byggematerialer, men ingen affaldsnyheder blandt de seneste). DTU Space og de andre institutter arbejder ikke med affald |
| Københavns Universitet | Fødevare- og Ressourceøkonomi (IFRO) | Plante- og Miljøvidenskab (RSS, ingen affaldsnyheder 2022-2026), Geovidenskab og Naturforvaltning og KU FOOD (ingen nyheder om affaldshåndtering) |
| Aarhus Universitet | Byggeri og Bygningsdesign | Miljøvidenskab (RSS, ingen affaldsnyheder siden oktober 2024), Bio- og Kemiteknologi, Agroøkologi og CBIO (bioøkonomi) |
| Aalborg Universitet | Ingen | Bæredygtighed og Planlægning (med DCEA) og Byggeri, By og Miljø er relevante, men nyhedslisterne hentes med JavaScript fra et API |
| Syddansk Universitet | Ingen | Institut for Grøn Teknologi: "Nyt fra IGT" er ikke opdateret siden 2022, og instituttets nyheder står på SDU's fælles nyhedsliste |
| Roskilde Universitet | Ingen | RUC_TEKST |
| CBS | Ingen | CBS_TEKST |
| IT-Universitetet | Ingen | Ingen institutter med affaldsforskning |

## EU og Norden

| Kilde | Hvorfor med | Hentes via |
|---|---|---|
| EU-Kommissionen, DG ENV | Nye EU-regler og forslag om affald, emballage og cirkulær økonomi | RSS (strengt filter) |
| Det Europæiske Miljøagentur (EEA) | Analyser og tal for affald i Europa | Sitemap (agenturets robots.txt forbyder RSS-feedsene) |
| Nordisk Ministerråd | Nordisk samarbejde om affald og cirkulær økonomi | RSS (strengt filter) |
| Avfall Sverige | Den svenske pendant til de kommunale affaldsselskabers forening | Nyhedsside |

Senere: Europa-Parlamentets miljøudvalg (ENVI, blokerer i dag automatisk hentning), Zero Waste Europe, ISWA, EEB, CEWEP, EXPRA, ACR+ og Municipal Waste Europe.

## Sådan ændrer du listen

Skriv i chatten, hvilke kilder der skal ind eller ud, eller ret `status` i `sources.yaml` direkte på GitHub. En kilde, der sættes til `aktiv`, bliver hentet ved næste time. Inden en ny kilde slås til, tjekkes den med `python -m affaldsfeed check --fetch <id> --explain`, så man kan se, hvad den bidrager med.
