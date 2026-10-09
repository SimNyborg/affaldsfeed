# Kommunernes egne nyheder

Oversigten viser, hvordan feedet henter nyhederne fra de 98 kommuners egne hjemmesider. Den bygger på en kortlægning fra 9. oktober 2026, hvor alle hjemmesider blev afprøvet fra GitHub Actions. Oversigten er et øjebliksbillede. Ændrer en kommune sin hjemmeside, viser kildesundheden på Om kilderne det.

## Sådan hentes kommunerne

Feedet henter 89 af de 98 kommuner. Kommunerne skriver mest om andet end affald, så alle har strengt filter, og hver kilde har kommunen som fast sted.

- **Sitemap (81 kommuner).** Sitemappet viser kommunens sider med datoen for seneste ændring. Et mønster pr. kommune udvælger nyhederne, fx `/nyheder/2026/okt/...`. Indsamleren henter kun en nyhed, når adressen har et affaldsord, så kommunernes mange andre nyheder koster ingen kald.
- **Nyhedsliste (5 kommuner).** Hillerød, Holstebro, Ikast-Brande, Ringkøbing-Skjern og Skanderborg. Indsamleren læser listen og henter kun de nyheder, hvor linkteksten eller adressen har et affaldsord.
- **RSS (3 kommuner).** Frederikssund og Varde har et nyhedsfeed. Esbjerg Kommunes hjemmeside svarer 403 til feedets UA, så kommunens pressemeddelelser hentes via Ritzau (via.ritzau.dk).

Sitemaps og nyhedslister hentes hver 6. time og RSS hver time. En nyhed med en adresse uden affaldsord bliver ikke hentet. Søgningen og routinens søgning efter oversete nyheder dækker en del af det hul.

## Kommuner, der ikke hentes

Ni kommuner står som kandidater i `sources.yaml` med en note og kan prøves igen senere.

- **Gentofte, Herlev og Slagelse** svarer 403 til feedets UA. Det er botbeskyttelse, og den omgås ikke. Ingen af dem har et nyhedsrum hos Ritzau.
- **Ringsted og Morsø** svarer ikke fra GitHub Actions, hvor forbindelsen timer ud.
- **Allerød, Ballerup og Sønderborg** henter deres nyhedsliste med JavaScript, og deres sitemap eller RSS har ikke nyhederne. Sønderborgs affaldsnyheder kommer fra SONFOR, der hentes direkte.
- **Rebild** har hverken en nyhedsliste eller nyheder i sitemappet, så vidt kortlægningen kunne se.

## Universiteterne

Alle otte universiteter hentes nu direkte. DTU, Aalborg Universitet og IT-Universitetet hentes via deres pressemeddelelser hos Ritzau, fordi deres egne nyhedssider bruger JavaScript eller ikke har nyhederne i sitemappet. CBS hentes fra sitemappet. Københavns Universitet, Aarhus Universitet, Syddansk Universitet og Roskilde Universitet var allerede med. Universiteterne har også strengt filter.

## Kommunerne

### Region Hovedstaden

| Kommune | Hentes via | Bemærkning |
|---|---|---|
| Albertslund | Sitemap |  |
| Allerød | Hentes ikke | Nyhedslisten bruger JavaScript, sitemappet har kun ugentlige samlesider |
| Ballerup | Hentes ikke | Nyhedslisten bruger JavaScript, intet sitemap |
| Bornholm | Sitemap |  |
| Brøndby | Sitemap |  |
| Dragør | Sitemap |  |
| Egedal | Sitemap |  |
| Fredensborg | Sitemap |  |
| Frederiksberg | Sitemap |  |
| Frederikssund | RSS |  |
| Furesø | Sitemap |  |
| Gentofte | Hentes ikke | Hjemmesiden svarer 403 (botbeskyttelse) |
| Gladsaxe | Sitemap |  |
| Glostrup | Sitemap |  |
| Gribskov | Sitemap |  |
| Halsnæs | Sitemap | Sitemappet er langsomt og har givet timeout |
| Helsingør | Sitemap |  |
| Herlev | Hentes ikke | Hjemmesiden svarer 403 (botbeskyttelse) |
| Hillerød | Nyhedsliste | Forsidens seneste nyheder, fordi nyhedslisten bruger JavaScript |
| Hvidovre | Sitemap |  |
| Høje-Taastrup | Sitemap |  |
| Hørsholm | Sitemap |  |
| Ishøj | Sitemap |  |
| København | Sitemap | Sitemap-indekset peger på localhost, så under-sitemaps hentes direkte |
| Lyngby-Taarbæk | Sitemap |  |
| Rudersdal | Sitemap |  |
| Rødovre | Sitemap |  |
| Tårnby | Sitemap |  |
| Vallensbæk | Sitemap |  |

