# Afprøvning 2026-10-07T14:38:34Z

## https://ctwatch.dk/robots.txt

```text
status 200, text/plain, 10791 bytes, slut-URL https://ctwatch.dk/robots.txt


 ########################################################################################################################
 ### AI crawler reference                                                                                             ###
 ### The link below provides instructions to what kind of content can be used to train AI models on this website      ###
 ### https://ctwatch.dk/ai.txt
 ########################################################################################################################

 #=======================================================================================================================
 # AI Training Crawlers - collect content to train or fine-tune AI/LLM models
 #
 # Sources:
 #   OpenAI:    https://platform.openai.com/docs/bots
 #   Anthropic: https://support.anthropic.com/en/articles/8896518
 #   Google:    https://developers.google.com/search/docs/crawling-indexing/overview-google-crawlers
 #   Meta:      https://developers.facebook.com/docs/sharing/webmasters/crawler
 #   Community: https://github.com/ai-robots-txt/ai.robots.txt
 #   Agents:    https://knownagents.com/agents
 #=======================================================================================================================

 # Common Crawl (open dataset used for ML/AI training)
 # https://commoncrawl.org/big-picture/frequently-asked-questions
 User-agent: CCBot
 Disallow: /

 # OpenAI - model training (GPT-4, GPT-5, etc.)
 # https://platform.openai.com/docs/bots
 User-agent: GPTBot
 Disallow: /

 # Anthropic - model training
 # https://support.anthropic.com/en/articles/8896518
 User-agent: ClaudeBot
 Disallow: /

 # Anthropic - legacy training token (not on current official docs, but widely referenced)
 # https://github.com/ai-robots-txt/ai.robots.txt
 User-agent: anthropic-ai
 Disallow: /

 # Google - AI training (Gemini, Vertex AI, etc.)
 # https://developers.google.com/search/docs/crawling-indexing/overview-google-crawlers
 User-agent: Google-Extended
 Disallow: /

 # Google - Cloud Vertex AI
 # https://developers.google.com/search/docs/crawling-indexing/overview-google-crawlers
 User-agent: Google-CloudVertexBot
 Disallow: /

 # Google - generic crawler used for internal R&D
 # https://developers.google.com/search/docs/crawling-indexing/overview-google-crawlers
 User-agent: GoogleOther
 Disallow: /

 # ByteDance / TikTok - LLM training (Doubao)
 # https://knownagents.com/agents/bytespider
 User-agent: Bytespider
 Disallow: /

 # ByteDance - image scraping for AI products
 # https://knownagents.com/agents/imagespider
 User-agent: imageSpider
 Disallow: /

 # Apple - AI model training
 # https://support.apple.com/en-us/119829
 User-agent: Applebot-Extended
 Disallow: /

 # Amazon - web content indexing for AI products
 # https://developer.amazon.com/amazonbot
 User-agent: Amazonbot
 Disallow: /

 # Meta - AI training and product improvement
 # https://developers.facebook.com/docs/sharing/webmasters/crawler
 User-agent: Meta-ExternalAgent
 Disallow: /

 # Meta - broader AI bot
 # https://developers.facebook.com/docs/sharing/webmasters/crawler
 User-agent: FacebookBot
 Disallow: /

 # Cohere - AI model training
 # https://cohere.com/bot
 User-agent: cohere-ai
 Disallow: /

 # Cohere - dedicated training data crawler
 # https://github.com/ai-robots-txt/ai.robots.txt
 User-agent: cohere-training-data-crawler
 Disallow: /

 # Allen Institute for AI - general crawler
 # https://allenai.org/crawler
 User-agent: AI2Bot
 Disallow: /

 # Allen Institute for AI - training data for open-source models (Dolma)
 # https://knownagents.com/agents/ai2bot-dolma
 User-agent: Ai2Bot-Dolma
 Disallow: /

 # Diffbot - web data extraction for AI
 # https://docs.diffbot.com/reference/crawl
 User-agent: Diffbot
 Disallow: /

 # Webz.io / Omgili - sells crawled data to LLM companies
 # https://neil-clarke.com/block-the-bots-that-feed-ai-models-by-scraping-your-website/
 User-agent: Omgilibot
 Disallow: /

 # Webz.io - newer AI
```

## https://ctwatch.dk/sitemap.xml

```text
status 403, application/xml, 111 bytes, slut-URL https://ctwatch.dk/sitemap.xml

<?xml version="1.0" encoding="UTF-8"?>
<Error><Code>AccessDenied</Code><Message>Access Denied</Message></Error>
```

