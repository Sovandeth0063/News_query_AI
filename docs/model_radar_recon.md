# Phase 0 Reconnaissance Report: Model Radar & Update Tracking

**Project:** AI & Data Science News Intelligence (NewsQuery)  
**Date:** September 21, 2026  
**Auditor:** Antigravity AI  

---

## 1. Directory Tree

```
News_query/
├── app/
│   ├── config.py                 # Application settings, model names, storage paths
│   ├── embeddings.py             # SentenceTransformers embedding service (all-MiniLM-L6-v2)
│   ├── llm.py                    # GeminiLLMService (gemini-3.5-flash-lite, gemini-3.5-flash)
│   ├── main.py                   # FastAPI application initialization & static mount
│   ├── sync_manager.py           # Background multi-stage ingestion & clustering manager
│   ├── worker.py                 # APScheduler background scheduled sync worker
│   ├── ingestion/
│   │   ├── arxiv_fetcher.py      # arXiv API preprint fetcher
│   │   ├── extractor.py          # Trafilatura / BeautifulSoup article text extractor
│   │   ├── normalizer.py         # URL canonicalizer, ISO UTC parser, clean_text()
│   │   └── rss_fetcher.py        # Feedparser async RSS fetcher
│   ├── processing/
│   │   ├── classifier.py         # Regex + LLM topic classifier
│   │   ├── clustering.py         # Embedding cosine distance story clustering
│   │   ├── dedup.py              # Exact URL & content hash deduplication
│   │   └── scoring.py            # Dynamic decay + authority + category ranking
│   ├── rag/
│   │   ├── digest.py             # Executive briefing generator & storage
│   │   ├── generator.py          # Grounded RAG chat answer generator
│   │   ├── query_parser.py       # Intent & keyword extractor
│   │   └── retriever.py          # Hybrid retrieval (FTS5 BM25 + Dense ChromaDB via RRF)
│   ├── storage/
│   │   ├── database.py           # SQLite database schema, FTS5 triggers, query helpers
│   │   └── vector_store.py       # ChromaDB persistent collection wrapper
│   └── web/
│       ├── api.py                # FastAPI REST API endpoints (/api/*)
│       └── static/
│           ├── index.html        # Dashboard HTML markup
│           ├── style.css         # Modern glassmorphism CSS design system
│           ├── js/               # Modular ES6 frontend components
│           │   ├── api.js        # Centralized HTTP client
│           │   ├── chat.js       # Ask AI chat controller
│           │   ├── digest.js     # Today's Digest controller
│           │   ├── feed.js       # Live feed & density controller
│           │   ├── main.js       # Application coordinator
│           │   ├── modal.js      # Story snippet preview modal
│           │   ├── papers.js     # arXiv research papers controller
│           │   ├── sidebar.js    # Dynamic intelligence sidebar widgets
│           │   ├── sources.js    # Ingested sources health drawer
│           │   ├── sync.js       # Background sync UI trigger
│           │   ├── tabs.js       # Roving tabindex tab bar
│           │   ├── theme.js      # Dark/light mode manager
│           │   ├── toast.js      # Accessible notification toasts
│           │   └── utils.js      # Date formatting, HTML sanitization
│           └── vendor/           # Vendored marked.min.js & purify.min.js
├── data/
│   ├── news.db                   # Primary SQLite database
│   └── chroma/                   # ChromaDB vector index directory
├── scripts/
│   ├── clean_and_backfill.py     # HTML entity purge & takeaway backfill script
│   ├── ingest_now.py             # CLI synchronous ingestion trigger
│   └── test_rag.py               # RAG validation script
├── tests/
│   └── test_components.py        # Pytest unit & integration test suite (15 tests)
├── sources.yaml                  # Feed definitions (RSS & arXiv)
├── requirements.txt              # Python package dependencies
└── run.py                        # Dev server runner (Uvicorn on :8000)
```

---

## 2. Active Database Schema (data/news.db)

Dumped directly from the active SQLite database:

### `sources`
- `id TEXT PRIMARY KEY`
- `name TEXT NOT NULL`
- `feed_url TEXT NOT NULL`
- `kind TEXT NOT NULL` (`rss` | `arxiv`)
- `category_hint TEXT`
- `authority REAL DEFAULT 1.0`
- `enabled INTEGER DEFAULT 1`
- `last_success_at TEXT`
- `consecutive_failures INTEGER DEFAULT 0`

