import logging
from typing import Tuple
import httpx
import trafilatura
from app.ingestion.normalizer import clean_text

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def extract_article_content(url: str, fallback_summary: str = "") -> Tuple[str, str]:
    """
    Extract clean article body using httpx + trafilatura with strict 5s timeout.
    Returns (body_text, extraction_status: 'full' | 'summary_only' | 'failed').
    """
    cleaned_fallback = clean_text(fallback_summary)
    if not url:
        return cleaned_fallback, "summary_only" if cleaned_fallback else "failed"

    try:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=4.0, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code == 200 and resp.text:
                extracted = trafilatura.extract(
                    resp.text,
                    include_comments=False,
                    include_tables=True,
                    no_fallback=False
                )
                if extracted and len(extracted.strip()) > 150:
                    return clean_text(extracted), "full"

        return cleaned_fallback, "summary_only" if cleaned_fallback else "failed"

    except Exception as e:
        logger.debug(f"Extraction fallback for {url}: {e}")
        return cleaned_fallback, "summary_only" if cleaned_fallback else "failed"

