"""
Standardized search result types for the Vector Store module.

`SearchResult` is the contract between the Vector Store and the future
RAG retrieval chain — each `SearchHit` carries everything needed for
retrieval-augmented generation without a database round-trip.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SearchHit:
    """
    A single search result from ChromaDB.

    Attributes:
        chunk_id: The chunk identifier stored in ChromaDB.
        document_id: The owning document's UUID (string).
        text: The chunk text (stored as the document in ChromaDB).
        score: Similarity/distance score from ChromaDB (lower = more similar
            for cosine distance). Normalized to 0–1 range where higher = better
            for consumer convenience.
        metadata: Full metadata dict stored alongside the vector.
    """

    chunk_id: str
    document_id: str
    text: str
    score: float
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "text": self.text,
            "score": self.score,
            "metadata": self.metadata,
        }


@dataclass
class SearchResult:
    """
    Complete search response from the Vector Store.

    Attributes:
        query: The original query text.
        hits: Ranked list of SearchHit objects.
        total_hits: Number of results returned.
        search_time_seconds: Time taken for the search operation.
        collection_name: ChromaDB collection searched.
    """

    query: str
    hits: list[SearchHit] = field(default_factory=list)
    total_hits: int = 0
    search_time_seconds: float = 0.0
    collection_name: str = ""

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "hits": [hit.to_dict() for hit in self.hits],
            "total_hits": self.total_hits,
            "search_time_seconds": self.search_time_seconds,
            "collection_name": self.collection_name,
        }


@dataclass
class IndexingResult:
    """
    Result of indexing embeddings into ChromaDB.

    Attributes:
        document_id: The document whose chunks were indexed.
        total_indexed: Number of vectors successfully stored.
        total_skipped: Number of vectors skipped (e.g. failed embeddings).
        collection_name: ChromaDB collection used.
        duration_seconds: Time taken for the indexing operation.
        warnings: Any non-fatal issues encountered.
    """

    document_id: str
    total_indexed: int = 0
    total_skipped: int = 0
    collection_name: str = ""
    duration_seconds: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "document_id": self.document_id,
            "total_indexed": self.total_indexed,
            "total_skipped": self.total_skipped,
            "collection_name": self.collection_name,
            "duration_seconds": self.duration_seconds,
            "warnings": self.warnings,
        }


@dataclass
class CollectionStats:
    """Statistics for a ChromaDB collection."""

    collection_name: str
    total_vectors: int = 0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "collection_name": self.collection_name,
            "total_vectors": self.total_vectors,
            "metadata": self.metadata,
        }