### `story_clusters`
- `id TEXT PRIMARY KEY`
- `representative_article_id TEXT`
- `size INTEGER DEFAULT 1`
- `first_seen_utc TEXT`
- `last_seen_utc TEXT`

### `articles`
- `id TEXT PRIMARY KEY` (`art_<hex12>`)
- `source_id TEXT` (REFERENCES `sources(id)`)
- `url TEXT UNIQUE NOT NULL`
- `canonical_url TEXT`
- `title TEXT NOT NULL`
- `summary TEXT`
- `body TEXT`
- `takeaway TEXT` (Single-sentence insight under 25 words)
- `lang TEXT DEFAULT 'en'`
- `published_at_utc TEXT NOT NULL` (ISO-8601 UTC)
- `fetched_at_utc TEXT NOT NULL` (ISO-8601 UTC)
- `content_hash TEXT` (SHA-256)
- `cluster_id TEXT` (REFERENCES `story_clusters(id)`)
- `category TEXT NOT NULL` (`AI_LLM` | `DATA_SCIENCE_ML` | `AI_RESEARCH` | `DATA_ENG_CLOUD` | `TECH_GENERAL`)
- `tags_json TEXT DEFAULT '[]'`
- `priority_weight REAL DEFAULT 1.0`
- `score_cached REAL DEFAULT 0.0`
- `extraction_status TEXT DEFAULT 'full'` (`full` | `summary_only` | `failed`)
- `embedded INTEGER DEFAULT 0`

### `articles_fts` (Virtual FTS5 Table)
- `id UNINDEXED`, `title`, `summary`, `body`, `category UNINDEXED`, `content='articles'`, `content_rowid='rowid'`
- Auto-synced with `articles` via INSERT, DELETE, and UPDATE triggers (`articles_ai`, `articles_ad`, `articles_au`).

### `digests`
- `id TEXT PRIMARY KEY`
- `digest_date TEXT UNIQUE NOT NULL` (`YYYY-MM-DD`)
- `content_md TEXT NOT NULL`
- `article_ids_json TEXT NOT NULL`
- `model TEXT`
- `created_at_utc TEXT NOT NULL`

### `read_state`
- `article_id TEXT PRIMARY KEY REFERENCES articles(id) ON DELETE CASCADE`
- `is_read INTEGER DEFAULT 0`
- `is_bookmarked INTEGER DEFAULT 0`
- `updated_at_utc TEXT NOT NULL`

### `ingestion_runs`
- `id TEXT PRIMARY KEY` (`run_<hex12>`)
- `started_at TEXT NOT NULL`, `finished_at TEXT`
- `trigger TEXT NOT NULL` (`schedule` | `manual`)
- `fetched INTEGER DEFAULT 0`, `new INTEGER DEFAULT 0`, `dupes INTEGER DEFAULT 0`, `failed INTEGER DEFAULT 0`
- `status TEXT NOT NULL` (`running` | `completed` | `failed`)
- `error_log TEXT`

---

## 3. Source Ingestion Configuration

- **File**: `sources.yaml`
- **Supported `kind` values**: `rss` (fetched via `feedparser` in `app/ingestion/rss_fetcher.py`), `arxiv` (fetched via `app/ingestion/arxiv_fetcher.py`).
- **Loader**: `sync_sources_from_yaml(sources_list)` in `app/storage/database.py` upserts into SQLite table `sources`.
- **Scheduled & Manual Triggering**: Managed by `SyncManager` in `app/sync_manager.py` with threading locks and status tracking.

---

## 4. Current LLM Calling Conventions

- **Module**: `app/llm.py` via singleton `gemini_service = GeminiLLMService()`.
- **API Client**: `google.genai.Client(api_key=settings.GEMINI_API_KEY)`.
- **Configured Models**:
  - `MODEL_CLASSIFIER`: `gemini-3.5-flash-lite` (temperature 0.1, JSON mode)
  - `MODEL_DIGEST`: `gemini-3.5-flash` (temperature 0.3)
  - `MODEL_CHAT_PRIMARY`: `gemini-3.5-flash-lite` (temperature 0.2)
  - `MODEL_CHAT_ESCALATE`: `gemini-3.5-flash` (escalated when context > 5 chunks and comparative queries)