### Region Sjælland

| Kommune | Hentes via | Bemærkning |
|---|---|---|
| Faxe | Sitemap |  |
| Greve | Sitemap |  |
| Guldborgsund | Sitemap |  |
| Holbæk | Sitemap |  |
| Kalundborg | Sitemap |  |
| Køge | Sitemap |  |
| Lejre | Sitemap |  |
| Lolland | Sitemap |  |
| Næstved | Sitemap |  |
| Odsherred | Sitemap |  |
| Ringsted | Hentes ikke | Svarer ikke fra GitHub Actions |
| Roskilde | Sitemap |  |
| Slagelse | Hentes ikke | Hjemmesiden svarer 403 (botbeskyttelse) |
| Solrød | Sitemap | Sitemappet er langsomt og har givet timeout |
| Sorø | Sitemap |  |
| Stevns | Sitemap |  |
| Vordingborg | Sitemap |  |

### Region Syddanmark

| Kommune | Hentes via | Bemærkning |
|---|---|---|
| Assens | Sitemap |  |
| Billund | Sitemap | Kun nyheder om Grindsted-forureningerne og klima står i sitemappet |
| Esbjerg | Ritzau (RSS) | Hjemmesiden svarer 403, så pressemeddelelser hentes via Ritzau |
| Fanø | Sitemap |  |
| Fredericia | Sitemap |  |
| Faaborg-Midtfyn | Sitemap |  |
| Haderslev | Sitemap |  |
| Kerteminde | Sitemap |  |
| Kolding | Sitemap |  |
| Langeland | Sitemap |  |
| Middelfart | Sitemap |  |
| Nordfyns | Sitemap |  |
| Nyborg | Sitemap |  |
| Odense | Sitemap |  |
| Svendborg | Sitemap |  |
| Sønderborg | Hentes ikke | Nyhedslisten bruger JavaScript, RSS har kun offentliggørelser |
| Tønder | Sitemap |  |
| Varde | RSS |  |
| Vejen | Sitemap |  |
| Vejle | Sitemap |  |
| Ærø | Sitemap |  |
| Aabenraa | Sitemap |  |

### Region Midtjylland

| Kommune | Hentes via | Bemærkning |
|---|---|---|
| Favrskov | Sitemap |  |
| Hedensted | Sitemap |  |
| Herning | Sitemap |  |
| Holstebro | Nyhedsliste |  |
| Horsens | Sitemap |  |
| Ikast-Brande | Nyhedsliste |  |
| Lemvig | Sitemap |  |
| Norddjurs | Sitemap |  |
| Odder | Sitemap |  |
| Randers | Sitemap |  |
| Ringkøbing-Skjern | Nyhedsliste |  |
| Samsø | Sitemap |  |
| Silkeborg | Sitemap |  |
| Skanderborg | Nyhedsliste |  |
| Skive | Sitemap |  |
| Struer | Sitemap |  |
| Syddjurs | Sitemap |  |
| Viborg | Sitemap |  |
| Aarhus | Sitemap |  |

### Region Nordjylland

| Kommune | Hentes via | Bemærkning |
|---|---|---|
| Brønderslev | Sitemap |  |
| Frederikshavn | Sitemap |  |
| Hjørring | Sitemap |  |
| Jammerbugt | Sitemap |  |
| Læsø | Sitemap |  |
| Mariagerfjord | Sitemap |  |
| Morsø | Hentes ikke | Svarer ikke fra GitHub Actions |
| Rebild | Hentes ikke | Ingen nyhedsliste eller nyheder i sitemappet fundet |
| Thisted | Sitemap |  |
| Vesthimmerlands | Sitemap |  |
| Aalborg | Sitemap |  |
