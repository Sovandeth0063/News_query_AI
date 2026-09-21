import re
import html
import hashlib
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
from typing import Optional
import email.utils

UTM_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term",
    "utm_content", "fbclid", "gclid", "ref", "source"
}

def canonicalize_url(url: str) -> str:
    """Strip UTM parameters, query tracking garbage, and URL fragments."""
    if not url:
        return ""
    try:
        parsed = urlparse(url.strip())
        query_pairs = parse_qsl(parsed.query)
        cleaned_query = [
            (k, v) for k, v in query_pairs if k.lower() not in UTM_PARAMS
        ]
        new_query = urlencode(cleaned_query)
        # Drop fragment, trailing slash on path if root
        path = parsed.path.rstrip('/') if parsed.path != '/' else '/'
        cleaned_url = urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            parsed.params,
            new_query,
            ""  # drop fragment
        ))
        return cleaned_url
    except Exception:
        return url.strip()

def parse_to_utc_iso(date_str: Optional[str], fallback_dt: Optional[datetime] = None) -> str:
    """Parse various date formats into standardized UTC ISO-8601 string."""
    if not date_str:
        dt = fallback_dt or datetime.now(timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()

    try:
        # Try email / RFC 2822 format (common in RSS)
        parsed_tuple = email.utils.parsedate_to_datetime(date_str)
        if parsed_tuple:
            return parsed_tuple.astimezone(timezone.utc).isoformat()
    except Exception:
        pass

    try:
        # Try ISO format
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        pass

    dt = fallback_dt or datetime.now(timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()

def compute_content_hash(title: str, text: str) -> str:
    """Compute SHA-256 hash over normalized title and text."""
    normalized = f"{title.strip().lower()}\n{text.strip().lower()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

from bs4 import BeautifulSoup

def clean_text(raw: Optional[str]) -> str:
    """Strip extraneous HTML entities, tags, WordPress boilerplate, and normalize whitespace."""
    if not raw:
        return ""
    text = BeautifulSoup(raw or "", "html.parser").get_text(" ", strip=True)
    text = html.unescape(text)                                   # &#8217; -> ’
    text = re.sub(r"\s*The post .+? appeared first on .+$", "", text, flags=re.I)
    text = re.sub(r"\s*\[(?:…|\.\.\.)\]\s*$", " …", text)         # [&#8230;] -> …
    return re.sub(r"\s+", " ", text).strip()

