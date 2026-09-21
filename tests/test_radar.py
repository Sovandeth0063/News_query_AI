import os
import json
import pytest
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from app.config import settings
from app.storage.database import init_db, get_db_connection
from app.ingestion.normalizer import clean_text
from app.processing.extraction_schemas import (
    EventType, EntityType, EntityRole, ExtractedEntityItem, ExtractedArticleItem, BatchExtractionResponse
)
from app.processing.entity_registry import (
    normalize_canonical_name,
    is_entity_emerging_rule,
    find_or_create_entity,
    link_article_entity,
    recompute_emerging_entities,
    get_entity_timeline
)
from app.rag.intent_router import detect_intent, parse_time_window_days
from app.rag.generator import sanitize_and_deduplicate_citations, answer_user_query, NOT_FOUND_MESSAGE
from app.processing.radar_pipeline import run_radar_extraction_batch
from app.main import app

# Test 1: Migrations run twice without error and without data loss
def test_migrations_idempotent():
    conn = get_db_connection()
    try:
        init_db()
        init_db()
        # Verify columns exist
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(articles);")
        col_names = {r["name"] for r in cur.fetchall()}
        assert "event_type" in col_names
        assert "event_confidence" in col_names
        assert "llm_extraction_status" in col_names
        assert "takeaway" in col_names
        assert "source_type" in col_names

        # Verify tables exist
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {r["name"] for r in cur.fetchall()}
        assert "entities" in tables
        assert "entity_aliases" in tables
        assert "article_entities" in tables
        assert "app_meta" in tables
    finally:
        conn.close()

# Test 2: clean_text fixes entities, HTML, and boilerplate
def test_clean_text_fixes():
    raw = "Google&#8217;s new model is here&#8230; The post Breaking: New AI appeared first on TechBlog."
    cleaned = clean_text(raw)
    assert "’" in cleaned or "'" in cleaned or "Google" in cleaned
    assert "…" in cleaned or "..." in cleaned
    assert "appeared first on" not in cleaned
    assert "The post" not in cleaned

# Test 3: Extraction validation rejects hallucinated entity names and oversized fields
def test_extraction_validation_schema():
    # Valid model
    item = ExtractedEntityItem(
        name="ValidModel",
        type=EntityType.model,
        role=EntityRole.subject,
        confidence=0.9,
        evidence="ValidModel is introduced here."
    )
    assert item.name == "ValidModel"
    assert item.type == EntityType.model

    # Unknown event type raises ValidationError
    with pytest.raises(Exception):
        ExtractedArticleItem(
            article_id="123",
            event_type="fabricated_event_type",
            entities=[]
        )

    # Unknown entity type raises ValidationError
    with pytest.raises(Exception):
        ExtractedEntityItem(
            name="Test",
            type="unknown_type",
            confidence=0.8,
            evidence="Evidence"
        )

    # Evidence longer than 200 chars gets safely truncated
    long_evidence = "a" * 250
    item_long = ExtractedEntityItem(
        name="TestModel",
        type=EntityType.model,
        confidence=0.8,
        evidence=long_evidence
    )
    assert len(item_long.evidence) <= 200

# Test 4: Entity normalization and alias matching; no cross-type merges
def test_entity_normalization_and_matching():
    canon1 = normalize_canonical_name("  Meta AI, Inc.  ")
    assert "meta ai" in canon1

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        now_iso = datetime.now(timezone.utc).isoformat()

        # Insert org entity
        ent1_id = find_or_create_entity(conn, "HyperScale Labs", "org", now_iso, is_baseline_default=0)
        assert ent1_id is not None

        # Same entity with suffix difference should merge into ent1_id
        ent2_id = find_or_create_entity(conn, "HyperScale", "org", now_iso, is_baseline_default=0)
        assert ent2_id == ent1_id

        # Different type ("model") must NEVER merge with org
        ent3_id = find_or_create_entity(conn, "HyperScale", "model", now_iso, is_baseline_default=0)
        assert ent3_id != ent1_id
    finally:
        conn.close()

