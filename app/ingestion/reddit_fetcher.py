import logging
import httpx
import feedparser
from datetime import datetime, timezone
from typing import List, Dict, Any

from app.ingestion.normalizer import clean_text, canonicalize_url, parse_to_utc_iso

logger = logging.getLogger(__name__)

REDDIT_USER_AGENT = "NewsQuery/1.0 (news-intelligence-bot; +https://github.com/news-query/news-intelligence)"

async def fetch_reddit_rss(source_config: Dict[str, Any], max_items: int = 20) -> List[Dict[str, Any]]:
    """
    Fetch Reddit community discussions via subreddit RSS.
    Requires a descriptive User-Agent to avoid HTTP 429 rate limiting.
    """
    url = source_config.get("feed_url", "")
    if not url:
        return []

    items = []
    try:
        async with httpx.AsyncClient(headers={"User-Agent": REDDIT_USER_AGENT}, timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code == 429:
                logger.warning(f"Reddit rate limit (429) encountered for {url}. Skipping gracefully.")
                return []
            resp.raise_for_status()
            content = resp.text

        parsed = feedparser.parse(content)
        now_utc = datetime.now(timezone.utc)

        for entry in parsed.entries[:max_items]:
            raw_url = entry.get("link", "")
            if not raw_url:
                continue

            canon_url = canonicalize_url(raw_url)
            title = clean_text(entry.get("title", ""))
            if not title:
                continue

            summary = clean_text(entry.get("summary", entry.get("description", "")))
            # Strip Reddit boilerplate if any
            if "submitted by" in summary:
                summary = summary.split("submitted by")[0].strip()

            pub_date = entry.get("published", entry.get("updated", ""))
            published_utc = parse_to_utc_iso(pub_date, fallback_dt=now_utc)

            items.append({
                "source_id": source_config["id"],
                "source_name": source_config.get("name", "Reddit"),
                "url": canon_url,
                "title": title,
                "summary": summary,
                "published_at_utc": published_utc,
                "category_hint": source_config.get("category_hint", "TECH_GENERAL"),
                "authority": source_config.get("authority", 1.0),
                "source_type": source_config.get("source_type", "community")
            })

    except Exception as e:
        logger.error(f"Error fetching Reddit RSS {url}: {e}")

    return items
