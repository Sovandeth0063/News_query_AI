import logging
from typing import List, Dict, Any
from datetime import datetime, timezone
import arxiv
from app.ingestion.normalizer import clean_text

logger = logging.getLogger(__name__)

def fetch_arxiv_papers(category: str = "cs.AI", max_results: int = 15) -> List[Dict[str, Any]]:
    """
    Fetch recent arXiv papers for a given category (e.g., cs.AI, cs.LG, cs.CL).
    Returns list of article dicts formatted for the database.
    """
    items = []
    try:
        client = arxiv.Client(page_size=max_results, delay_seconds=1.0, num_retries=2)
        search = arxiv.Search(
            query=f"cat:{category}",
            max_results=max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending
        )

        for result in client.results(search):
            title = clean_text(result.title)
            summary = clean_text(result.summary)
            published_utc = result.published.astimezone(timezone.utc).isoformat()
            authors = [a.name for a in result.authors[:4]]

            items.append({
                "source_id": f"arxiv_{category.lower().replace('.', '_')}",
                "source_name": f"arXiv ({category})",
                "url": result.entry_id,
                "title": title,
                "summary": summary,
                "body": f"Abstract: {summary}\n\nAuthors: {', '.join(authors)}\nPrimary Category: {result.primary_category}\nPDF: {result.pdf_url}",
                "published_at_utc": published_utc,
                "category_hint": "AI_RESEARCH",
                "authority": 1.2,
                "extraction_status": "full",
                "tags": [category] + [c for c in result.categories if c != category][:3]
            })

    except Exception as e:
        logger.error(f"Error fetching arXiv category {category}: {e}")

    return items
