import uuid
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from app.config import settings
from app.storage.database import get_db_connection
from app.embeddings import embedding_service

def compute_cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Compute cosine similarity between two normalized vectors."""
    a = np.array(vec1)
    b = np.array(vec2)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))

def assign_story_clusters(articles: List[Dict[str, Any]], embeddings: List[List[float]]) -> List[Dict[str, Any]]:
    """
    Cluster new articles with existing recent articles (within last 72 hours).
    Updates story_clusters table in SQLite.
    """
    if not articles or not embeddings:
        return articles

    conn = get_db_connection()
    now_utc = datetime.now(timezone.utc)
    threshold = settings.DEDUP_SIM_THRESHOLD
    cutoff_iso = (now_utc - timedelta(hours=72)).isoformat()

    # 1. Fetch active recent cluster representatives from DB
    with conn:
        cursor = conn.execute("""
            SELECT c.id as cluster_id, c.representative_article_id, c.size, c.first_seen_utc, c.last_seen_utc,
                   a.title as rep_title, a.summary as rep_summary
            FROM story_clusters c
            JOIN articles a ON c.representative_article_id = a.id
            WHERE c.last_seen_utc >= ?
            ORDER BY c.last_seen_utc DESC
            LIMIT 200;
        """, (cutoff_iso,))
        recent_clusters = [dict(r) for r in cursor.fetchall()]
    conn.close()

    # Encode recent cluster representatives if any exist
    cluster_pool = []
    if recent_clusters:
        rep_texts = [f"{r['rep_title']}\n{(r['rep_summary'] or '')[:400]}" for r in recent_clusters]
        rep_embeddings = embedding_service.encode(rep_texts)
        for r, emb in zip(recent_clusters, rep_embeddings):
            cluster_pool.append({
                "cluster_id": r["cluster_id"],
                "size": r["size"],
                "embedding": emb,
                "last_seen_utc": r["last_seen_utc"]
            })

    # 2. Match incoming articles against recent DB clusters or batch items
    conn = get_db_connection()
    with conn:
        for i, article in enumerate(articles):
            art_emb = embeddings[i]
            matched_cluster_entry = None
            best_sim = -1.0

            # First, check against active recent clusters from DB
            for c_entry in cluster_pool:
                sim = compute_cosine_similarity(art_emb, c_entry["embedding"])
                if sim >= threshold and sim > best_sim:
                    best_sim = sim
                    matched_cluster_entry = c_entry

            if matched_cluster_entry:
                # Attach to existing cluster
                matched_cluster_id = matched_cluster_entry["cluster_id"]
                matched_cluster_entry["size"] += 1
                matched_cluster_entry["last_seen_utc"] = article["published_at_utc"]
                article["cluster_id"] = matched_cluster_id
                article["cluster_size"] = matched_cluster_entry["size"]

                conn.execute("""
                UPDATE story_clusters 
                SET size = ?, last_seen_utc = ?
                WHERE id = ?;
                """, (matched_cluster_entry["size"], article["published_at_utc"], matched_cluster_id))

            else:
                # Check previous articles in this batch
                batch_matched_prev = None
                for j in range(i):
                    prev_article = articles[j]
                    prev_emb = embeddings[j]
                    sim = compute_cosine_similarity(art_emb, prev_emb)
                    if sim >= threshold and sim > best_sim:
                        best_sim = sim
                        batch_matched_prev = prev_article

                if batch_matched_prev:
                    matched_cluster_id = batch_matched_prev.get("cluster_id")
                    batch_matched_prev["cluster_size"] = batch_matched_prev.get("cluster_size", 1) + 1
                    article["cluster_id"] = matched_cluster_id
                    article["cluster_size"] = batch_matched_prev["cluster_size"]

                    conn.execute("""
                    UPDATE story_clusters 
                    SET size = size + 1, last_seen_utc = ?
                    WHERE id = ?;
                    """, (article["published_at_utc"], matched_cluster_id))
                else:
                    # Create brand new cluster
                    new_cluster_id = f"cluster_{uuid.uuid4().hex[:12]}"
                    article["cluster_id"] = new_cluster_id
                    article["cluster_size"] = 1

                    conn.execute("""
                    INSERT INTO story_clusters (id, representative_article_id, size, first_seen_utc, last_seen_utc)
                    VALUES (?, ?, 1, ?, ?);
                    """, (new_cluster_id, article["id"], article["published_at_utc"], article["published_at_utc"]))

                    # Add new cluster to cluster_pool so subsequent batch articles can link to it
                    cluster_pool.append({
                        "cluster_id": new_cluster_id,
                        "size": 1,
                        "embedding": art_emb,
                        "last_seen_utc": article["published_at_utc"]
                    })
    conn.close()

    return articles

