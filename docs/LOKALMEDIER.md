# Lokalmedier pr. kommune

Oversigten viser, hvilke lokale og regionale medier der dækker hver af de 98 kommuner, og hvordan feedet henter dem. Den bygger på en kortlægning fra 8. oktober 2026, hvor medierne også blev afprøvet fra GitHub Actions. Oversigten er et øjebliksbillede. Kommer en kilde til eller falder fra, rettes tabellerne i hånden.

## Sådan hentes medierne

Feedet henter et lokalmedie på en af to måder.

- **Direkte.** Mediet er en kilde i `sources.yaml` og hentes via RSS, sitemap eller forsiden med strengt filter. Artikler med et tydeligt affaldsord i titlen eller adressen kommer med.
- **Kun via søgning.** Mediet står i `config/medier.yaml` og kommer kun med, når nyhedssøgningen finder artiklen. Søgningen giver omkring 25 resultater pr. runde for hele landet, så de fleste lokale artikler bliver ikke fundet.

Et medie, der hverken er kilde eller står i `medier.yaml`, dækkes ikke. Alle kommuner dækkes desuden af en TV 2-region og af DR's regionale redaktioner, som begge hentes direkte.

## Huller i kortlægningen

Kortlægningen søgte på nettet efter medier i hver kommune, men loftet på 200 websøgninger blev nået undervejs. I 33 kommuner er der søgt målrettet, også efter uafhængige netaviser. I de øvrige 65 bygger oversigten på de store mediehuses egne lister (Jysk Fynske Medier, Sjællandske Medier, Nordjyske, Din Avis og Midtjyske Medier) og på de medier, repoet kendte i forvejen. Her kan der mangle uafhængige netaviser.

De 65 kommuner er Albertslund, Ballerup, Bornholm, Brøndby, Dragør, Frederiksberg, Furesø, Gladsaxe, Glostrup, Gribskov, Halsnæs, Herlev, Hillerød, Hvidovre, Hørsholm, Ishøj, Rudersdal, Rødovre og Vallensbæk i Region Hovedstaden. Faxe, Holbæk, Kalundborg, Næstved, Odsherred, Ringsted, Slagelse, Sorø, Stevns og Vordingborg i Region Sjælland. Aabenraa, Billund, Esbjerg, Fanø, Fredericia, Haderslev, Kolding, Langeland, Middelfart, Nordfyns, Odense, Svendborg, Sønderborg, Tønder, Varde, Vejen, Vejle og Ærø i Region Syddanmark. Aarhus, Herning, Holstebro, Ikast-Brande, Lemvig, Odder, Randers, Ringkøbing-Skjern, Samsø, Silkeborg, Skanderborg, Skive, Struer og Viborg i Region Midtjylland. Læsø, Mariagerfjord, Rebild og Thisted i Region Nordjylland.

Dagbladenes dækningsområder er delvis udledt af deres lokalredaktioner. En stjerne (*) efter et navn betyder, at kortlægningen ikke har bekræftet, at mediet udgiver i 2026.

## Kommuner uden fundet lokalmedie

Brøndby, Glostrup og Rødovre mistede deres ugeaviser, da Sjællandske Medier lukkede dem i 2026. I Ishøj, Vallensbæk og Læsø er der ikke fundet noget lokalmedie, men de tre kommuner er kun søgt overfladisk. Alle seks dækkes stadig af TV 2 og DR.

## Medier, der ikke hentes direkte

Ti medier findes kun via søgningen, fordi de ikke kan hentes på en høflig og generisk måde:

- Randers Ugeavis spærrer for feedets User-Agent i robots.txt.
- Magasinet KBH og Netavisen Grindsted svarer 403, og Fanø Posten svarer 406. Feedet omgår ikke den slags afvisninger.
- Skjern-Tarm Ugeblad, Avisen 2770 og Bryggebladet lægger kun hele udgivelser ud, ikke enkelte artikler med titler.
- Gråsten Avis' feed har ikke haft nye indslag siden 2021, og KunMedierne har ikke udgivet siden 2025.
- Blokhus Avis er et grænsetilfælde med meget event- og turiststof.

Sytten medier dækkes slet ikke:

