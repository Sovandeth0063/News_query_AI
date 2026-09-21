import time
import logging
import httpx
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from urllib.parse import quote_plus

from app.ingestion.normalizer import clean_text, canonicalize_url, parse_to_utc_iso

logger = logging.getLogger(__name__)

ALGOLIA_SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"

async def fetch_hn_algolia(source_config: Dict[str, Any], max_items: int = 25) -> List[Dict[str, Any]]:
    """
    Fetch articles from Hacker News Algolia search API.
    Config options:
      query: search keywords string
      min_points: minimum score threshold (default 20)
      lookback_hours: how far back to search (default 48)
    """
    query = source_config.get("query", "model")
    min_points = source_config.get("min_points", 20)
    lookback_hours = source_config.get("lookback_hours", 48)

    cutoff_ts = int(time.time() - (lookback_hours * 3600))
    numeric_filters = f"created_at_i>{cutoff_ts},points>={min_points}"

    params = {
        "query": query,
        "tags": "story",
        "numericFilters": numeric_filters,
        "hitsPerPage": min(max_items * 2, 100)
    }

    items = []
    try:
        async with httpx.AsyncClient(headers={"User-Agent": "NewsQuery/1.0"}, timeout=15.0) as client:
            resp = await client.get(ALGOLIA_SEARCH_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        hits = data.get("hits", [])
        now_utc = datetime.now(timezone.utc)

        for h in hits[:max_items]:
            title = clean_text(h.get("title", ""))
            if not title:
                continue

            raw_url = h.get("url")
            obj_id = h.get("objectID")
            if not raw_url:
                raw_url = f"https://news.ycombinator.com/item?id={obj_id}"

            canon_url = canonicalize_url(raw_url)
            created_at = h.get("created_at")
            pub_utc = parse_to_utc_iso(created_at, fallback_dt=now_utc)
            points = h.get("points", 0)
            num_comments = h.get("num_comments", 0)

            summary = f"Hacker News discussion ({points} points, {num_comments} comments) on '{title}'."

            items.append({
                "source_id": source_config["id"],
                "source_name": source_config.get("name", "Hacker News"),
                "url": canon_url,
                "title": title,
                "summary": summary,
                "published_at_utc": pub_utc,
                "category_hint": source_config.get("category_hint", "TECH_GENERAL"),
                "authority": source_config.get("authority", 1.1),
                "source_type": source_config.get("source_type", "community")
            })

    except Exception as e:
        logger.error(f"Error fetching HN Algolia source {source_config.get('id')}: {e}")

    return items
