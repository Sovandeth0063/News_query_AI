from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
import json

from app.storage.database import (
    get_articles_for_feed, get_papers, set_read_state, get_db_connection, get_sidebar_data
)
from app.rag.generator import answer_user_query
from app.rag.digest import get_or_generate_digest
from app.sync_manager import sync_manager
from app.processing.entity_registry import get_entity_timeline
from app.processing.radar_pipeline import run_radar_extraction_batch

router = APIRouter(prefix="/api")

class ChatRequest(BaseModel):
    question: str
    history: Optional[List[Dict[str, str]]] = []

class ReadStateRequest(BaseModel):
    is_read: Optional[bool] = None
    is_bookmarked: Optional[bool] = None

@router.get("/feed")
def get_feed(
    category: Optional[str] = Query(None, description="Category filter e.g. AI_LLM, DATA_SCIENCE_ML, DATA_ENG_CLOUD"),
    search: Optional[str] = Query(None, description="Keyword search query"),
    sort: str = Query("score", description="Sort order: score or date"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """Retrieve ranked news feed sorted by dynamic score or date."""
    articles = get_articles_for_feed(category=category, search=search, sort=sort, limit=limit, offset=offset)
    return {"articles": articles, "count": len(articles)}

@router.get("/papers")
def get_research_papers(
    search: Optional[str] = Query(None, description="Keyword search in papers"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """Retrieve academic arXiv research papers."""
    papers = get_papers(search=search, limit=limit, offset=offset)
    return {"papers": papers, "count": len(papers)}

@router.get("/articles/{article_id}")
def get_article_detail(article_id: str):
    """Retrieve full article text and cluster siblings (coverage by other sources)."""
    conn = get_db_connection()
    cursor = conn.execute("""
        SELECT a.*, s.name as source_name, s.authority as source_authority
        FROM articles a
        LEFT JOIN sources s ON a.source_id = s.id
        WHERE a.id = ?;
    """, (article_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Article not found")

    article = dict(row)
    article["tags"] = json.loads(article.get("tags_json") or "[]")

    # Fetch siblings in same cluster
    siblings = []
    if article.get("cluster_id"):
        cursor = conn.execute("""
            SELECT a.id, a.title, a.url, a.published_at_utc, s.name as source_name
            FROM articles a
            LEFT JOIN sources s ON a.source_id = s.id
            WHERE a.cluster_id = ? AND a.id != ?;
        """, (article["cluster_id"], article_id))
        siblings = [dict(r) for r in cursor.fetchall()]

    conn.close()
    return {"article": article, "siblings": siblings}

@router.post("/articles/{article_id}/read")
def toggle_read(article_id: str, req: ReadStateRequest):
    set_read_state(article_id, is_read=req.is_read)
    return {"status": "ok", "article_id": article_id, "is_read": req.is_read}

@router.post("/articles/{article_id}/bookmark")
def toggle_bookmark(article_id: str, req: ReadStateRequest):
    set_read_state(article_id, is_bookmarked=req.is_bookmarked)
    return {"status": "ok", "article_id": article_id, "is_bookmarked": req.is_bookmarked}

@router.get("/digest")
def get_daily_digest(date: Optional[str] = None):
    """Fetch daily executive AI briefing."""
    digest = get_or_generate_digest(target_date=date, force_regenerate=False)
    return digest

@router.post("/digest/generate")
def force_regenerate_digest(date: Optional[str] = None):
    """Force synthesize/regenerate executive briefing using gemini-3.5-flash."""
    digest = get_or_generate_digest(target_date=date, force_regenerate=True)
    return digest

@router.post("/chat")
def chat_with_ai(req: ChatRequest):
    """Ask AI questions grounded in ingested tech & AI news."""
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    result = answer_user_query(req.question, history=req.history)
    return result

@router.post("/sync")
def trigger_sync():
    """Trigger background sync with global lock."""
    run_id = sync_manager.run_sync_background(trigger="manual")
    return {"status": "started", "run_id": run_id}

@router.get("/sync/{run_id}")
def get_sync_status(run_id: str):
    """Check sync progress."""
    return sync_manager.get_status()

@router.get("/sources")
def get_sources():
    """List all configured news feeds, category hints, and health."""
    conn = get_db_connection()
    cursor = conn.execute("SELECT * FROM sources ORDER BY authority DESC, name ASC;")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"sources": rows}

@router.get("/sidebar")
def get_sidebar():
    """Retrieve dynamic sidebar intelligence widgets (Top 3 today, topic counts, digest preview)."""
    return get_sidebar_data()

# -------------------------------------------------------------
# Model Radar & Entity Intelligence Endpoints (Section 8.1)
# -------------------------------------------------------------

@router.get("/radar")
def get_radar_feed(
    days: int = Query(7, ge=1, le=90, description="Time window in days"),
    event_type: Optional[str] = Query(None, description="Event type filter (e.g. model_release, model_update)"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    GET /api/radar: Recent model_release/model_update items, clustered, with entities and coverage count.
    """
    cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conn = get_db_connection()
    cur = conn.cursor()

    sql = """
        SELECT a.id, a.title, a.url, a.published_at_utc, a.source_id,
               s.name as source_name, a.source_type, a.event_type, a.event_confidence,
               a.takeaway, a.summary, a.cluster_id, a.score_cached
        FROM articles a
        LEFT JOIN sources s ON a.source_id = s.id
        WHERE a.published_at_utc >= ?
    """
    params = [cutoff_iso]

    if event_type:
        sql += " AND a.event_type = ?"
        params.append(event_type)
    else:
        sql += " AND a.event_type IN ('model_release', 'model_update')"

    sql += " ORDER BY a.published_at_utc DESC, a.score_cached DESC LIMIT ? OFFSET ?;"
    params.extend([limit, offset])

    cur.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]

    # Attach linked entities and coverage count for each article
    items = []
    for r in rows:
        art_id = r["id"]
        cid = r.get("cluster_id")
        coverage_count = 1
        if cid:
            cur.execute("SELECT COUNT(DISTINCT source_id) as cnt FROM articles WHERE cluster_id = ?;", (cid,))
            c_row = cur.fetchone()
            if c_row:
                coverage_count = c_row["cnt"]

        # Fetch entities linked to this article
        cur.execute("""
            SELECT e.id, e.display_name as name, e.type, e.is_emerging, ae.role, ae.confidence
            FROM article_entities ae
            JOIN entities e ON ae.entity_id = e.id
            WHERE ae.article_id = ?;
        """, (art_id,))
        ent_rows = [dict(e) for e in cur.fetchall()]

        items.append({
            "article_id": art_id,
            "title": r["title"],
            "url": r["url"],
            "published_at_utc": r["published_at_utc"],
            "source_id": r["source_id"],
            "source_name": r.get("source_name") or "Unknown",
            "source_type": r.get("source_type") or "press",
            "event_type": r["event_type"],
            "event_confidence": r.get("event_confidence") or 0.0,
            "takeaway": r.get("takeaway") or r.get("summary"),
            "cluster_id": cid,
            "coverage_count": coverage_count,
            "entities": ent_rows
        })

    conn.close()
    return {"items": items, "count": len(items)}

@router.get("/entities")
def get_entities(
    emerging: Optional[bool] = Query(None, description="Filter only emerging entities"),
    type: Optional[str] = Query(None, description="Entity type: model, org, person, benchmark, product"),
    q: Optional[str] = Query(None, description="Search prefix or name"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    GET /api/entities: Entity list with optional emerging, type, and prefix/alias search.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    sql = """
        SELECT e.id, e.canonical_name, e.display_name, e.type, e.first_seen_utc,
               e.last_seen_utc, e.mention_count, e.is_baseline, e.is_emerging, e.emerging_since_utc
        FROM entities e
        WHERE 1=1
    """
    params = []

    if emerging is not None:
        sql += " AND e.is_emerging = ?"
        params.append(1 if emerging else 0)

    if type:
        sql += " AND e.type = ?"
        params.append(type)

    if q:
        norm_q = q.strip().lower()
        sql += """ AND (
            e.canonical_name LIKE ? OR e.display_name LIKE ?
            OR e.id IN (SELECT entity_id FROM entity_aliases WHERE alias LIKE ?)
        )"""
        like_term = f"%{norm_q}%"
        params.extend([like_term, like_term, like_term])

    sql += " ORDER BY e.is_emerging DESC, e.mention_count DESC, e.last_seen_utc DESC LIMIT ? OFFSET ?;"
    params.extend([limit, offset])

    cur.execute(sql, params)
    entities = [dict(r) for r in cur.fetchall()]
    conn.close()

    return {"entities": entities, "count": len(entities)}

@router.get("/entities/{entity_id}")
def get_entity_detail(entity_id: int):
    """
    GET /api/entities/{id}: Entity detail + aliases.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM entities WHERE id = ?;", (entity_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Entity not found")

    ent = dict(row)

    cur.execute("SELECT alias FROM entity_aliases WHERE entity_id = ?;", (entity_id,))
    aliases = [r["alias"] for r in cur.fetchall()]
    conn.close()

    return {"entity": ent, "aliases": aliases}

@router.get("/entities/{entity_id}/timeline")
def get_entity_timeline_endpoint(entity_id: int):
    """
    GET /api/entities/{id}/timeline: Chronological timeline for an entity.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM entities WHERE id = ?;", (entity_id,))
    ent_row = cur.fetchone()
    if not ent_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Entity not found")

    ent = dict(ent_row)
    timeline = get_entity_timeline(conn, entity_id)
    conn.close()

    return {"entity": ent, "timeline": timeline, "count": len(timeline)}

@router.post("/radar/reprocess")
def reprocess_radar(days: int = Query(7, ge=1, le=90)):
    """
    POST /api/radar/reprocess: Re-run extraction for articles in window.
    """
    cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conn = get_db_connection()
    with conn:
        conn.execute("""
            UPDATE articles
            SET llm_extraction_status = 'pending'
            WHERE published_at_utc >= ?;
        """, (cutoff_iso,))
    conn.close()

    stats = run_radar_extraction_batch()
    return {"status": "completed", "window_days": days, "stats": stats}