## https://cepos.dk/sitemap.xml

```text
status 200, text/xml; charset=UTF-8, 89561 bytes, slut-URL https://cepos.dk/sitemap.xml

<?xml version="1.0" encoding="UTF-8"?><?xml-stylesheet type="text/xsl" href="/__sitemap__/style.xsl"?>
<urlset xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:video="http://www.google.com/schemas/sitemap-video/1.1" xmlns:xhtml="http://www.w3.org/1999/xhtml" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1" xmlns:news="http://www.google.com/schemas/sitemap-news/0.9" xsi:schemaLocation="http://www.sitemaps.org/schemas/sitemap/0.9 http://www.sitemaps.org/schemas/sitemap/0.9/sitemap.xsd http://www.google.com/schemas/sitemap-image/1.1 http://www.google.com/schemas/sitemap-image/1.1/sitemap-image.xsd" xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>https://cepos.dk/</loc>
        <lastmod>2026-10-02</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/abent-seminar-den-smukke-borgerlighed/</loc>
        <lastmod>2024-10-01</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/cookie-og-privatlivspolitik/</loc>
        <lastmod>2024-08-28</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/english/</loc>
        <lastmod>2024-09-24</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/nyheder/</loc>
        <lastmod>2024-09-17</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/om-cepos/</loc>
        <lastmod>2024-09-25</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/presse/</loc>
        <lastmod>2026-07-27</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/privatlivspolitik/</loc>
        <lastmod>2024-08-27</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/soegeresultater/</loc>
    </url>
    <url>
        <loc>https://cepos.dk/stot-cepos/</loc>
        <lastmod>2026-07-10</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/undervisning/</loc>
        <lastmod>2024-08-20</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/viden/</loc>
        <lastmod>2025-09-29</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/1-700-sygeplejersker-fritages-for-topskatten-ved-oget-topskattegraense/</loc>
        <lastmod>2021-11-08</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0001-646000-personer-i-den-erhvervsaktive-alder-er-pa-overforselsindkomst/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/2-200-flere-praktikpladser-ved-at-saenke-elevlonnen-med-5-kr-i-timen/</loc>
        <lastmod>2016-04-12</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/2-artiers-skattereformer-storrelse-af-skattelettelserne-og-effekter-pa-arbejdsudbud/</loc>
        <lastmod>2024-09-12</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0002-danmark-har-de-12-hojeste-offentlige-udgifter-blandt-oecd-landene/</loc>
        <lastmod>2026-02-03</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/2-millioner-personer-pa-overforelsesindkomst-i-2015/</loc>
        <lastmod>2010-11-24</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/2-ud-af-3-danskere-onsker-at-privathospitalerne-skal-forblive-en-del-af-sundhedssystemet/</loc>
        <lastmod>2012-10-15</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/2-ud-af-3-synes-at-skat-pa-sundhedsforsikringer-er-en-darlig-ide/</loc>
        <lastmod>2011-11-25</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/3-800-sygeplejersker-betaler-topskat-i-2022/</loc>
        <lastmod>2015-11-17</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0003-danmark-har-de-7-hojeste-offentlige-udgifter-til-forskning-og-udvikling-blandt-oecd-landene/</loc>
        <lastmod>2025-01-16</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/3-ud-af-43%c2%bd-mio-over-18-ar-modtager-overforselsindkomst/</loc>
        <lastmod>2017-12-27</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/3f-vildleder-om-overforsler-og-skattetryk/</loc>
        <lastmod>2019-01-04</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0004-danmark-har-den-9-laveste-ulighed-blandt-oecd-landene/</loc>
        <lastmod>2026-05-20</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0005-danmark-har-det-9-hojeste-offentlige-forbrug-blandt-oecd-landene/</loc>
        <lastmod>2026-02-20</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0006-danmark-har-oecds-hojeste-skattetryk-i-2024/</loc>
        <lastmod>2025-12-18</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/7-000-ikke-vestlige-indvandrere-i-job-ved-at-indfore-en-indslusningslon-pa-70-kr-i-timen/</loc>
        <lastmod>2015-06-02</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/7-000-indvandrere-i-job-ved-indslusningslon/</loc>
        <lastmod>2015-06-02</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/8-500-flere-til-administration-efter-kommunalreform/</loc>
        <lastmod>2010-02-08</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0008-hojere-efterlonsalder-oger-beskaeftigelsen/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0009-hojere-produktivitet-giver-hojere-lon/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/10-000-flere-skal-betale-topskat-de-kommende-ar/</loc>
        <lastmod>2024-08-30</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0010-kontanthjaelp-hvor-meget-far-man-udbetalt/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0011-konsekvenser-af-at-afskaffe-mellemskat-topskat-og-toptopskat/</loc>
        <lastmod>2026-02-03</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/11-milliarder-kroner-kan-forsvinde-forbavsende-hurtigt-isaer-nar-man-serverer-dem-for-sultne-politikere/</loc>
        <lastmod>2024-06-04</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/12-000-kr-ekstra-arligt-til-hver-lo-familie-fra-lokkes-skattelettelser-siden-2015/</loc>
        <lastmod>2018-10-22</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/12-13-kr-i-manedlig-gevinst-ved-lavtlonsjob-for-person-pa-maksimal-dagpenge/</loc>
        <lastmod>2015-05-07</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0012-su-til-personer-med-lang-videregaende-uddannelse-mindsker-ikke-uligheden-set-over-hele-livet/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/13-pct-af-vaelgerne-vil-betale-prisen-for-efterlonsordningen/</loc>
        <lastmod>2008-11-14</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0013-topskatten-har-kun-lille-betydning-for-uligheden/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0014-uligheden-reduceres-med-ca-35-pct-nar-man-ser-pa-livsindkomster/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/15-pct-pensionsfradrag-loser-samspilsproblemer-i-pensionssystemet-1/</loc>
        <lastmod>2017-05-24</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/15-pct-pensionsfradrag-loser-samspilsproblemer-i-pensionssystemet/</loc>
        <lastmod>2017-05-24</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0015-velfaerdskoalitionen-overforselsmodtagere-og-offentligt-ansatte-udgor-6-ud-af-10-voksne/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0016-danmark-har-de-8-hojeste-offentlige-udgifter-til-uddannelse-blandt-oecd-landene/</loc>
        <lastmod>2026-02-20</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0017-hoj-og-uens-beskatning-af-kapitalafkast-i-danmark/</loc>
        <lastmod>2024-09-11</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/18-000-flere-faglaerte-i-2025-ved-bortfald-af-efterlon/</loc>
        <lastmod>2016-05-09</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0018-danmark-har-den-3-hojeste-skat-pa-aktieudbytte-blandt-oecd-lande/</loc>
        <lastmod>2026-02-03</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0020-dagpenge-hoj-kompensationsgrad-ved-ledighed-for-lavtlonnede-i-danmark-sammenlignet-med-oecd-lande/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/20-pct-af-fleksjobberne-kunne-klare-et-job-uden-offentlig-stotte/</loc>
        <lastmod>2012-06-29</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0021-ikke-videnskabelig-dokumentation-for-dynamiske-effekter-af-offentligt-forbrug/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0022-global-fattigdom-er-reduceret-markant-siden-1990-13-mia-loftet-ud-af-fattigdom/</loc>
        <lastmod>2025-01-13</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0023-imf-undersogelse-oget-frihandel-giver-hojere-produktivitet/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0024-danskerne-har-et-lavere-privatforbrug-end-vores-velstandsniveau-tilsiger/</loc>
        <lastmod>2026-08-03</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/25-aars-arbejdsudbudsreformer/</loc>
        <lastmod>2026-04-08</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0025-efter-indforelse-af-budgetloven-og-sanktionsmekanismen-overholder-kommunerne-budgetterne/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/26-anbefalinger-til-omkostningseffektivt-energiforlig/</loc>
        <lastmod>2018-02-09</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0026-danskerne-har-lav-samlet-arbejdsindsats-blandt-oecd-lande-trods-hoj-beskaeftigelsesgrad/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0027-top-1-pct-betaler-108-pct-af-alle-skatter-og-afgifter-svarende-til-127-mia-kr/</loc>
        <lastmod>2026-02-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0028-veldokumenteret-at-lavere-topskat-har-positive-effekter-pa-arbejdsindsats-og-velstand/</loc>
        <lastmod>2024-09-11</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0029-absolutte-og-relative-fattigdomsgraenser/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/29-millioner-personer-er-enten-pa-overforelsesindkomst-eller-offentligt-ansat/</loc>
        <lastmod>2013-08-20</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/30-000-personer-i-beskaeftigelse-ved-reduktion-i-dagpengeperiode-til-1-ar/</loc>
        <lastmod>2007-01-07</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/30-ar-efter-berlinmuren-ideen-om-at-borgerne-tilhorer-staten-stortrives-stadig/</loc>
        <lastmod>2019-11-11</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0030-reformer-der-oger-vaekst-og-beskaeftigelse-oger-ogsa-uligheden/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0031-kun-1-ud-af-7-med-lav-indkomst-defineres-som-relativt-fattig/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0032-danskerne-har-4-hojeste-produktivitet-og-10-laveste-arbejdsindsats-blandt-oecd-landene/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0033-77-personer-pa-overforselsindkomst-for-hver-100-personer-i-beskaeftigelse/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0035-svagt-incitament-til-at-tage-lavtlonsjob-for-dagpengemodtagere-pa-maksimale-dagpenge/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0036-mediemarkedet-er-i-hastigt-opbrud/</loc>
        <lastmod>2024-09-11</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0037-mediestotte-dr-modtager-37-mia-kr-6-gange-sa-meget-som-private-aktorer/</loc>
        <lastmod>2024-09-11</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0038-licens-international-sammenligning/</loc>
        <lastmod>2024-09-11</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0039-oget-arbejdsudbud-medforer-oget-beskaeftigelse/</loc>
        <lastmod>2025-01-13</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0040-velstandseffekt-af-forskellige-skattelettelser-topskat-bundskat-beskaeftigelsesfradrag-mv/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0041-beskaeftigelseseffekt-af-forskellige-skattelettelser-topskat-bundskat-beskaeftigelsesfradrag-mv/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0042-top-10-pct-betaler-324-pct-af-alle-skatter-og-afgifter-svarende-til-382-mia-kr/</loc>
        <lastmod>2026-02-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0043-undervisningseffekten/</loc>
        <lastmod>2024-12-10</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/44-000-far-forhojet-marginalskatten-som-folge-af-indkomstaftrapningen-af-bornechecken/</loc>
        <lastmod>2012-08-01</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0044-mange-boligejere-med-dyre-ejendomme-har-lave-indkomster-2/</loc>
        <lastmod>2024-09-11</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/44-pct-med-en-lang-videregaende-uddannelse-betaler-topskat/</loc>
        <lastmod>2016-08-15</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0045-kommunepotentiale/</loc>
        <lastmod>2024-09-11</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0048-4-ud-af-10-vil-betale-topskat-pa-et-tidspunkt-i-livet/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0049-imf-analyse-om-ulighed-og-omfordeling-er-ikke-relevant-for-danmark/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0050-oecd-analyse-af-ulighed-ikke-relevant-for-danmark/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0051-unge-under-30-ar-op-til-8000-kr-ekstra-i-kontanthjaelp-ved-at-blive-erklaeret-ikke-jobparat/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0052-dobbelt-sa-mange-ikke-jobparate-kontanthjaelpsmodtagere-i-darligste-kommune-sammenlignet-med-bedste-kommune/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0053-stor-stigning-i-offentlige-bevillinger-til-forskning-siden-2006/</loc>
        <lastmod>2026-08-07</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0054-hvad-er-en-marginalskat/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/55-000-flere-ikke-vestlige-indvandrere-i-job-fjerner-negativt-bidrag-pa-offentlige-finanser/</loc>
        <lastmod>2015-12-11</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/55-000-ikke-vestlige-indvandrere-i-job-fjerner-negativt-bidrag-pa-offentlige-finanser/</loc>
        <lastmod>2015-12-11</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0055-hvad-er-en-sammensat-marginalskat/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0056-2-mio-danskere-er-pa-overforselsindkomst-naesten-halvdelen-af-de-voksne-danskere/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0058-knap-halvdelen-er-ude-af-den-1-arige-lavindkomstgruppe-efter-1-ar/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0059-danmark-har-det-4-hojeste-niveau-for-udviklingsbistand-blandt-oecd-lande/</loc>
        <lastmod>2026-08-07</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0060-danmark-har-det-11-storste-beskaeftigelsesgab-for-indvandrere-blandt-oecd-lande/</loc>
        <lastmod>2025-01-16</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0062-skatteprovenu-fra-boligskatter-er-hojt-i-en-international-sammenligning/</loc>
        <lastmod>2026-05-20</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0064-robotter-og-anden-ny-teknologi-truer-ikke-beskaeftigelsen/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0065-lille-lonpraemie-ved-at-tage-en-videregaende-uddannelse-i-danmark/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0069-det-offentlige-forbrugs-andel-af-bnp-over-tid/</loc>
        <lastmod>2025-09-19</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0070-hoj-tillid-skyldes-ikke-velfaerdsstaten/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0071-udviklingen-i-venezuela-og-chile-illustrerer-betydning-af-okonomisk-frihed/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0072-top-1-pct-betaler-108-pct-af-alle-skatter-og-afgifter-i-2024-en-stigning-fra-64-pct-i-1994/</loc>
        <lastmod>2026-02-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0073-skat-pa-arbejde-er-en-skat-pa-samhandel-mellem-personer/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0074-danmark-har-det-naestmest-progressive-skattesystem-i-oecd/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/74-pct-af-pendlere-takker-nej-til-en-betalingsring/</loc>
        <lastmod>2011-11-22</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/75-pct-af-stigningen-i-skattetrykket-fra-1970-2001-skyldes-kommuneskatten/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0076-skattestop-standsede-stigning-i-kommuneskatter/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0077-flere-offentligt-ansatte-i-2026-end-i-2010/</loc>
        <lastmod>2026-08-07</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0081-markant-fald-i-privatforbrugets-andel-af-bnp-over-de-sidste-60-ar/</loc>
        <lastmod>2025-10-14</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/81-pct-af-danskerne-mener-der-kan-fas-mere-service-for-pengene-i-den-offentlige-sektor/</loc>
        <lastmod>2008-07-28</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0082-danmark-har-hoj-grad-af-okonomisk-frihed/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0083-lande-med-hoj-grad-af-okonomisk-frihed-har-ogsa-et-hojt-velstandsniveau/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0084-hoj-grad-af-okonomisk-frihed-i-danmark-pa-trods-af-hoje-skatter-og-stor-offentlig-sektor/</loc>
        <lastmod>2024-12-26</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0085-danmark-havde-skattetryk-pa-25-pct-af-bnp-i-1960-som-i-usa/</loc>
        <lastmod>2026-04-21</lastmod>
    </url>
    <url>
        <loc>https://cepos.dk/artikler/0087-hoj-okonomisk-frihed-gavner-folk-med-lave-indkomster/</loc>
    
```

