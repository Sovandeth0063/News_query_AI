import re
import logging
from typing import List, Dict, Any
from app.config import settings

logger = logging.getLogger(__name__)

class EmbeddingService:
    def __init__(self):
        self.model_name = settings.EMBEDDING_MODEL
        self._model = None

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading local embedding model: {self.model_name}")
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def encode(self, texts: List[str]) -> List[List[float]]:
        """Encode list of strings into embedding vectors."""
        if not texts:
            return []
        embeddings = self.model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        return embeddings.tolist()

    def chunk_article(self, article: Dict[str, Any], chunk_chars: int = 1500, overlap_chars: int = 200) -> List[Dict[str, Any]]:
        """
        Split article body/summary into clean text chunks with article metadata.
        Produces 2-5 focused, high-quality chunks per article.
        """
        body = article.get("body") or article.get("summary") or ""
        text = body.strip()
        if not text:
            return []

        chunks = []
        start = 0
        while start < len(text):
            end = min(len(text), start + chunk_chars)
            chunk_text = text[start:end].strip()
            if len(chunk_text) > 80:
                chunks.append(chunk_text)
            if end == len(text):
                break
            start += (chunk_chars - overlap_chars)

        # Build chunk metadata objects
        chunk_objects = []
        for i, c_text in enumerate(chunks):
            chunk_objects.append({
                "id": f"{article['id']}_chunk_{i}",
                "article_id": article["id"],
                "text": c_text,
                "title": article.get("title", ""),
                "source_name": article.get("source_name", ""),
                "published_at_utc": article.get("published_at_utc", ""),
                "category": article.get("category", "TECH_GENERAL"),
                "url": article.get("url", "")
            })

        return chunk_objects


embedding_service = EmbeddingService()