- **JSON Validation**: Uses `json.loads(response.text.strip())` guarded with try/except.
- **Fallback**: Returns heuristics/summary slices if `gemini_service.is_available()` is False or upon exception.

---

## 5. Embeddings, Vector Store & Retrieval

- **Embedding Model**: `sentence-transformers` running locally with `all-MiniLM-L6-v2` (384 dimensions).
- **Chunking**: `chunk_article()` in `app/embeddings.py` (chunks title + body with 400-char window and 60-char overlap).
- **ChromaDB**: `app/storage/vector_store.py` (`PersistentClient` at `data/chroma`, collection: `news_articles`).
- **Retrieval Signature**:
  ```python
  def hybrid_retrieve(query: str, top_k: int = 10, category_filter: Optional[str] = None, days_filter: Optional[int] = None) -> List[Dict[str, Any]]
  ```
  Combines Dense Vector Search (ChromaDB cosine similarity) and Sparse Text Search (SQLite FTS5 BM25 match) via Reciprocal Rank Fusion ($k=60$).

---

## 6. RAG / Chat Entry Point & Response Shape

- **Entry point**: `answer_user_query(question: str, history: Optional[List[Dict[str, str]]] = None)` in `app/rag/generator.py`.
- **Endpoint**: `POST /api/chat` accepting `{ question: str, history: List[dict] }`.
- **Response Shape**:
  ```json
  {
    "answer": "Grounded answer text with inline citations like [1], [2].",
    "sources": [
      {
        "index": 1,
        "title": "Article Title",
        "source": "Source Name",
        "published_at": "2026-09-20T12:00:00+00:00",
        "url": "https://..."
      }
    ],
    "model_used": "gemini-3.5-flash-lite"
  }
  ```

---

## 7. Existing Web API Endpoints

- `GET /api/feed` (category filter, search, sort=score|date, limit, offset)
- `GET /api/papers` (search, limit, offset)
- `GET /api/articles/{article_id}` (detail + cluster siblings)
- `POST /api/articles/{article_id}/read`
- `POST /api/articles/{article_id}/bookmark`
- `GET /api/digest` & `POST /api/digest/generate`
- `POST /api/chat`
- `POST /api/sync` & `GET /api/sync/{run_id}`
- `GET /api/sources`
- `GET /api/sidebar` (Top 3 today, topic counts, digest preview)

---

## 8. Test Setup & Verification Command

- Framework: `pytest` with `anyio`.
- Test suite: `tests/test_components.py` (15 passing tests).
- Execution command: `.\.venv\Scripts\python.exe -m pytest`.
- Web server launcher: `.\.venv\Scripts\python.exe run.py` (Uvicorn running on port 8000).

---

## 9. Assumptions, Compatibility & Conflict Analysis

### Key Finding: Article ID Type in `article_entities`
- **Spec note**: Section 3 of `refactored_prompt.md` wrote `article_id INTEGER NOT NULL REFERENCES articles(id)` in the example DDL.
- **Reality**: In our SQLite schema, `articles.id` is `TEXT PRIMARY KEY` (e.g. `art_1a2b3c4d5e6f`).
- **Resolution**: `article_entities.article_id` will be defined as `TEXT NOT NULL REFERENCES articles(id)` to match the primary key type.

### Key Finding: Extraction Status Disambiguation
- **Spec note**: Section 4.5 mentions "Full-text via the existing extractor; on failure keep the summary and set `extraction_status` of the text extraction accordingly (do not confuse it with LLM extraction status)."
- **Reality**: Our `articles` table currently has `extraction_status TEXT DEFAULT 'full'` (`full` | `summary_only` | `failed`), representing text crawling status.
- **Resolution**: We will add `llm_extraction_status TEXT DEFAULT 'pending'` (`pending` | `done` | `failed` | `skipped`) or alias it cleanly so HTML crawler status and LLM entity extraction status do not collide.

### Non-Breaking Design
All changes for Phase 1 to Phase 6 are strictly additive, matching Golden Rule #5. No existing endpoints, tables, or response shapes will be broken.