- Syv netaviser med samme skabelon (Faxe, Favrskov, Guldborgsund, Hedensted, Lolland, Syddjurs og Vordingborg Netavis) samt Det Rigtige Faaborg og Vordingborg.in. Kortlægningen kunne ikke bekræfte en navngiven redaktør eller en henvisning til Pressenævnet, så de opfylder ikke troværdighedskravet endnu. De syv netaviser bliver ofte opdateret i samme minut, så indholdet ser ud til at være fælles.
- Der Nordschleswiger skriver på tysk, som feedet ikke understøtter. Den står som kandidat i `sources.yaml`.
- Christianshavneren, Kjerteminde Avis, Onsdagsavisen i Horsens, Lokalavisen Nordsjælland og tre lokalradioer (Radio Djursland, Radio Rønde og Radio Sydhavsøerne) har ingen hjemmeside, som kortlægningen kunne finde.

To poster i den gamle liste var ikke aviser. thisted-dagblad.dk samler annoncørbetalte indlæg fra Det Nordjyske Mediehus, og aars.dk er en side for lokale medlemmer og virksomheder. De er fravalgt i `sources.yaml` og er ikke med i tabellerne.

## Kommunerne

Tabellerne viser de medier, kortlægningen fandt i hver kommune. For de direkte kilder står metoden i parentes. Et dagblad eller en fælles titel står under alle de kommuner, den dækker.

### Region Hovedstaden

| Kommune | Hentes direkte | Kun via søgning | Ikke dækket |
|---|---|---|---|
| Albertslund | AlbertslundNYT (forside), Albertslund Posten* (sitemap) |  |  |
| Allerød | Frederiksborg Amts Avis (sitemap), Allerød Nyt (sitemap) |  |  |
| Ballerup | Ballerup Bladet (sitemap) |  |  |
| Bornholm | Bornholms Tidende (RSS), Bornholm.nu (forside), Bornholmnyt (RSS) |  |  |
| Brøndby | | | |
| Dragør | AmagerLIV (sitemap), Dragør Nyt (sitemap) |  |  |
| Egedal | Frederiksborg Amts Avis (sitemap), Lokalavisen Egedal (sitemap) |  |  |
| Fredensborg | Frederiksborg Amts Avis (sitemap), Uge-Nyt Fredensborg (sitemap), TjekFredensborg (RSS) |  |  |
| Frederiksberg | FrederiksbergLIV (sitemap) |  |  |
| Frederikssund | Frederiksborg Amts Avis (sitemap), Lokalavisen Frederikssund (sitemap), Hornsherred Lokalavis (RSS), Netavisen Sjælland (Frederikssund Posten) (RSS) |  |  |
| Furesø | Frederiksborg Amts Avis (sitemap), Furesø Avis (sitemap), Alt om Furesø (RSS) |  |  |
| Gentofte | Villabyerne (sitemap) |  |  |
| Gladsaxe | GladsaxeNetNyt (forside), Gladsaxe Bladet* (sitemap) |  |  |
| Glostrup | | | |
| Gribskov | Frederiksborg Amts Avis (sitemap), Ugeavisen Gribskov (tidl. Ugeposten Gribskov) (sitemap), Netavisen Gribskov (RSS) |  |  |
| Halsnæs | Frederiksborg Amts Avis (sitemap), Halsnæs Avis (sitemap) |  |  |
| Helsingør | Frederiksborg Amts Avis (sitemap), Helsingør Dagblad (sitemap) |  | Lokalavisen Nordsjælland* |
| Herlev | Herlev Bladet (RSS) |  |  |
| Hillerød | Frederiksborg Amts Avis (sitemap), Hillerød Posten (sitemap) |  |  |
| Hvidovre | Hvidovre Avis (forside), HvidovreNyt (forside) |  |  |
| Høje-Taastrup | Lokalavisen Taastrup (sitemap) |  |  |
| Hørsholm | Frederiksborg Amts Avis (sitemap), Ugebladet Hørsholm (sitemap) |  |  |
| Ishøj | | | |
| København | KøbenhavnLIV (sitemap), ØsterbroLIV* (sitemap), AmagerLIV (sitemap), Ørestad Avis (RSS), Nordhavn Avis (RSS), MigogKBH (RSS) | Bryggebladet*, Magasinet KBH* | Christianshavneren* |
| Lyngby-Taarbæk | Det Grønne Område* (sitemap) |  |  |
| Rudersdal | Rudersdal Avis (sitemap) |  |  |
| Rødovre | | | |
| Tårnby | AmagerLIV (sitemap) | Avisen 2770* |  |
| Vallensbæk | | | |

