"""
Hybrid RAG Retrieval Service.

Combines ChromaDB semantic search, Knowledge Graph queries, and document
metadata into a unified, ranked retrieval result. Views never query
ChromaDB or the Knowledge Graph directly — they call this service.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from agents.config import RAGConfig
from agents.exceptions import RetrievalError

logger = logging.getLogger("agents.retrieval")


@dataclass
class RetrievalHit:
    """A single retrieval result from any source."""

    source: str  # "chromadb", "knowledge_graph", "metadata"
    content: str = ""
    score: float = 0.0
    document_id: str = ""
    chunk_id: str = ""
    metadata: dict = field(default_factory=dict)
    entity_id: str = ""
    relationship_type: str = ""

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "content": self.content,
            "score": self.score,
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "metadata": self.metadata,
            "entity_id": self.entity_id,
            "relationship_type": self.relationship_type,
        }


@dataclass
class RetrievalResult:
    """Combined result of hybrid retrieval."""

    query: str
    hits: list[RetrievalHit] = field(default_factory=list)
    total_hits: int = 0
    duration_seconds: float = 0.0
    sources_queried: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "hits": [h.to_dict() for h in self.hits],
            "total_hits": self.total_hits,
            "duration_seconds": self.duration_seconds,
            "sources_queried": self.sources_queried,
            "warnings": self.warnings,
        }


class RAGRetrievalService:
    """
    Hybrid retrieval combining ChromaDB + Knowledge Graph + metadata.

    Usage:
        result = RAGRetrievalService.retrieve(query, query_embedding, config)
    """

    @classmethod
    def retrieve(
        cls,
        query: str,
        query_embedding: list[float] | None = None,
        config: RAGConfig | None = None,
        filters: dict | None = None,
    ) -> RetrievalResult:
        """
        Performs hybrid retrieval across all knowledge stores.

        Args:
            query: The user's search query text.
            query_embedding: Pre-computed embedding for the query
                (if None, only KG and metadata search are performed).
            config: Optional config override.
            filters: Optional metadata filters (document_id, document_type, etc.)

        Returns:
            RetrievalResult with merged, ranked hits.
        """
        start_time = time.time()
        if config is None:
            config = RAGConfig.from_settings()

        all_hits: list[RetrievalHit] = []
        sources_queried: list[str] = []
        warnings: list[str] = []

        # 1. ChromaDB semantic search
        if query_embedding:
            try:
                chromadb_hits = cls._search_chromadb(
                    query_embedding, config, filters
                )
                all_hits.extend(chromadb_hits)
                sources_queried.append("chromadb")
            except Exception as exc:
                warnings.append(f"ChromaDB search failed: {exc}")
                logger.warning("ChromaDB search failed: %s", exc)

        # 2. Knowledge Graph search
        if query:
            try:
                kg_hits = cls._search_knowledge_graph(query, config)
                all_hits.extend(kg_hits)
                sources_queried.append("knowledge_graph")
            except Exception as exc:
                warnings.append(f"Knowledge graph search failed: {exc}")
                logger.warning("KG search failed: %s", exc)

        # 3. Rank and deduplicate
        ranked_hits = cls._rank_hits(all_hits, config)

        # 4. Limit to top_k
        ranked_hits = ranked_hits[: config.top_k]

        duration = round(time.time() - start_time, 3)

        return RetrievalResult(
            query=query,
            hits=ranked_hits,
            total_hits=len(ranked_hits),
            duration_seconds=duration,
            sources_queried=sources_queried,
            warnings=warnings,
        )

    @classmethod
    def search_semantic(
        cls,
        query_embedding: list[float],
        k: int = 10,
        config: RAGConfig | None = None,
        filters: dict | None = None,
    ) -> list[RetrievalHit]:
        """ChromaDB-only semantic search."""
        if config is None:
            config = RAGConfig.from_settings()
        return cls._search_chromadb(query_embedding, config, filters, k=k)

    @classmethod
    def search_knowledge_graph(
        cls,
        query: str,
        entity_type: str | None = None,
    ) -> list[RetrievalHit]:
        """Knowledge-graph-only entity search."""
        from knowledge_graph.service import KnowledgeGraphService

        entities = KnowledgeGraphService.search_entities(query, entity_type)
        hits = []
        for entity in entities:
            hits.append(RetrievalHit(
                source="knowledge_graph",
                content=f"{entity.get('entity_type', '')}: {entity.get('name', '')}",
                score=entity.get("confidence", 0.5),
                entity_id=entity.get("entity_id", ""),
                metadata=entity,
            ))
        return hits

    @classmethod
    def search_drawings(
        cls,
        query: str = "",
        drawing_type: str | None = None,
        equipment: str | None = None,
    ) -> list[RetrievalHit]:
        """Drawing-specific search via Knowledge Graph."""
        from knowledge_graph.service import KnowledgeGraphService

        hits = []

        if equipment:
            entities = KnowledgeGraphService.search_entities(equipment)
            for entity in entities:
                source_docs = entity.get("source_document_ids", [])
                meta = entity.get("metadata", {})
                if meta.get("source") == "drawing_analysis" or meta.get("drawing_type"):
                    hits.append(RetrievalHit(
                        source="knowledge_graph",
                        content=f"Drawing equipment: {entity.get('name', '')}",
                        score=entity.get("confidence", 0.5),
                        entity_id=entity.get("entity_id", ""),
                        document_id=source_docs[0] if source_docs else "",
                        metadata=entity,
                    ))

        if query:
            entities = KnowledgeGraphService.search_entities(query)
            for entity in entities:
                meta = entity.get("metadata", {})
                if drawing_type and meta.get("drawing_type") != drawing_type:
                    continue
                hits.append(RetrievalHit(
                    source="knowledge_graph",
                    content=f"{entity.get('entity_type', '')}: {entity.get('name', '')}",
                    score=entity.get("confidence", 0.5),
                    entity_id=entity.get("entity_id", ""),
                    metadata=entity,
                ))

        return hits

    @classmethod
    def _search_chromadb(
        cls,
        query_embedding: list[float],
        config: RAGConfig,
        filters: dict | None = None,
        k: int | None = None,
    ) -> list[RetrievalHit]:
        """Queries ChromaDB and converts results to RetrievalHits."""
        from rag.vectorstore.service import VectorStoreService

        search_result = VectorStoreService.search(
            query_embedding=query_embedding,
            k=k or config.top_k,
            where=filters,
        )

        hits = []
        for hit in search_result.hits:
            hits.append(RetrievalHit(
                source="chromadb",
                content=hit.text,
                score=hit.score,
                document_id=hit.document_id,
                chunk_id=hit.chunk_id,
                metadata=hit.metadata,
            ))
        return hits

    @classmethod
    def _search_knowledge_graph(
        cls, query: str, config: RAGConfig
    ) -> list[RetrievalHit]:
        """Queries the Knowledge Graph and converts results to RetrievalHits."""
        from knowledge_graph.service import KnowledgeGraphService

        # Try full query first
        entities = KnowledgeGraphService.search_entities(query)

        # If no results, try individual keywords (3+ chars, not stopwords)
        if not entities:
            stopwords = {
                "the", "is", "in", "at", "on", "for", "to", "of", "and",
                "or", "a", "an", "what", "where", "how", "when", "why",
                "who", "which", "are", "was", "were", "has", "have", "do",
                "does", "did", "can", "could", "would", "should", "will",
                "this", "that", "these", "those", "it", "its", "with",
                "from", "about", "into", "been", "being", "not", "me",
                "my", "show", "tell", "find", "get",
            }
            keywords = [
                w for w in query.split()
                if len(w) >= 3 and w.lower().strip("?.,!") not in stopwords
            ]
            seen_ids: set[str] = set()
            for keyword in keywords[:5]:
                keyword_clean = keyword.strip("?.,!")
                found = KnowledgeGraphService.search_entities(keyword_clean)
                for entity in found:
                    eid = entity.get("entity_id", "")
                    if eid not in seen_ids:
                        seen_ids.add(eid)
                        entities.append(entity)

        hits = []
        for entity in entities[:config.top_k]:
            # Get relationships for context
            related = KnowledgeGraphService.get_related_entities(
                entity.get("entity_id", "")
            )
            related_names = [r.get("name", "") for r in related[:5]]

            content_parts = [
                f"{entity.get('entity_type', '')}: {entity.get('name', '')}"
            ]
            if related_names:
                content_parts.append(f"Related: {', '.join(related_names)}")

            hits.append(RetrievalHit(
                source="knowledge_graph",
                content=" | ".join(content_parts),
                score=entity.get("confidence", 0.5),
                entity_id=entity.get("entity_id", ""),
                document_id=(
                    entity.get("source_document_ids", [""])[0]
                    if entity.get("source_document_ids") else ""
                ),
                metadata=entity,
            ))

        return hits

    @classmethod
    def _rank_hits(
        cls, hits: list[RetrievalHit], config: RAGConfig
    ) -> list[RetrievalHit]:
        """Ranks and deduplicates hits using configurable weights."""
        seen_content: set[str] = set()
        unique_hits: list[RetrievalHit] = []

        for hit in hits:
            content_key = hit.content[:100].lower().strip()
            if content_key and content_key in seen_content:
                continue
            if content_key:
                seen_content.add(content_key)
            unique_hits.append(hit)

        # Apply source-based weighting
        for hit in unique_hits:
            if hit.source == "chromadb":
                hit.score *= config.weight_semantic / 0.4  # normalize
            elif hit.source == "knowledge_graph":
                hit.score *= config.weight_graph / 0.25

        # Sort by score descending
        unique_hits.sort(key=lambda h: h.score, reverse=True)
        return unique_hits
