import logging
from typing import List, Dict, Any
from datetime import datetime, timezone
import feedparser
import httpx
from app.ingestion.normalizer import canonicalize_url, parse_to_utc_iso, clean_text

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

async def fetch_rss_feed(source: Dict[str, Any], max_items: int = 25) -> List[Dict[str, Any]]:
    """
    Fetch and parse an RSS feed.
    Returns list of raw item dicts.
    """
    url = source["feed_url"]
    items = []
    try:
        async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=15.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            content = response.text

        parsed = feedparser.parse(content)
        now_utc = datetime.now(timezone.utc)

        for entry in parsed.entries[:max_items]:
            raw_url = entry.get("link", "")
            if not raw_url:
                continue

            canon_url = canonicalize_url(raw_url)
            title = clean_text(entry.get("title", "Untitled"))
            summary = clean_text(entry.get("summary", entry.get("description", "")))

            # Date extraction
            pub_date = entry.get("published", entry.get("pubDate", entry.get("updated", "")))
            published_utc = parse_to_utc_iso(pub_date, fallback_dt=now_utc)

            items.append({
                "source_id": source["id"],
                "source_name": source["name"],
                "url": canon_url,
                "title": title,
                "summary": summary,
                "published_at_utc": published_utc,
                "category_hint": source.get("category_hint", "TECH_GENERAL"),
                "authority": source.get("authority", 1.0)
            })

    except Exception as e:
        logger.error(f"Error fetching RSS source {source.get('name', url)}: {e}")

    return items
