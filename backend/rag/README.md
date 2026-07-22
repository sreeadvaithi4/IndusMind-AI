# rag/

Retrieval-Augmented Generation logic for IndusMind AI.

## Implemented

### `embeddings/` — Embedding Generator (Sprint 7)

Generates vector embeddings for document chunks using the Google Gemini
Embedding API via LangChain's `GoogleGenerativeAIEmbeddings`.

**Features:**
- Batch embedding with configurable batch size
- Retry with exponential backoff for transient failures
- Rate limit handling (429 detection + extended backoff)
- Timeout handling (per-request configurable timeout)
- Progress tracking via structured logging
- Input validation (empty/oversized chunk detection)
- Duplicate protection (SHA-256 checksum per chunk)
- Metadata preservation (original chunk metadata carried through)

**Entry point:** `rag.embeddings.service.EmbeddingGeneratorService.generate_embeddings(chunk_collection)`

**Input:** `ingestion.chunking.result.ChunkCollection`  
**Output:** `rag.embeddings.result.EmbeddingResult`

## Reserved for Future

- ChromaDB vector store integration
- Retrieval chains
- Prompt construction for Google Gemini via LangChain
