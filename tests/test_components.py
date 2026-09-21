import pytest
from datetime import datetime, timezone, timedelta
from app.ingestion.normalizer import canonicalize_url, parse_to_utc_iso, compute_content_hash
from app.processing.scoring import calculate_article_score
from app.processing.classifier import rule_based_classify
from app.rag.generator import validate_citations
from app.storage.database import init_db, get_db_connection, upsert_article

def test_canonicalize_url():
    raw_url = "https://techcrunch.com/2026/09/20/new-ai-model/?utm_source=twitter&utm_medium=social&ref=feed#comments"
    canon = canonicalize_url(raw_url)
    assert "utm_source" not in canon
    assert "ref=feed" not in canon
    assert "#comments" not in canon
    assert canon == "https://techcrunch.com/2026/09/20/new-ai-model"

def test_date_parser():
    iso_date = parse_to_utc_iso("Mon, 21 Sep 2026 09:00:00 GMT")
    assert "2026-09-21" in iso_date
    assert "+00:00" in iso_date or "Z" in iso_date

def test_scoring_recency_and_priority():
    now_utc = datetime.now(timezone.utc)
    today_iso = now_utc.isoformat()
    four_days_ago_iso = (now_utc - timedelta(days=4)).isoformat()

    # Fresh AI story
    score_fresh_ai = calculate_article_score("AI_LLM", today_iso, source_authority=1.2, cluster_size=1)
    # 4-day-old AI story
    score_old_ai = calculate_article_score("AI_LLM", four_days_ago_iso, source_authority=1.2, cluster_size=1)
    # Fresh general tech story
    score_fresh_tech = calculate_article_score("TECH_GENERAL", today_iso, source_authority=1.0, cluster_size=1)

    # Assertions
    assert score_fresh_ai > score_old_ai, "Fresh AI story must outrank old AI story"
    assert score_fresh_ai > score_fresh_tech, "Fresh AI story must outrank fresh tech story"

def test_classifier_rules():
    ai_item = rule_based_classify("OpenAI releases new reasoning LLM model", "Benchmarking transformer architecture")
    assert ai_item["category"] == "AI_LLM"

    ds_item = rule_based_classify("Kaggle grandmaster tips for tabular data science", "Using PyTorch and pandas for feature engineering")
    assert ds_item["category"] == "DATA_SCIENCE_ML"

    tech_item = rule_based_classify("Sony unveils new OLED wireless headphones", "Battery lasts 30 hours on a single charge")
    assert tech_item["category"] == "TECH_GENERAL"

def test_citation_validator():
    text = "Recent breakthroughs in reasoning [1] and diffusion models [2] outshine older techniques [99]."
    validated = validate_citations(text, num_sources=3)
    assert "[1]" in validated
    assert "[2]" in validated
    assert "[99]" not in validated, "Out-of-bounds citations must be stripped"

def test_sqlite_fts_and_upsert():
    init_db()
    conn = get_db_connection()
    now_iso = datetime.now(timezone.utc).isoformat()
    test_article = {
        "id": "art_test_123",
        "url": "https://example.com/test-ai-article",
        "title": "Quantum Deep Learning Breakthrough",
        "summary": "Scientists merge quantum computing with deep learning neural networks.",
        "body": "Detailed content about quantum neural network training and convergence speeds.",
        "category": "AI_LLM",
        "published_at_utc": now_iso,
        "fetched_at_utc": now_iso,
        "score_cached": 1.2
    }
    is_new, art_id = upsert_article(test_article)
    assert is_new is True or art_id == "art_test_123"

    # Test FTS5 query
    cursor = conn.execute("SELECT title FROM articles_fts WHERE articles_fts MATCH 'title:Quantum';")
    row = cursor.fetchone()
    assert row is not None
    assert "Quantum" in row[0]
    conn.close()

