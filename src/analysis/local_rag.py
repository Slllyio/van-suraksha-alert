"""
Local RAG Engine — Qdrant + Ollama for offline AI Q&A.
=====================================================

Provides vector-based retrieval-augmented generation using locally hosted
Qdrant (vector DB) and Ollama (LLM), enabling forest officers to query
fire data and SOPs even without internet connectivity.

Adapted from Project NOMAD RAG patterns for the Van Suraksha Alert System.
"""

import hashlib
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

log = logging.getLogger(__name__)

# Forest domain query expansion — maps abbreviations to full terms
FOREST_QUERY_EXPANSION: Dict[str, str] = {
    "fwi": "Fire Weather Index FWI danger rating",
    "frp": "Fire Radiative Power FRP thermal intensity megawatts",
    "ndvi": "Normalized Difference Vegetation Index NDVI greenness",
    "nbr": "Normalized Burn Ratio NBR burn severity",
    "firms": "Fire Information Resource Management System FIRMS VIIRS satellite",
    "viirs": "Visible Infrared Imaging Radiometer Suite VIIRS satellite fire detection",
    "modis": "Moderate Resolution Imaging Spectroradiometer MODIS satellite",
    "sar": "Synthetic Aperture Radar SAR Sentinel-1 backscatter",
    "cusum": "Cumulative Sum CuSum change detection persistent trend",
    "hls": "Harmonized Landsat Sentinel-2 HLS surface reflectance",
    "cfl": "Counter Fire Line CFL firebreak patrol",
    "sop": "Standard Operating Procedure SOP protocol",
    "dfo": "Divisional Forest Officer DFO",
    "rfo": "Range Forest Officer RFO",
    "beat": "forest beat patrol area guard",
    "teak": "tectona grandis teak timber hardwood",
    "tendu": "diospyros melanoxylon tendu bidi leaf",
    "mahua": "madhuca longifolia mahua flower",
    "bamboo": "dendrocalamus strictus bamboo",
    "guna": "Guna Division Madhya Pradesh MP forest",
}

# Default configuration
DEFAULT_QDRANT_URL = "http://localhost:6333"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_EMBED_MODEL = "nomic-embed-text:v1.5"
DEFAULT_CHAT_MODEL = "llama3.2:3b"
DEFAULT_COLLECTION = "fire_knowledge"
EMBED_DIM = 768  # nomic-embed-text v1.5 dimension

DEFAULT_CHUNK_SIZE = 5100
DEFAULT_CHUNK_OVERLAP = 450


