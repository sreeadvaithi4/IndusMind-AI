"""
ChromaDB Vector Store module for IndusMind AI.

Persists embedding vectors and chunk metadata into ChromaDB for semantic
search. Consumes `EmbeddingResult` from the Embedding Generator module
and provides a search interface returning ranked chunks with similarity
scores.
"""