### Region Sjælland

| Kommune | Hentes direkte | Kun via søgning | Ikke dækket |
|---|---|---|---|
| Faxe | Sjællandske (Næstved og Slagelse) (sitemap), Haslev-Faxe Posten (sitemap), Netavisen Sjælland (RSS) |  | Faxe Netavis* |
| Greve | DAGBLADET (Roskilde, Køge, Ringsted) (sitemap), Sydkysten (inkl. Solrød Avis) (sitemap), Netavisen Sjælland (RSS) |  |  |
| Guldborgsund | Lolland-Falsters Folketidende (sitemap), Ugeavisen Guldborgsund (sitemap), Saxkjøbing Avis (sitemap), Netavisen Sjælland (RSS), GuldborgsundNyt (RSS) |  | Radio Sydhavsøerne*, Guldborgsund Netavis* |
| Holbæk | Nordvestnyt (Holbæk/Odsherred og Kalundborg) (sitemap), Ugeavisen Holbæk (sitemap), Netavisen Sjælland (RSS) |  |  |
| Kalundborg | Nordvestnyt (Holbæk/Odsherred og Kalundborg) (sitemap), Ugeavisen Kalundborg (sitemap), Netavisen Sjælland (RSS) |  |  |
| Køge | DAGBLADET (Roskilde, Køge, Ringsted) (sitemap), Ugeavisen Køge (sitemap), Netavisen Sjælland (RSS) |  |  |
| Lejre | DAGBLADET (Roskilde, Køge, Ringsted) (sitemap), Ugeavisen Lejre (sitemap), Netavisen Sjælland (RSS), LejreMagasinet (MitLejre) (RSS), Hornsherred Lokalavis (RSS) |  |  |
| Lolland | Lolland-Falsters Folketidende (sitemap), Ugeavisen Lolland (sitemap), Netavisen Sjælland (RSS) |  | Radio Sydhavsøerne*, Lolland Netavis* |
| Næstved | Sjællandske (Næstved og Slagelse) (sitemap), Ugeavisen Næstved (sitemap), Netavisen Sjælland (RSS) |  |  |
| Odsherred | Nordvestnyt (Holbæk/Odsherred og Kalundborg) (sitemap), Ugeavisen Odsherred (sitemap), Netavisen Sjælland (RSS) |  |  |
| Ringsted | DAGBLADET (Roskilde, Køge, Ringsted) (sitemap), Lokalbladet Ringsted (sitemap), Netavisen Sjælland (RSS) |  |  |
| Roskilde | DAGBLADET (Roskilde, Køge, Ringsted) (sitemap), Roskilde Avis (sitemap), Netavisen Sjælland (RSS) |  |  |
| Slagelse | Sjællandske (Næstved og Slagelse) (sitemap), Ugeavisen Slagelse (sitemap), Netavisen Sjælland (RSS) |  |  |
| Solrød | DAGBLADET (Roskilde, Køge, Ringsted) (sitemap), Sydkysten (inkl. Solrød Avis) (sitemap), Netavisen Sjælland (RSS), Viborher (RSS) |  |  |
| Sorø | Sjællandske (Næstved og Slagelse) (sitemap), Sorø Avis (sitemap), Netavisen Sjælland (RSS) |  |  |
| Stevns | DAGBLADET (Roskilde, Køge, Ringsted) (sitemap), Stevnsbladet (sitemap), Netavisen Sjælland (RSS) |  |  |
| Vordingborg | Sjællandske (Næstved og Slagelse) (sitemap), Ugeavisen Sydsjælland og Møn (sitemap), Netavisen Sjælland (RSS) |  | Vordingborg Netavis, Vordingborg.in* |

### Region Syddanmark

