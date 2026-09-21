import logging
import asyncio
import httpx
import feedparser
from urllib.parse import quote_plus
from datetime import datetime, timezone
from typing import List, Dict, Any

from app.ingestion.normalizer import clean_text, canonicalize_url, parse_to_utc_iso

logger = logging.getLogger(__name__)

GOOGLE_NEWS_SEARCH_BASE = "https://news.google.com/rss/search"

async def _resolve_redirect(client: httpx.AsyncClient, url: str) -> str:
    """Resolve Google News redirect URL with hard 4s timeout."""
    try:
        resp = await client.head(url, follow_redirects=True, timeout=4.0)
        final_url = str(resp.url)
        if "news.google.com" not in final_url:
            return final_url
    except Exception:
        pass
    return url

async def fetch_google_news_rss(source_config: Dict[str, Any], max_items: int = 20) -> List[Dict[str, Any]]:
    """
    Fetch news aggregator stories via Google News RSS search query.
    Config options:
      query: search keywords string
    """
    query = source_config.get("query", "AI model launch")
    encoded_query = quote_plus(query)
    feed_url = f"{GOOGLE_NEWS_SEARCH_BASE}?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"

    items = []
    try:
        async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, timeout=15.0) as client:
            resp = await client.get(feed_url)
            resp.raise_for_status()
            content = resp.text

            parsed = feedparser.parse(content)
            now_utc = datetime.now(timezone.utc)

            entries = parsed.entries[:max_items]

            # Concurrently resolve redirects with short timeout
            resolve_tasks = [_resolve_redirect(client, entry.get("link", "")) for entry in entries]
            resolved_urls = await asyncio.gather(*resolve_tasks, return_exceptions=True)

            for entry, resolved_res in zip(entries, resolved_urls):
                raw_url = resolved_res if isinstance(resolved_res, str) and resolved_res else entry.get("link", "")
                if not raw_url:
                    continue

                canon_url = canonicalize_url(raw_url)
                title = clean_text(entry.get("title", ""))
                if not title:
                    continue

                # Extract clean publisher name if title has ' - Publisher'
                source_name = source_config.get("name", "Google News")
                if " - " in title:
                    parts = title.rsplit(" - ", 1)
                    if len(parts[1]) < 40:
                        title = parts[0].strip()
                        source_name = parts[1].strip()

                summary = clean_text(entry.get("summary", entry.get("description", "")))
                pub_date = entry.get("published", entry.get("updated", ""))
                published_utc = parse_to_utc_iso(pub_date, fallback_dt=now_utc)

                items.append({
                    "source_id": source_config["id"],
                    "source_name": source_name,
                    "url": canon_url,
                    "title": title,
                    "summary": summary,
                    "published_at_utc": published_utc,
                    "category_hint": source_config.get("category_hint", "TECH_GENERAL"),
                    "authority": source_config.get("authority", 1.0),
                    "source_type": source_config.get("source_type", "aggregator")
                })

    except Exception as e:
        logger.error(f"Error fetching Google News RSS ({query}): {e}")

    return items
