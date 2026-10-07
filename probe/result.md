# Afprøvning 2026-10-07T14:39:13Z

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

 # Webz.io - newer AI training agent
 # https://neil-clarke.com/block-the-bots-that-feed-ai-models-by-scraping-your-website/
 User-agent: Webzio-Extended
 Disallow: /

 # Timpi search - AI training
 # https://knownagents.com/agents/timpibot
 User-agent: Timpibot
 Disallow: /

 # ImagesiftBot - image scraping for AI generation
 # https://knownagents.com/agents/imagesiftbot
 User-agent: ImagesiftBot
 Disallow: /

 # DeepSeek - Chinese LLM (undocumented but observed)
 # https://knownagents.com/agents/deepseekbot
 User-agent: DeepSeekBot
 Disallow: /

 # Zhipu AI - ChatGLM training data (Chinese LLM)
 # https://knownagents.com/agents/chatglm-spider
 User-agent: ChatGLM-Spider
 Disallow: /

 # Huawei - PanGu LLM training data
 # https://knownagents.com/agents/pangubot
 User-agent: PanguBot
 Disallow: /

 # Firecrawl - web content extraction for LLM/AI apps
 # https://knownagents.com/agents/firecrawlagent
 User-agent: FirecrawlAgent
 Disallow: /

 # Apify - web content extraction for AI data scraping
 # https://knownagents.com/agents/apifywebsitecontentcrawler
 User-agent: ApifyWebsiteContentCrawler
 Disallow: /

 # Apify - undocumented AI bot
 # https://knownagents.com/agents/apifybot
 User-agent: ApifyBot
 Disallow: /

 #=======================================================================================================================
 # AI Autonomous Agents — browser-based agents that navigate and interact with websites
 #=======================================================================================================================

 # OpenAI - ChatGPT autonomous browser agent
 # https://knownagents.com/agents/chatgpt-agent
 User-agent: ChatGPT-Agent
 Disallow: /

 # Google - Project Mariner autonomous browser agent
 # https://knownagents.com/agents/googleagent-mariner
 User-agent: GoogleAgent-Mariner
 Disallow: /

 # Butterfly Effect - Manus autonomous browser agent (China)
 # https://knownagents.com/agents/manus-user
 User-agent: Manus-User
 Disallow: /

 # Amazon - Nova Act autonomous browser agent
 # https://knownagents.com/agents/novaact
 User-agent: NovaAct
 Disallow: /

 #=======================================================================================================================
 # AI Search / Assistant Crawlers — fetch content in real-time for AI-powered search answers
 #=======================================================================================================================

 # OpenAI - ChatGPT search and citations
 # https://platform.openai.com/docs/bots
 User-agent: OAI-SearchBot
 Disallow: /

 # OpenAI - user-initiated browsing in ChatGPT
 # https://platform.openai.com/docs/bots
 User-agent: ChatGPT-User
 Disallow: /

 # Anthropic - search quality indexing
 # https://support.anthropic.com/en/articles/8896518
 User-agent: Claude-SearchBot
 Disallow: /

 # Anthropic - user-initiated fetches in Claude
 # https://support.anthropic.com/en/articles/8896518
 User-agent: Claude-User
 Disallow: /

 # Anthropic - undocumented AI-related agent
 # https://knownagents.com/agents/claude-web
 User-agent: Claude-Web
 Disallow: /

 # Meta - user-initiated fetches for AI assistant
 # https://developers.facebook.com/docs/sharing/webmasters/crawler
 User-agent: Meta-ExternalFetcher
 Disallow: /

 # Meta - web indexing for Meta AI search results
 # https://knownagents.com/agents/meta-webindexer
 User-agent: meta-webindexer
 Disallow: /

 # Perplexity - AI search engine indexing
 # https://docs.perplexity.ai/guides/perplexitybot
 User-agent: PerplexityBot
 Disallow: /

 # Perplexity - user-initiated fetches
 # https://knownagents.com/agents/perplexity-user
 User-agent: Perplexity-User
 Disallow: /

 # You.com
 # https://knownagents.com/agents/youbot
 User-agent: YouBot
 Disallow: /

 # DuckDuckGo AI assistant
 # https://duckduckgo.com/duckduckgo-help-pages/results/duckassistbot
 User-agent: DuckAssistBot
 Disallow: /

 # Microsoft - Azure AI search indexing
 # https://knownagents.com/agents/azureai-searchbot
 User-agent: AzureAI-SearchBot
 Disallow: /

 # Brave - AI search engine
 # https://knownagents.com/agents/bravebot
 User-agent: Bravebot
 Disallow: /

 # Huawei - Petal Search and AI recommendations
 # https://knownagents.com/agents/petalbot
 User-agent: PetalBot
 Disallow: /

 # Exa - semantic search API for AI applications
 # https://knownagents.com/agents/exabot
 User-agent: ExaBot
 Disallow: /

 # Cloudflare - AI Search (AutoRAG) indexing
 # https://knownagents.com/agents/cloudflare-autorag
 User-agent: Cloudflare-AutoRAG
 Disallow: /

 # Amazon - AI search indexing for Alexa
 # https://knownagents.com/agents/amzn-searchbot
 User-agent: Amzn-SearchBot
 Disallow: /

 # Amazon - AI assistant (Alexa) user-initiated fetches
 # https://knownagents.com/agents/amzn-user
 User-agent: Amzn-User
 Disallow: /

 # Google - Gemini Deep Research
 # https://knownagents.com/agents/gemini-deep-research
 User-agent: Gemini-Deep-Research
 Disallow: /

 # Google - NotebookLM content fetching
 # https://knownagents.com/agents/google-notebooklm
 User-agent: Google-NotebookLM
 Disallow: /

 # Allen Institute for AI - deep research evaluations
 # https://knownagents.com/agents/ai2bot-deepresearcheval
 User-agent: AI2Bot-DeepResearchEval
 Disallow: /

 # Mistral - Le Chat user-initiated browsing
 # https://knownagents.com/agents/mistralai-user
 User-agent: MistralAI-User
 Disallow: /

 # Phind - AI-powered developer search
 # https://knownagents.com/agents/phindbot
 User-agent: PhindBot
 Disallow: /

 # Kagi - AI assistant content fetching
 # https://knownagents.com/agents/kagi-fetcher
 User-agent: kagi-fetcher
 Disallow: /

 # Tavily - AI search API (undocumented)
 # https://knownagents.com/agents/tavilybot
 User-agent: TavilyBot
 Disallow: /

 # Crawl4AI - open-source AI crawling tool
 # https://knownagents.com/agents/crawl4ai
 User-agent: Crawl4AI
 Disallow: /

 # iAsk - AI search engine
 # https://knownagents.com/agents/iaskbot
 User-agent: iAskBot
 Disallow: /

 # iAsk - AI search spider
 # https://knownagents.com/agents/iaskspider
 User-agent: iaskspider
 Disallow: /

 # Wrtn - AI platform (undocumented)
 # https://knownagents.com/agents/wrtnbot
 User-agent: WRTNBot
 Disallow: /

 #=======================================================================================================================
 # Standard crawl rules
 #=======================================================================================================================

 User-agent: *
 Disallow: /archive/
 Disallow: /auth
 Disallow: /user/addTrial
 Disallow: /metrics
 Disallow: /health
 Disallow: /cache
 Disallow: /esi
 Disallow: /mark-variant-won
 Disallow: /article/5253094
 Disallow: /Sygdom___Sundhed/article5253094.ece
 Disallow: /service/cbp
 Sitemap: https://ctwatch.dk/sitemapindex.xml
 
```

## https://ctwatch.dk/ai.txt

```text
status 200, text/plain, 15 bytes, slut-URL https://ctwatch.dk/ai.txt

[object Object]
```

