# IndusMind AI — Architecture

This document describes the system architecture of IndusMind AI as it
exists today. For a prompt-by-prompt development history and detailed
extension-point notes, see [`PROJECT_CONTEXT.md`](../PROJECT_CONTEXT.md)
at the project root — that file is the authoritative, continuously
updated project memory. This document is a human-oriented architectural
reference derived from it.

## 1. System Overview

IndusMind AI is a Django-based enterprise industrial intelligence
platform. Its long-term purpose is to let users upload industrial
documents (manuals, inspection reports, maintenance logs, spreadsheets)
and query them through AI-powered search, a knowledge graph, and a
chat interface.

As of the current build, the platform implements the **complete document
ingestion pipeline, RAG retrieval system, AI chat interface, persistent
conversation history, Maintenance Intelligence, Quality/Compliance
Intelligence, Operations Intelligence with multi-agent orchestration,
Executive AI Briefing, and an Operations Command Center dashboard**.
The remaining work is authentication UI and production deployment.

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ Presentation Layer                                               │
│  apps/landing (marketing site) · apps/dashboard (workspace UI)   │
│  Upload Workspace + AI Copilot Chat (/dashboard/chat/)            │
│  Django Templates + Tailwind CSS + GSAP + JS fetch → /api/query/  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ API Layer                                                         │
│  apps/documents — document CRUD + ingestion pipeline trigger       │
│  api/ — search (semantic, KG, drawings) + hybrid RAG query         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Document Persistence & Orchestration Layer (apps/documents)        │
│  Document model (status machine) · DocumentUploadService ·         │
│  DocumentStatusService · DocumentStorageService ·                   │
│  DocumentProcessingService (orchestrates every pipeline stage)      │
└─────────────────────────────────────────────────────────────────┘
            │                    │                     │
            ▼                    ▼                     ▼
┌──────────────────────┐ ┌──────────────────────┐ ┌──────────────────────┐
│ Ingestion: Parser     │ │ Ingestion: Chunker    │ │ Intelligence:         │
│  ingestion/            │ │  ingestion/chunking/   │ │  Embedding Generator  │
│  BaseParser + Registry  │ │  Header/recursive/     │ │  rag/embeddings/       │
│  PDF/DOCX/TXT/CSV/XLSX  │ │  table strategies      │ │  Google Gemini via     │
│  Optional OCR fallback   │ │  ChunkCollection       │ │  LangChain             │
│  → ParsedDocument        │ │  (consumes             │ │  EmbeddingResult       │
│                           │ │   ParsedDocument)      │ │  (consumes             │
│                           │ │                         │ │   ChunkCollection)     │
└──────────────────────┘ └──────────────────────┘ └──────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Intelligence: ChromaDB Vector Store                                │
│  rag/vectorstore/ — persists embeddings, semantic search,          │
│  metadata filtering, document deletion, collection management       │
│  (consumes EmbeddingResult)                                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Intelligence: Knowledge Graph                                      │
│  knowledge_graph/ — pattern-based entity extraction, NetworkX        │
│  graph (nodes=entities, edges=relationships), search, traversal,     │
│  document cleanup (consumes ParsedDocument.text)                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Intelligence: Computer Vision / Drawing Analysis                    │
│  vision/ — drawing classification, enhanced OCR extraction,          │
│  symbol detection (20+ types), equipment + relationship extraction,   │
│  integrated with Knowledge Graph (consumes ParsedDocument.text)        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Application Layer: Hybrid RAG Pipeline + Orchestrator               │
│  agents/ — query intent detection, hybrid retrieval (ChromaDB +      │
│  KG + metadata), ranking, context building with citations,            │
│  Google Gemini LLM, session memory                                     │
│  api/ — REST endpoints for search + query                               │
└─────────────────────────────────────────────────────────────────┘
```

## 3. Django App Structure

| App | Purpose | Status |
|---|---|---|
| `apps.landing` | Public marketing site: hero, features, how-it-works, industries, stats, CTA | Implemented |
| `apps.dashboard` | Authenticated workspace shell: sidebar, topbar, overview metrics, and the Upload Workspace page | Implemented (overview uses static demo data; Upload Workspace is wired to the real API) |
| `apps.documents` | Document model, REST API, and pipeline orchestration (`DocumentProcessingService`) | Implemented — full pipeline through INDEXED |

No custom user/auth app exists yet — `apps.documents` uses Django's
built-in `auth.User` model and `IsAuthenticated`/session authentication.

## 4. The Document Pipeline

`Document.status` (a `TextChoices` state machine defined in
`apps/documents/models.py`) is the single source of truth for where a
document is in the pipeline:

```
UPLOADED → VALIDATING → STORED → READY_FOR_PARSING
    → PARSING → PARSED                    (Parser — implemented)
    → CHUNKING → CHUNKED                   (Chunker — implemented)
    → EMBEDDING → EMBEDDED                  (Embedding Generator — implemented)
    → INDEXING_VECTOR_DB → VECTOR_INDEXED    (ChromaDB — implemented)
    → INDEXING_KNOWLEDGE_GRAPH → INDEXED      (Knowledge Graph — implemented)

