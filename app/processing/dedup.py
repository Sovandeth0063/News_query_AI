import sqlite3
from typing import Optional
from app.storage.database import get_db_connection

def is_duplicate_exact(url: str, content_hash: Optional[str] = None) -> bool:
    """
    Check if an article already exists by canonical URL or content hash.
    """
    conn = get_db_connection()
    try:
        if content_hash:
            cursor = conn.execute(
                "SELECT id FROM articles WHERE url = ? OR (content_hash = ? AND content_hash != '') LIMIT 1;",
                (url, content_hash)
            )
        else:
            cursor = conn.execute("SELECT id FROM articles WHERE url = ? LIMIT 1;", (url,))
        
        row = cursor.fetchone()
        return row is not None
    finally:
        conn.close()