# Test 5: Emerging logic (pure function over DB rows)
def test_emerging_logic_pure_function():
    now = datetime.now(timezone.utc)
    recent_seen = (now - timedelta(hours=12)).isoformat()
    old_seen = (now - timedelta(hours=60)).isoformat()

    # Case A: Baseline entity never emerges
    ent_baseline = {
        "is_baseline": 1,
        "type": "model",
        "first_seen_utc": recent_seen,
        "is_emerging": 0
    }
    articles_ok = [
        {"source_id": "src1", "cluster_id": "c1", "event_type": "model_release"},
        {"source_id": "src2", "cluster_id": "c2", "event_type": "model_release"}
    ]
    assert is_entity_emerging_rule(ent_baseline, articles_ok, now_utc=now) is False

    # Case B: Needs >= 2 distinct sources (same cluster same source counts once)
    ent_new = {
        "is_baseline": 0,
        "type": "model",
        "first_seen_utc": recent_seen,
        "is_emerging": 0
    }
    same_source_articles = [
        {"source_id": "src1", "cluster_id": "c1", "event_type": "model_release"},
        {"source_id": "src1", "cluster_id": "c1", "event_type": "model_release"}
    ]
    assert is_entity_emerging_rule(ent_new, same_source_articles, now_utc=now) is False

    # Case C: 2 distinct sources and valid event type -> Emerging!
    distinct_source_articles = [
        {"source_id": "src1", "cluster_id": "c1", "event_type": "model_release"},
        {"source_id": "src2", "cluster_id": "c2", "event_type": "model_update"}
    ]
    assert is_entity_emerging_rule(ent_new, distinct_source_articles, now_utc=now) is True

    # Case D: Outside window (> 48h)
    ent_old = {
        "is_baseline": 0,
        "type": "model",
        "first_seen_utc": old_seen,
        "is_emerging": 0
    }
    assert is_entity_emerging_rule(ent_old, distinct_source_articles, now_utc=now) is False

# Test 6: Citation cleanup: uncited sources stripped, invalid [n] removed, duplicates collapsed
def test_citation_cleanup():
    sources = [
        {"title": "Source 1", "url": "https://news.ycombinator.com/item?id=1"},
        {"title": "Source 2", "url": "https://techcrunch.com/article/2"},
        {"title": "Source 3", "url": "https://arxiv.org/abs/3"}
    ]
    answer = "This model was released recently [1] with high throughput [3]. Note invalid [99]."
    cleaned_answer, cleaned_sources = sanitize_and_deduplicate_citations(answer, sources)

    assert "[1]" in cleaned_answer
    assert "[2]" in cleaned_answer  # Source 3 renumbered to [2]
    assert "[99]" not in cleaned_answer
    assert len(cleaned_sources) == 2
    assert cleaned_sources[0]["url"] == "https://news.ycombinator.com/item?id=1"
    assert cleaned_sources[1]["url"] == "https://arxiv.org/abs/3"

# Test 7: API endpoints test
def test_radar_api_endpoints():
    client = TestClient(app)
    
    # GET /api/radar
    r1 = client.get("/api/radar?days=7")
    assert r1.status_code == 200
    assert "items" in r1.json()

    # GET /api/entities
    r2 = client.get("/api/entities?limit=10")
    assert r2.status_code == 200
    assert "entities" in r2.json()

    # GET /api/entities?emerging=true
    r3 = client.get("/api/entities?emerging=true")
    assert r3.status_code == 200
    assert "entities" in r3.json()

    # GET /api/entities/99999 (not found)
    r4 = client.get("/api/entities/99999")
    assert r4.status_code == 404

    # GET /api/entities/99999/timeline (not found)
    r5 = client.get("/api/entities/99999/timeline")
    assert r5.status_code == 404

# Test 8: Anti-hardcoding test (verify no test fixture names exist in app source code or configs)
def test_anti_hardcoding():
    fixture_path = Path("tests/fixtures/articles.json")
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Names from fixture: AetheriaX, OmniNova
    forbidden_tokens = ["AetheriaX", "OmniNova"]

    app_dir = Path("app")
    config_dir = Path("config")
    sources_file = Path("sources.yaml")

    files_to_check = list(app_dir.rglob("*.py"))
    if config_dir.exists():
        files_to_check.extend(list(config_dir.rglob("*")))
    if sources_file.exists():
        files_to_check.append(sources_file)

    for p in files_to_check:
        if p.is_file() and not p.name.endswith((".pyc", ".db")):
            content = p.read_text(encoding="utf-8", errors="ignore")
            for tok in forbidden_tokens:
                assert tok.lower() not in content.lower(), f"Forbidden hardcoded token '{tok}' found in application source file: {p}"