FAILED  (terminal, reachable from any stage, always carries error_message)
```

Every transition goes through `DocumentStatusService.transition()`,
which keeps `status`, `processing_stage`, and `processing_percentage`
consistent, so no code outside that service ever sets `document.status`
directly.

### 4.1 Upload → Storage

`POST /api/documents/upload/` → `DocumentUploadService.upload()`:
validates extension/size (`apps/documents/validators.py`), sanitizes
the filename and builds a date-partitioned storage path
(`apps/documents/storage.py`), saves the file, and creates the
`Document` row at `READY_FOR_PARSING`.

### 4.2 Parsing

`POST /api/documents/{id}/parse/` → `DocumentProcessingService.run_parser()`
→ `ingestion.service.DocumentParserService.parse_document()`:

- `ingestion/base.py` defines `BaseParser` (interface) and
  `ParserRegistry` (a factory keyed by file extension).
- `ingestion/parsers/` contains one module per format: `pdf_parser.py`
  (PyMuPDF, with optional Tesseract+pdf2image OCR fallback for
  scanned pages), `docx_parser.py` (python-docx; also registers a
  `DocParser` for legacy `.doc` that intentionally raises a clear
  "not supported" error, since no approved dependency can parse it),
  `txt_parser.py` (chardet-based encoding detection),
  `csv_parser.py`/`xlsx_parser.py` (pandas/openpyxl).
- Every parser returns a standardized `ParsedDocument`
  (`ingestion/result.py`): `text`, `metadata` (title, author, dates,
  language, page count, parser used, OCR used, timing),
  `tables`, `images`, `ocr`, `processing`.
- A summary is persisted to `Document.parser_metadata`
  (`JSONField`) and `Document.page_count`; the full `ParsedDocument`
  (including text) stays in memory and is handed directly to the
  Chunker within the same request.

### 4.3 Chunking

Immediately follows parsing within the same `POST .../parse/` request
→ `DocumentProcessingService.run_chunker()` →
`ingestion.chunking.service.DocumentChunkerService.chunk_document()`:

- `ingestion/chunking/strategies/header_aware.py` splits the parsed
  text into sections using heading-shape heuristics (markdown `#`,
  numbered headings, short all-caps lines).
- `ingestion/chunking/strategies/recursive.py` is the primary text
  splitter: paragraph boundaries first, falling back to sentence
  boundaries (`strategies/sentence.py`), falling back to a hard
  character split for any single unbroken block of text — with
  configurable chunk size and overlap (`ingestion/chunking/config.py`,
  overridable via `CHUNKING_*` environment variables).
- `ingestion/chunking/strategies/table.py` chunks tables entirely
  separately from prose, repeating the header row in every resulting
  piece if a table is split across multiple chunks.
- Output is a standardized `ChunkCollection`
  (`ingestion/chunking/result.py`): a list of `Chunk` objects, each
  with `chunk_id`, `text`, `chunk_type` (text/table), `metadata`
  (document id, filename, parser used, OCR used, chunk number, total
  chunks, section, source type), word/character counts, and
  `page_number`/`section_title`.
- A summary is persisted to `Document.chunker_metadata`,
  `Document.chunk_count`, and `Document.chunking_time_seconds`; the
  full `ChunkCollection` stays in memory, ready for the future
  Embedding Generator to consume directly.

**Known limitation:** `Chunk.page_number` is always `None`. The Parser's
`ParsedDocument.text` has no embedded per-page offsets for any format,
so the Chunker cannot attribute a chunk to a specific page without a
(deliberately out-of-scope) change to the Parser's output contract.
Section titles ARE populated, since they can be derived from the text
alone.

### 4.4 Embedding Generation

Immediately follows chunking within the same `POST .../parse/` request
→ `DocumentProcessingService.run_embedding_generator()` →
`rag.embeddings.service.EmbeddingGeneratorService.generate_embeddings()`:

- `rag/embeddings/config.py` defines `EmbeddingConfig` (model name,
  API key, batch size, max retries, timeout, max concurrent requests,
  max chunk text length) — all environment-variable-driven via
  Django settings.
- `rag/embeddings/validators.py` validates the input
  `ChunkCollection` (non-None, non-empty, has a document ID) and
  individual chunks (non-empty text, valid chunk ID).
- `rag/embeddings/service.py` is the core service: batches chunks,
  detects duplicates via SHA-256 checksum, calls
  `GoogleGenerativeAIEmbeddings.embed_documents()` with retry +
  exponential backoff for transient errors, classifies exceptions
  (auth → stop, rate limit → extended backoff, timeout/network →
  standard backoff), skips empty/duplicate chunks, and truncates
  oversized ones.
