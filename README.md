# ⚡ AI & Data Science News Intelligence Engine

An automated AI platform that continuously ingests, cleans, clusters, ranks, and analyzes technical news, academic preprints, and developer community discussions across Artificial Intelligence, Machine Learning, and Data Science.

Includes a **Hybrid RAG Chat Assistant**, **Model Radar** for tracking LLM releases, and an **Executive Daily Briefing**.

---

## 🚀 Quick Start

### 1. Clone & Setup Environment
```bash
git clone https://github.com/Sovandeth0063/News_query_AI.git
cd News_query_AI

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.\.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure `.env`
Copy `.env.example` to `.env` and add your Google Gemini API key:
```bash
cp .env.example .env
```
Inside `.env`:
```env
GEMINI_API_KEY=your_gemini_api_key_here
INGEST_INTERVAL_HOURS=24
```

### 4. Run the App
```bash
python run.py
```
Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** in your browser.  
API documentation is available at **[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)**.

---

## 🌟 Key Features

- 🔄 **Automated 24h Scheduler**: Background worker pulls fresh news daily (or on-demand with "Sync Now").
- 📑 **Smart Deduplication & Clustering**: Groups multiple outlets reporting on the same event into story clusters.
- 🏷️ **AI Classification & Takeaways**: Categorizes articles (`AI_LLM`, `DATA_SCIENCE_ML`, `AI_RESEARCH`, `DATA_ENG_CLOUD`, `TECH_GENERAL`) and generates bullet-point takeaways.
- 🎯 **Model Radar**: Automatically identifies and tracks new model launches, weights, and benchmarks.
- 💬 **Citation-Backed AI Chat**: Hybrid search (Keyword + Vector Embeddings) that answers technical queries with clickable source citations.
- ☕ **Daily Executive Digest**: One-click summary of the most critical daily advancements.

---

## 🔄 How It Works

```
Ingestion Sources (RSS, arXiv, Reddit, Hacker News, Google News)
                          │ (Every 24 Hours)
                          ▼
            Deduplication & Full-Text Scraping
                          │
                          ▼
        AI Classification & Story Clustering (Gemini)
                          │
                          ▼
             SQLite (FTS5) + ChromaDB (Vectors)
                          │
                          ▼
          Web Dashboard & Hybrid RAG Assistant
```

### Dynamic Ranking Formula
Articles are ranked by:
$$\text{Score} = \text{Category Weight} \times \text{Recency Decay (36h half-life)} \times \text{Source Authority} \times \text{Coverage Boost}$$

---

## 🛠️ Helpful Commands

- **Trigger Ingestion Immediately via CLI**:
  ```bash
  python scripts/ingest_now.py
  ```
- **Test AI Search & Retrieval**:
  ```bash
  python scripts/test_rag.py "What are the latest open-weight reasoning models?"
  ```
- **Run Tests**:
  ```bash
  python -m pytest tests/
  ```

---

## 📁 Project Structure

```
├── app/
│   ├── config.py         # App configurations
│   ├── worker.py         # 24h Background scheduler (APScheduler)
│   ├── sync_manager.py   # Ingestion & processing pipeline
│   ├── llm.py            # Gemini API integration
│   ├── ingestion/        # RSS, arXiv, Reddit, and HN scrapers
│   ├── processing/       # Scoring, clustering, and radar extraction
│   ├── rag/              # Hybrid retrieval and chat generator
│   ├── storage/          # SQLite database and ChromaDB vector store
│   └── web/              # FastAPI endpoints & web interface
├── sources.yaml          # Configurable list of news and RSS feeds
├── requirements.txt      # Python dependencies
└── run.py                # Server runner
```

---

## 📄 License
MIT License.
