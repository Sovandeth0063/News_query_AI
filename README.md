# ⚡ NewsQuery: AI & Data Science News Intelligence Engine

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green.svg)](https://fastapi.tiangolo.com/)
[![Google Gemini](https://img.shields.io/badge/Gemini-3.5%20Flash%20%26%20Lite-orange.svg)](https://ai.google.dev/)
[![Vector Search](https://img.shields.io/badge/Embeddings-all--MiniLM--L6--v2-purple.svg)](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)
[![Database](https://img.shields.io/badge/Storage-SQLite%20(FTS5)%20%2B%20ChromaDB-blueviolet.svg)](https://www.sqlite.org/)
[![Tests](https://img.shields.io/badge/Tests-24%20Passing-brightgreen.svg)](https://docs.pytest.org/)

An automated, full-stack intelligence engine that continuously ingests, cleans, clusters, ranks, and analyzes technical news, academic preprints, and developer discussions across **Artificial Intelligence, Machine Learning, and Data Science**.

Equipped with an **Entity-Powered Model Radar**, **Citation-Backed Hybrid RAG Analyst**, **Executive Daily Briefings**, and a **Glassmorphism Web Dashboard** with offline-first vendored assets.

---

## 🌟 Key Features & Capabilities

### 📡 1. Model Radar & Entity Intelligence
- **Automated Event Detection**: Classifies stories into discrete event types (`model_release`, `model_update`, `research_paper`, `tool_release`, `benchmark_result`).
- **Entity Knowledge Graph**: Automatically extracts entities (models, organizations, creators, benchmarks, hardware) and resolves them into canonical representations with alias mapping.
- **Emerging Entity Spikes**: Detects velocity spikes when newly introduced entities gain multi-source coverage against historical baselines.
- **Entity Chronological Timelines**: Inspect complete release histories, benchmarks, and updates for any model or organization (e.g. tracking iterations across versions).

### 🔄 2. Multi-Source Ingestion Pipeline
- **Diverse Ingestion Adapters**:
  - 📰 **RSS/Atom**: Industry publishers, tech press, and research labs (VentureBeat, Hugging Face Blog, OpenAI, MIT Tech Review, TechCrunch, Ars Technica).
  - 🔬 **Academic Preprints (arXiv)**: Direct API integration querying `cs.AI`, `cs.LG`, and `cs.CL`.
  - 💬 **Hacker News (Algolia API)**: High-signal community submissions tracking model launches with points thresholds.
  - 🤖 **Reddit**: Filtered community intelligence from subreddits like `r/LocalLLaMA`.
  - 🌐 **Google News Aggregators**: Multi-outlet tracking of breaking model releases and funding rounds.
- **Automated Scheduler**: APScheduler background daemon running every 24 hours (configurable) or triggered on-demand via UI/API.
- **Deduplication & Full-Text Crawling**: URL canonicalization (stripping tracking parameters), SHA-256 content hashing, and Trafilatura-powered HTML article extraction.

### 📑 3. Story Clustering & Dynamic Decay Ranking
- **Dense Cosine Clustering**: SentenceTransformer embeddings (`all-MiniLM-L6-v2`) group articles reporting on the same event into story clusters.
- **Dynamic Half-Life Exponential Ranking**:
  $$\text{Score} = \text{Category Weight} \times \text{Source Authority} \times \text{Coverage Boost} \times 2^{-\frac{\text{age (hours)}}{36}}$$
  Articles stay relevant for breaking news while smoothly decaying over a 36-hour half-life.

### 💬 4. Citation-Backed Hybrid RAG Analyst
- **Hybrid Retrieval (RRF)**: Combines dense vector search (ChromaDB cosine similarity) with sparse keyword search (SQLite FTS5 BM25) using Reciprocal Rank Fusion ($k=60$).
- **Anti-Hallucination Guardrails**: Queries are routed through intent classifiers; answers include inline citations (`[1]`, `[2]`) linked to verified sources. Citations are strictly validated, stripping ungrounded numbers or returning a clean fallback when no evidence is found.
- **Tiered Gemini Engine**: Fast routing via `gemini-3.5-flash-lite`, with automatic escalation to `gemini-3.5-flash` for multi-source comparative queries or syntheses.

### ☕ 5. Executive Daily Briefing
- One-click daily briefing synthesizing the day's top technical breakthroughs into structured Markdown with takeaway bullet points.
- Date picker to review past briefings, with built-in quota confirmation prompts before regeneration.

### 🎨 6. Modern Glassmorphism Dashboard
- **5 Dedicated Tabs**: Live Feed, Model Radar, arXiv Papers, Today's Digest, Ask AI Analyst.
- **Interactive Reader Modal**: Displays extracted takeaways, tags, summary, sibling cluster coverage, and full article text.
- **Dynamic Sidebar**: Live top 3 stories today, active category distribution pills, and briefing snippet.
- **Zero External CDNs**: Vendored `marked.min.js` and `purify.min.js` for zero tracking, fast loads, and offline support.
- **Keyboard Shortcuts**: `/` to search, `T` to toggle dark/light theme, `D` to toggle compact density, `ESC` to dismiss modals, `← / →` to cycle tabs, and `?` for help.

---

## 🔄 System Architecture

```
                      INGESTION ADAPTERS
 ┌─────────────────────────────────────────────────────────────┐
 │ RSS / Atom Feeds │ arXiv API │ Hacker News │ Reddit │ GNews │
 └──────────────────────────────┬──────────────────────────────┘
                                │
                                ▼
 ┌─────────────────────────────────────────────────────────────┐
 │         Normalizer, Deduplication & HTML Extractor          │
 │         - Canonicalize URL & SHA-256 Content Hash           │
 │         - HTML Entity Purge & Trafilatura Full-Text         │
 └──────────────────────────────┬──────────────────────────────┘
                                │
                                ▼
 ┌─────────────────────────────────────────────────────────────┐
 │           AI Enrichment & Processing Pipeline               │
 │  - Local SentenceTransformers (all-MiniLM-L6-v2)            │
 │  - Cosine Distance Story Clustering & Half-Life Ranking     │
 │  - Gemini Entity Extraction, Event Classification & Radar   │
 └──────────────────────────────┬──────────────────────────────┘
                                │
                                ▼
 ┌─────────────────────────────────────────────────────────────┐
 │                     Dual-Storage Layer                      │
 │   - SQLite: Metadata, Clusters, Entities Graph & FTS5 BM25  │
 │   - ChromaDB: Dense 384-d Chunk Vector Embeddings           │
 └──────────────────────────────┬──────────────────────────────┘
                                │
                                ▼
 ┌─────────────────────────────────────────────────────────────┐
 │               FastAPI REST & RAG Serving Layer              │
 │  - Hybrid Search (RRF: FTS5 BM25 + Dense ChromaDB)          │
 │  - Tiered Gemini RAG Generator with Strict Citation Checker │
 │  - Responsive Glassmorphism Web App (Zero External CDNs)    │
 └─────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### 1. Prerequisites
- **Python 3.10+**
- **Git**
- Google Gemini API Key ([Get one free on Google AI Studio](https://aistudio.google.com/))

### 2. Clone & Setup Environment
```bash
git clone https://github.com/Sovandeth0063/News_query_AI.git
cd News_query_AI

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# Windows (cmd):
.\.venv\Scripts\activate.bat
# Linux / macOS:
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy `.env.example` to `.env` and configure your keys:
```bash
cp .env.example .env
```

Key environment settings in `.env`:
```env
# Required for AI summaries, classification, and RAG chat
GEMINI_API_KEY=your_gemini_api_key_here

# Tiered Models (Gemini 3+)
MODEL_CLASSIFIER=gemini-3.5-flash-lite
MODEL_DIGEST=gemini-3.5-flash
MODEL_CHAT_PRIMARY=gemini-3.5-flash-lite
MODEL_CHAT_ESCALATE=gemini-3.5-flash

# Storage & Database Paths
DB_PATH=./data/news.db
CHROMA_PATH=./data/chroma

# Ingestion & Ranking Parameters
INGEST_INTERVAL_HOURS=24
DISPLAY_TZ=UTC
DEDUP_SIM_THRESHOLD=0.85
RANK_HALF_LIFE_HOURS=36
RETENTION_DAYS=90

# Local Embeddings (Free, runs on CPU/GPU)
EMBEDDING_MODEL=all-MiniLM-L6-v2
```

### 5. Run the Application
```bash
python run.py
```
- Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** in your browser.
- Interactive OpenAPI documentation is available at **[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)**.

---

## 🛠️ CLI Operations & Scripts

The project includes purpose-built maintenance and testing scripts in `scripts/`:

| Command | Description |
| :--- | :--- |
| `python scripts/ingest_now.py` | Runs a complete, synchronous ingestion, clustering, and embedding run immediately. |
| `python scripts/check_sources.py` | Validates every source configured in `sources.yaml`, outputting parsed items, latency, and status codes. |
| `python scripts/clean_and_backfill.py` | Purges unescaped HTML entities from titles/summaries and generates batch LLM key takeaways. |
| `python scripts/test_rag.py "<query>"` | CLI tester for the Hybrid RAG retriever and citation-verified generator. |
| `pytest` | Runs all 24 automated unit and integration tests across normalizers, scoring, RAG citations, and the Model Radar. |

---

## 📡 REST API Reference

The engine provides a comprehensive REST API under `/api`:

### Feeds & Content
- `GET /api/feed`: Paginated, ranked articles with category filtering (`AI_LLM`, `DATA_SCIENCE_ML`, `DATA_ENG_CLOUD`, `TECH_GENERAL`), search, and sorting (`score` or `date`).
- `GET /api/papers`: Paginated arXiv academic research preprints with keyword search.
- `GET /api/articles/{id}`: Detailed article view with extracted body and sibling coverage from other sources.
- `POST /api/articles/{id}/read`: Toggle article read/unread state.
- `POST /api/articles/{id}/bookmark`: Toggle article bookmark state.

### Model Radar & Entities
- `GET /api/radar`: Filtered model releases and updates with entity associations, confidence scores, and cross-source coverage counts.
- `GET /api/entities`: Entity list with search, entity type filter (`model`, `org`, `person`, `benchmark`, `product`), and `emerging` status flag.
- `GET /api/entities/{id}`: Entity details including canonical name and all resolved aliases.
- `GET /api/entities/{id}/timeline`: Chronological event timeline for a specific model or organization.
- `POST /api/radar/reprocess`: Trigger re-extraction of entities and events for articles within a specified day window.

### Intelligence & Chat
- `GET /api/digest`: Retrieve today's (or a specified date's) executive briefing.
- `POST /api/digest/generate`: Force regenerate/synthesize an executive briefing using `gemini-3.5-flash`.
- `POST /api/chat`: Grounded RAG assistant conversation (`{"question": "...", "history": [...]}`) with clickable source citations.

### System & Telemetry
- `GET /api/sources`: List all configured sources, health status, and authority metrics.
- `GET /api/sidebar`: Dynamic widgets payload (Top 3 stories today, active topic counts, briefing preview).
- `POST /api/sync`: Trigger a background ingestion run protected by a global run lock.
- `GET /api/sync/{run_id}`: Poll background sync progress and stats.

---

## ⚙️ Source Configuration (`sources.yaml`)

News sources are declaratively configured in `sources.yaml`. Supported feed kinds include:

```yaml
sources:
  # Standard RSS Feed
  - id: huggingface_blog
    name: Hugging Face Blog
    feed_url: https://huggingface.co/blog/feed.xml
    kind: rss
    category_hint: AI_LLM
    authority: 1.3
    enabled: true

  # Academic arXiv Feed
  - id: arxiv_cs_ai
    name: arXiv Artificial Intelligence (cs.AI)
    feed_url: cs.AI
    kind: arxiv
    category_hint: AI_RESEARCH
    authority: 1.2
    enabled: true

  # Hacker News Keyword Stream
  - id: hn_new_models
    name: Hacker News - Model Launches
    kind: hn_algolia
    query: "AI model"
    min_points: 10
    lookback_hours: 72
    source_type: community
    category_hint: AI_LLM
    authority: 1.2
    enabled: true

  # Reddit Subreddit Feed
  - id: reddit_localllama
    name: Reddit - LocalLLaMA
    kind: reddit_rss
    feed_url: https://www.reddit.com/r/LocalLLaMA/.rss
    source_type: community
    category_hint: AI_LLM
    authority: 1.1
    enabled: true

  # Google News Topic Aggregator
  - id: gnews_model_launches
    name: Google News - Model Launches
    kind: google_news_rss
    query: "new AI model launch OR releases AI model OR emerges from stealth AI"
    source_type: aggregator
    category_hint: AI_LLM
    authority: 1.0
    enabled: true
```

---

## 📁 Project Structure

```
News_query/
├── app/
│   ├── config.py                 # Pydantic & environment settings
│   ├── embeddings.py             # SentenceTransformers embedding service & chunker
│   ├── llm.py                    # Official Google GenAI SDK wrapper (Gemini 3+)
│   ├── main.py                   # FastAPI initialization & static file mounting
│   ├── sync_manager.py           # Multi-stage ingestion & clustering manager
│   ├── worker.py                 # APScheduler background scheduled worker
│   ├── ingestion/
│   │   ├── arxiv_fetcher.py      # arXiv API client
│   │   ├── extractor.py          # Trafilatura & BeautifulSoup article content extractor
│   │   ├── google_news_fetcher.py# Google News RSS query aggregator
│   │   ├── hn_fetcher.py         # Hacker News Algolia search API client
│   │   ├── normalizer.py         # URL canonicalization, date parsing, text cleaner
│   │   ├── reddit_fetcher.py     # Reddit RSS community client
│   │   └── rss_fetcher.py        # Feedparser async RSS client
│   ├── processing/
│   │   ├── classifier.py         # Heuristic + LLM category classifier
│   │   ├── clustering.py         # Embedding cosine distance story clustering
│   │   ├── dedup.py              # URL & SHA-256 content deduplication
│   │   ├── entity_registry.py    # Canonical entity resolution, aliasing & timelines
│   │   ├── extraction_schemas.py # Pydantic extraction models & prompt schemas
│   │   ├── prefilter.py          # Fast regex prefilter for model release candidates
│   │   ├── radar_pipeline.py     # Batch entity extraction & radar pipeline
│   │   └── scoring.py            # Dynamic 36h exponential decay ranking
│   ├── rag/
│   │   ├── digest.py             # Executive briefing generator
│   │   ├── generator.py          # Grounded RAG answer generator with citation validator
│   │   ├── intent_router.py      # User intent classification & time window parsing
│   │   ├── query_parser.py       # Query entity & keyword extraction
│   │   └── retriever.py          # Hybrid retrieval (FTS5 BM25 + Dense ChromaDB via RRF)
│   ├── storage/
│   │   ├── database.py           # SQLite database schema, FTS5 triggers & queries
│   │   └── vector_store.py       # Persistent ChromaDB collection wrapper
│   └── web/
│       ├── api.py                # FastAPI REST API endpoints
│       └── static/
│           ├── index.html        # Responsive glassmorphism dashboard
│           ├── style.css         # Complete CSS design system (dark & light modes)
│           ├── js/               # Modular ES6 components (feed, radar, chat, digest)
│           └── vendor/           # Local vendored Marked & DOMPurify (Zero CDNs)
├── config/
│   └── entity_stoplist.txt       # Excluded generic words for entity extraction
├── data/
│   ├── news.db                   # SQLite primary database (auto-created)
│   └── chroma/                   # ChromaDB vector index directory (auto-created)
├── docs/
│   └── model_radar_recon.md      # Reconnaissance and technical specification notes
├── scripts/
│   ├── check_sources.py          # Ingestion sources verification script
│   ├── clean_and_backfill.py     # HTML entity cleanup & takeaway backfill script
│   ├── ingest_now.py             # CLI synchronous ingestion trigger
│   └── test_rag.py               # RAG assistant verification script
├── tests/
│   ├── fixtures/                 # Sample feed payloads and mocks
│   ├── test_components.py        # Unit & integration tests for core subsystems
│   └── test_radar.py             # Comprehensive test suite for Model Radar & migrations
├── sources.yaml                  # Source feed definitions
├── requirements.txt              # Production & test dependencies
├── run.py                        # Local development runner
└── README.md                     # Project documentation
```

---

## ⌨️ Keyboard Shortcuts

| Key | Action |
| :---: | :--- |
| `/` | Focus global search bar |
| `ESC` | Close active modal, reader, or drawer |
| `←` / `→` | Switch between dashboard tabs |
| `T` | Toggle dark and light theme |
| `D` | Toggle compact card density in the live feed |
| `?` | Open keyboard shortcuts reference modal |

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