| Kommune | Hentes direkte | Kun via søgning | Ikke dækket |
|---|---|---|---|
| Assens | Fyens Stiftstidende (sitemap), LokalAvisen Assens (sitemap), Folkebladet (Aarup) (RSS) |  |  |
| Billund | JydskeVestkysten (sitemap), Ugeavisen Billund-Grindsted (sitemap), BillundOnline (RSS) | Netavisen Grindsted* |  |
| Esbjerg | JydskeVestkysten (sitemap), Ugeavisen Esbjerg (sitemap), Ugeavisen Ribe (sitemap), Bramming Posten (RSS), Hjerting Posten (RSS), MigogEsbjerg (RSS) |  |  |
| Fanø | JydskeVestkysten (sitemap) | Fanø Posten* |  |
| Fredericia | Fredericia Dagblad (sitemap) |  |  |
| Faaborg-Midtfyn | Fyens Stiftstidende (sitemap), Fyns Amts Avis (sitemap), Ugeavisen Faaborg (sitemap), Midtfyns Posten* (sitemap) |  | Det Rigtige Faaborg |
| Haderslev | JydskeVestkysten (sitemap), Ugeavisen Haderslev (sitemap) |  | Der Nordschleswiger |
| Kerteminde | Fyens Stiftstidende (sitemap), Kerteminde Ugeavis (sitemap) |  | Kjerteminde Avis* |
| Kolding | JydskeVestkysten (sitemap), Ugeavisen Kolding (sitemap), Fællesavisen (RSS) |  |  |
| Langeland | Fyns Amts Avis (sitemap), Øboen (sitemap) |  |  |
| Middelfart | Fyens Stiftstidende (sitemap), Melfar Posten (sitemap) |  |  |
| Nordfyns | Fyens Stiftstidende (sitemap), Ugeavis for Nordfyn (JFM) (sitemap) |  |  |
| Nyborg | Fyens Stiftstidende (sitemap), Lokalavisen Nyborg (sitemap) |  |  |
| Odense | Fyens Stiftstidende (sitemap), Ugeavisen Odense (sitemap), MigogOdense (RSS) |  |  |
| Svendborg | Fyns Amts Avis (sitemap), Ugeavisen Svendborg (sitemap) |  |  |
| Sønderborg | JydskeVestkysten (sitemap), Ugeavisen Sønderborg (sitemap), SønderborgNYT (RSS) | Gråsten Avis* | Der Nordschleswiger |
| Tønder | JydskeVestkysten (sitemap), Ugeavisen Tønder (sitemap) |  | Der Nordschleswiger |
| Varde | JydskeVestkysten (sitemap), Ugeavisen Varde (sitemap), Vesterhavsposten* (sitemap) |  |  |
| Vejen | JydskeVestkysten (sitemap), Ugeavisen Vejen (sitemap), Migogvejen (forside) |  |  |
| Vejle | Vejle Amts Folkeblad (sitemap), Vores Lokalavis (Give) (sitemap) |  |  |
| Ærø | Fyns Amts Avis (sitemap), Øboen (sitemap) |  |  |
| Aabenraa | JydskeVestkysten (sitemap), Ugeavisen Aabenraa (sitemap) |  | Der Nordschleswiger |

### Region Midtjylland

| Kommune | Hentes direkte | Kun via søgning | Ikke dækket |
|---|---|---|---|
| Favrskov | Århus Stiftstidende (sitemap), Randers Amtsavis (sitemap), Din Avis Favrskov (RSS), Byens Nyt (RSS), PingvinNyt (RSS) |  | Favrskov Netavis |
| Hedensted | Horsens Folkeblad (sitemap), Vejle Amts Folkeblad (sitemap), Hedensted/Juelsminde Avis (Hedensted Avis) (sitemap), Tørring Folkeblad* (sitemap), Østjysk Næravis (RSS) |  | Hedensted Netavis* |
| Herning | Herning Folkeblad (forside) |  |  |
| Holstebro | Dagbladet Holstebro-Struer (sitemap), Holstebro Onsdag (sitemap), Dit Vinderup (Vinderup-Spøttrup Nyt) (forside) |  |  |
| Horsens | Horsens Folkeblad (sitemap), Horsens Posten (sitemap), Østjysk Næravis (RSS) |  | Onsdagsavisen (Horsens)* |
| Ikast-Brande | Herning Folkeblad (forside), Ikast Avis (Dit Ikast-Brande) (forside), Brande Bladet (RSS) |  |  |
| Lemvig | Folkebladet Lemvig (sitemap), LokalAvisen Lemvig (sitemap) |  |  |
| Norddjurs | Randers Amtsavis (sitemap), Din Avis Norddjurs (RSS), DjurslandsPosten* (RSS) |  | Radio Djursland* |
| Odder | Odder Avis (sitemap), Østjysk Næravis (RSS) |  |  |
| Randers | Randers Amtsavis (sitemap), Randers Onsdag (sitemap) | Randers Ugeavis* |  |
| Ringkøbing-Skjern | Dagbladet Ringkøbing-Skjern (sitemap), Ugeavisen Ringkøbing (sitemap), Ugeposten Skjern* (sitemap) | Skjern-Tarm Ugeblad* |  |
| Samsø | Samsø Posten (forside) |  |  |
| Silkeborg | Midtjyllands Avis (forside), Dit Kjellerup (Kjellerup Tidende) (forside) |  |  |
| Skanderborg | Din Avis Skanderborg* (RSS), Dit Ry (Ry Ugeavis) (forside), Galten Folkeblad (sitemap) |  |  |
| Skive | Skive Folkeblad (forside), Dit Salling (Salling-Mors Avis) (forside), Dit Vinderup (Vinderup-Spøttrup Nyt) (forside) |  |  |
| Struer | Dagbladet Holstebro-Struer (sitemap), Ugeavisen Struer* (sitemap) |  |  |
| Syddjurs | Randers Amtsavis (sitemap), Din Avis Syddjurs* (RSS), DjurslandsPosten* (RSS) |  | Syddjurs Netavis*, Radio Djursland*, Radio Rønde, Syddjurs Lokalradio* |
| Viborg | Viborg Folkeblad (sitemap), Viborg Nyt (sitemap), Bjerringbro Avis (sitemap), Ugeavisen Møldrup-Aalestrup* (sitemap), Dit Karup (Karup-Frederiks Ugeavis) (forside) |  |  |
| Aarhus | Århus Stiftstidende (sitemap), Din Avis Aarhus* (RSS), MigogAarhus (RSS) |  |  |

