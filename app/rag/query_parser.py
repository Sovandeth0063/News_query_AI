import re
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

def parse_query_filters(query: str) -> Dict[str, Any]:
    """
    Extract date and category filters from user natural language query.
    Returns:
      - cleaned_query: query string with temporal words preserved or refined
      - date_from_iso: ISO timestamp string or None
      - category_filter: specific category string or None
    """
    q_lower = query.lower()
    now_utc = datetime.now(timezone.utc)
    date_from = None

    if "today" in q_lower:
        date_from = (now_utc - timedelta(hours=24)).isoformat()
    elif "yesterday" in q_lower:
        date_from = (now_utc - timedelta(hours=48)).isoformat()
    elif any(w in q_lower for w in ["this week", "past week", "last 7 days", "latest"]):
        date_from = (now_utc - timedelta(days=7)).isoformat()
    elif any(w in q_lower for w in ["this month", "past month", "last 30 days"]):
        date_from = (now_utc - timedelta(days=30)).isoformat()

    category_filter = None
    if re.search(r'\b(papers?|arxiv|research papers?)\b', q_lower):
        category_filter = "AI_RESEARCH"
    elif re.search(r'\b(llms?|large language models?|gpt|claude|gemini)\b', q_lower):
        category_filter = "AI_LLM"
    elif re.search(r'\b(data science|machine learning|ml)\b', q_lower):
        category_filter = "DATA_SCIENCE_ML"

    return {
        "query": query.strip(),
        "date_from_iso": date_from,
        "category_filter": category_filter
    }
