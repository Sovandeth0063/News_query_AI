import chromadb
from chromadb.config import Settings as ChromaSettings
from typing import List, Dict, Any, Optional
from app.config import settings

class VectorStore:
    def __init__(self):
        self.client = chromadb.PersistentClient(
            path=str(settings.CHROMA_PATH),
            settings=ChromaSettings(anonymized_telemetry=False)
        )
        self.collection = self.client.get_or_create_collection(
            name="news_chunks",
            metadata={"hnsw:space": "cosine"}
        )

    def add_chunks(self, chunks: List[Dict[str, Any]], embeddings: List[List[float]]):
        """
        Add text chunks with embeddings and metadata to ChromaDB.
        Each chunk dict has: id, text, article_id, title, source_name, published_at_utc, category, url.
        """
        if not chunks:
            return

        ids = [c["id"] for c in chunks]
        documents = [c["text"] for c in chunks]
        metadatas = [{
            "article_id": c["article_id"],
            "title": c.get("title", ""),
            "source_name": c.get("source_name", ""),
            "published_at_utc": c.get("published_at_utc", ""),
            "category": c.get("category", "TECH_GENERAL"),
            "url": c.get("url", "")
        } for c in chunks]

        self.collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas
        )

    def search(self, query_embedding: List[float], top_k: int = 20, where: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Dense similarity search in ChromaDB."""
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where
        )

        matches = []
        if results and results["ids"] and len(results["ids"][0]) > 0:
            for i in range(len(results["ids"][0])):
                matches.append({
                    "id": results["ids"][0][i],
                    "text": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i] if "distances" in results and results["distances"] else 0.0
                })
        return matches

vector_store = VectorStore()