### Region Nordjylland

| Kommune | Hentes direkte | Kun via søgning | Ikke dækket |
|---|---|---|---|
| Brønderslev | Nordjyske (Nordjyske Stiftstidende) (sitemap), LigeHer.nu (Nordjyskes lokalaviser, inkl. Aalborg:nu) (sitemap), Midtvendsyssel Avis (RSS) |  |  |
| Frederikshavn | Nordjyske (Nordjyske Stiftstidende) (sitemap), LigeHer.nu (Nordjyskes lokalaviser, inkl. Aalborg:nu) (sitemap), Kanal Frederikshavn (forside), Midtvendsyssel Avis (RSS), Østvendsyssel Folkeblad (RSS) |  |  |
| Hjørring | Nordjyske (Nordjyske Stiftstidende) (sitemap), LigeHer.nu (Nordjyskes lokalaviser, inkl. Aalborg:nu) (sitemap), NordsøPosten (RSS), Østvendsyssel Folkeblad (RSS) |  |  |
| Jammerbugt | Nordjyske (Nordjyske Stiftstidende) (sitemap), LigeHer.nu (Nordjyskes lokalaviser, inkl. Aalborg:nu) (sitemap), Lokalavisen Vodskov-Vestbjerg-Vadum (sitemap), Jammerbugtposten (RSS) | Blokhus Avis / Blokhus Medier |  |
| Læsø | | | |
| Mariagerfjord | Nordjyske (Nordjyske Stiftstidende) (sitemap), LigeHer.nu (Nordjyskes lokalaviser, inkl. Aalborg:nu) (sitemap), Mariagerfjordposten (RSS) |  |  |
| Morsø | Nordjyske (Nordjyske Stiftstidende) (sitemap), LigeHer.nu (Nordjyskes lokalaviser, inkl. Aalborg:nu) (sitemap) | KunMedierne (KunMors, KunThy)* |  |
| Rebild | Nordjyske (Nordjyske Stiftstidende) (sitemap), Folkebladet Rebild (Midthimmerlands Folkeblad) (forside) |  |  |
| Thisted | Nordjyske (Nordjyske Stiftstidende) (sitemap), LigeHer.nu (Nordjyskes lokalaviser, inkl. Aalborg:nu) (sitemap) | KunMedierne (KunMors, KunThy)* |  |
| Vesthimmerlands | Nordjyske (Nordjyske Stiftstidende) (sitemap), Vesthimmerlands Avis (RSS), Farsø Avis (RSS) |  |  |
| Aalborg | Nordjyske (Nordjyske Stiftstidende) (sitemap), LigeHer.nu (Nordjyskes lokalaviser, inkl. Aalborg:nu) (sitemap), Lokalavisen Vodskov-Vestbjerg-Vadum (sitemap), Nibe Avis (RSS), Hasseris Avis (RSS), MigogAalborg (RSS) |  |  |
