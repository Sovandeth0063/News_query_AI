import re
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from app.storage.database import get_db_connection
from app.rag.retriever import hybrid_retrieve, search_fts
from app.rag.intent_router import detect_intent
from app.processing.entity_registry import get_entity_timeline
from app.llm import gemini_service

NOT_FOUND_MESSAGE = "I couldn't find news about that in the sources I've ingested."

def validate_citations(answer: str, num_sources: int) -> str:
    """
    Backward-compatible citation validator for legacy callers/tests.
    """
    def replace_citation(match):
        idx = int(match.group(1))
        if 1 <= idx <= num_sources:
            return match.group(0)
        return ""
    return re.sub(r'\[(\d+)\]', replace_citation, answer)

def sanitize_and_deduplicate_citations(answer: str, sources: List[Dict[str, Any]]) -> tuple[str, List[Dict[str, Any]]]:
    """
    Section 7.3:
    Return only sources actually cited (strip uncited ones, dedupe by article/url),
    and remove any [n] that doesn't map to a provided source.
    """
    if not sources or not answer:
        # Strip any stray citations if sources is empty
        sanitized = re.sub(r'\[\d+\]', '', answer).strip()
        return sanitized, []

    # 1. Find all cited 1-based indices in answer
    cited_indices = set()
    for m in re.finditer(r'\[(\d+)\]', answer):
        idx = int(m.group(1))
        if 1 <= idx <= len(sources):
            cited_indices.add(idx)

    if not cited_indices:
        # If model didn't cite with [n] or cited invalid indices, strip and keep unique sources up to 5
        sanitized = re.sub(r'\[\d+\]', '', answer).strip()
        seen_urls = set()
        deduped = []
        for s in sources:
            u = s.get("url")
            if u and u not in seen_urls:
                seen_urls.add(u)
                deduped.append(s)
        return sanitized, deduped[:5]

    # 2. Build mapping from old index -> new 1-based index with URL deduplication
    old_to_new = {}
    new_sources = []
    seen_urls = set()

    for old_idx in sorted(cited_indices):
        src = sources[old_idx - 1]
        url = src.get("url", "")
        # Check if already added
        existing_new_idx = None
        for i, existing in enumerate(new_sources):
            if existing.get("url") == url or (existing.get("title") and existing.get("title") == src.get("title")):
                existing_new_idx = i + 1
                break

        if existing_new_idx is not None:
            old_to_new[old_idx] = existing_new_idx
        else:
            new_sources.append(src)
            old_to_new[old_idx] = len(new_sources)

    # 3. Replace citations in answer with renumbered indices or remove invalid ones
    def replace_citation(match):
        orig_idx = int(match.group(1))
        if orig_idx in old_to_new:
            return f"[{old_to_new[orig_idx]}]"
        return ""

    sanitized = re.sub(r'\[(\d+)\]', replace_citation, answer)
    # Clean up accidental double spaces from stripped citations
    sanitized = re.sub(r' +', ' ', sanitized).strip()

    # Re-index new_sources cleanly
    for i, s in enumerate(new_sources):
        s["index"] = i + 1

    return sanitized, new_sources

def answer_user_query(question: str, history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    """
    End-to-end RAG pipeline adhering to Section 7:
    1. Intent routing (latest_releases, entity_updates, general)
    2. Honest not-found behavior with 0 LLM calls when ungrounded
    3. LLM answer generation with Section 7.3 system rules
    4. Post-validation and citation cleanup
    """
    clean_q = question.strip()
    if not clean_q:
        return {
            "answer": "Please ask a question about AI models, research, or industry news.",
            "sources": [],
            "suggest_web_search": False,
            "model_used": "none"
        }

    conn = get_db_connection()
    try:
        intent, intent_data = detect_intent(clean_q, conn=conn)

        context_chunks = []

        # Intent 1: Latest releases
        if intent == "latest_releases":
            days = (intent_data or {}).get("window_days", 7)
            cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

            cur = conn.cursor()
            cur.execute("""
                SELECT a.id, a.title, a.summary, a.body, a.published_at_utc, a.url,
                       s.name as source_name, a.event_type, a.takeaway, a.score_cached
                FROM articles a
                LEFT JOIN sources s ON a.source_id = s.id
                WHERE a.event_type IN ('model_release', 'model_update')
                  AND a.published_at_utc >= ?
                ORDER BY a.score_cached DESC, a.published_at_utc DESC
                LIMIT 15;
            """, (cutoff_iso,))
            rows = [dict(r) for r in cur.fetchall()]

            if not rows:
                return {
                    "answer": NOT_FOUND_MESSAGE,
                    "sources": [],
                    "suggest_web_search": True,
                    "intent": intent,
                    "model_used": "none"
                }

            for r in rows:
                text_content = f"Title: {r.get('title')}\nTakeaway: {r.get('takeaway') or r.get('summary')}\nDetails: {(r.get('body') or '')[:500]}"
                context_chunks.append({
                    "id": f"{r['id']}_radar",
                    "text": text_content,
                    "metadata": {
                        "article_id": r["id"],
                        "title": r.get("title", ""),
                        "source_name": r.get("source_name", "Unknown"),
                        "published_at_utc": r.get("published_at_utc", ""),
                        "url": r.get("url", "")
                    }
                })

        # Intent 2: Entity updates
        elif intent == "entity_updates":
            ent_id = intent_data["id"]
            timeline = get_entity_timeline(conn, ent_id)

            if not timeline:
                return {
                    "answer": NOT_FOUND_MESSAGE,
                    "sources": [],
                    "suggest_web_search": True,
                    "intent": intent,
                    "model_used": "none"
                }

            for item in timeline[:12]:
                text_content = f"Event: {item.get('event_type')}\nTitle: {item.get('title')}\nTakeaway: {item.get('takeaway')}\nEvidence: {item.get('evidence')}"
                context_chunks.append({
                    "id": f"{item['article_id']}_ent",
                    "text": text_content,
                    "metadata": {
                        "article_id": item["article_id"],
                        "title": item.get("title", ""),
                        "source_name": item.get("source_name", "Unknown"),
                        "published_at_utc": item.get("published_at_utc", ""),
                        "url": item.get("url", "")
                    }
                })

        # Intent 3: General hybrid retrieval
        else:
            # Check for rare terms / FTS hit requirement (Section 7.2):
            # Dense similarity is unreliable for rare or new terms: require at least one FTS5 hit or an entity match before answering
            fts_hits = search_fts(clean_q, limit=5)
            if not fts_hits:
                return {
                    "answer": NOT_FOUND_MESSAGE,
                    "sources": [],
                    "suggest_web_search": True,
                    "intent": intent,
                    "model_used": "none"
                }

            context_chunks = hybrid_retrieve(clean_q, top_k=8)

        # If after retrieval there is still no context:
        if not context_chunks:
            return {
                "answer": NOT_FOUND_MESSAGE,
                "sources": [],
                "suggest_web_search": True,
                "intent": intent,
                "model_used": "none"
            }

        # Generate answer with Gemini LLM
        rag_result = gemini_service.chat_rag(clean_q, context_chunks, history)
        sources = rag_result.get("sources", [])
        raw_answer = str(rag_result.get("answer") or "")

        # Citation cleanup & deduplication
        validated_answer, cleaned_sources = sanitize_and_deduplicate_citations(raw_answer, sources)

        return {
            "answer": validated_answer,
            "sources": cleaned_sources,
            "suggest_web_search": False,
            "intent": intent,
            "model_used": rag_result.get("model_used", "gemini-3.5-flash-lite")
        }

    finally:
        conn.close()
