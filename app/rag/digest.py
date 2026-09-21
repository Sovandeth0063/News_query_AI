import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from app.storage.database import get_db_connection
from app.llm import gemini_service
from app.config import settings

def get_or_generate_digest(target_date: Optional[str] = None, force_regenerate: bool = False) -> Dict[str, Any]:
    """
    Fetch cached daily digest or generate a new one using gemini-3.5-flash.
    Target date format: YYYY-MM-DD (defaults to today UTC).
    """
    now_utc = datetime.now(timezone.utc)
    date_str = target_date or now_utc.strftime("%Y-%m-%d")

    conn = get_db_connection()
    if not force_regenerate:
        cursor = conn.execute("SELECT id, digest_date, content_md, article_ids_json, model, created_at_utc FROM digests WHERE digest_date = ?", (date_str,))
        existing = cursor.fetchone()
        if existing:
            conn.close()
            return {
                "id": existing["id"],
                "digest_date": existing["digest_date"],
                "content_md": existing["content_md"],
                "article_ids": json.loads(existing["article_ids_json"]),
                "model": existing["model"],
                "created_at_utc": existing["created_at_utc"]
            }

    # Gather top scored articles from the last 24 hours
    since_iso = (now_utc - timedelta(hours=36)).isoformat()
    cursor = conn.execute("""
        SELECT a.id, a.title, a.summary, a.category, a.url, s.name as source_name, a.score_cached
        FROM articles a
        LEFT JOIN sources s ON a.source_id = s.id
        WHERE a.published_at_utc >= ?
        ORDER BY a.score_cached DESC
        LIMIT 25;
    """, (since_iso,))
    articles = [dict(r) for r in cursor.fetchall()]

    if not articles:
        # Fallback to recent articles if no articles in last 36h
        cursor = conn.execute("""
            SELECT a.id, a.title, a.summary, a.category, a.url, s.name as source_name, a.score_cached
            FROM articles a
            LEFT JOIN sources s ON a.source_id = s.id
            ORDER BY a.published_at_utc DESC
            LIMIT 20;
        """)
        articles = [dict(r) for r in cursor.fetchall()]

    content_md = gemini_service.generate_daily_digest(date_str, articles)
    digest_id = f"digest_{uuid.uuid4().hex[:12]}"
    article_ids = [a["id"] for a in articles]
    now_iso = now_utc.isoformat()

    with conn:
        conn.execute("""
        INSERT INTO digests (id, digest_date, content_md, article_ids_json, model, created_at_utc)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(digest_date) DO UPDATE SET
            content_md = excluded.content_md,
            article_ids_json = excluded.article_ids_json,
            model = excluded.model,
            created_at_utc = excluded.created_at_utc;
        """, (digest_id, date_str, content_md, json.dumps(article_ids), settings.MODEL_DIGEST, now_iso))
    conn.close()

    return {
        "id": digest_id,
        "digest_date": date_str,
        "content_md": content_md,
        "article_ids": article_ids,
        "model": settings.MODEL_DIGEST,
        "created_at_utc": now_iso
    }
