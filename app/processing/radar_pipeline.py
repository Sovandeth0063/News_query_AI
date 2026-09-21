import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from app.config import settings
from app.storage.database import get_db_connection
from app.processing.prefilter import should_extract
from app.processing.entity_registry import (
    find_or_create_entity,
    link_article_entity,
    recompute_emerging_entities
)
from app.llm import gemini_service

logger = logging.getLogger(__name__)

def is_within_baseline(conn) -> bool:
    """Check if current time is within radar cold-start baseline."""
    cur = conn.cursor()
    cur.execute("SELECT value FROM app_meta WHERE key = 'radar_baseline_until_utc';")
    row = cur.fetchone()
    if not row or not row["value"]:
        return False
    try:
        val = str(row["value"]).replace("Z", "+00:00")
        baseline_until = datetime.fromisoformat(val)
        if baseline_until.tzinfo is None:
            baseline_until = baseline_until.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) <= baseline_until
    except Exception:
        return False

def run_radar_extraction_batch(
    max_calls: Optional[int] = None,
    articles_override: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Executes event and entity extraction on pending articles newest-first.
    Respects EXTRACTION_MAX_CALLS_PER_RUN and EXTRACTION_BATCH_SIZE.
    Applies Section 5.2 prefilter first.
    Applies Section 5.4 validation & Section 6 entity registry updates.
    """
    max_calls_allowed = max_calls if max_calls is not None else settings.EXTRACTION_MAX_CALLS_PER_RUN
    batch_size = settings.EXTRACTION_BATCH_SIZE

    conn = get_db_connection()
    stats = {
        "prefiltered_skipped": 0,
        "articles_processed": 0,
        "entities_linked": 0,
        "llm_calls": 0,
        "model_used": "none"
    }

    try:
        baseline_active = 1 if is_within_baseline(conn) else 0

        # 1. Fetch pending articles
        if articles_override is not None:
            pending_articles = articles_override
        else:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, title, summary, body, category, published_at_utc, source_id
                FROM articles
                WHERE llm_extraction_status = 'pending'
                ORDER BY published_at_utc DESC
                LIMIT ?;
            """, (max_calls_allowed * batch_size * 2,))
            pending_articles = [dict(r) for r in cur.fetchall()]

        if not pending_articles:
            return stats

        # 2. Prefilter articles (Section 5.2)
        articles_to_extract = []
        skipped_ids = []

        for a in pending_articles:
            if should_extract(a):
                articles_to_extract.append(a)
            else:
                skipped_ids.append(a["id"])

        if skipped_ids:
            cur = conn.cursor()
            cur.executemany(
                "UPDATE articles SET llm_extraction_status = 'skipped' WHERE id = ?;",
                [(sid,) for sid in skipped_ids]
            )
            conn.commit()
            stats["prefiltered_skipped"] = len(skipped_ids)

        if not articles_to_extract:
            return stats

        # 3. Batched LLM processing
        calls_made = 0
        for i in range(0, len(articles_to_extract), batch_size):
            if calls_made >= max_calls_allowed:
                logger.info(f"Reached max extraction calls per run ({max_calls_allowed}). Stopping extraction.")
                break

            batch = articles_to_extract[i:i + batch_size]
            results, model_used = gemini_service.extract_events_and_entities_batch(batch)
            calls_made += 1
            stats["llm_calls"] = calls_made
            if model_used != "none":
                stats["model_used"] = model_used

            if not results:
                # LLM service unavailable or failed completely: leave remaining pending
                logger.warning("LLM extraction returned no results. Leaving remaining articles as pending.")
                break

            # 4. Persist extraction results & update entity registry
            art_meta_map = {a["id"]: a for a in batch}
            cur = conn.cursor()

            for res in results:
                art_id = res["article_id"]
                art_item = art_meta_map.get(art_id, {})
                pub_utc = art_item.get("published_at_utc") or datetime.now(timezone.utc).isoformat()
                status = res.get("status", "done")

                # Update article event & extraction fields
                cur.execute("""
                    UPDATE articles
                    SET event_type = ?,
                        event_confidence = ?,
                        takeaway = COALESCE(?, takeaway),
                        llm_extraction_status = ?,
                        extraction_model = ?
                    WHERE id = ?;
                """, (
                    res.get("event_type", "other"),
                    res.get("event_confidence", 0.0),
                    res.get("takeaway"),
                    status,
                    model_used,
                    art_id
                ))
                stats["articles_processed"] += 1

                # Link validated entities
                for ent in res.get("entities", []):
                    ent_id = find_or_create_entity(
                        conn,
                        display_name=ent["name"],
                        ent_type=ent["type"],
                        pub_utc=pub_utc,
                        is_baseline_default=baseline_active
                    )
                    if ent_id:
                        link_article_entity(
                            conn,
                            article_id=art_id,
                            entity_id=ent_id,
                            role=ent.get("role", "mentioned"),
                            confidence=ent.get("confidence", 0.8),
                            evidence=ent.get("evidence", "")
                        )
                        stats["entities_linked"] += 1

            conn.commit()

        # 5. Recompute emerging entities after batch extraction run (Section 6.3)
        recompute_emerging_entities(conn)

    except Exception as e:
        logger.exception(f"Error in radar extraction pipeline: {e}")
    finally:
        conn.close()

    return stats
