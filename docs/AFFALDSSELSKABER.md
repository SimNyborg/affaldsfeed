# Kommunale affaldsselskaber

Oversigten viser, hvordan feedet henter nyhederne fra de kommunale affalds- og forsyningsselskaber. Den bygger på medlemslisten hos brancheforeningen Cirkulær, der tidligere hed Dansk Affaldsforening, og på en kortlægning fra 9. oktober 2026, hvor alle hjemmesiderne blev afprøvet fra GitHub Actions. Oversigten er et øjebliksbillede. Ændrer et selskab sin hjemmeside, viser kildesundheden på Om kilderne det.

## Sådan hentes selskaberne

Cirkulær har 63 medlemmer. Ti af dem blev allerede hentet, ni er kommuner, som feedet henter via kommunernes egne nyheder (se [KOMMUNER.md](KOMMUNER.md)), og to er færøske og ligger uden for feedets geografi. Resten er afprøvet ét for ét, og 34 selskaber er kommet til. Med HOFOR, der ikke er medlem, henter feedet nu 45 selskaber.

- **RSS (12 selskaber).** Feedet på selskabets egen hjemmeside, fx AFLD, Arwos, Nyborg Forsyning & Service og Tønder Forsyning.
- **Ritzau (4 selskaber).** Silkeborg Forsyning, DIN Forsyning, Assens Forsyning og Fors har intet feed eller et sitemap uden datoer, så deres pressemeddelelser hentes fra deres nyhedsrum hos Ritzau (via.ritzau.dk).
- **Sitemap (19 selskaber).** Et mønster pr. selskab udvælger nyhederne i sitemappet, typisk `/nyheder/...`. Ren Forsyning Mariagerfjord, Revas og Vesthimmerlands Forsyning har ingen datoer i sitemappet. Her er en nyhed ny, når den dukker op i sitemappet første gang.
- **Nyhedsliste (10 selskaber).** Indsamleren læser selskabets liste over nyheder, fx hos HTK Forsyning, Norfors og Kerteminde Forsyning.

Rene affaldsselskaber som AFLD, Energnist, Middelfart Affald & Genbrug, Nomi4s og Revas har intet filter, fordi alt, de skriver, handler om affald. Forsyninger, der også har vand, spildevand eller varme, har normalt filter, så kun nyheder med et affaldsord kommer med. Fjernvarme Fyn og HOFOR skriver mest om varme og vand og har strengt filter. Driftsbeskeder om fx åbningstider, helligdage og vejarbejde afvises for alle kommunale afsendere.

Hvert selskab har sine ejerkommuner som faste steder, så nyhederne kan findes med stedfiltret. Det gælder også de selskaber, der var med i forvejen, når ejerne er bekræftet. Vestforbrænding har 19 ejerkommuner på Sjælland og får i stedet Region Hovedstaden. ARGO, Energnist, HOFOR og Motas har ingen faste steder, fordi de har for mange ejere, eller fordi ejerne ikke er bekræftet.

## Selskaber, der ikke hentes

Syv selskaber står i `sources.yaml` som kandidater eller fravalgte med en note og kan prøves igen senere.

- **Kredsløb** (Aarhus) svarer 403 til feedets UA, også på robots.txt. Det er botbeskyttelse, og den omgås ikke. Kredsløb har intet nyhedsrum hos Ritzau, som kortlægningen kunne finde.
- **Langeland Forsyning** svarer med en captcha, også på robots.txt, og den omgås heller ikke.
- **Reno Djurs, BOFA, Motas, Deponi Syd og Ressourceindsamling** har ingen nyheder på hjemmesiden.

Klintholm, der driver et deponi på Sydfyn, har ingen hjemmeside, som kortlægningen kunne finde, og står ikke i `sources.yaml`.

## Selskaberne

