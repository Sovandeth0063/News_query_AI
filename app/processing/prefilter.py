import re
from typing import Dict, Any
from app.config import settings

AI_CATEGORIES = {"AI_LLM", "DATA_SCIENCE_ML", "AI_RESEARCH"}
_COMPILED_REGEX = None

def get_prefilter_regex():
    global _COMPILED_REGEX
    if _COMPILED_REGEX is None:
        pattern = settings.EXTRACTION_PREFILTER_REGEX
        _COMPILED_REGEX = re.compile(pattern, re.IGNORECASE)
    return _COMPILED_REGEX

def should_extract(article: Dict[str, Any]) -> bool:
    """
    Section 5.2 Cheap prefilter (no LLM).
    Only send an article to the LLM if it passes a generic prefilter:
    category in the AI/Data Science categories OR its title/summary matches
    a generic regex list. Everything else gets skipped.
    """
    if not settings.EXTRACTION_PREFILTER_ENABLED:
        return True

    cat = article.get("category") or article.get("category_hint")
    if cat in AI_CATEGORIES:
        return True

    title = article.get("title") or ""
    summary = article.get("summary") or ""
    combined = f"{title} {summary}"

    rx = get_prefilter_regex()
    if rx.search(combined):
        return True

    return False
