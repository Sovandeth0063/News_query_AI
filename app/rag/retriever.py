import re
import math
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from collections import defaultdict

from app.storage.vector_store import vector_store
from app.storage.database import get_db_connection
from app.embeddings import embedding_service
from app.rag.query_parser import parse_query_filters

STOP_WORDS = {
    "in", "on", "to", "is", "by", "at", "an", "as", "it", "or", "if", 
    "be", "do", "no", "so", "up", "my", "we", "he", "me", "of", "the", 
    "and", "for", "with", "from", "that", "this", "are", "was", "were",
    "tell", "about", "can", "you", "give", "show", "what", "which", "who",
    "when", "where", "why", "how", "has", "have", "had", "been", "will",
    "would", "could", "should", "does", "did", "their", "there", "they",
    "them", "then", "than", "more", "most", "some", "any", "other", "into",
    "over", "after", "also", "just", "like", "such"
}
DOMAIN_ACRONYMS = {"ai", "ml", "dl", "cv", "rl", "llm", "nlp", "rag"}

def sanitize_search_tokens(query: str) -> List[str]:
    """Extract and validate search tokens, keeping domain acronyms and filtering stop words."""
    raw_tokens = re.findall(r'[a-zA-Z0-9]+(?:[-_][a-zA-Z0-9]+)*', query.strip())
    valid_tokens = []
    for t in raw_tokens:
        t_lower = t.lower()
        if len(t) > 2:
            if t_lower not in STOP_WORDS:
                valid_tokens.append(t)
        elif len(t) == 2:
            if t_lower in DOMAIN_ACRONYMS or t_lower not in STOP_WORDS:
                valid_tokens.append(t)
    return valid_tokens

def search_fts(query: str, limit: int = 20, date_from_iso: Optional[str] = None) -> List[Dict[str, Any]]:
    """Keyword search in SQLite FTS5 index."""
    tokens = sanitize_search_tokens(query)
    if not tokens:
        return []

    # Double quote each token to avoid syntax errors with hyphens or operators in FTS5
    fts_query = " OR ".join(f'"{t}"' for t in tokens[:8])
    conn = get_db_connection()
    try:
        sql = """
        SELECT a.id as article_id, a.title, a.summary, a.body, a.category,
               a.published_at_utc, a.url, s.name as source_name,
               bm25(articles_fts) as rank_score
        FROM articles_fts f
        JOIN articles a ON f.rowid = a.rowid
        LEFT JOIN sources s ON a.source_id = s.id
        WHERE articles_fts MATCH ?
        """
        params = [fts_query]
        if date_from_iso:
            sql += " AND a.published_at_utc >= ?"
            params.append(date_from_iso)

        sql += " ORDER BY rank_score LIMIT ?;"
        params.append(limit)

        cursor = conn.execute(sql, params)
        rows = [dict(r) for r in cursor.fetchall()]
        return rows
    except Exception:
        return []
    finally:
        conn.close()

def hybrid_retrieve(query: str, top_k: int = 8) -> List[Dict[str, Any]]:
    """
    Perform Hybrid Retrieval:
    1. Parse natural language filters (date, category)
    2. Dense search in ChromaDB (top 20)
    3. Keyword search in SQLite FTS5 (top 20)
    4. Fuse ranks using Reciprocal Rank Fusion (RRF) at the article level with recency boost
    5. Enforce article diversity (max 2 chunks per article)
    """
    filters = parse_query_filters(query)
    cleaned_q = filters["query"]
    date_from = filters["date_from_iso"]
    cat_filter = filters["category_filter"]

    # 1. Dense search
    q_vec = embedding_service.encode([cleaned_q])[0]
    where_clause = {}
    if cat_filter:
        where_clause["category"] = cat_filter
    
    dense_results = vector_store.search(
        query_embedding=q_vec,
        top_k=20,
        where=where_clause if where_clause else None
    )

    # 2. Keyword search
    fts_results = search_fts(cleaned_q, limit=20, date_from_iso=date_from)

    # 3. Reciprocal Rank Fusion at the article level
    article_rrf = defaultdict(float)
    article_chunks = defaultdict(list)
    article_metadata = {}

    for rank, hit in enumerate(dense_results):
        meta = hit.get("metadata", {})
        art_id = meta.get("article_id")
        if not art_id:
            continue
        article_rrf[art_id] += 1.0 / (60.0 + rank + 1)
        article_chunks[art_id].append(hit)
        if art_id not in article_metadata:
            article_metadata[art_id] = meta

    for rank, hit in enumerate(fts_results):
        art_id = hit["article_id"]
        article_rrf[art_id] += 1.0 / (60.0 + rank + 1)
        fts_chunk = {
            "id": f"{art_id}_fts",
            "text": (hit.get("summary") or hit.get("body") or "")[:800],
            "metadata": {
                "article_id": art_id,
                "title": hit.get("title", ""),
                "source_name": hit.get("source_name", ""),
                "published_at_utc": hit.get("published_at_utc", ""),
                "category": hit.get("category", "TECH_GENERAL"),
                "url": hit.get("url", "")
            }
        }
        if art_id not in article_metadata:
            article_metadata[art_id] = fts_chunk["metadata"]
        if not article_chunks[art_id]:
            article_chunks[art_id].append(fts_chunk)

    # 4. Apply recency weighting to article RRF scores
    now_utc = datetime.now(timezone.utc)
    ranked_articles = []
    for art_id, score in article_rrf.items():
        meta = article_metadata.get(art_id, {})
        pub_iso = meta.get("published_at_utc")
        recency_multiplier = 1.0
        if pub_iso:
            try:
                dt = datetime.fromisoformat(pub_iso)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                age_hours = max(0.0, (now_utc - dt).total_seconds() / 3600.0)
                recency_multiplier = 1.0 + 0.25 * math.exp(-age_hours / 72.0)
            except Exception:
                pass

        final_score = score * recency_multiplier
        ranked_articles.append((final_score, art_id))

    # Sort descending by final fused score
    ranked_articles.sort(key=lambda x: x[0], reverse=True)

    # 5. Deduplicate and diversify (up to 2 chunks per article)
    selected_chunks = []
    for _, art_id in ranked_articles:
        chunks = article_chunks.get(art_id, [])
        for chunk in chunks[:2]:
            selected_chunks.append(chunk)
            if len(selected_chunks) >= top_k:
                break
        if len(selected_chunks) >= top_k:
            break

    return selected_chunks
