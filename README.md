# ⚡ AI & Data Science News Intelligence Engine

An automated, production-grade intelligence platform that continuously ingests, cleans, clusters, ranks, and analyzes technical news, academic preprints, and developer community discussions across Artificial Intelligence, Machine Learning, and Data Science.

Equipped with a **Hybrid RAG (Retrieval-Augmented Generation)** assistant, **Model Radar** for emerging AI models and benchmarks, **Daily Executive Briefing synthesis**, and an interactive web interface.

---

## 🌟 Key Features

- 🔄 **Automated 24-Hour Scheduling**: Background daemon (`APScheduler`) automatically fetches, updates, and ranks feeds every 24 hours (or on-demand via UI / CLI).
- 🛡️ **Multi-Tier Deduplication**: URL normalization, SHA256 content hashing, and semantic near-duplicate story clustering via dense embeddings (`all-MiniLM-L6-v2`).
- ⚡ **Parallel Full-Text Extraction**: Concurrent web scraping via `trafilatura` (12 worker threads) to extract clean article content and strip ads/navigation.
- 🏷️ **Hybrid AI Classification**: Powered by Google **Gemini 3.5 Flash Lite** to classify content into 5 domain categories and extract structured tags.
- 📈 **Dynamic Recency & Authority Scoring**: Time-decay scoring with an exponential 36-hour half-life, authority weighting, and cross-source coverage boost.
- 🎯 **Model Radar**: Dedicated tracking of new model releases, weights, licenses, architecture updates, and benchmark claims.
- 💬 **Citation-Backed Hybrid RAG**: Combines SQLite FTS5 (BM25 keyword search) with ChromaDB (vector cosine similarity) using Reciprocal Rank Fusion (RRF), enforced with verified, click-through source citations.
- ☕ **Daily Executive Digest**: Daily briefing synthesizing key themes, research breakthroughs, and strategic shifts using **Gemini 3.5 Flash**.
- 💻 **Modern Web Interface**: Responsive interface with zero heavy frontend framework dependencies (Vanilla JS/CSS), dark mode, bookmarks, and real-time ingestion diagnostics.

---

## 🏗️ System Architecture & Workflow