def test_fts_hyphenated_search():
    from app.storage.database import get_articles_for_feed, get_papers, sanitize_fts_query
    from app.rag.retriever import search_fts

    init_db()
    conn = get_db_connection()
    now_iso = datetime.now(timezone.utc).isoformat()
    article = {
        "id": "art_test_hyphen_1",
        "url": "https://example.com/test-hyphen-models",
        "title": "Benchmarking Claude-3 vs GPT-4 and DeepSeek-R1 in C++",
        "summary": "Comprehensive benchmarks of GPT-4, Claude-3, and DeepSeek-R1 runtimes.",
        "body": "Detailed benchmark runtime test written in C++ for GPT-4 and Claude-3.",
        "category": "AI_LLM",
        "published_at_utc": now_iso,
        "fetched_at_utc": now_iso,
        "score_cached": 2.0
    }
    upsert_article(article)

    # Test feed search with hyphenated queries - must not throw SQLite syntax errors
    for query_str in ["GPT-4", "Claude-3", "DeepSeek-R1", "C++", "Claude-3 vs GPT-4"]:
        sanitized = sanitize_fts_query(query_str)
        assert sanitized != ""
        feed_results = get_articles_for_feed(search=query_str)
        assert isinstance(feed_results, list)
        fts_results = search_fts(query_str)
        assert isinstance(fts_results, list)

def test_fts_ai_ml_acronyms():
    from app.rag.retriever import search_fts, sanitize_search_tokens

    # Verify acronyms are preserved
    tokens_ai = sanitize_search_tokens("Latest breakthroughs in AI")
    assert "AI" in tokens_ai or "ai" in [t.lower() for t in tokens_ai]
    assert "in" not in [t.lower() for t in tokens_ai], "Stop-words like 'in' should be filtered"

    tokens_ml = sanitize_search_tokens("What is new in ML?")
    assert "ML" in tokens_ml or "ml" in [t.lower() for t in tokens_ml]
    assert "is" not in [t.lower() for t in tokens_ml]

    # Insert test article for AI and ML
    now_iso = datetime.now(timezone.utc).isoformat()
    article = {
        "id": "art_test_acronym_1",
        "url": "https://example.com/test-ai-ml-acronyms",
        "title": "State of AI and ML in Enterprise Production",
        "summary": "How AI and ML pipelines are being deployed at scale.",
        "body": "Engineering best practices for AI models and ML systems.",
        "category": "AI_LLM",
        "published_at_utc": now_iso,
        "fetched_at_utc": now_iso,
        "score_cached": 1.5
    }
    upsert_article(article)

    res_ai = search_fts("AI", limit=100)
    assert len(res_ai) > 0, "Searching for 'AI' must return valid results rather than being stripped"
    assert any(r["article_id"] == "art_test_acronym_1" for r in res_ai)

    res_ml = search_fts("ML")
    assert any(r["article_id"] == "art_test_acronym_1" for r in res_ml)

def test_query_parser_word_boundary():
    from app.rag.query_parser import parse_query_filters

    # "html5" should NOT trigger DATA_SCIENCE_ML because of "ml" substring
    parsed_html = parse_query_filters("html5 updates for frontend development")
    assert parsed_html["category_filter"] is None

    # "million" or "fill" should NOT trigger AI_LLM because of "llm" substring
    parsed_million = parse_query_filters("startup reaches ten million users")
    assert parsed_million["category_filter"] is None

    # Genuine category matches with word boundary
    parsed_ml = parse_query_filters("what are the latest trends in ml?")
    assert parsed_ml["category_filter"] == "DATA_SCIENCE_ML"

    parsed_llm = parse_query_filters("what new llm was released today?")
    assert parsed_llm["category_filter"] == "AI_LLM"
    assert parsed_llm["date_from_iso"] is not None

    parsed_paper = parse_query_filters("show me latest arxiv papers")
    assert parsed_paper["category_filter"] == "AI_RESEARCH"