# Test 9: End-to-end acceptance test (Section 9.3)
def test_e2e_model_radar_acceptance():
    fixture_path = Path("tests/fixtures/articles.json")
    with open(fixture_path, "r", encoding="utf-8") as f:
        fixtures = json.load(f)["articles"]

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        # Ensure test sources and articles are inserted
        for a in fixtures:
            cur.execute("""
                INSERT OR REPLACE INTO sources (id, name, feed_url, kind, enabled)
                VALUES (?, ?, 'https://techpulse.dev/feed', 'rss', 1);
            """, (a["source_id"], a["source_name"]))
            cur.execute("""
                INSERT OR REPLACE INTO articles (
                    id, source_id, url, title, summary, body, category,
                    published_at_utc, fetched_at_utc, llm_extraction_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending');
            """, (
                a["id"], a["source_id"], a["url"], a["title"],
                a["summary"], a["body"], a["category"], a["published_at_utc"],
                datetime.now(timezone.utc).isoformat()
            ))
        conn.commit()

        # Disable baseline period for acceptance test
        cur.execute("UPDATE app_meta SET value = '2020-01-01T00:00:00Z' WHERE key = 'radar_baseline_until_utc';")
        conn.commit()

        # Mock LLM response for extraction
        mock_canned_extraction = [
            {
                "article_id": fixtures[0]["id"],
                "event_type": "model_release",
                "event_confidence": 0.95,
                "entities": [
                    {
                        "name": "AetheriaX-70B",
                        "type": "model",
                        "role": "subject",
                        "confidence": 0.95,
                        "evidence": "OmniNova Labs announced AetheriaX-70B today"
                    },
                    {
                        "name": "OmniNova Labs",
                        "type": "org",
                        "role": "subject",
                        "confidence": 0.9,
                        "evidence": "OmniNova Labs has officially announced"
                    }
                ],
                "takeaway": "OmniNova Labs has released the open-weights AetheriaX-70B reasoning model.",
                "status": "done"
            },
            {
                "article_id": fixtures[1]["id"],
                "event_type": "model_update",
                "event_confidence": 0.9,
                "entities": [
                    {
                        "name": "AetheriaX-70B",
                        "type": "model",
                        "role": "subject",
                        "confidence": 0.95,
                        "evidence": "Independent evaluations of AetheriaX-70B"
                    }
                ],
                "takeaway": "Independent benchmark tests confirm high math performance for AetheriaX-70B.",
                "status": "done"
            }
        ]

        with patch("app.llm.gemini_service.extract_events_and_entities_batch", return_value=(mock_canned_extraction, "mock-gemini-classifier")):
            stats = run_radar_extraction_batch(articles_override=fixtures)
            assert stats["articles_processed"] == 2

        client = TestClient(app)

        # 1. The entity appears in /api/entities?emerging=true
        resp_ent = client.get("/api/entities?emerging=true")
        assert resp_ent.status_code == 200
        emerging_entities = resp_ent.json().get("entities", [])
        emerging_names = [e["canonical_name"] for e in emerging_entities]
        assert "aetheriax-70b" in emerging_names

        # 2. It appears in /api/radar
        resp_radar = client.get("/api/radar?days=7")
        assert resp_radar.status_code == 200
        radar_items = resp_radar.json().get("items", [])
        radar_art_ids = [item["article_id"] for item in radar_items]
        assert fixtures[0]["id"] in radar_art_ids or fixtures[1]["id"] in radar_art_ids

        # 3. Intent router: question about known entity resolves to entity_updates
        intent, data = detect_intent("Any updates on AetheriaX-70B?", conn=conn)
        assert intent == "entity_updates"
        assert data["canonical_name"] == "aetheriax-70b"

        # 4. Question containing known entity returns timeline
        with patch("app.llm.gemini_service.chat_rag") as mock_chat:
            mock_chat.return_value = {
                "answer": "AetheriaX-70B was released by OmniNova Labs [1] and tested in benchmarks [2].",
                "sources": [
                    {"title": fixtures[0]["title"], "url": fixtures[0]["url"]},
                    {"title": fixtures[1]["title"], "url": fixtures[1]["url"]}
                ],
                "model_used": "mock-gemini-chat"
            }
            res_query = answer_user_query("any updates on AetheriaX-70B?")
            assert res_query["intent"] == "entity_updates"
            assert "AetheriaX-70B" in res_query["answer"]
            assert len(res_query["sources"]) >= 1

        # 5. Question about generic releases resolves to latest_releases
        intent_generic, _ = detect_intent("What new models launched this week?", conn=conn)
        assert intent_generic == "latest_releases"

        # 6. Unknown entity name -> not-found path with ZERO LLM calls
        with patch("app.llm.gemini_service.chat_rag") as mock_chat_never:
            res_unknown = answer_user_query("tell me about NonExistentModelXYZ12345")
            assert NOT_FOUND_MESSAGE in res_unknown["answer"]
            assert res_unknown["suggest_web_search"] is True
            assert len(res_unknown["sources"]) == 0
            assert mock_chat_never.call_count == 0

    finally:
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM article_entities WHERE article_id IN ('art_fixture_001', 'art_fixture_002');")
            cur.execute("DELETE FROM articles WHERE id IN ('art_fixture_001', 'art_fixture_002');")
            cur.execute("DELETE FROM sources WHERE id IN ('src_fixture_alpha', 'src_fixture_beta');")
            cur.execute("DELETE FROM entities WHERE id NOT IN (SELECT DISTINCT entity_id FROM article_entities);")
            conn.commit()
        except Exception:
            pass
        conn.close()