| Selskab | Ejerkommuner | Hentes via | Bemærkning |
|---|---|---|---|
| AffaldPlus | Faxe, Næstved, Ringsted, Slagelse, Sorø og Vordingborg | RSS |  |
| AFLD | Billund, Hedensted, Herning, Ikast-Brande, Ringkøbing-Skjern og Varde | RSS | Behandlingsanlæg i Tarm og Fasterholt |
| ARC (Amager Ressourcecenter) | Dragør, Frederiksberg, Hvidovre, København og Tårnby | RSS | Amager Bakke |
| ARGO |  | RSS | Ni kommuner på Sjælland |
| Arwos | Aabenraa | RSS | Affald, vand og spildevand |
| Assens Forsyning | Assens | Ritzau | Affald, vand og spildevand |
| BOFA | Bornholm | Hentes ikke | Ingen nyheder på hjemmesiden |
| Deponi Syd | Billund, Esbjerg, Haderslev, Kolding, Vejen, Vejle og Aabenraa | Hentes ikke | Deponi. Ingen nyheder på hjemmesiden |
| DIN Forsyning | Esbjerg og Varde | Ritzau | Affald, vand, spildevand og fjernvarme |
| Energnist |  | RSS | Affaldsenergi i Esbjerg og Kolding, 16 ejerkommuner |
| Favrskov Forsyning | Favrskov | Nyhedsliste | Affald, vand og spildevand |
| Faxe Forsyning | Faxe | Sitemap | Affald, vand og spildevand |
| FFV Energi & Miljø | Faaborg-Midtfyn | Sitemap | Affald, spildevand og fjernvarme |
| Fjernvarme Fyn | Nordfyns og Odense | Nyhedsliste | Mest fjernvarme, så strengt filter |
| Fors | Holbæk, Lejre og Roskilde | Ritzau | Affald, vand, spildevand og varme |
| Forsyning Helsingør | Helsingør | Sitemap | Affald, vand, spildevand og varme |
| Forsyningen (Frederikshavn) | Frederikshavn | Nyhedsliste | Affald, el, vand, spildevand og varme |
| Fredensborg Forsyning | Fredensborg | Sitemap | Affald, vand og spildevand |
| Glostrup Forsyning | Glostrup | Sitemap | Affald, vand, spildevand og fjernvarme |
| Gribskov Forsyning | Gribskov | Sitemap | Affald, vand og spildevand |
| Halsnæs Forsyning | Halsnæs | Sitemap | Affald, vand, spildevand og fjernvarme |
| Hillerød Forsyning | Hillerød | Sitemap | Affald, vand, spildevand og fjernvarme |
| HOFOR |  | RSS | Mest vand og varme, så strengt filter |
| HTK Forsyning | Høje-Taastrup | Nyhedsliste | Hed tidligere Høje-Taastrup Forsyning |
| Kerteminde Forsyning | Kerteminde | Nyhedsliste | Affald, vand, spildevand og fjernvarme |
| KLAR Forsyning | Greve, Køge, Solrød og Stevns | Nyhedsliste | Affald i Greve og Solrød |
| Kredsløb | Aarhus | Hentes ikke | Botbeskyttelse (403) |
| Langeland Forsyning | Langeland | Hentes ikke | Captcha på hjemmesiden |
| Lyngby-Taarbæk Forsyning | Lyngby-Taarbæk | Sitemap | Affald, vand og spildevand |
| Maabjerg Energy Center | Holstebro og Struer | Nyhedsliste | Affaldsenergi, ejet af Vestforsyning og Struer Forsyning |
| Middelfart Affald & Genbrug | Middelfart | Sitemap | Kun affald |
| Motas |  | Hentes ikke | Farligt affald, mange ejerkommuner. Ingen nyheder på hjemmesiden |
| Nomi4s | Holstebro, Lemvig, Skive og Struer | Nyhedsliste |  |
| Nordværk | Brønderslev, Hjørring, Jammerbugt, Mariagerfjord, Rebild og Aalborg | Sitemap | Tidligere Reno-Nord og AVV |
| Norfors | Allerød, Fredensborg, Helsingør, Hørsholm og Rudersdal | Nyhedsliste | Affald og fjernvarme |
| Nyborg Forsyning & Service | Nyborg | RSS | Affald, vand, spildevand og varme |
| Odense Renovation | Odense | Sitemap |  |
| Provas | Haderslev | Sitemap | Affald, vand og spildevand |
| REFA | Guldborgsund og Lolland | RSS |  |
| Ren Forsyning Mariagerfjord | Mariagerfjord | Sitemap | Sitemappet har ingen datoer |
| Reno Djurs | Norddjurs og Syddjurs | Hentes ikke | Ingen nyheder på hjemmesiden |
| Renosyd | Odder og Skanderborg | RSS |  |
| Ressourceindsamling |  | Hentes ikke | Indsamling, ejet via IPT I/S. Ingen nyheder på hjemmesiden |
| Revas | Viborg | Sitemap | Sitemappet har ingen datoer |
| Silkeborg Forsyning | Silkeborg | Ritzau | Affald, vand, spildevand og fjernvarme |
| SONFOR (Sønderborg Forsyning) | Sønderborg | RSS |  |
| Thy Forsyning | Thisted | Sitemap | Affald, vand og spildevand |
| Tønder Forsyning | Tønder | RSS | Affald, vand, spildevand og varme |
| Vand og Affald | Svendborg | Sitemap | Affald, vand og spildevand |
| Vestforbrænding | Region Hovedstaden | Sitemap | 19 ejerkommuner på Sjælland |
| Vesthimmerlands Forsyning | Vesthimmerlands | Sitemap | Sitemappet har ingen datoer |
| Ærø Forsyning | Ærø | Nyhedsliste | Nyhederne om affald |
