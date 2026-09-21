import math
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from app.config import settings
from app.storage.database import get_db_connection

CATEGORY_PRIORITY_WEIGHTS = {
    "AI_LLM": 1.0,
    "DATA_SCIENCE_ML": 1.0,
    "AI_RESEARCH": 0.8,
    "DATA_ENG_CLOUD": 0.6,
    "TECH_GENERAL": 0.4
}

def calculate_article_score(
    category: str,
    published_at_utc: str,
    source_authority: float = 1.0,
    cluster_size: int = 1,
    half_life_hours: Optional[float] = None
) -> float:
    """
    Compute dynamic ranking score:
    score = priority_weight * recency_decay(age_hours) * source_authority * (1 + 0.15 * ln(cluster_size))
    """
    if half_life_hours is None:
        half_life_hours = settings.RANK_HALF_LIFE_HOURS

    priority_weight = CATEGORY_PRIORITY_WEIGHTS.get(category, 0.5)

    # Calculate age in hours
    try:
        dt = datetime.fromisoformat(published_at_utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        age_seconds = max(0.0, (now - dt).total_seconds())
        age_hours = age_seconds / 3600.0
    except Exception:
        age_hours = 24.0

    # Exponential decay using exact half-life formula: at age_hours == half_life_hours, decay is 0.5
    recency_decay = math.exp(-math.log(2.0) * age_hours / max(1.0, half_life_hours))

    # Cluster boost (logarithmic)
    cluster_boost = 1.0 + 0.15 * math.log(max(1, cluster_size))

    score = priority_weight * recency_decay * max(0.5, source_authority) * cluster_boost
    return round(score, 5)

def refresh_cached_scores():
    """
    Batch recalculate and update score_cached for all articles in SQLite.
    Keeps feed ordering fresh over time.
    """
    conn = get_db_connection()
    with conn:
        cursor = conn.execute("""
            SELECT a.id, a.category, a.published_at_utc,
                   COALESCE(s.authority, 1.0) as authority,
                   COALESCE(c.size, 1) as cluster_size
            FROM articles a
            LEFT JOIN sources s ON a.source_id = s.id
            LEFT JOIN story_clusters c ON a.cluster_id = c.id;
        """)
        rows = cursor.fetchall()
        for row in rows:
            new_score = calculate_article_score(
                category=row["category"],
                published_at_utc=row["published_at_utc"],
                source_authority=row["authority"],
                cluster_size=row["cluster_size"]
            )
            conn.execute("UPDATE articles SET score_cached = ? WHERE id = ?;", (new_score, row["id"]))
    conn.close()
