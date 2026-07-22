"""
Embedding Generator module for IndusMind AI.

Generates vector embeddings for document chunks using Google Gemini
Embedding API via LangChain. Consumes `ChunkCollection` from the
Chunker module and produces `EmbeddingResult` objects suitable for
downstream vector storage (ChromaDB) integration.
"""
