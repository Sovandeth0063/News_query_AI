import re
import sqlite3
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from app.config import settings

def sanitize_fts_query(query: str) -> str:
    """
    Sanitize a user search string for safe SQLite FTS5 MATCH execution.
    Removes dangerous FTS5 operators (like hyphens, colons, quotes) and
    quotes individual tokens to prevent syntax errors (e.g. 'GPT-4' -> '"GPT-4"').
    """
    if not query or not query.strip():
        return ""
    # Extract alphanumeric words or hyphenated/underscored tokens
    tokens = re.findall(r'[a-zA-Z0-9]+(?:[-_][a-zA-Z0-9]+)*', query.strip())
    if not tokens:
        return ""
    # Double quote each token to treat it as an exact phrase/token in FTS5
    return " OR ".join(f'"{t}"' for t in tokens[:10])


def get_db_connection() -> sqlite3.Connection:
    """Create and return a thread-safe connection with WAL mode enabled."""
    conn = sqlite3.connect(settings.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def init_db():
    """Initialize database tables, FTS5 virtual table, and sync triggers."""
    conn = get_db_connection()
    with conn:
        # Sources table
        conn.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            feed_url TEXT NOT NULL,
            kind TEXT NOT NULL, -- rss | arxiv
            category_hint TEXT,
            authority REAL DEFAULT 1.0,
            enabled INTEGER DEFAULT 1,
            last_success_at TEXT,
            consecutive_failures INTEGER DEFAULT 0
        );
        """)

        # Story clusters
        conn.execute("""
        CREATE TABLE IF NOT EXISTS story_clusters (
            id TEXT PRIMARY KEY,
            representative_article_id TEXT,
            size INTEGER DEFAULT 1,
            first_seen_utc TEXT,
            last_seen_utc TEXT
        );
        """)

        # Articles table
        conn.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id TEXT PRIMARY KEY,
            source_id TEXT,
            url TEXT UNIQUE NOT NULL,
            canonical_url TEXT,
            title TEXT NOT NULL,
            summary TEXT,
            body TEXT,
            takeaway TEXT,
            lang TEXT DEFAULT 'en',
            published_at_utc TEXT NOT NULL,
            fetched_at_utc TEXT NOT NULL,
            content_hash TEXT,
            cluster_id TEXT,
            category TEXT NOT NULL, -- AI_LLM | DATA_SCIENCE_ML | AI_RESEARCH | DATA_ENG_CLOUD | TECH_GENERAL
            tags_json TEXT DEFAULT '[]',
            priority_weight REAL DEFAULT 1.0,
            score_cached REAL DEFAULT 0.0,
            extraction_status TEXT DEFAULT 'full', -- full | summary_only | failed
            embedded INTEGER DEFAULT 0,
            FOREIGN KEY (source_id) REFERENCES sources(id),
            FOREIGN KEY (cluster_id) REFERENCES story_clusters(id)
        );
        """)

        conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at_utc DESC);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_score ON articles(score_cached DESC);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_cluster ON articles(cluster_id);")

        # FTS5 Virtual Table for full-text search
        conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
            id UNINDEXED,
            title,
            summary,
            body,
            category UNINDEXED,
            content='articles',
            content_rowid='rowid'
        );
        """)

        # Triggers to keep FTS5 table in sync with articles
        conn.execute("""
        CREATE TRIGGER IF NOT EXISTS articles_ai AFTER INSERT ON articles BEGIN
            INSERT INTO articles_fts(rowid, id, title, summary, body, category)
            VALUES (new.rowid, new.id, new.title, new.summary, new.body, new.category);
        END;
        """)

        conn.execute("""
        CREATE TRIGGER IF NOT EXISTS articles_ad AFTER DELETE ON articles BEGIN
            INSERT INTO articles_fts(articles_fts, rowid, id, title, summary, body, category)
            VALUES ('delete', old.rowid, old.id, old.title, old.summary, old.body, old.category);
        END;
        """)

        conn.execute("""
        CREATE TRIGGER IF NOT EXISTS articles_au AFTER UPDATE ON articles BEGIN
            INSERT INTO articles_fts(articles_fts, rowid, id, title, summary, body, category)
            VALUES ('delete', old.rowid, old.id, old.title, old.summary, old.body, old.category);
            INSERT INTO articles_fts(rowid, id, title, summary, body, category)
            VALUES (new.rowid, new.id, new.title, new.summary, new.body, new.category);
        END;
        """)

        # Digests table
        conn.execute("""
        CREATE TABLE IF NOT EXISTS digests (
            id TEXT PRIMARY KEY,
            digest_date TEXT UNIQUE NOT NULL,
            content_md TEXT NOT NULL,
            article_ids_json TEXT NOT NULL,
            model TEXT,
            created_at_utc TEXT NOT NULL
        );
        """)

        # Read state & bookmarks
        conn.execute("""
        CREATE TABLE IF NOT EXISTS read_state (
            article_id TEXT PRIMARY KEY,
            is_read INTEGER DEFAULT 0,
            is_bookmarked INTEGER DEFAULT 0,
            updated_at_utc TEXT NOT NULL,
            FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE
        );
        """)

        # Ingestion runs tracking
        conn.execute("""
        CREATE TABLE IF NOT EXISTS ingestion_runs (
            id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            trigger TEXT NOT NULL, -- schedule | manual
            fetched INTEGER DEFAULT 0,
            new INTEGER DEFAULT 0,
            dupes INTEGER DEFAULT 0,
            failed INTEGER DEFAULT 0,
            status TEXT NOT NULL, -- running | completed | failed
            error_log TEXT
        );
        """)

        # Additive Radar tables
        conn.execute("""
        CREATE TABLE IF NOT EXISTS entities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_name TEXT NOT NULL,
            display_name TEXT NOT NULL,
            type TEXT NOT NULL, -- model | org | person | benchmark | product
            first_seen_utc TEXT NOT NULL,
            last_seen_utc TEXT NOT NULL,
            mention_count INTEGER NOT NULL DEFAULT 0,
            is_baseline INTEGER NOT NULL DEFAULT 0,
            is_emerging INTEGER NOT NULL DEFAULT 0,
            emerging_since_utc TEXT,
            UNIQUE (canonical_name, type)
        );
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS entity_aliases (
            entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            alias TEXT NOT NULL,
            PRIMARY KEY (entity_id, alias)
        );
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS article_entities (
            article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
            entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            role TEXT NOT NULL, -- subject | mentioned
            confidence REAL,
            evidence TEXT,
            PRIMARY KEY (article_id, entity_id)
        );
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS app_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """)

        # Column migrations on articles & sources tables
        article_new_cols = [
            ("takeaway", "TEXT"),
            ("event_type", "TEXT"),
            ("event_confidence", "REAL"),
            ("llm_extraction_status", "TEXT DEFAULT 'pending'"),
            ("extraction_model", "TEXT"),
            ("source_type", "TEXT")
        ]
        for col_name, col_def in article_new_cols:
            try:
                conn.execute(f"ALTER TABLE articles ADD COLUMN {col_name} {col_def};")
            except sqlite3.OperationalError:
                pass

        try:
            conn.execute("ALTER TABLE sources ADD COLUMN source_type TEXT DEFAULT 'press';")
        except sqlite3.OperationalError:
            pass

        # Additive indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_event_type_pub ON articles(event_type, published_at_utc);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_article_entities_entity ON article_entities(entity_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_emerging ON entities(is_emerging, last_seen_utc);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_aliases_alias ON entity_aliases(alias);")

        # Cold-start baseline metadata initialization
        cursor = conn.execute("SELECT value FROM app_meta WHERE key = 'installed_at_utc';")
        if not cursor.fetchone():
            now_dt = datetime.now(timezone.utc)
            installed_iso = now_dt.isoformat()
            baseline_until_iso = (now_dt + timedelta(days=settings.RADAR_BASELINE_DAYS)).isoformat()
            conn.execute("INSERT OR IGNORE INTO app_meta (key, value) VALUES ('installed_at_utc', ?);", (installed_iso,))
            conn.execute("INSERT OR IGNORE INTO app_meta (key, value) VALUES ('radar_baseline_until_utc', ?);", (baseline_until_iso,))

    conn.close()

def sync_sources_from_yaml(sources_list: List[Dict[str, Any]]):
    """Sync source configurations from sources.yaml into SQLite."""
    conn = get_db_connection()
    with conn:
        for s in sources_list:
            conn.execute("""
            INSERT INTO sources (id, name, feed_url, kind, category_hint, authority, enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                feed_url=excluded.feed_url,
                kind=excluded.kind,
                category_hint=excluded.category_hint,
                authority=excluded.authority,
                enabled=excluded.enabled;
            """, (
                s["id"], s["name"], s["feed_url"], s["kind"],
                s.get("category_hint", "TECH_GENERAL"),
                s.get("authority", 1.0),
                1 if s.get("enabled", True) else 0
            ))
    conn.close()

def upsert_article(article_data: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Upsert an article into SQLite.
    Returns (is_new, article_id).
    """
    conn = get_db_connection()
    is_new = False
    with conn:
        cursor = conn.execute("SELECT id FROM articles WHERE url = ?", (article_data["url"],))
        existing = cursor.fetchone()
        if existing:
            article_id = existing["id"]
            tags_str = json.dumps(article_data["tags"]) if "tags" in article_data else None
            conn.execute("""
            UPDATE articles SET
                title = ?, summary = ?, body = ?, content_hash = ?,
                takeaway = COALESCE(?, takeaway),
                category = COALESCE(?, category),
                tags_json = COALESCE(?, tags_json),
                cluster_id = COALESCE(?, cluster_id),
                priority_weight = COALESCE(?, priority_weight),
                score_cached = COALESCE(?, score_cached),
                extraction_status = ?,
                event_type = COALESCE(?, event_type),
                event_confidence = COALESCE(?, event_confidence),
                llm_extraction_status = COALESCE(?, llm_extraction_status),
                extraction_model = COALESCE(?, extraction_model),
                source_type = COALESCE(?, source_type)
            WHERE id = ?;
            """, (
                article_data["title"], article_data.get("summary", ""),
                article_data.get("body", ""), article_data.get("content_hash", ""),
                article_data.get("takeaway"),
                article_data.get("category"),
                tags_str,
                article_data.get("cluster_id"),
                article_data.get("priority_weight"),
                article_data.get("score_cached"),
                article_data.get("extraction_status", "full"),
                article_data.get("event_type"),
                article_data.get("event_confidence"),
                article_data.get("llm_extraction_status"),
                article_data.get("extraction_model"),
                article_data.get("source_type"),
                article_id
            ))
        else:
            is_new = True
            article_id = article_data["id"]
            conn.execute("""
            INSERT INTO articles (
                id, source_id, url, canonical_url, title, summary, body, takeaway, lang,
                published_at_utc, fetched_at_utc, content_hash, cluster_id,
                category, tags_json, priority_weight, score_cached,
                extraction_status, embedded, event_type, event_confidence,
                llm_extraction_status, extraction_model, source_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                article_data["id"], article_data.get("source_id"), article_data["url"],
                article_data.get("canonical_url", article_data["url"]),
                article_data["title"], article_data.get("summary", ""),
                article_data.get("body", ""), article_data.get("takeaway"),
                article_data.get("lang", "en"),
                article_data["published_at_utc"], article_data["fetched_at_utc"],
                article_data.get("content_hash", ""), article_data.get("cluster_id"),
                article_data["category"], json.dumps(article_data.get("tags", [])),
                article_data.get("priority_weight", 1.0), article_data.get("score_cached", 0.0),
                article_data.get("extraction_status", "full"),
                1 if article_data.get("embedded", False) else 0,
                article_data.get("event_type"), article_data.get("event_confidence"),
                article_data.get("llm_extraction_status", "pending"),
                article_data.get("extraction_model"), article_data.get("source_type")
            ))
    conn.close()
    return is_new, article_id

# Domains/patterns that should never appear in the reader feed
_JUNK_URL_PATTERNS = (
    'example.com', 'example.org', 'example.net',
    'localhost', '127.0.0.1', '0.0.0.0',
    'test.com', 'foo.com', 'bar.com',
    'placeholder', 'dummy',
)

def _is_valid_article_url(url: Optional[str]) -> bool:
    """Return False for empty, non-HTTP, or known placeholder/junk URLs."""
    if not url or not url.strip():
        return False
    url_lower = url.lower().strip()
    if not (url_lower.startswith('http://') or url_lower.startswith('https://')):
        return False
    return not any(pat in url_lower for pat in _JUNK_URL_PATTERNS)


def get_articles_for_feed(category: Optional[str] = None, search: Optional[str] = None, sort: str = "score", limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """
    Retrieve ranked feed articles with cluster metadata and read state.
    Excludes AI_RESEARCH (goes to Papers tab) and any articles with
    invalid/placeholder URLs or blank titles.
    """
    conn = get_db_connection()
    query = """
    SELECT 
        a.id, a.source_id, a.url, a.title, a.summary, a.takeaway, a.category,
        a.published_at_utc, a.score_cached, a.cluster_id, a.tags_json,
        a.event_type, a.event_confidence, a.source_type,
        s.name as source_name, s.authority as source_authority,
        c.size as cluster_size,
        COALESCE(r.is_read, 0) as is_read,
        COALESCE(r.is_bookmarked, 0) as is_bookmarked
    FROM articles a
    LEFT JOIN sources s ON a.source_id = s.id
    LEFT JOIN story_clusters c ON a.cluster_id = c.id
    LEFT JOIN read_state r ON a.id = r.article_id
    WHERE a.category != 'AI_RESEARCH'
      AND a.title IS NOT NULL AND TRIM(a.title) != ''
      AND a.url IS NOT NULL AND TRIM(a.url) != ''
      AND (a.url LIKE 'http://%' OR a.url LIKE 'https://%')
    """
    # Exclude known junk/placeholder domains
    for pat in _JUNK_URL_PATTERNS:
        query += f" AND LOWER(a.url) NOT LIKE '%{pat}%'"

    params = []
    if category and category != 'ALL':
        query += " AND a.category = ?"
        params.append(category)

    if search and search.strip():
        clean_search = sanitize_fts_query(search)
        if clean_search:
            query += " AND a.rowid IN (SELECT rowid FROM articles_fts WHERE articles_fts MATCH ?)"
            params.append(clean_search)

    if sort == "date":
        query += " ORDER BY a.published_at_utc DESC, a.score_cached DESC LIMIT ? OFFSET ?;"
    else:
        query += " ORDER BY a.score_cached DESC, a.published_at_utc DESC LIMIT ? OFFSET ?;"
    params.extend([limit, offset])

    cursor = conn.execute(query, params)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()

    for r in rows:
        r["tags"] = json.loads(r.get("tags_json") or "[]")
    return rows

def get_papers(search: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """Retrieve academic arXiv research papers for the Papers tab.
    Excludes papers with invalid/placeholder URLs or blank titles.
    """
    conn = get_db_connection()
    query = """
    SELECT 
        a.id, a.source_id, a.url, a.title, a.summary, a.takeaway, a.category,
        a.published_at_utc, a.tags_json,
        s.name as source_name,
        COALESCE(r.is_read, 0) as is_read,
        COALESCE(r.is_bookmarked, 0) as is_bookmarked
    FROM articles a
    LEFT JOIN sources s ON a.source_id = s.id
    LEFT JOIN read_state r ON a.id = r.article_id
    WHERE a.category = 'AI_RESEARCH'
      AND a.title IS NOT NULL AND TRIM(a.title) != ''
      AND a.url IS NOT NULL AND TRIM(a.url) != ''
      AND (a.url LIKE 'http://%' OR a.url LIKE 'https://%')
    """
    for pat in _JUNK_URL_PATTERNS:
        query += f" AND LOWER(a.url) NOT LIKE '%{pat}%'"

    params = []
    if search and search.strip():
        clean_search = sanitize_fts_query(search)
        if clean_search:
            query += " AND a.rowid IN (SELECT rowid FROM articles_fts WHERE articles_fts MATCH ?)"
            params.append(clean_search)

    query += " ORDER BY a.published_at_utc DESC LIMIT ? OFFSET ?;"
    params.extend([limit, offset])

    cursor = conn.execute(query, params)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    for r in rows:
        r["tags"] = json.loads(r.get("tags_json") or "[]")
    return rows

def get_sidebar_data() -> Dict[str, Any]:
    """Retrieve top stories today, topic tag counts, and latest digest preview for the sidebar widget."""
    conn = get_db_connection()

    # 1. Top 3 stories today by score
    cursor = conn.execute("""
        SELECT a.id, a.title, a.takeaway, a.summary, a.category,
               a.published_at_utc, a.score_cached, a.url, s.name as source_name
        FROM articles a
        LEFT JOIN sources s ON a.source_id = s.id
        WHERE a.category != 'AI_RESEARCH'
          AND a.title IS NOT NULL AND TRIM(a.title) != ''
          AND a.url IS NOT NULL AND TRIM(a.url) != ''
          AND (a.url LIKE 'http://%' OR a.url LIKE 'https://%')
        ORDER BY a.score_cached DESC, a.published_at_utc DESC
        LIMIT 3;
    """)
    top_today = [dict(r) for r in cursor.fetchall()]

    # 2. Topic tag aggregation from recent articles
    cursor = conn.execute("""
        SELECT tags_json FROM articles
        WHERE tags_json IS NOT NULL AND tags_json != '[]'
        ORDER BY published_at_utc DESC LIMIT 300;
    """)
    tag_counter = {}
    for row in cursor.fetchall():
        try:
            tags = json.loads(row["tags_json"] or "[]")
            for t in tags:
                if t and isinstance(t, str):
                    norm = t.strip()
                    if len(norm) > 1 and norm.lower() not in ["tech", "article"]:
                        tag_counter[norm] = tag_counter.get(norm, 0) + 1
        except Exception:
            pass

    sorted_tags = sorted(tag_counter.items(), key=lambda x: x[1], reverse=True)[:6]
    topic_counts = [{"tag": t, "count": c} for t, c in sorted_tags]

    # 3. Latest digest preview
    cursor = conn.execute("""
        SELECT digest_date, content_md, created_at_utc
        FROM digests
        ORDER BY digest_date DESC, created_at_utc DESC
        LIMIT 1;
    """)
    digest_row = cursor.fetchone()
    digest_preview = None
    if digest_row:
        content = digest_row["content_md"] or ""
        lines = [line.strip() for line in content.split("\n") if line.strip() and not line.strip().startswith("#")]
        snippet = " ".join(lines[:3])[:220]
        if len(snippet) >= 220:
            snippet += "…"
        digest_preview = {
            "digest_date": digest_row["digest_date"],
            "snippet": snippet or "Executive daily AI & tech briefing ready to read."
        }

    conn.close()
    return {
        "top_today": top_today,
        "topic_counts": topic_counts,
        "digest_preview": digest_preview
    }

def set_read_state(article_id: str, is_read: Optional[bool] = None, is_bookmarked: Optional[bool] = None):
    """Set or toggle read/bookmark state for an article."""
    conn = get_db_connection()
    now_utc = datetime.now(timezone.utc).isoformat()
    with conn:
        cursor = conn.execute("SELECT is_read, is_bookmarked FROM read_state WHERE article_id = ?", (article_id,))
        existing = cursor.fetchone()
        if existing:
            new_read = existing["is_read"] if is_read is None else (1 if is_read else 0)
            new_bookmark = existing["is_bookmarked"] if is_bookmarked is None else (1 if is_bookmarked else 0)
            conn.execute("""
            UPDATE read_state SET is_read = ?, is_bookmarked = ?, updated_at_utc = ?
            WHERE article_id = ?;
            """, (new_read, new_bookmark, now_utc, article_id))
        else:
            new_read = 1 if is_read else 0
            new_bookmark = 1 if is_bookmarked else 0
            conn.execute("""
            INSERT INTO read_state (article_id, is_read, is_bookmarked, updated_at_utc)
            VALUES (?, ?, ?, ?);
            """, (article_id, new_read, new_bookmark, now_utc))
    conn.close()

def purge_expired_articles(retention_days: Optional[int] = None) -> int:
    """
    Purge articles older than retention_days (defaulting to settings.RETENTION_DAYS).
    Preserves bookmarked articles.
    Cascades to read_state and articles_fts automatically, and removes orphaned clusters.
    Returns the number of articles deleted.
    """
    if retention_days is None:
        retention_days = settings.RETENTION_DAYS

    cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
    conn = get_db_connection()
    deleted_count = 0
    with conn:
        cursor = conn.execute("""
            SELECT id FROM articles 
            WHERE published_at_utc < ? 
              AND id NOT IN (SELECT article_id FROM read_state WHERE is_bookmarked = 1);
        """, (cutoff_iso,))
        expired_ids = [row["id"] for row in cursor.fetchall()]
        
        if expired_ids:
            chunk_size = 500
            for i in range(0, len(expired_ids), chunk_size):
                batch = expired_ids[i:i + chunk_size]
                placeholders = ",".join("?" * len(batch))
                conn.execute(f"DELETE FROM articles WHERE id IN ({placeholders});", batch)
            deleted_count = len(expired_ids)

        # Clean up orphaned story clusters
        conn.execute("""
            DELETE FROM story_clusters 
            WHERE id NOT IN (SELECT DISTINCT cluster_id FROM articles WHERE cluster_id IS NOT NULL);
        """)
    conn.close()
    return deleted_count