## https://www.aau.dk/robots.txt

```text
status 200, text/plain; charset=UTF-8, 22 bytes, slut-URL https://www.aau.dk/robots.txt

User-agent: *
Allow: /
```

## https://www.cbs.dk/robots.txt

```text
status 200, text/plain; charset=UTF-8, 1683 bytes, slut-URL https://www.cbs.dk/robots.txt

User-agent: *
# CSS, JS, Images
Allow: /core/*.css$
Allow: /core/*.css?
Allow: /core/*.js$
Allow: /core/*.js?
Allow: /core/*.gif
Allow: /core/*.jpg
Allow: /core/*.jpeg
Allow: /core/*.png
Allow: /core/*.svg
Allow: /profiles/*.css$
Allow: /profiles/*.css?
Allow: /profiles/*.js$
Allow: /profiles/*.js?
Allow: /profiles/*.gif
Allow: /profiles/*.jpg
Allow: /profiles/*.jpeg
Allow: /profiles/*.png
Allow: /profiles/*.svg
# Directories
Disallow: /core/
Disallow: /profiles/
# Files
Disallow: /README.md
Disallow: /composer/Metapackage/README.txt
Disallow: /composer/Plugin/ProjectMessage/README.md
Disallow: /composer/Plugin/Scaffold/README.md
Disallow: /composer/Plugin/VendorHardening/README.txt
Disallow: /composer/Template/README.txt
Disallow: /modules/README.txt
Disallow: /sites/README.txt
Disallow: /themes/README.txt
Disallow: /web.config
# Paths (clean URLs)
Disallow: /admin/
Disallow: /comment/reply/
Disallow: /filter/tips
Disallow: /node/add/
Disallow: /search/
Disallow: /user/register
Disallow: /user/password
Disallow: /user/login
Disallow: /user/logout
Disallow: /media/oembed
Disallow: /*/media/oembed
Disallow: /?query=
Disallow: /?keywords=
# Paths (no clean URLs)
Disallow: /index.php/admin/
Disallow: /index.php/comment/reply/
Disallow: /index.php/filter/tips
Disallow: /index.php/node/add/
Disallow: /index.php/search/
Disallow: /index.php/user/password
Disallow: /index.php/user/register
Disallow: /index.php/user/login
Disallow: /index.php/user/logout
Disallow: /index.php/media/oembed
Disallow: /index.php/*/media/oembed
Sitemap: https://www.cbs.dk/en/sitemap.xml
Sitemap: https://www.cbs.dk/sitemap.xml
```

## https://www.itu.dk/robots.txt

```text
status 200, text/plain; charset=utf-8, 147 bytes, slut-URL https://www.itu.dk/robots.txt


   User-agent: AhrefsBot
   Disallow: /

   User-agent: *
   Disallow: /docadm/
   Disallow: /kommunikation/
   Disallow: /sitecore/
     
```