def test_half_life_scoring_exact():
    now_utc = datetime.now(timezone.utc)
    t0_iso = now_utc.isoformat()
    t_halflife_iso = (now_utc - timedelta(hours=36.0)).isoformat()
    t_2halflife_iso = (now_utc - timedelta(hours=72.0)).isoformat()

    s0 = calculate_article_score("AI_LLM", t0_iso, source_authority=1.0, cluster_size=1, half_life_hours=36.0)
    s_half = calculate_article_score("AI_LLM", t_halflife_iso, source_authority=1.0, cluster_size=1, half_life_hours=36.0)
    s_2half = calculate_article_score("AI_LLM", t_2halflife_iso, source_authority=1.0, cluster_size=1, half_life_hours=36.0)

    # Half life should be exactly 50% of initial score
    ratio_half = s_half / s0
    assert abs(ratio_half - 0.5) < 0.02, f"Expected ~0.5 at half-life, got {ratio_half}"

    # 2 half-lives should be ~25%
    ratio_2half = s_2half / s0
    assert abs(ratio_2half - 0.25) < 0.02, f"Expected ~0.25 at 2 half-lives, got {ratio_2half}"

    # Test naive ISO string (without timezone offset)
    naive_iso = now_utc.strftime("%Y-%m-%dT%H:%M:%S")
    s_naive = calculate_article_score("AI_LLM", naive_iso, source_authority=1.0, cluster_size=1, half_life_hours=36.0)
    assert abs(s_naive - s0) < 0.05, "Naive datetime should not crash or fallback to 24h age"

def test_upsert_article_updates_metadata():
    init_db()
    conn = get_db_connection()
    now_iso = datetime.now(timezone.utc).isoformat()
    with conn:
        conn.execute("DELETE FROM articles WHERE url = 'https://example.com/test-metadata-article';")
        conn.execute("INSERT OR IGNORE INTO story_clusters (id, size, first_seen_utc, last_seen_utc) VALUES ('cluster_abc123', 1, ?, ?);", (now_iso, now_iso))
    conn.close()

    art_id = "art_test_metadata_update"
    initial_art = {
        "id": art_id,
        "url": "https://example.com/test-metadata-article",
        "title": "Initial Title",
        "summary": "Initial summary",
        "body": "Initial body",
        "category": "TECH_GENERAL",
        "tags": ["initial"],
        "published_at_utc": now_iso,
        "fetched_at_utc": now_iso,
        "score_cached": 0.5,
        "cluster_id": None
    }
    is_new, _ = upsert_article(initial_art)
    assert is_new is True

    # Update with new category, cluster_id, score, and tags
    updated_art = {
        "id": art_id,
        "url": "https://example.com/test-metadata-article",
        "title": "Updated Title",
        "summary": "Updated summary",
        "body": "Updated body",
        "category": "AI_LLM",
        "tags": ["updated", "ai"],
        "published_at_utc": now_iso,
        "score_cached": 1.8,
        "cluster_id": "cluster_abc123"
    }
    is_new_up, art_id_up = upsert_article(updated_art)
    assert is_new_up is False
    assert art_id_up == art_id

    conn = get_db_connection()
    row = conn.execute("SELECT title, category, cluster_id, score_cached FROM articles WHERE id = ?", (art_id,)).fetchone()
    conn.close()
    assert row["title"] == "Updated Title"
    assert row["category"] == "AI_LLM"
    assert row["cluster_id"] == "cluster_abc123"
    assert abs(row["score_cached"] - 1.8) < 1e-4

def test_purge_expired_articles():
    from app.storage.database import purge_expired_articles, set_read_state
    init_db()
    conn = get_db_connection()

    old_iso = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
    now_iso = datetime.now(timezone.utc).isoformat()

    # Expired unbookmarked article
    upsert_article({
        "id": "art_expired_unbookmarked",
        "url": "https://example.com/expired-unbookmarked",
        "title": "Old news to purge",
        "category": "TECH_GENERAL",
        "published_at_utc": old_iso,
        "fetched_at_utc": old_iso
    })

    # Expired bookmarked article
    upsert_article({
        "id": "art_expired_bookmarked",
        "url": "https://example.com/expired-bookmarked",
        "title": "Old news saved by user",
        "category": "TECH_GENERAL",
        "published_at_utc": old_iso,
        "fetched_at_utc": old_iso
    })
    set_read_state("art_expired_bookmarked", is_bookmarked=True)

    # Fresh article
    upsert_article({
        "id": "art_fresh_keep",
        "url": "https://example.com/fresh-article",
        "title": "Fresh news to keep",
        "category": "TECH_GENERAL",
        "published_at_utc": now_iso,
        "fetched_at_utc": now_iso
    })

    purged = purge_expired_articles(retention_days=90)
    assert purged >= 1

    # Verify unbookmarked expired is gone, bookmarked remains, fresh remains
    conn = get_db_connection()
    assert conn.execute("SELECT id FROM articles WHERE id = 'art_expired_unbookmarked'").fetchone() is None
    assert conn.execute("SELECT id FROM articles WHERE id = 'art_expired_bookmarked'").fetchone() is not None
    assert conn.execute("SELECT id FROM articles WHERE id = 'art_fresh_keep'").fetchone() is not None
    conn.close()