- Output is a standardized `EmbeddingResult`
  (`rag/embeddings/result.py`): a list of `ChunkEmbedding` objects,
  each with `chunk_id`, `embedding` (dense vector), `embedding_model`,
  `embedding_dimension`, `embedding_timestamp`, `checksum`, `status`
  (success/failed/skipped), `error_message`, and `metadata` (original
  chunk metadata passed through).
- A summary is persisted to `Document.embedding_metadata` and
  `Document.embedding_status`; the full `EmbeddingResult` stays in
  memory, ready for the future `store_in_vector_db` to consume
  directly.

### 4.5 Vector Storage (ChromaDB)

Immediately follows embedding within the same `POST .../parse/` request
→ `DocumentProcessingService.store_in_vector_db()` →
`rag.vectorstore.service.VectorStoreService.index_embeddings()`:

- `rag/vectorstore/config.py` defines `VectorStoreConfig` (persist
  directory, collection name, batch size, search K, similarity
  threshold, max results) — all environment-variable-driven.
- `rag/vectorstore/service.py` is the core service: validates input,
  filters to successful embeddings only, builds ChromaDB-compatible
  metadata (flattened, no None values), upserts in batches,
  provides semantic search with metadata filtering, and manages
  document deletion.
- Uses ChromaDB's `PersistentClient` with connection pooling (cached
  per persist directory). Collections use cosine distance metric.
- Automatic cleanup: document deletion (via Django `post_delete`
  signal) removes associated vectors from ChromaDB.

### 4.6 Knowledge Graph (Entity Extraction + NetworkX)

Immediately follows vector storage within the same `POST .../parse/`
request → `DocumentProcessingService.update_knowledge_graph()` →
`knowledge_graph.service.KnowledgeGraphService.process_document()`:

- `knowledge_graph/config.py` defines `KnowledgeGraphConfig` (confidence
  thresholds, entity/relationship type lists, max counts, dedup flag).
- `knowledge_graph/extractor.py` performs pattern-based entity and
  relationship extraction using compiled regex patterns for 30+ entity
  types and 20+ relationship types.
- `knowledge_graph/graph.py` is the NetworkX-backed graph service: adds
  nodes (entities) and edges (relationships), supports merge/dedup,
  search, traversal, deletion, and statistics.
- Automatic cleanup: document deletion removes associated graph nodes
  via `KnowledgeGraphService.delete_document()`.

### 4.7 Hybrid RAG Pipeline (Query → Response)

`POST /api/query/` → `QueryOrchestrator.process_query()`:

1. **Intent detection** — pattern-based classification (8 intents:
   equipment_lookup, maintenance, compliance, drawing_lookup,
   document_lookup, incident_lookup, knowledge_search, general_question).
2. **Hybrid retrieval** — `RAGRetrievalService.retrieve()` queries
   ChromaDB (semantic) + Knowledge Graph (keyword-fallback) in parallel,
   merges, ranks, and deduplicates.
3. **Context building** — `ContextBuilder.build()` constructs a prompt
   with [Source N] labels, citations, conversation history, and token-
   limit enforcement.
4. **LLM generation** — `GeminiService.generate()` calls Google Gemini
   with retries and timeout handling (or falls back to retrieval-only
   answer if no API key).
5. **Response** — structured JSON with answer, confidence, citations,
   related documents/equipment, KG references, drawing references,
   and suggested follow-up questions.

Document deletion automatically cleans up stored files, ChromaDB
vectors, and Knowledge Graph entities via three `post_delete` signals.

### 4.8 Beyond RAG (not yet implemented)

The remaining work is a chat UI frontend consuming `/api/query/`,
persistent chat history, and production deployment.

## 5. Cross-Cutting Concerns

- **Configuration**: `backend/config/settings.py`, entirely
  environment-variable-driven via `django-environ` (12-factor). SQLite
  in development; switches to PostgreSQL via `DATABASE_URL` with no
  code change.
- **Storage**: local filesystem via Django's `FileSystemStorage` in
  development; `MEDIA_ROOT`/`MEDIA_URL` configured for production
  behind WhiteNoise or a proper media host.
- **Security**: extension allowlist + max-size validation, filename
  sanitization (path-traversal-safe), `IsAuthenticated` +
  object-level ownership checks (`IsDocumentOwnerOrReadOnlyForStaff`)
  on every document endpoint, CSRF-protected client-side API calls
  (`ensure_csrf_cookie` on pages that call the API via fetch/XHR).
- **Testing**: 528 passing Django tests across all modules.
- **No task queue yet**: the pipeline runs synchronously inside the
  request that calls `POST /api/documents/{id}/parse/`. The service
  layer is structured so each stage can be wrapped in a Celery task
  later without changing its method contracts, but Celery/Redis are
  not installed or configured.

## 6. What Is Not Yet Implemented

- Authentication UI (login/logout) — use Django admin to obtain sessions.
- Legacy `.doc` parsing.
- Celery/Redis-based asynchronous pipeline execution.
- Production deployment configuration (Docker, gunicorn, PostgreSQL).

See `PROJECT_CONTEXT.md` §5–6 for the complete, continuously maintained
completed/pending module tables.
