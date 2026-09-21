"""
Source Verification Script:
Fetches every configured or candidate source from sources.yaml.
Outputs a structured summary table of:
  id | kind | status | items_parsed | newest_date | empty_text_count
Exits with non-zero status code if any enabled source fails.
"""

import sys
import yaml
import asyncio
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.ingestion.rss_fetcher import fetch_rss_feed
from app.ingestion.arxiv_fetcher import fetch_arxiv_papers
from app.ingestion.hn_fetcher import fetch_hn_algolia
from app.ingestion.reddit_fetcher import fetch_reddit_rss
from app.ingestion.google_news_fetcher import fetch_google_news_rss

async def check_single_source(source: dict) -> dict:
    sid = source.get("id", "unknown")
    kind = source.get("kind", "rss")
    enabled = source.get("enabled", False)

    status_str = "OK"
    items = []
    error_msg = None

    try:
        if kind == "rss":
            items = await fetch_rss_feed(source, max_items=5)
        elif kind == "arxiv":
            items = fetch_arxiv_papers(source.get("feed_url", "cs.AI"), max_results=5)
        elif kind == "hn_algolia":
            items = await fetch_hn_algolia(source, max_items=5)
        elif kind == "reddit_rss":
            items = await fetch_reddit_rss(source, max_items=5)
        elif kind == "google_news_rss":
            items = await fetch_google_news_rss(source, max_items=5)
        else:
            status_str = f"UNKNOWN_KIND ({kind})"
    except Exception as e:
        status_str = f"ERROR ({type(e).__name__})"
        error_msg = str(e)

    parsed_count = len(items)
    if parsed_count == 0 and status_str == "OK":
        status_str = "EMPTY (0 items)"

    newest_date = "N/A"
    empty_text_count = 0
    if items:
        newest_date = items[0].get("published_at_utc", "N/A")[:10]
        empty_text_count = sum(1 for it in items if not it.get("title") and not it.get("summary"))

    return {
        "id": sid,
        "kind": kind,
        "enabled": enabled,
        "status": status_str,
        "items": parsed_count,
        "newest_date": newest_date,
        "empty_text": empty_text_count,
        "error": error_msg
    }

async def main():
    with open(settings.SOURCES_FILE, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    sources = config.get("sources", [])

    print(f"\nChecking {len(sources)} configured sources...\n")
    print(f"{'Source ID':<25} | {'Kind':<15} | {'Enabled':<8} | {'Status':<15} | {'Items':<6} | {'Newest Date':<12} | {'Empty'}")
    print("-" * 95)

    has_enabled_failure = False
    results = []

    for s in sources:
        res = await check_single_source(s)
        results.append(res)
        enabled_str = "YES" if res["enabled"] else "NO"
        print(f"{res['id']:<25} | {res['kind']:<15} | {enabled_str:<8} | {res['status']:<15} | {res['items']:<6} | {res['newest_date']:<12} | {res['empty_text']}")

        if res["enabled"] and ("ERROR" in res["status"] or res["items"] == 0):
            has_enabled_failure = True

    print("-" * 95)

    if has_enabled_failure:
        print("\n[FAIL] One or more enabled sources failed connectivity or returned 0 items.\n")
        sys.exit(1)
    else:
        print("\n[SUCCESS] All enabled sources verified healthy.\n")
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main())