def test_rrf_hybrid_fusion(monkeypatch):
    from app.rag.retriever import hybrid_retrieve
    from datetime import datetime, timezone

    now_iso = datetime.now(timezone.utc).isoformat()
    # Mock dense search to return article A and article B
    mock_dense = [
        {
            "id": "chunk_A_0",
            "text": "Dense content for A",
            "metadata": {
                "article_id": "art_A",
                "title": "Article A",
                "published_at_utc": now_iso
            }
        },
        {
            "id": "chunk_B_0",
            "text": "Dense content for B",
            "metadata": {
                "article_id": "art_B",
                "title": "Article B",
                "published_at_utc": now_iso
            }
        }
    ]

    # Mock FTS search to return article A and article C
    mock_fts = [
        {
            "article_id": "art_A",
            "title": "Article A",
            "summary": "FTS content for A",
            "published_at_utc": now_iso
        },
        {
            "article_id": "art_C",
            "title": "Article C",
            "summary": "FTS content for C",
            "published_at_utc": now_iso
        }
    ]

    monkeypatch.setattr("app.rag.retriever.vector_store.search", lambda **kwargs: mock_dense)
    monkeypatch.setattr("app.rag.retriever.search_fts", lambda *args, **kwargs: mock_fts)
    monkeypatch.setattr("app.rag.retriever.embedding_service.encode", lambda texts: [[0.1] * 384 for _ in texts])

    results = hybrid_retrieve("AI query", top_k=5)
    # Article A appeared in BOTH modalities, so its chunks must be ranked first (#1)
    assert len(results) > 0
    assert results[0]["metadata"]["article_id"] == "art_A"

def test_clean_text_advanced_purging():
    from app.ingestion.normalizer import clean_text
    raw = "Nvidia&#8217;s breakthrough [&#8230;] The post AI News appeared first on Towards Data Science."
    cleaned = clean_text(raw)
    assert "breakthrough" in cleaned
    assert "The post" not in cleaned
    assert "Towards Data Science" not in cleaned
    assert "&#8217;" not in cleaned
    assert "…" in cleaned

def test_takeaway_and_sidebar_api():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.storage.database import init_db, upsert_article

    init_db()
    client = TestClient(app)

    # 1. Test sidebar endpoint
    res = client.get("/api/sidebar")
    assert res.status_code == 200
    data = res.json()
    assert "top_today" in data
    assert "topic_counts" in data
    assert "digest_preview" in data

    # 2. Test feed endpoint with takeaway & DATA_ENG_CLOUD
    now_iso = datetime.now(timezone.utc).isoformat()
    test_article = {
        "id": "art_cloud_test_1",
        "url": "https://example-test-infra.org/cloud-data-pipeline",
        "title": "Scaling Distributed Data Pipelines with Apache Spark and Kubernetes",
        "summary": "Best practices for deploying fault-tolerant MLOps pipelines.",
        "takeaway": "Kubernetes orchestration cuts Spark MLOps pipeline latency by 40%.",
        "body": "Full body content for testing data engineering cloud pipeline scaling.",
        "category": "DATA_ENG_CLOUD",
        "published_at_utc": now_iso,
        "fetched_at_utc": now_iso,
        "score_cached": 1.5,
        "tags": ["Data Engineering", "Cloud", "Spark"]
    }
    upsert_article(test_article)

    feed_res = client.get("/api/feed?category=DATA_ENG_CLOUD")
    assert feed_res.status_code == 200
    articles = feed_res.json()["articles"]
    assert any(a["id"] == "art_cloud_test_1" for a in articles)
    matched = next(a for a in articles if a["id"] == "art_cloud_test_1")
    assert matched["takeaway"] == "Kubernetes orchestration cuts Spark MLOps pipeline latency by 40%."