class LocalRAGEngine:
    """
    Offline RAG engine using Qdrant for vector search and Ollama for LLM chat.

    Mirrors NOMAD's RagService pattern:
      chunk -> embed (nomic-embed-text:v1.5) -> Qdrant cosine search
      -> keyword rerank -> context inject -> Ollama stream
    """

    def __init__(
        self,
        qdrant_url: str = "",
        ollama_url: str = "",
        embed_model: str = "",
        chat_model: str = "",
        collection: str = DEFAULT_COLLECTION,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ):
        self.qdrant_url = qdrant_url or os.environ.get("VS_QDRANT_URL", DEFAULT_QDRANT_URL)
        self.ollama_url = ollama_url or os.environ.get("VS_OLLAMA_URL", DEFAULT_OLLAMA_URL)
        self.embed_model = embed_model or DEFAULT_EMBED_MODEL
        self.chat_model = chat_model or DEFAULT_CHAT_MODEL
        self.collection = collection
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        self._qdrant = None
        self._ollama = None
        self._available = None

    def _get_qdrant(self):
        """Lazy-init Qdrant client."""
        if self._qdrant is None:
            from qdrant_client import QdrantClient
            self._qdrant = QdrantClient(url=self.qdrant_url, timeout=10)
        return self._qdrant

    def _get_ollama(self):
        """Lazy-init Ollama client."""
        if self._ollama is None:
            import ollama
            self._ollama = ollama.Client(host=self.ollama_url)
        return self._ollama

    def _ensure_collection(self) -> None:
        """Create Qdrant collection if it doesn't exist."""
        from qdrant_client.models import Distance, VectorParams

        client = self._get_qdrant()
        collections = [c.name for c in client.get_collections().collections]
        if self.collection not in collections:
            client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(
                    size=EMBED_DIM,
                    distance=Distance.COSINE,
                ),
            )
            log.info("Created Qdrant collection: %s", self.collection)

    def _chunk_text(self, text: str) -> List[str]:
        """Split text into overlapping chunks."""
        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
                separators=["\n\n", "\n", ". ", " ", ""],
            )
            return splitter.split_text(text)
        except ImportError:
            # Manual fallback
            chunks = []
            start = 0
            while start < len(text):
                end = start + self.chunk_size
                chunks.append(text[start:end])
                start = end - self.chunk_overlap
            return chunks

    def _embed(self, texts: List[str]) -> List[List[float]]:
        """Embed texts using Ollama nomic-embed-text."""
        client = self._get_ollama()
        embeddings = []
        batch_size = 8
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            for text in batch:
                # nomic-embed-text uses search_document: prefix for documents
                resp = client.embeddings(
                    model=self.embed_model,
                    prompt=f"search_document: {text}",
                )
                embeddings.append(resp["embedding"])
        return embeddings

    def _embed_query(self, query: str) -> List[float]:
        """Embed a query using search_query: prefix."""
        client = self._get_ollama()
        resp = client.embeddings(
            model=self.embed_model,
            prompt=f"search_query: {query}",
        )
        return resp["embedding"]

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract domain-relevant keywords from text."""
        words = set(re.findall(r"\b[a-zA-Z]{3,}\b", text.lower()))
        keywords = []
        for word in words:
            if word in FOREST_QUERY_EXPANSION:
                keywords.append(word)
            elif len(word) > 4:
                keywords.append(word)
        return keywords[:20]

    def ingest_text(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> int:
        """
        Chunk, embed, and upsert text into Qdrant.

        Returns number of chunks ingested.
        """
        self._ensure_collection()
        from qdrant_client.models import PointStruct

        metadata = metadata or {}
        chunks = self._chunk_text(text)
        if not chunks:
            return 0

        embeddings = self._embed(chunks)
        client = self._get_qdrant()

        points = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            point_id = str(uuid.uuid5(
                uuid.NAMESPACE_DNS,
                hashlib.md5(chunk.encode()).hexdigest(),
            ))
            payload = {
                "text": chunk,
                "source": metadata.get("source", "unknown"),
                "keywords": self._extract_keywords(chunk),
                "chunk_index": i,
                "total_chunks": len(chunks),
                **{k: v for k, v in metadata.items() if k != "source"},
            }
            points.append(PointStruct(
                id=point_id,
                vector=embedding,
                payload=payload,
            ))

        # Upsert in batches
        batch_size = 64
        for i in range(0, len(points), batch_size):
            client.upsert(
                collection_name=self.collection,
                points=points[i:i + batch_size],
            )

        log.info("Ingested %d chunks from %s", len(chunks), metadata.get("source", "unknown"))
        return len(chunks)

    def ingest_file(self, path: str | Path) -> int:
        """Read and ingest a file (txt, md, json)."""
        path = Path(path)
        if not path.exists():
            log.warning("File not found: %s", path)
            return 0

        suffix = path.suffix.lower()
        try:
            if suffix == ".json":
                with open(path, "r", encoding="utf-8") as f:
                    data = __import__("json").load(f)
                # Flatten JSON to text
                if isinstance(data, dict):
                    text = __import__("json").dumps(data, indent=2, ensure_ascii=False)
                elif isinstance(data, list):
                    text = "\n\n".join(
                        __import__("json").dumps(item, indent=2, ensure_ascii=False)
                        if isinstance(item, dict) else str(item)
                        for item in data
                    )
                else:
                    text = str(data)
            else:
                text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            log.error("Failed to read %s: %s", path, e)
            return 0

        return self.ingest_text(text, metadata={"source": str(path), "filename": path.name})

    def _expand_query(self, query: str) -> str:
        """Expand query with domain-specific terms."""
        expanded = query
        for abbr, expansion in FOREST_QUERY_EXPANSION.items():
            if re.search(rf"\b{abbr}\b", query, re.IGNORECASE):
                expanded = f"{expanded} {expansion}"
        return expanded

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Semantic search with query expansion and keyword reranking.

        Returns top-k results with text, score, and metadata.
        """
        self._ensure_collection()
        expanded = self._expand_query(query)
        query_embedding = self._embed_query(expanded)
        query_keywords = set(self._extract_keywords(query))

        client = self._get_qdrant()
        results = client.search(
            collection_name=self.collection,
            query_vector=query_embedding,
            limit=min(limit * 3, 15),  # Over-fetch for reranking
            score_threshold=0.3,
        )

        # Keyword rerank + source diversity
        scored = []
        seen_sources = set()
        for hit in results:
            payload = hit.payload or {}
            score = hit.score

            # Keyword boost
            hit_keywords = set(payload.get("keywords", []))
            keyword_overlap = len(query_keywords & hit_keywords)
            score += keyword_overlap * 0.05

            # Source diversity penalty (reduce score for repeat sources)
            source = payload.get("source", "")
            if source in seen_sources:
                score -= 0.1
            seen_sources.add(source)

            scored.append({
                "text": payload.get("text", ""),
                "score": round(score, 4),
                "source": source,
                "chunk_index": payload.get("chunk_index", 0),
            })

        # Sort by adjusted score and return top-k
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]

    def chat_stream(
        self, query: str, model: str = ""
    ) -> Generator[str, None, None]:
        """
        RAG-augmented chat with streaming response.

        Search -> inject context as system message -> Ollama stream -> yield tokens.
        """
        model = model or self.chat_model

        # Retrieve relevant context
        results = self.search(query, limit=5)
        context_parts = []
        for i, r in enumerate(results, 1):
            source = Path(r["source"]).name if r["source"] else "unknown"
            context_parts.append(
                f"[Source {i}: {source} (relevance: {r['score']:.2f})]\n{r['text']}"
            )
        context = "\n\n---\n\n".join(context_parts)

        system_prompt = (
            "You are VanAagni AI, the cognitive guardian of Guna Forest Division, "
            "Madhya Pradesh, India. You help forest officers monitor fire risks, "
            "understand fire weather, and protect forests.\n\n"
            "Use ONLY the following retrieved context to answer. "
            "If the context doesn't contain enough information, say so honestly. "
            "Be specific with numbers and cite sources when possible.\n"
            "If the question is in Hindi, respond in Hindi (Devanagari).\n"
            "Keep responses concise (3-5 sentences).\n\n"
            f"RETRIEVED CONTEXT:\n{context}"
        )

        client = self._get_ollama()
        stream = client.chat(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ],
            stream=True,
        )

        for chunk in stream:
            token = chunk.get("message", {}).get("content", "")
            if token:
                yield token

    def chat(self, query: str, model: str = "") -> str:
        """Non-streaming chat (collects full response)."""
        return "".join(self.chat_stream(query, model))

    def is_available(self) -> bool:
        """Health check: verify both Qdrant and Ollama are reachable."""
        if self._available is not None:
            return self._available

        try:
            # Check Qdrant
            client = self._get_qdrant()
            client.get_collections()

            # Check Ollama
            ollama_client = self._get_ollama()
            ollama_client.list()

            self._available = True
            log.info("Local RAG available (Qdrant: %s, Ollama: %s)",
                     self.qdrant_url, self.ollama_url)
        except Exception as e:
            self._available = False
            log.debug("Local RAG not available: %s", e)

        return self._available

    def reset_availability(self) -> None:
        """Reset cached availability status (re-check on next call)."""
        self._available = None
        self._qdrant = None
        self._ollama = None

    def collection_stats(self) -> Dict[str, Any]:
        """Get collection statistics."""
        try:
            client = self._get_qdrant()
            info = client.get_collection(self.collection)
            return {
                "points_count": info.points_count,
                "vectors_count": info.vectors_count,
                "status": info.status.value,
            }
        except Exception as e:
            return {"error": str(e)}
