"""
Clean existing article titles/summaries and backfill takeaways.
- Applies clean_text() to purge HTML entities, WordPress boilerplate, and unescaped entities.
- Generates batch LLM takeaways for the top 30 ranked articles via Gemini.
- Populates fallback takeaways for the remaining articles.
"""

import sys
import logging
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.storage.database import get_db_connection, init_db
from app.ingestion.normalizer import clean_text
from app.llm import gemini_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("clean_and_backfill")

def run_migration():
    init_db()
    conn = get_db_connection()
    cursor = conn.execute("""
        SELECT id, title, summary, score_cached, published_at_utc
        FROM articles
        ORDER BY score_cached DESC, published_at_utc DESC;
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    logger.info(f"Loaded {len(rows)} articles from SQLite.")

    if not rows:
        logger.info("No articles found to clean.")
        conn.close()
        return

    # 1. Clean title and summary for all rows
    cleaned_rows = []
    for r in rows:
        c_title = clean_text(r.get("title", ""))
        c_summary = clean_text(r.get("summary", ""))
        cleaned_rows.append({
            "id": r["id"],
            "title": c_title,
            "summary": c_summary,
            "score_cached": r.get("score_cached", 0.0)
        })

    # 2. Take top 30 articles for LLM takeaway generation
    top_30 = cleaned_rows[:30]
    rest = cleaned_rows[30:]

    logger.info(f"Generating LLM takeaways for top {len(top_30)} scored articles...")
    takeaways_top = gemini_service.generate_takeaways_batch(top_30)

    for item, takeaway in zip(top_30, takeaways_top):
        item["takeaway"] = takeaway

    # For remaining items, fallback to concise first sentence
    for item in rest:
        summary_text = item.get("summary", "").strip()
        first_sent = summary_text.split(". ")[0].strip()
        if first_sent and len(first_sent) > 10:
            item["takeaway"] = (first_sent[:180] + ".") if not first_sent.endswith((".", "!", "?", "…")) else first_sent[:180]
        else:
            item["takeaway"] = summary_text[:180]

    # 3. Batch update SQLite
    logger.info("Committing cleaned texts and takeaways to SQLite...")
    all_items = top_30 + rest
    with conn:
        for item in all_items:
            conn.execute("""
                UPDATE articles
                SET title = ?, summary = ?, takeaway = ?
                WHERE id = ?;
            """, (item["title"], item["summary"], item["takeaway"], item["id"]))

    conn.close()
    logger.info(f"Successfully cleaned and updated {len(all_items)} articles.")

if __name__ == "__main__":
    run_migration()
