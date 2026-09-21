import uuid
import yaml
import asyncio
import logging
import threading
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from app.config import settings
from app.storage.database import (
    get_db_connection, sync_sources_from_yaml, upsert_article, init_db, purge_expired_articles
)
from app.storage.vector_store import vector_store
from app.ingestion.rss_fetcher import fetch_rss_feed
from app.ingestion.arxiv_fetcher import fetch_arxiv_papers
from app.ingestion.hn_fetcher import fetch_hn_algolia
from app.ingestion.reddit_fetcher import fetch_reddit_rss
from app.ingestion.google_news_fetcher import fetch_google_news_rss
from app.ingestion.extractor import extract_article_content
from app.ingestion.normalizer import compute_content_hash
from app.processing.dedup import is_duplicate_exact
from app.processing.classifier import classify_articles
from app.processing.clustering import assign_story_clusters
from app.processing.scoring import calculate_article_score, refresh_cached_scores
from app.embeddings import embedding_service
from app.llm import gemini_service
from app.processing.radar_pipeline import run_radar_extraction_batch

logger = logging.getLogger(__name__)

class SyncManager:
    def __init__(self):
        self._lock = threading.Lock()
        self.current_run_id: Optional[str] = None
        self.progress: Dict[str, Any] = {
            "status": "idle",
            "percent": 0,
            "message": "Ready",
            "stats": {"fetched": 0, "new": 0, "dupes": 0, "failed": 0}
        }

    def get_status(self) -> Dict[str, Any]:
        return {
            "run_id": self.current_run_id,
            **self.progress
        }

    def run_sync_background(self, trigger: str = "manual") -> str:
        """Launch sync in a background daemon thread if not already running."""
        with self._lock:
            if self.progress["status"] == "running":
                return self.current_run_id or "running"

            run_id = f"run_{uuid.uuid4().hex[:12]}"
            self.current_run_id = run_id
            self.progress = {
                "status": "running",
                "percent": 5,
                "message": "Initializing ingestion...",
                "stats": {"fetched": 0, "new": 0, "dupes": 0, "failed": 0}
            }

            thread = threading.Thread(target=self._execute_sync, args=(run_id, trigger), daemon=True)
            thread.start()
            return run_id

    def _execute_sync(self, run_id: str, trigger: str):
        init_db()
        now_iso = datetime.now(timezone.utc).isoformat()
        conn = get_db_connection()
        with conn:
            conn.execute("""
            INSERT INTO ingestion_runs (id, started_at, trigger, status)
            VALUES (?, ?, ?, 'running');
            """, (run_id, now_iso, trigger))
        conn.close()

        stats = {"fetched": 0, "new": 0, "dupes": 0, "failed": 0}
        error_log = []

        try:
            # 1. Load sources.yaml
            self.progress.update({"percent": 10, "message": "Loading configured sources..."})
            with open(settings.SOURCES_FILE, "r", encoding="utf-8") as f:
                sources_config = yaml.safe_load(f).get("sources", [])
            
            sync_sources_from_yaml(sources_config)
            enabled_sources = [s for s in sources_config if s.get("enabled", True)]

            # 2. Fetch raw items
            self.progress.update({"percent": 25, "message": "Fetching RSS feeds and arXiv preprints..."})
            raw_items = []

            async def _gather_all():
                tasks = []
                for s in enabled_sources:
                    max_items = s.get("max_items_per_run", 15)
                    kind = s.get("kind", "rss")
                    if kind == "rss":
                        tasks.append(fetch_rss_feed(s, max_items=max_items))
                    elif kind == "hn_algolia":
                        tasks.append(fetch_hn_algolia(s, max_items=max_items))
                    elif kind == "reddit_rss":
                        tasks.append(fetch_reddit_rss(s, max_items=max_items))
                    elif kind == "google_news_rss":
                        tasks.append(fetch_google_news_rss(s, max_items=max_items))
                return await asyncio.gather(*tasks, return_exceptions=True)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            rss_results = loop.run_until_complete(_gather_all())
            loop.close()

            for res in rss_results:
                if isinstance(res, list):
                    raw_items.extend(res)

            # Fetch arXiv papers
            for s in enabled_sources:
                if s["kind"] == "arxiv":
                    papers = fetch_arxiv_papers(s.get("feed_url", "cs.AI"), max_results=10)
                    raw_items.extend(papers)

            stats["fetched"] = len(raw_items)
            self.progress.update({"percent": 45, "message": f"Fetched {len(raw_items)} items. Deduplicating..."})

            # 3. Exact Deduplication (In-batch + Database)
            seen_urls = set()
            seen_hashes = set()
            unseen_items = []
            for item in raw_items:
                url = item.get("url", "").strip()
                chash = compute_content_hash(item.get("title", ""), item.get("summary", ""))
                item["content_hash"] = chash
                if not url or url in seen_urls or chash in seen_hashes or is_duplicate_exact(url, chash):
                    stats["dupes"] += 1
                else:
                    seen_urls.add(url)
                    seen_hashes.add(chash)
                    unseen_items.append(item)

            self.progress.update({"percent": 60, "message": f"Extracting full text for {len(unseen_items)} new articles..."})

            # 4. Extract full text in parallel
            from concurrent.futures import ThreadPoolExecutor, as_completed

            def _extract_worker(item):
                try:
                    if item.get("category_hint") == "AI_RESEARCH" and item.get("body"):
                        return item, None
                    body, status = extract_article_content(item["url"], fallback_summary=item.get("summary", ""))
                    item["body"] = body
                    item["extraction_status"] = status
                    return item, None
                except Exception as ex:
                    return item, str(ex)

            processed_items = []
            with ThreadPoolExecutor(max_workers=12) as executor:
                future_to_item = {executor.submit(_extract_worker, item): item for item in unseen_items}
                for future in as_completed(future_to_item):
                    item, err = future.result()
                    if err:
                        stats["failed"] += 1
                        error_log.append(f"Extraction error ({item.get('url')}): {err}")
                    else:
                        processed_items.append(item)


            # 5. Hybrid Classification (Rules + Gemini 3.5-flash-lite)
            self.progress.update({"percent": 75, "message": "Classifying news items into AI & Tech topics..."})
            classifications = classify_articles(processed_items)
            for item, cls in zip(processed_items, classifications):
                item["category"] = cls["category"]
                item["tags"] = cls.get("tags", [])
                item["id"] = f"art_{uuid.uuid4().hex[:12]}"

            # 6. Embedding & Near-duplicate Story Clustering
            self.progress.update({"percent": 85, "message": "Computing vector embeddings and clustering stories..."})
            if processed_items:
                texts_to_embed = [f"{a.get('title')}\n{a.get('summary', '')[:400]}" for a in processed_items]
                article_embeddings = embedding_service.encode(texts_to_embed)
                clustered_items = assign_story_clusters(processed_items, article_embeddings)

                # 7. Generate Takeaways & Upsert to DB
                self.progress.update({"percent": 86, "message": "Scoring and generating intelligence takeaways..."})
                for item in clustered_items:
                    score = calculate_article_score(
                        category=item["category"],
                        published_at_utc=item["published_at_utc"],
                        source_authority=item.get("authority", 1.0),
                        cluster_size=item.get("cluster_size", 1)
                    )
                    item["score_cached"] = score
                    item["fetched_at_utc"] = datetime.now(timezone.utc).isoformat()

                # Sort by score descending to prioritize top 30 for LLM takeaways
                clustered_items.sort(key=lambda x: x.get("score_cached", 0.0), reverse=True)
                top_slice = clustered_items[:30]
                rest_slice = clustered_items[30:]

                # Generate batch takeaways for top articles (LLM quota protection)
                top_takeaways = gemini_service.generate_takeaways_batch(top_slice)
                for item, takeaway in zip(top_slice, top_takeaways):
                    item["takeaway"] = takeaway

                for item in rest_slice:
                    summary_text = (item.get("summary") or item.get("body") or "").strip()
                    first_sent = summary_text.split(". ")[0].strip()
                    item["takeaway"] = (first_sent[:180] + ".") if first_sent and not first_sent.endswith((".", "!", "?", "…")) else summary_text[:180]

                all_chunks = []
                new_art_ids = []
                for item in clustered_items:
                    is_new, art_id = upsert_article(item)
                    if is_new:
                        stats["new"] += 1
                        new_art_ids.append(art_id)
                        chunks = embedding_service.chunk_article(item)
                        all_chunks.extend(chunks)

                # Stream newly chunked articles to ChromaDB
                if all_chunks:
                    self.progress.update({"percent": 88, "message": f"Embedding {len(all_chunks)} new chunks for vector search..."})
                    batch_size = 64
                    for i in range(0, len(all_chunks), batch_size):
                        batch = all_chunks[i:i + batch_size]
                        chunk_texts = [c["text"] for c in batch]
                        chunk_embeddings = embedding_service.encode(chunk_texts)
                        vector_store.add_chunks(batch, chunk_embeddings)

                    conn = get_db_connection()
                    with conn:
                        for art_id in new_art_ids:
                            conn.execute("UPDATE articles SET embedded = 1 WHERE id = ?;", (art_id,))
                    conn.close()

            # Process any leftover unembedded articles (without arbitrary LIMIT)
            while True:
                conn = get_db_connection()
                cursor = conn.execute("SELECT id, title, summary, body, category, published_at_utc, url FROM articles WHERE embedded = 0 LIMIT 100;")
                unembedded_rows = [dict(r) for r in cursor.fetchall()]
                conn.close()
                if not unembedded_rows:
                    break

                self.progress.update({"percent": 90, "message": f"Embedding {len(unembedded_rows)} leftover unembedded articles..."})
                unembedded_chunks = []
                embedded_ids = []
                for row in unembedded_rows:
                    chunks = embedding_service.chunk_article(row)
                    unembedded_chunks.extend(chunks)
                    embedded_ids.append(row["id"])

                if unembedded_chunks:
                    batch_size = 64
                    for i in range(0, len(unembedded_chunks), batch_size):
                        batch = unembedded_chunks[i:i + batch_size]
                        chunk_texts = [c["text"] for c in batch]
                        chunk_embeddings = embedding_service.encode(chunk_texts)
                        vector_store.add_chunks(batch, chunk_embeddings)

                conn = get_db_connection()
                with conn:
                    for art_id in embedded_ids:
                        conn.execute("UPDATE articles SET embedded = 1 WHERE id = ?;", (art_id,))
                conn.close()

            # 8. Refresh all scores
            self.progress.update({"percent": 93, "message": "Refreshing dynamic ranking scores..."})
            refresh_cached_scores()

            # 9. Model Radar: Event & Entity Extraction (Validated LLM with prefilter)
            self.progress.update({"percent": 96, "message": "Extracting events and entities for Model Radar..."})
            try:
                radar_stats = run_radar_extraction_batch()
                logger.info(f"Radar extraction completed: {radar_stats}")
            except Exception as rx:
                logger.error(f"Error during radar extraction step: {rx}")

            # 10. Retention policy purge
            purged = purge_expired_articles(settings.RETENTION_DAYS)
            if purged > 0:
                logger.info(f"Purged {purged} expired articles past retention window.")


            # Finish
            finished_iso = datetime.now(timezone.utc).isoformat()
            conn = get_db_connection()
            with conn:
                conn.execute("""
                UPDATE ingestion_runs SET
                    finished_at = ?, fetched = ?, new = ?, dupes = ?, failed = ?,
                    status = 'completed', error_log = ?
                WHERE id = ?;
                """, (finished_iso, stats["fetched"], stats["new"], stats["dupes"], stats["failed"], "\n".join(error_log), run_id))
            conn.close()

            self.progress = {
                "status": "completed",
                "percent": 100,
                "message": f"Sync completed! {stats['new']} new articles indexed, {stats['dupes']} duplicates skipped.",
                "stats": stats
            }

        except Exception as e:
            logger.exception("Error during sync run:")
            finished_iso = datetime.now(timezone.utc).isoformat()
            conn = get_db_connection()
            with conn:
                conn.execute("""
                UPDATE ingestion_runs SET
                    finished_at = ?, status = 'failed', error_log = ?
                WHERE id = ?;
                """, (finished_iso, str(e), run_id))
            conn.close()

            self.progress = {
                "status": "failed",
                "percent": 100,
                "message": f"Sync failed: {str(e)}",
                "stats": stats
            }

sync_manager = SyncManager()
