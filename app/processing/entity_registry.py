import re
import string
import unicodedata
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

from app.config import settings

logger = logging.getLogger(__name__)

STOPLIST_FILE = Path("config/entity_stoplist.txt")
_STOPLIST_CACHE = None
SUFFIX_TOKENS = {"inc", "ltd", "llc", "corp", "corporation", "labs", "lab", "technologies", "technology", "ai"}

def load_stoplist() -> set[str]:
    global _STOPLIST_CACHE
    if _STOPLIST_CACHE is not None:
        return _STOPLIST_CACHE

    stopset = set()
    if STOPLIST_FILE.exists():
        with open(STOPLIST_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip().lower()
                if line and not line.startswith("#"):
                    stopset.add(line)
    _STOPLIST_CACHE = stopset
    return _STOPLIST_CACHE

def normalize_canonical_name(name: str) -> str:
    """
    NFKC-normalize, lowercase, strip punctuation at ends, collapse whitespace.
    """
    if not name:
        return ""
    # NFKC normalize
    text = unicodedata.normalize("NFKC", name)
    # Strip non-alphanumeric at boundaries
    text = text.strip()
    strip_chars = string.punctuation + "“”‘’`'"
    text = text.strip(strip_chars).lower()
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text

def is_stopword_entity(name: str) -> bool:
    canon = normalize_canonical_name(name)
    if not canon or len(canon) < 2:
        return True
    stoplist = load_stoplist()
    return canon in stoplist

def is_entity_emerging_rule(
    entity_dict: Dict[str, Any],
    linked_articles: List[Dict[str, Any]],
    now_utc: Optional[datetime] = None
) -> bool:
    """
    Pure function implementing Section 6.3 emerging rule:
    An entity becomes is_emerging = 1 when ALL are true:
    - is_baseline == 0
    - type in ('model', 'org')
    - first_seen_utc within EMERGING_WINDOW_HOURS (default 48)
    - mentioned in articles from >= EMERGING_MIN_SOURCES distinct source_ids
      (articles in the same story cluster from the same source count once)
    - at least one linked article has event_type in ('model_release', 'model_update', 'funding')
    - Emerging flag expires after EMERGING_TTL_HOURS since emerging_since_utc
    """
    if entity_dict.get("is_baseline", 0) == 1:
        return False

    ent_type = entity_dict.get("type", "")
    if ent_type not in ("model", "org"):
        return False

    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

def parse_iso_utc(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        clean = date_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None

def is_entity_emerging_rule(
    entity_dict: Dict[str, Any],
    linked_articles: List[Dict[str, Any]],
    now_utc: Optional[datetime] = None
) -> bool:
    """
    Pure function implementing Section 6.3 emerging rule:
    An entity becomes is_emerging = 1 when ALL are true:
    - is_baseline == 0
    - type in ('model', 'org')
    - first_seen_utc within EMERGING_WINDOW_HOURS (default 48)
    - mentioned in articles from >= EMERGING_MIN_SOURCES distinct source_ids
      (articles in the same story cluster from the same source count once)
    - at least one linked article has event_type in ('model_release', 'model_update', 'funding')
    - Emerging flag expires after EMERGING_TTL_HOURS since emerging_since_utc
    """
    if entity_dict.get("is_baseline", 0) == 1:
        return False

    ent_type = entity_dict.get("type", "")
    if ent_type not in ("model", "org"):
        return False

    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    # Window check
    first_seen_dt = parse_iso_utc(entity_dict.get("first_seen_utc"))
    if not first_seen_dt:
        return False

    age_hours = (now_utc - first_seen_dt).total_seconds() / 3600.0
    if age_hours > settings.EMERGING_WINDOW_HOURS:
        return False

    # TTL check if already emerging
    emerging_since_str = entity_dict.get("emerging_since_utc")
    if emerging_since_str:
        em_dt = parse_iso_utc(emerging_since_str)
        if em_dt:
            em_age_hours = (now_utc - em_dt).total_seconds() / 3600.0
            if em_age_hours > settings.EMERGING_TTL_HOURS:
                return False

    # Source diversity check:
    # Articles in same story cluster from same source count once
    seen_source_cluster = set()
    distinct_sources = set()
    has_valid_event = False

    valid_events = {"model_release", "model_update", "funding"}

    for a in linked_articles:
        s_id = a.get("source_id")
        c_id = a.get("cluster_id") or a.get("article_id")
        key = (s_id, c_id)
        if key not in seen_source_cluster:
            seen_source_cluster.add(key)
            if s_id:
                distinct_sources.add(s_id)

        ev_type = a.get("event_type")
        if ev_type in valid_events:
            has_valid_event = True

    if len(distinct_sources) < settings.EMERGING_MIN_SOURCES:
        return False

    if not has_valid_event:
        return False

    return True

def find_or_create_entity(
    conn,
    display_name: str,
    ent_type: str,
    pub_utc: str,
    is_baseline_default: int = 0
) -> Optional[int]:
    """
    Find matching entity or insert new one.
    Matching order:
    1. exact (canonical_name, type) match
    2. alias match in entity_aliases
    3. suffix token match for same type
    4. create new
    """
    canon = normalize_canonical_name(display_name)
    if not canon or is_stopword_entity(canon):
        return None

    cur = conn.cursor()

    # 1. Exact match
    cur.execute("SELECT id, display_name, mention_count FROM entities WHERE canonical_name = ? AND type = ?", (canon, ent_type))
    row = cur.fetchone()
    if row:
        ent_id = row["id"]
        cur.execute("""
            UPDATE entities
            SET mention_count = mention_count + 1,
                last_seen_utc = CASE WHEN last_seen_utc < ? THEN ? ELSE last_seen_utc END
            WHERE id = ?
        """, (pub_utc, pub_utc, ent_id))
        return ent_id

    # 2. Alias match
    cur.execute("""
        SELECT e.id, e.display_name
        FROM entity_aliases a
        JOIN entities e ON a.entity_id = e.id
        WHERE a.alias = ? AND e.type = ?
    """, (canon, ent_type))
    alias_row = cur.fetchone()
    if alias_row:
        ent_id = alias_row["id"]
        cur.execute("""
            UPDATE entities
            SET mention_count = mention_count + 1,
                last_seen_utc = CASE WHEN last_seen_utc < ? THEN ? ELSE last_seen_utc END
            WHERE id = ?
        """, (pub_utc, pub_utc, ent_id))
        return ent_id

    # 3. Safe suffix token merge (only if same type)
    canon_tokens = set(canon.split())
    cur.execute("SELECT id, canonical_name FROM entities WHERE type = ?", (ent_type,))
    candidate_rows = cur.fetchall()
    for cand in candidate_rows:
        cand_tokens = set(cand["canonical_name"].split())
        diff = canon_tokens.symmetric_difference(cand_tokens)
        if diff and diff.issubset(SUFFIX_TOKENS):
            ent_id = cand["id"]
            logger.info(f"Conservative suffix merge: '{display_name}' ({canon}) merged into entity #{ent_id} ({cand['canonical_name']})")
            # Register alias
            cur.execute("INSERT OR IGNORE INTO entity_aliases (entity_id, alias) VALUES (?, ?)", (ent_id, canon))
            cur.execute("""
                UPDATE entities
                SET mention_count = mention_count + 1,
                    last_seen_utc = CASE WHEN last_seen_utc < ? THEN ? ELSE last_seen_utc END
                WHERE id = ?
            """, (pub_utc, pub_utc, ent_id))
            return ent_id

    # 4. Create new entity
    cur.execute("""
        INSERT INTO entities (
            canonical_name, display_name, type, first_seen_utc, last_seen_utc,
            mention_count, is_baseline, is_emerging
        ) VALUES (?, ?, ?, ?, ?, 1, ?, 0)
    """, (canon, display_name.strip(), ent_type, pub_utc, pub_utc, is_baseline_default))
    ent_id = cur.lastrowid

    # Add canonical and original as aliases
    cur.execute("INSERT OR IGNORE INTO entity_aliases (entity_id, alias) VALUES (?, ?)", (ent_id, canon))
    orig_canon = normalize_canonical_name(display_name)
    if orig_canon != canon:
        cur.execute("INSERT OR IGNORE INTO entity_aliases (entity_id, alias) VALUES (?, ?)", (ent_id, orig_canon))

    return ent_id

def link_article_entity(
    conn,
    article_id: str,
    entity_id: int,
    role: str,
    confidence: float,
    evidence: str
):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO article_entities (article_id, entity_id, role, confidence, evidence)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(article_id, entity_id) DO UPDATE SET
            confidence = MAX(article_entities.confidence, excluded.confidence),
            evidence = CASE WHEN LENGTH(article_entities.evidence) < LENGTH(excluded.evidence) THEN excluded.evidence ELSE article_entities.evidence END
    """, (article_id, entity_id, role, confidence, evidence[:200]))

def recompute_emerging_entities(conn):
    """
    Recompute emerging status across non-baseline models and orgs.
    """
    cur = conn.cursor()
    now_utc = datetime.now(timezone.utc)
    now_iso = now_utc.isoformat()

    cur.execute("""
        SELECT id, canonical_name, display_name, type, first_seen_utc, last_seen_utc,
               mention_count, is_baseline, is_emerging, emerging_since_utc
        FROM entities
        WHERE is_baseline = 0 AND type IN ('model', 'org')
    """)
    entities = [dict(r) for r in cur.fetchall()]

    for ent in entities:
        ent_id = ent["id"]
        # Fetch linked articles
        cur.execute("""
            SELECT a.id as article_id, a.source_id, a.cluster_id, a.event_type, a.published_at_utc
            FROM article_entities ae
            JOIN articles a ON ae.article_id = a.id
            WHERE ae.entity_id = ?
        """, (ent_id,))
        articles = [dict(r) for r in cur.fetchall()]

        was_emerging = ent.get("is_emerging", 0) == 1
        is_emerging = is_entity_emerging_rule(ent, articles, now_utc=now_utc)

        if is_emerging and not was_emerging:
            cur.execute("""
                UPDATE entities
                SET is_emerging = 1,
                    emerging_since_utc = COALESCE(emerging_since_utc, ?)
                WHERE id = ?
            """, (now_iso, ent_id))
            logger.info(f"Entity flagged EMERGING: {ent['display_name']} (#{ent_id}, type={ent['type']})")
        elif not is_emerging and was_emerging:
            cur.execute("""
                UPDATE entities
                SET is_emerging = 0
                WHERE id = ?
            """, (ent_id,))
            logger.info(f"Entity no longer emerging: {ent['display_name']} (#{ent_id})")

    conn.commit()

def get_entity_timeline(conn, entity_id: int) -> List[Dict[str, Any]]:
    """
    Chronological timeline of articles for an entity (Section 6.4).
    Ordered by published_at_utc DESC.
    Groups siblings from the same story cluster into one item with 'also_covered_by'.
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT a.id, a.title, a.url, a.published_at_utc, a.source_id, s.name as source_name,
               a.source_type, a.event_type, a.takeaway, a.cluster_id, a.summary,
               ae.role, ae.confidence, ae.evidence
        FROM article_entities ae
        JOIN articles a ON ae.article_id = a.id
        LEFT JOIN sources s ON a.source_id = s.id
        WHERE ae.entity_id = ?
        ORDER BY a.published_at_utc DESC
    """, (entity_id,))
    rows = [dict(r) for r in cur.fetchall()]

    # Group by cluster_id if clustered
    timeline = []
    seen_clusters = {}

    for r in rows:
        cid = r.get("cluster_id")
        if cid and cid in seen_clusters:
            parent = seen_clusters[cid]
            parent["also_covered_by"].append({
                "source_name": r.get("source_name"),
                "source_id": r.get("source_id"),
                "url": r.get("url"),
                "title": r.get("title")
            })
            continue

        item = {
            "article_id": r["id"],
            "title": r["title"],
            "url": r["url"],
            "published_at_utc": r["published_at_utc"],
            "source_id": r["source_id"],
            "source_name": r["source_name"],
            "source_type": r["source_type"],
            "event_type": r["event_type"],
            "takeaway": r["takeaway"] or r["summary"],
            "role": r["role"],
            "confidence": r["confidence"],
            "evidence": r["evidence"],
            "cluster_id": cid,
            "also_covered_by": []
        }
        if cid:
            seen_clusters[cid] = item
        timeline.append(item)

    return timeline
