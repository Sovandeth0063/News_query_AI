import re
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Tuple, Optional, List
from app.storage.database import get_db_connection
from app.processing.entity_registry import normalize_canonical_name

GENERIC_RELEASE_PATTERNS = [
    r"\bnew\s+models?\b",
    r"\blatest\s+models?\b",
    r"\brecent\s+models?\b",
    r"\bmodel\s+launch(es)?\b",
    r"\bmodel\s+release(s)?\b",
    r"\bwhat\s+(models?\s+)?launched\b",
    r"\bwhat\s+(models?\s+)?released\b",
    r"\breleased\s+(this\s+week|today|recently)\b",
    r"\blaunched\s+(this\s+week|today|recently)\b",
    r"\bnew\s+ai(\s+models?)?\b",
    r"\bwhat\s+new\s+ai\b",
    r"\bnew\s+open[- ]weight\b"
]

def parse_time_window_days(query: str, default_days: int = 7) -> int:
    q = query.lower()
    if "today" in q:
        return 1
    if "yesterday" in q:
        return 2
    if "this week" in q or "last 7 days" in q or "past week" in q:
        return 7
    if "this month" in q or "last month" in q or "past 30 days" in q or "last 30 days" in q:
        return 30
    return default_days

def find_matching_entity_in_query(query: str, conn) -> Optional[Dict[str, Any]]:
    """
    Data-driven lookup in entities and entity_aliases table.
    Checks if any normalized entity canonical_name or alias appears as a whole phrase in query.
    Sorts candidate entity names by length descending to match longest specific entity first.
    Zero hardcoded names.
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT e.id, e.canonical_name, e.display_name, e.type, a.alias
        FROM entities e
        LEFT JOIN entity_aliases a ON e.id = a.entity_id
    """)
    rows = cur.fetchall()
    if not rows:
        return None

    # Group aliases by entity
    entity_map = {}
    for r in rows:
        eid = r["id"]
        if eid not in entity_map:
            entity_map[eid] = {
                "id": eid,
                "canonical_name": r["canonical_name"],
                "display_name": r["display_name"],
                "type": r["type"],
                "aliases": set()
            }
        entity_map[eid]["aliases"].add(r["canonical_name"])
        if r["alias"]:
            entity_map[eid]["aliases"].add(r["alias"])

    # Clean query for matching
    cleaned_q = " " + normalize_canonical_name(query) + " "

    # Check candidates sorted by length of name descending
    matched_candidate = None
    best_len = 0

    for eid, ent in entity_map.items():
        for name_candidate in ent["aliases"]:
            if len(name_candidate) < 2:
                continue
            token_pattern = r"(?:^|\W)" + re.escape(name_candidate) + r"(?:$|\W)"
            if re.search(token_pattern, cleaned_q):
                if len(name_candidate) > best_len:
                    best_len = len(name_candidate)
                    matched_candidate = ent

    return matched_candidate

def detect_intent(query: str, conn=None) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Rules-first intent router adhering to Section 7.1:
    1. entity_updates: if any token/phrase matches a known entity in the DB
    2. latest_releases: generic release/launch question without specific entity
    3. general: standard hybrid RAG
    """
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True

    try:
        # Check entity match first
        matched_ent = find_matching_entity_in_query(query, conn)
        if matched_ent:
            return "entity_updates", matched_ent

        # Check latest releases patterns
        for pat in GENERIC_RELEASE_PATTERNS:
            if re.search(pat, query, re.IGNORECASE):
                days = parse_time_window_days(query)
                return "latest_releases", {"window_days": days}

        return "general", None

    finally:
        if should_close:
            conn.close()