```
 ┌────────────────────────────────────────────────────────────────────────┐
 │                           INGESTION SOURCES                            │
 │  RSS Feeds  •  arXiv Papers  •  Hacker News  •  Reddit  •  Google News │
 └───────────────────────────────────┬────────────────────────────────────┘
                                     │ (Runs every 24h via APScheduler)
                                     ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                      INGESTION & PROCESSING ENGINE                     │
 │  1. Exact Deduplication (URL & SHA256 Hash of Title + Summary)         │
 │  2. Parallel Full-Text Extraction (ThreadPoolExecutor + Trafilatura)   │
 │  3. Topic Classification & Tagging (gemini-3.5-flash-lite)             │
 │  4. Dense Embedding & Story Clustering (all-MiniLM-L6-v2, sim >= 0.85) │
 │  5. Dynamic Half-Life Scoring & AI Key Takeaways (Top 30 batch)        │
 │  6. Model Radar Entity Extraction (Models, Orgs, Versions, Benchmarks) │
 └──────────────────┬─────────────────────────────────┬───────────────────┘
                    │                                 │
                    ▼                                 ▼
       ┌─────────────────────────┐       ┌────────────────────────┐
       │     SQLite Database     │       │   ChromaDB Vectors     │
       │  (Articles, Clusters,   │       │  (Chunk Embeddings     │
       │  Entities, FTS5 Search) │       │   for Semantic Search) │
       └────────────┬────────────┘       └───────────┬────────────┘
                    │                                │
                    └────────────────┬───────────────┘
                                     │
                                     ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                       API & RAG GENERATION LAYER                       │
 │  • Hybrid Retrieval: SQLite FTS5 (BM25) + ChromaDB (Vector RRF)        │
 │  • Intent Routing: Entity-specific vs Releases vs General RAG          │
 │  • LLM Answering: gemini-3.5-flash-lite (Escalate: gemini-3.5-flash)   │
 │  • Citation Enforcement: Strips uncited & hallucinated source links    │
 └───────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                        FRONTEND WEB APPLICATION                        │
 │  Feed • arXiv Papers • Model Radar • Daily Digest • Chat • Diagnostics │
 └────────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Dynamic Ranking & Scoring Algorithm

Every article is assigned a dynamic score calculated as:

$$\text{Score} = \text{priority\_weight} \times \text{recency\_decay} \times \text{source\_authority} \times \text{cluster\_boost}$$

### 1. Category Priority Weights
- `AI_LLM`: **1.0**
- `DATA_SCIENCE_ML`: **1.0**
- `AI_RESEARCH`: **0.8**
- `DATA_ENG_CLOUD`: **0.6**
- `TECH_GENERAL`: **0.4**

### 2. Recency Decay (Exponential Half-Life)
$$\text{recency\_decay} = e^{-\ln(2) \times \frac{\text{age\_hours}}{\text{half\_life\_hours}}}$$
With a default half-life of **36 hours**, an article's score naturally decays by 50% every 36 hours.

### 3. Cross-Coverage Cluster Boost
$$\text{cluster\_boost} = 1.0 + 0.15 \times \ln(\max(1, \text{cluster\_size}))$$
Stories reported concurrently by multiple outlets receive an organic boost proportional to coverage volume.

---

## 📡 Configured Ingestion Sources

Sources are defined in [`sources.yaml`](sources.yaml):

| Kind | Sources | Purpose |
| :--- | :--- | :--- |
| **Curated AI RSS** | OpenAI News, Google DeepMind, Hugging Face Blog, MIT Tech Review, VentureBeat AI, Towards Data Science, KDnuggets, The Gradient | Direct announcements, tutorials, and applied machine learning |
| **General Tech RSS** | TechCrunch, Ars Technica, The Verge, Dev.to AI | Broad tech developments and ecosystem news |
| **arXiv Research** | `cs.AI` (Artificial Intelligence), `cs.LG` (Machine Learning), `cs.CL` (Computation & Language) | Academic preprints and theoretical breakthroughs |
| **Community & Radar** | Hacker News (Algolia API), Reddit (`r/LocalLLaMA`, `r/MachineLearning`), Google News RSS | Breaking model releases, open-weights benchmarks, and developer discussions |

---

## 📁 Repository Structure

```
├── app/
│   ├── config.py              # Central application settings & environment variables
│   ├── main.py                # FastAPI entry point & lifespan scheduler
│   ├── worker.py              # APScheduler background worker (24h interval)
│   ├── sync_manager.py        # 10-step ingestion & processing coordinator
│   ├── llm.py                 # Gemini GenAI client (classification, takeaways, RAG)
│   ├── embeddings.py          # Sentence-transformers local embedding model
│   ├── ingestion/             # Fetchers: RSS, arXiv, Reddit, Hacker News, Trafilatura
│   ├── processing/            # Scoring, clustering, deduplication, radar entity extraction
│   ├── rag/                   # Hybrid retriever (FTS5 + ChromaDB), intent router, generator
│   ├── storage/               # SQLite database schemas and ChromaDB vector store
│   └── web/                   # Web API routes & Vanilla JS/CSS frontend UI
├── config/
│   └── entity_stoplist.txt    # Common tokens ignored during entity extraction
├── data/                      # Local SQLite database & ChromaDB vectors (gitignored)
├── docs/                      # Architectural specifications and design documents
├── scripts/
│   ├── ingest_now.py          # CLI trigger for immediate manual news ingestion
│   ├── test_rag.py            # CLI tool to test RAG search and answers
│   └── clean_and_backfill.py  # Utility to re-clean and backfill article takeaways
├── tests/                     # Unit and integration tests (pytest)
├── sources.yaml               # Configurable news & research feeds
├── requirements.txt           # Python dependencies
├── run.py                     # Local application runner (Uvicorn)
└── .env.example               # Example environment variables template
```

---

## 🚀 Quick Start Guide

### 1. Clone the Repository
```bash
git clone https://github.com/Sovandeth0063/News_query_AI.git
cd News_query_AI
```

### 2. Set Up Virtual Environment
```bash
# Windows
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy `.env.example` to `.env` and insert your Gemini API Key:
```bash
cp .env.example .env
```

Edit `.env`:
```env
# Google Gemini API Key (Required for AI features)
GEMINI_API_KEY=your_actual_gemini_api_key

# Refresh interval (hours)
INGEST_INTERVAL_HOURS=24
```

### 5. Run the Application
```bash
python run.py
```

Open your browser and navigate to:
- **Web UI**: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **API Documentation**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 🛠️ CLI Utilities & Testing

- **Run news ingestion immediately**:
  ```bash
  python scripts/ingest_now.py
  ```
- **Test RAG search & answers**:
  ```bash
  python scripts/test_rag.py "What are the latest developments in open-weights reasoning models?"
  ```
- **Run automated test suite**:
  ```bash
  python -m pytest tests/
  ```

---

## 🔌 API Endpoints Reference

| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Web UI frontend |
| `GET` | `/api/feed` | Ranked news articles with filter & search |
| `GET` | `/api/papers` | Academic arXiv preprints |
| `GET` | `/api/articles/{id}` | Article details and cross-coverage cluster siblings |
| `POST` | `/api/articles/{id}/read` | Mark article as read/unread |
| `POST` | `/api/articles/{id}/bookmark` | Toggle article bookmark |
| `GET` | `/api/radar` | Model Radar releases, updates, and benchmarks |
| `GET` | `/api/digest` | Daily executive AI briefing |
| `POST` | `/api/digest/generate` | Force synthesize a new daily digest |
| `POST` | `/api/chat` | AI Chat Assistant with citation-backed RAG |
| `POST` | `/api/sync` | Trigger background ingestion job |
| `GET` | `/api/sync/{run_id}` | Check ingestion progress |
| `GET` | `/api/sources` | Status and health of all configured sources |
| `GET` | `/api/sidebar` | Summary counters and trending topics |

---

## 📄 License
This project is open-source under the [MIT License](LICENSE).
