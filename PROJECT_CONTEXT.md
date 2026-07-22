# PROJECT_CONTEXT.md

This file is the persistent memory for the IndusMind AI project. It is
updated at the end of every development phase and must be treated as the
source of truth for project state across sessions/prompts.

---

## 1. Project Name

**IndusMind AI** — Enterprise Industrial Intelligence Platform powered by AI.

## 2. Technology Stack

### Frontend
- Django Templates
- HTML5
- Tailwind CSS
- JavaScript (ES6)
- GSAP (animation)
- Lottie (animation)
- Chart.js (data visualization)

### Backend
- Django 5.x
- Django REST Framework

### AI
- LangChain
- Google Gemini (via `langchain-google-genai` / `google-generativeai`)

### Vector Database
- ChromaDB (persisted locally, path configured via `CHROMA_PERSIST_DIRECTORY`)

### Knowledge Graph
- NetworkX

### Database
- SQLite (development default)
- PostgreSQL (production-ready — swap in via `DATABASE_URL` env var, no code changes needed)

### OCR
- Tesseract OCR (via `pytesseract`)
- `pdf2image` (rasterizes PDF pages for OCR)
- Optional and configurable: gated by `settings.OCR_ENABLED`, and only
  ever invoked as a fallback when direct PDF text extraction yields
  suspiciously little text — see `ingestion/ocr.py`.

### Document Processing
- PyMuPDF (PDF parsing)
- python-docx (Word document parsing — .docx only, see Sprint 5 notes on legacy .doc)
- pandas (tabular data / spreadsheet parsing)
- openpyxl (XLSX engine used by pandas)
- chardet (text encoding detection)
- langdetect (best-effort language detection, optional/soft dependency)

### Infrastructure / Utilities
- django-environ (environment variable management)
- whitenoise (static file serving in production)
- django-cors-headers (CORS)
- gunicorn (production WSGI server)
- pytest + pytest-django (testing)

### Celery / Redis readiness
- Not yet installed or configured. `apps.documents.services.DocumentProcessingService`
  is structured as a plain synchronous orchestration class today
  specifically so it can be wrapped in Celery tasks later without
  changing its method contracts.

### Embedding Generator Configuration
- All values overridable via `EMBEDDING_MODEL_NAME`,
  `EMBEDDING_BATCH_SIZE`, `EMBEDDING_MAX_RETRIES`,
  `EMBEDDING_TIMEOUT_SECONDS`, `EMBEDDING_MAX_CONCURRENT_REQUESTS`,
  `EMBEDDING_MAX_CHUNK_TEXT_LENGTH` environment variables — see
  `rag/embeddings/config.py:EmbeddingConfig`.

### Document Chunking Configuration
- All values overridable via `CHUNKING_CHUNK_SIZE`,
  `CHUNKING_CHUNK_OVERLAP`, `CHUNKING_MAX_CHUNK_LENGTH`,
  `CHUNKING_MIN_CHUNK_LENGTH` environment variables — see
  `ingestion/chunking/config.py:ChunkingConfig`.

## 3. Folder Structure

```
indusmind-ai/
├── backend/
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings.py       # All env-driven Django settings
│   │   ├── urls.py           # Root URLconf (admin + landing page registered)
│   │   ├── wsgi.py
│   │   └── asgi.py
│   ├── apps/
│   │   ├── __init__.py
│   │   ├── landing/            # Marketing landing page app (implemented)
│   │   │   ├── __init__.py
│   │   │   ├── apps.py
│   │   │   ├── urls.py
│   │   │   ├── views.py
│   │   │   └── templates/landing/
│   │   │       ├── base.html
│   │   │       ├── index.html
│   │   │       └── partials/     # navbar, hero, features, how_it_works,
│   │   │                          # industries, stats, cta, footer, _icon
│   │   ├── dashboard/           # Enterprise dashboard app (implemented)
│   │   │   ├── __init__.py
│   │   │   ├── apps.py
│   │   │   ├── urls.py
│   │   │   ├── views.py
│   │   │   └── templates/dashboard/
│   │   │       ├── base.html
│   │   │       ├── overview.html
│   │   │       ├── upload_workspace.html   # Rebuilt Sprint 4: full Upload
│   │   │       │                            # Workspace UI wired to apps.documents API
│   │   │       ├── partials/      # sidebar, topbar, welcome, summary_cards,
│   │   │       │                   # recent_documents, processing_status,
│   │   │       │                   # activity_feed, right_panel,
│   │   │       │                   # upload_dropzone, upload_queue,
│   │   │       │                   # upload_processing, upload_documents_table,
│   │   │       │                   # upload_sidebar_panel
│   │   │       └── components/     # dashboard_card, status_badge (extended
│   │   │                            # with uploaded/stored/validating/
│   │   │                            # ready_for_parsing/queued/deleted
│   │   │                            # variants), sidebar_item, nav_item,
│   │   │                            # metric_card, progress_widget, section_header
│   │   └── documents/           # Document Management app (implemented)
│   │       ├── __init__.py
│   │       ├── apps.py
│   │       ├── admin.py
│   │       ├── models.py           # Document model (UUID PK, full pipeline
│   │       │                        # status/stage/percentage, parser_metadata
│   │       │                        # JSONField (Sprint 5), chunk_count/
│   │       │                        # chunking_time_seconds/chunker_metadata
│   │       │                        # (Sprint 6), embedding_status/
│   │       │                        # embedding_metadata (Sprint 7)/
│   │       │                        # knowledge_graph_status)
│   │       ├── validators.py        # extension/size/filename-sanitization/duplicate checks
│   │       ├── storage.py            # secure, date-partitioned upload path builder
│   │       ├── services.py            # DocumentUploadService, DocumentStatusService,
│   │       │                           # DocumentStorageService (implemented) +
│   │       │                           # DocumentProcessingService (all stages
│   │       │                           # implemented: run_parser (Sprint 5),
│   │       │                           # run_chunker (Sprint 6),
│   │       │                           # run_embedding_generator (Sprint 7),
│   │       │                           # store_in_vector_db (Sprint 8),
│   │       │                           # update_knowledge_graph (Sprint 9))
│   │       ├── permissions.py          # IsAuthenticatedForDocumentAccess,
│   │       │                            # IsDocumentOwnerOrReadOnlyForStaff
│   │       ├── signals.py               # post_delete: file cleanup + ChromaDB vector
│   │       │                            # cleanup + Knowledge Graph entity cleanup
│   │       ├── serializers.py            # upload/list/detail/supported-formats
│   │       │                              # serializers (detail adds
│   │       │                              # parser_metadata (Sprint 5),
│   │       │                              # chunker_metadata/chunking_time_seconds
│   │       │                              # (Sprint 6), embedding_metadata
│   │       │                              # (Sprint 7))
│   │       ├── views.py                   # REST API views (service-layer only);
│   │       │                               # DocumentParseView (Sprint 5) now
│   │       │                               # auto-chains Parser -> Chunker (Sprint 6)
│   │       ├── urls.py                     # includes <id>/parse/ (Sprint 5)
│   │       ├── migrations/                  # 0001_initial (Document model),
│   │       │                                 # 0002_document_parser_metadata (Sprint 5),
│   │       │                                 # 0003_document_chunker_fields (Sprint 6),
│   │       │                                 # 0004_document_embedding_metadata (Sprint 7),
│   │       │                                 # 0005_update_embedding_status_help_text (Sprint 7)
│   │       └── tests/                        # test_models, test_validators,
│   │                                          # test_services, test_api,
│   │                                          # test_parser_integration,
│   │                                          # test_parse_api (Sprint 5),
│   │                                          # test_chunker_integration (Sprint 6),
│   │                                          # test_embedding_integration (Sprint 7) —
│   │                                          # 83 tests total in this app
│   ├── templates/
│   │   └── shared/_icon.html    # Cross-app Heroicons partial (implemented)
│   ├── api/                  # Search & Query REST API (Sprint 11):
│   │   ├── __init__.py        # semantic search, KG search, drawing search,
│   │   ├── views.py            # hybrid RAG query endpoints
│   │   └── urls.py             # /api/search/*, /api/query/
│   ├── agents/                # Hybrid RAG Pipeline + Orchestrator (Sprint 11)
│   │   ├── __init__.py
│   │   ├── exceptions.py       # AgentError hierarchy
│   │   ├── config.py            # RAGConfig (top_k, LLM model, weights, etc.)
│   │   ├── retrieval/           # RAGRetrievalService — hybrid search
│   │   │                         # (ChromaDB + KG + metadata, keyword fallback,
│   │   │                         # ranking, dedup)
│   │   ├── llm/                  # GeminiService — Google Gemini LLM integration
│   │   │                          # (retries, timeout, rate-limit handling)
│   │   ├── orchestrator/          # QueryOrchestrator — intent detection,
│   │   │                           # strategy selection, full pipeline
│   │   ├── context/                # ContextBuilder — prompt construction,
│   │   │                            # citations, token limits
│   │   ├── memory/                  # ConversationMemory — session-level
│   │   │                             # in-memory conversation history
│   │   └── tests/                    # 40 tests: config, intent, retrieval,
│   │                                  # context, memory, LLM, orchestrator, API
│   ├── ingestion/              # Document Parser (Sprint 5) + Chunker (Sprint 6) modules
│   │   ├── __init__.py
│   │   ├── exceptions.py        # ParserError hierarchy
│   │   ├── result.py             # ParsedDocument / DocumentMetadata / OcrInfo / ProcessingInfo
│   │   ├── base.py                # BaseParser interface + ParserRegistry (factory backing store)
│   │   ├── factory.py              # get_parser_for_extension() — public factory function
│   │   ├── validators.py            # pre-parse checks (file exists, non-empty)
│   │   ├── utils.py                  # char/word counts, language detection, encoding-aware decode
│   │   ├── ocr.py                     # optional/configurable OCR fallback (Tesseract + pdf2image)
│   │   ├── service.py                  # DocumentParserService — entry point run_parser() calls
│   │   ├── parsers/                     # pdf_parser, docx_parser (+ DocParser for legacy .doc,
│   │   │                                 # which intentionally raises "not supported"), txt_parser,
│   │   │                                 # csv_parser, xlsx_parser — each self-registers via
│   │   │                                 # @ParserRegistry.register
│   │   ├── tests/                        # 69 tests: per-parser, factory, OCR fallback logic
│   │   │                                   # (mocked — no Tesseract binary required), validators/utils
│   │   └── chunking/                       # Document Chunker module (IMPLEMENTED Sprint 6)
│   │       ├── __init__.py
│   │       ├── exceptions.py                # ChunkingError hierarchy
│   │       ├── config.py                     # ChunkingConfig (chunk_size/overlap/min/max length,
│   │       │                                  # env-driven via CHUNKING_* settings)
│   │       ├── result.py                      # Chunk / ChunkMetadata / ChunkCollection / ChunkType
│   │       ├── validators.py                   # pre-chunk checks (non-empty, well-formed tables)
│   │       ├── service.py                       # DocumentChunkerService — entry point
│   │       │                                     # run_chunker() calls; consumes ParsedDocument
│   │       │                                     # directly and unmodified
│   │       ├── strategies/                       # header_aware (section detection),
│   │       │                                      # recursive (primary text splitter: paragraph
│   │       │                                      # -> sentence -> hard-split fallback),
│   │       │                                      # sentence (regex sentence boundaries),
│   │       │                                      # table (tables always chunked separately,
│   │       │                                      # header repeated in every resulting chunk)
│   │       └── tests/                             # 62 tests: every strategy, config validation,
│   │                                                # small/large/table/OCR/empty/invalid-input
│   ├── rag/                     # RAG pipeline — Embedding Generator implemented (Sprint 7)
│   │   ├── __init__.py
│   │   ├── README.md
│   │   └── embeddings/           # Embedding Generator module (IMPLEMENTED Sprint 7)
│   │       ├── __init__.py
│   │       ├── exceptions.py       # EmbeddingError hierarchy
│   │       ├── config.py            # EmbeddingConfig (model/batch_size/retries/timeout,
│   │       │                         # env-driven via EMBEDDING_* settings)
│   │       ├── result.py             # ChunkEmbedding / EmbeddingProcessingInfo / EmbeddingResult
│   │       ├── validators.py          # pre-embed checks (non-empty, well-formed collection)
│   │       ├── service.py              # EmbeddingGeneratorService — entry point
│   │       │                            # generate_embeddings() calls; consumes ChunkCollection
│   │       │                            # directly and unmodified
│   │       └── tests/                   # 40 tests: config, validation, batch, retry,
│   │                                     # rate-limit, timeout, auth, progress, serialization
│   ├── knowledge_graph/           # NetworkX graph logic (package scaffolded, empty) —
│   │                               # future implementation plugs into the same service
│   ├── tools/                      # LangChain tools (package scaffolded, empty)
│   ├── static/
│   │   ├── css/
│   │   │   ├── design-system.css   # Design tokens + reusable primitives (implemented)
│   │   │   ├── landing.css          # Landing-page-specific styles (implemented)
│   │   │   ├── dashboard.css         # Dashboard shell, sidebar, table, pipeline, dark mode (implemented)
│   │   │   └── upload-workspace.css   # Upload Workspace layout, dropzone, queue,
│   │   │                               # table toolbar, sidebar panel (Sprint 4)
│   │   ├── js/
│   │   │   ├── navbar.js             # Sticky navbar scroll state + mobile menu (implemented)
│   │   │   ├── gsap-animations.js     # Landing page scroll-triggered animations (implemented)
│   │   │   ├── counters.js             # Animated numeric counters — shared by landing & dashboard (implemented)
│   │   │   ├── ui-interactions.js       # Button ripple effect — shared by landing & dashboard (implemented)
│   │   │   ├── dashboard-sidebar.js      # Sidebar collapse + mobile drawer (implemented)
│   │   │   ├── dashboard-animations.js    # Dashboard entrance/progress/gauge animations
│   │   │   │                               # (implemented; reused as-is by the Upload
│   │   │   │                               # Workspace via [data-animate]/[data-gauge-fill])
│   │   │   ├── dark-mode.js                # Light/dark theme toggle (implemented)
│   │   │   └── upload-workspace.js          # Upload Workspace behavior: drag/drop,
│   │   │                                     # XHR upload progress, queue, documents
│   │   │                                     # table (search/filter/sort/pagination),
│   │   │                                     # confetti (Sprint 4)
│   │   └── images/
│   ├── media/                          # User-facing media (git-ignored)
│   ├── uploads/                          # Raw ingestion uploads (git-ignored)
│   ├── tests/                             # Test suite (empty)
│   └── manage.py
├── docs/                                    # Architecture docs / ADRs (empty)
├── dataset/                                   # sample_documents/ (Parser test fixtures,
│                                                # added Sprint 5 — see dataset/README.md)
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
└── PROJECT_CONTEXT.md
```

Each reserved-for-future-use directory (`apps`, `api`, `agents`,
`ingestion`, `rag`, `knowledge_graph`, `tools`, `templates`, `static`,
`media`, `uploads`, `tests`, `docs`, `dataset`) contains a `README.md`
(and `__init__.py` where it is a Python package) stating its intended
purpose and current empty status. **Do not delete these placeholder
files** — they preserve the folder structure in git, since git does not
track empty directories.

## 4. Coding Standards

- **Clean Architecture**: strict separation of concerns between
  configuration (`config/`), ingestion, AI/RAG, knowledge graph, API, and
  presentation (`templates/`, `static/`) layers.
- **SOLID principles** applied to all class and module design.
- **No placeholders, no TODO comments** — a module is only added to the
  codebase once fully implemented. Empty foundation directories use
  README.md files to describe intent rather than stub code.
- **12-factor configuration**: all environment-specific values (secrets,
  database URL, API keys, debug flag) are read from environment variables
  via `django-environ`, never hardcoded.
- **Production-ready by default**: SQLite for local development,
  PostgreSQL for production, switched purely via the `DATABASE_URL`
  environment variable — no code branching by environment.
- **Conventional Commits** for all commit messages.
- Static assets are collected via Django's `collectstatic` and served
  through WhiteNoise in production.

## 5. Completed Modules

| Module | Description | Status |
|---|---|---|
| Project architecture & foundation | Folder structure, Django project skeleton, settings, requirements, env config, git config | ✅ Complete |
| Landing page & design system | `apps/landing` Django app; hero, features, how-it-works, industries, stats, CTA, footer sections; sticky navbar; Heroicons; GSAP/ScrollTrigger animations; design tokens in `static/css/design-system.css` | ✅ Complete |
| Enterprise Dashboard | `apps/dashboard` Django app; collapsible sidebar, topbar (search, upload, notifications, dark mode, avatar), welcome + quick actions, 6 summary metric cards, processing pipeline widget, recent documents table, activity feed, right-panel system health; dark mode; reusable components (Dashboard Card, Metric Card, Status Badge, Progress Widget, Sidebar Item, Nav Item, Section Header); `dashboard:upload` route reserved as the real entry point for the future Upload Workspace module | ✅ Complete |
| Document Management backend foundation | `apps/documents` Django app: `Document` model + migration (UUID PK, full pipeline status/stage/percentage, chunk/embedding/knowledge-graph status fields, error tracking); secure storage layer (date-partitioned paths, filename sanitization, path-traversal-safe); validators (extension allowlist, max size, duplicate-filename check); service layer (`DocumentUploadService`, `DocumentStatusService`, `DocumentStorageService` fully implemented; `DocumentProcessingService` orchestration contract — `run_parser` and `run_chunker` are now implemented as of Sprints 5–6, `run_embedding_generator`/`store_in_vector_db`/`update_knowledge_graph` still raise `NotImplementedError`); REST API (upload, list, retrieve, delete, status, processing-status, recent, supported-formats) gated by `IsAuthenticated`/`IsDocumentOwnerOrReadOnlyForStaff`; Django admin registration; `post_delete` signal for on-disk file cleanup; 55 passing unit/API tests as originally built in Sprint 3 (see later rows for Sprint 5–6 additions to this same app) | ✅ Complete (infrastructure only — no AI) |
| Upload Workspace (frontend) | `dashboard:upload` page rebuilt (was a holding page) into a full Google-Drive/ChatGPT-style workspace: drag-and-drop dropzone (multi-file, browse, keyboard-accessible), client-side upload queue with real XHR-driven progress bars/ETA/cancel/retry, Processing Status widget (Uploading → Saving File → Ready for Parsing), Recent Documents table (search/status-filter/type-filter/sort/pagination), and a right-rail (storage usage gauge, supported formats, quick tips); GSAP entrance animations and a confetti completion celebration; fully wired to the existing `apps.documents` REST API via `static/js/upload-workspace.js` — no new backend endpoints were created. **Note:** this widget was built in Sprint 4, before the Parser (Sprint 5) and Chunker (Sprint 6) existed — it still only visualizes through "Ready for Parsing" and has not been updated to call `POST /api/documents/{id}/parse/` or display real Parsing/Chunking stage progress; see Pending Modules | ✅ Complete (frontend only — consumes upload/list/status/delete endpoints; not yet wired to parse/chunk) |
| Document Parser (`ingestion/`) | Enterprise Parser module: `BaseParser` interface + `ParserRegistry` factory; real, tested parsers for PDF (PyMuPDF — text, page count, title/author/dates, language, OCR fallback), DOCX (python-docx — paragraphs, headers/footers, tables, core properties), TXT (encoding-detected via chardet), CSV and XLSX (pandas/openpyxl — rows, columns, headers, per-column statistics); legacy `.doc` registered with a parser that raises a clear, honest "not supported by this dependency set" error rather than faking support; optional/configurable OCR fallback (Tesseract + pdf2image, gated by `OCR_ENABLED` and heuristic text-density check, degrades gracefully when dependencies/binary are absent); standardized `ParsedDocument` output (text, metadata, tables, images, ocr, processing) designed for direct consumption by the future Chunker; `DocumentProcessingService.run_parser` now fully implemented (was `NotImplementedError`), wired through a new `parser_metadata` JSONField on `Document` and a new `POST /api/documents/{id}/parse/` trigger endpoint; 69 new passing tests (parsers, factory, OCR fallback logic, validators/utils, and full Document-model integration against real sample files) | ✅ Complete (Parser only — Chunker/Embedding/ChromaDB/Knowledge Graph remain unimplemented) |
| Document Chunker (`ingestion/chunking/`) | Enterprise Chunking module consuming the Parser's `ParsedDocument` directly and unmodified: header-aware section splitting (heading-shape heuristics), recursive text chunking (paragraph → sentence → hard-split fallback, with configurable `chunk_size`/`chunk_overlap`/`max_chunk_length`/`min_chunk_length` via `ChunkingConfig`), table-aware chunking (tables always chunked separately, header repeated in every resulting chunk); standardized `ChunkCollection`/`Chunk`/`ChunkMetadata` output designed for direct consumption by the future Embedding Generator; `DocumentProcessingService.run_chunker` now fully implemented (was `NotImplementedError`), wired through new `chunk_count`(reused)/`chunking_time_seconds`/`chunker_metadata` fields on `Document`; `POST /api/documents/{id}/parse/` now automatically chains Parser → Chunker in one request, per the sprint requirement that chunking run automatically after parsing; 62 new passing tests (every strategy, config validation, and full Document-model integration for small/large/table/OCR/empty/invalid-input scenarios against real sample files) | ✅ Complete (Chunker only — Embedding/ChromaDB/Knowledge Graph remain unimplemented) |
| Embedding Generator (`rag/embeddings/`) | Enterprise Embedding Generator module consuming the Chunker's `ChunkCollection` directly and unmodified: batch embedding via Google Gemini Embedding API through LangChain (`GoogleGenerativeAIEmbeddings`); exponential-backoff retry with configurable max retries; rate-limit detection (429) with extended backoff; timeout handling; authentication-error detection (non-retryable); input validation (empty/oversized/missing-ID chunks); duplicate protection (SHA-256 checksum per chunk); metadata preservation (original chunk metadata carried through to every `ChunkEmbedding`); standardized `EmbeddingResult`/`ChunkEmbedding`/`EmbeddingProcessingInfo` output designed for direct consumption by the future ChromaDB integration; `DocumentProcessingService.run_embedding_generator` now fully implemented (was `NotImplementedError`), wired through new `embedding_metadata` JSONField on `Document` and `embedding_status` (existing field, now populated); `POST /api/documents/{id}/parse/` now automatically chains Parser → Chunker → Embedding Generator in one request; 45 new passing tests (config, validation, batch logic, retry/rate-limit/timeout/auth error handling, progress tracking, serialization, exception classification, and full Document-model pipeline integration against real sample files with mocked API) | ✅ Complete (Embedding Generator only — ChromaDB/Knowledge Graph remain unimplemented) |
| ChromaDB Vector Store (`rag/vectorstore/`) | Enterprise Vector Store module consuming the Embedding Generator's `EmbeddingResult` directly and unmodified: batch indexing into ChromaDB via `PersistentClient` with connection pooling; upsert semantics for duplicate prevention; ChromaDB-compatible metadata flattening (no None values); semantic search with Top-K results, similarity scoring (cosine distance → 0-1 similarity), and metadata filtering (document_id, document_type, source_filename, date, etc.); document vector deletion (both explicit API and automatic via Django `post_delete` signal); collection management and statistics; health check endpoint; configurable via `CHROMA_*` environment variables (persist directory, collection name, batch size, search K, similarity threshold, max results); `DocumentProcessingService.store_in_vector_db` now fully implemented (was `NotImplementedError`); `POST /api/documents/{id}/parse/` now automatically chains Parser → Chunker → Embedding Generator → Vector Store in one request, reaching `VECTOR_INDEXED` status; 31 new passing tests (config, validation, indexing, batch, upsert, deletion, search with filtering, collection stats, health check, and full Document-model pipeline integration against real sample files + real local ChromaDB) | ✅ Complete (Vector Store only — Knowledge Graph remains unimplemented) |

No other functional application modules (authentication UI) have been
implemented yet. The dashboard overview still renders static data. The
complete platform includes: ingestion pipeline → ChromaDB → Knowledge
Graph → Drawing Analysis (now enhanced with Gemini Vision analysis,
structured warnings, caching, and RAG context bridging) → Hybrid RAG →
Maintenance Agent → Compliance Agent → Failure Intelligence Agent →
Warning Engine → Trend Analysis → Operations Intelligence Orchestrator →
Response Composer → Enterprise Reports → Executive AI Briefing →
Operations Command Center dashboard. Persistent chat history stores all
conversations. All `DocumentProcessingService` stage methods are
implemented.

## 6. Pending Modules

The following modules are **explicitly not yet built** and are the
expected next steps, in no particular mandated order (to be prioritized
in future prompts):

- [ ] Upload Workspace UI → full pipeline integration: the Upload Workspace frontend (Sprint 4) should be updated to call `POST /api/documents/{id}/parse/` and display real pipeline stage progress
- [ ] Authentication (user model, login/logout, session or token auth)
- [ ] Chunk page-number attribution: `Chunk.page_number` is always `None` (see Sprint 6 docs)
- [ ] Automatic/async pipeline triggering (Celery/Redis)
- [ ] Legacy `.doc` support
- [ ] Dashboards / data visualization (Chart.js) — wiring overview page to real data
- [ ] Production deployment configuration (Docker, PostgreSQL, gunicorn, static collection)

## 7. Architecture Overview

IndusMind AI follows a layered, clean-architecture approach:

1. **Presentation layer** (`templates/`, `static/`) — Django server-rendered
   HTML, styled with Tailwind CSS, enhanced with GSAP/Lottie animations and
   Chart.js visualizations. The public landing page (`apps/landing`) and
   the enterprise dashboard (`apps/dashboard`) are implemented; both
   currently render static, representative data. The chatbot UI, the full
   Upload Workspace, and Chart.js-driven analytics are not yet built.
2. **API layer** — `apps.documents` exposes a complete, production-ready
   REST API for document upload/list/retrieve/delete/status. The `api/`
   package (Sprint 11) provides search and query endpoints: semantic
   search (`/api/search/semantic/`), Knowledge Graph search
   (`/api/search/knowledge-graph/`), drawing search
   (`/api/search/drawings/`), and a full hybrid RAG query endpoint
   (`/api/query/`) that orchestrates intent detection, retrieval, context
   building, and LLM generation.
3. **Application/domain layer** (`agents/`) — The Hybrid RAG Pipeline
   and Query Orchestrator (Sprint 11): intent detection, multi-source
   retrieval (ChromaDB + Knowledge Graph + metadata), configurable
   ranking, context building with citations and token limits, Google
   Gemini LLM integration with retries, and session-level conversation
   memory. Fully implemented.
4. **Intelligence layer** (`rag/`, `knowledge_graph/`, `vision/`) —
   Retrieval-Augmented Generation over ChromaDB for unstructured document
   search, combined with a NetworkX knowledge graph for structured
   entity/relationship reasoning, and computer vision for engineering
   drawing analysis. All implemented: Embedding Generator (Sprint 7),
   ChromaDB Vector Store (Sprint 8), Knowledge Graph (Sprint 9),
   Computer Vision (Sprint 10).
5. **Ingestion layer** (`ingestion/`) — Converts raw uploaded documents
   (PDF, DOCX, TXT, CSV, XLSX via PyMuPDF/python-docx/pandas/openpyxl,
   with optional Tesseract+pdf2image OCR fallback) into a standardized
   `ParsedDocument` (text, metadata, tables, images, ocr, processing
   info), then (as of Sprint 6) splits that `ParsedDocument` into a
   standardized `ChunkCollection` via `ingestion/chunking/` — both
   consumed by the intelligence layer. **Parser implemented Sprint 5**
   — see `ingestion/service.py:DocumentParserService` and
   `ingestion/base.py:BaseParser`/`ParserRegistry`. **Chunker
   implemented Sprint 6** — see
   `ingestion/chunking/service.py:DocumentChunkerService`. Legacy
   `.doc` is registered but intentionally unsupported (see Pending
   Modules). This module will next need to expose its `ChunkCollection`
   to the Embedding Generator (Sprint 7), which may land in `rag/`.
6. **Document persistence & orchestration layer** (`apps/documents`) —
   Owns the `Document` model, secure upload storage, validation, and the
   REST API for document CRUD. Drives the full pipeline through `INDEXED`
   via `DocumentProcessingService.run_parser`, `run_chunker`,
   `run_embedding_generator`, `store_in_vector_db`, and
   `update_knowledge_graph`. Document deletion automatically cleans up
   stored files, ChromaDB vectors, and Knowledge Graph entities via
   `post_delete` signals. All orchestration stage methods are
   implemented — no `NotImplementedError` stubs remain.
7. **Configuration layer** (`config/`) — Centralized, environment-driven
   Django settings.

Data flow: a document is uploaded → `apps.documents` validates, stores
it, and marks it `READY_FOR_PARSING` → a client calls
`POST /api/documents/{id}/parse/`, which auto-chains:
`run_parser` → `run_chunker` → `run_embedding_generator` →
`store_in_vector_db` → `update_knowledge_graph` → the document reaches
`INDEXED` with all knowledge stores populated (ChromaDB vectors +
NetworkX graph) → a user calls `POST /api/query/` with a question →
the `QueryOrchestrator` detects intent, performs hybrid retrieval
(ChromaDB semantic search + Knowledge Graph keyword search), ranks and
deduplicates, builds a context with citations, invokes Google Gemini,
and returns a structured response with answer, confidence, citations,
related equipment, and suggested follow-ups.

### 7.1 Parser Architecture (Sprint 5)

**Flow:**
```
Document (status=READY_FOR_PARSING)
  → apps.documents.services.DocumentProcessingService.run_parser(document)
      → DocumentStatusService.transition(document, PARSING)
      → ingestion.service.DocumentParserService.parse_document(
            file_path=document.file.path,
            extension=document.extension,
            document_id=str(document.id),
        )
          → ingestion.validators.validate_file_exists_on_disk(file_path)
          → ingestion.factory.get_parser_for_extension(extension)
              → returns a BaseParser instance from ParserRegistry
          → parser.parse(file_path, document_id) -> ParsedDocument
              (may internally call ingestion.ocr.run_ocr_on_pdf as a
              fallback — PDF parser only, and only when direct text
              extraction looks like it failed)
      → on success: document.page_count, document.parser_metadata are
        set; DocumentStatusService.transition(document, PARSED)
      → on ParserError: DocumentStatusService.transition(document,
        FAILED, error_message=str(exc)); re-raised to the caller
```

**Interfaces:**
- `ingestion.base.BaseParser` — abstract `parse(file_path, document_id) -> ParsedDocument`.
  Every format parser implements exactly this.
- `ingestion.base.ParserRegistry` — the factory backing store; parsers
  self-register via `@ParserRegistry.register` at import time (see
  `ingestion/parsers/__init__.py`, which imports every parser submodule
  specifically to trigger this side effect).
- `ingestion.factory.get_parser_for_extension(extension)` — the public
  factory function; the only way calling code should obtain a parser.
- `ingestion.result.ParsedDocument` — the standardized output contract
  (text, metadata, tables, images, ocr, processing). JSON-serializable
  via `.to_dict()` (used for persistence) but also usable directly
  in-memory by the next pipeline stage.
- `ingestion.exceptions.ParserError` — the single exception hierarchy
  `run_parser` catches; every format parser and the OCR module raise a
  subclass of this rather than a raw library exception.

**Extension points for future work:**
- **New file format**: add `ingestion/parsers/<format>_parser.py` with
  a `BaseParser` subclass decorated `@ParserRegistry.register`, and
  import it from `ingestion/parsers/__init__.py`. No other file needs
  to change.
- **Legacy `.doc` support**: replace the body of
  `ingestion.parsers.docx_parser.DocParser.parse` with a real
  implementation once an approved dependency (e.g. antiword, textract,
  or a LibreOffice-based converter) is selected — its `extension = "doc"`
  registration is already wired.
- **OCR engine swap**: `ingestion/ocr.py` isolates all
  Tesseract/pdf2image usage; swapping OCR engines means changing only
  this file.

**Future integration with the Chunker:** superseded — the Chunker is
now implemented as of Sprint 6. See section 7.2 below.

### 7.2 Chunker Architecture (Sprint 6)

**Flow:**
```
Document (status=PARSED, in-memory ParsedDocument from run_parser)
  → apps.documents.services.DocumentProcessingService.run_chunker(document, parsed_content)
      → DocumentStatusService.transition(document, CHUNKING)
      → ingestion.chunking.service.DocumentChunkerService.chunk_document(
            parsed_document=parsed_content,
            filename=document.original_filename,
        )
          → ingestion.chunking.validators.validate_parsed_document(parsed_document)
          → if parsed_document.text: ingestion.chunking.strategies.header_aware.split_into_sections(text)
              → for each (section_title, section_text):
                  ingestion.chunking.strategies.recursive.recursive_chunk_text(section_text, config)
                    (internally: paragraph split -> per-piece sentence-boundary
                    break if oversized -> hard character split as last resort
                    -> greedy packing to chunk_size -> overlap -> short-trailing-chunk merge)
              → each resulting piece becomes one TEXT Chunk
          → for each table in parsed_document.tables:
              ingestion.chunking.strategies.table.chunk_table(table, config)
                (splits by row group if the table exceeds max_chunk_length,
                repeating the header row in every resulting piece)
              → each resulting piece becomes one TABLE Chunk
          → backfill Chunk.metadata.total_chunks on every chunk now that
            the final count is known
      → on success: document.chunk_count, document.chunking_time_seconds,
        document.chunker_metadata are set;
        DocumentStatusService.transition(document, CHUNKED)
      → on ChunkingError: DocumentStatusService.transition(document,
        FAILED, error_message=str(exc)); re-raised to the caller
```

`POST /api/documents/{id}/parse/` (Sprint 5) now automatically chains
`run_parser` followed by `run_chunker` within the same request, per the
Sprint 6 requirement that chunking run automatically once parsing
completes. There is still no separate `/chunk/` endpoint — chunking is
not independently client-triggerable outside of that automatic chain
(mirroring how there is no task queue yet to trigger it any other way).

**Chunk model** (`ingestion/chunking/result.py`):
- `Chunk`: `chunk_id` (`"{document_id}_chunk_{NNNN}"`), `document_id`,
  `chunk_number`, `text`, `chunk_type` (`TEXT` | `TABLE`), `metadata`,
  `word_count`, `character_count`, `page_number` (always `None` this
  sprint — see limitation note below), `section_title`.
- `ChunkCollection`: `document_id`, `chunks: list[Chunk]`, `processing`
  (timing + warnings); computed properties `total_chunks`,
  `text_chunk_count`, `table_chunk_count`. `to_dict()` excludes chunk
  text (same rationale as `ParsedDocument.to_dict()` — avoid bloating
  `Document.chunker_metadata`); the in-memory `ChunkCollection` (with
  full chunk text) is what gets passed to the future Embedding
  Generator.

**Metadata schema** (`ChunkMetadata`, attached to every chunk):
`document_id`, `filename` (passed in by `run_chunker` from
`document.original_filename` — not carried by `ParsedDocument` itself),
`parser_used`, `ocr_used` (both copied from `ParsedDocument.metadata`/`.ocr`),
`chunk_number`, `total_chunks`, `section` (the detected section title,
or a `"Table N"` label for table chunks), `source_type` (`"text"` |
`"table"`).

**Known limitation (documented, not a bug):** `Chunk.page_number` is
always `None`. `ParsedDocument.text` has no embedded page-boundary
markers for any format, and DOCX/TXT/CSV/XLSX have no page concept at
all (the Sprint 5 DOCX parser already documents `page_count=None` for
the same reason). Populating real page numbers would require extending
the Parser's output contract — explicitly out of scope for a sprint
that must not modify the Parser. Section titles ARE populated
best-effort via heading-shape heuristics (markdown `#`, numbered
headings, short all-caps lines) since that information can be derived
from `ParsedDocument.text` alone without touching the Parser.

**Future integration with the ChromaDB Vector Store (Sprint 8):**
`DocumentProcessingService.store_in_vector_db(document, embedding_result)`
is already defined (raising `NotImplementedError`) with its expected
contract documented in its docstring: it should transition the document
to `INDEXING_VECTOR_DB`, persist the embedding vectors from
`embedding_result.embeddings` (the same `EmbeddingResult` object
`run_embedding_generator` returns) to the ChromaDB collection configured
via `settings.CHROMA_PERSIST_DIRECTORY`, and transition to
`VECTOR_INDEXED` (or `FAILED`) using the same
`DocumentStatusService.transition` helper the earlier stages use. No
changes to `rag/embeddings/` should be required to implement ChromaDB
storage; it only needs to consume the `EmbeddingResult` contract
(specifically each `ChunkEmbedding.embedding`, `ChunkEmbedding.chunk_id`,
and `ChunkEmbedding.metadata`).

### 7.3 Embedding Generator Architecture (Sprint 7)

**Flow:**
```
Document (status=CHUNKED, in-memory ChunkCollection from run_chunker)
  → apps.documents.services.DocumentProcessingService.run_embedding_generator(document, chunk_collection)
      → DocumentStatusService.transition(document, EMBEDDING)
      → document.embedding_status = IN_PROGRESS; save()
      → rag.embeddings.service.EmbeddingGeneratorService.generate_embeddings(
            chunk_collection=chunk_collection,
        )
          → rag.embeddings.validators.validate_chunk_collection(chunk_collection)
          → rag.embeddings.config.EmbeddingConfig.from_settings()
          → EmbeddingGeneratorService._create_embeddings_model(config)
              → langchain_google_genai.GoogleGenerativeAIEmbeddings(
                    model=config.model_name,
                    google_api_key=config.api_key,
                )
          → for each batch of chunks (batch_size from config):
              → validate each chunk (empty → skip, oversized → truncate,
                duplicate checksum → skip)
              → _embed_batch_with_retry(model, valid_chunks, config)
                  → model.embed_documents(texts)  ← actual API call
                  → on transient failure: exponential backoff, retry up to max_retries
                  → on auth error: stop immediately (non-retryable)
                  → on success: build ChunkEmbedding with vector, model, dimension,
                    timestamp, checksum, metadata
          → if ALL chunks failed: raise EmbeddingError
          → build EmbeddingResult with all ChunkEmbeddings + processing info
      → on success: document.embedding_status = COMPLETED;
        document.embedding_metadata = result.to_dict(); save();
        DocumentStatusService.transition(document, EMBEDDED)
      → on EmbeddingError: document.embedding_status = FAILED; save();
        DocumentStatusService.transition(document, FAILED,
        error_message=str(exc)); re-raised to the caller
```

`POST /api/documents/{id}/parse/` (Sprint 5, extended Sprint 6 and
Sprint 7) now automatically chains `run_parser` → `run_chunker` →
`run_embedding_generator` within the same request. There is still no
separate `/embed/` endpoint — embedding is not independently
client-triggerable outside of that automatic chain (mirroring how there
is no task queue yet to trigger it any other way).

**Output model** (`rag/embeddings/result.py`):
- `ChunkEmbedding`: `chunk_id`, `document_id`, `chunk_number`,
  `embedding` (list[float]), `embedding_model`, `embedding_dimension`,
  `embedding_timestamp` (ISO UTC), `checksum` (SHA-256 of chunk text),
  `status` (`SUCCESS` | `FAILED` | `SKIPPED`), `error_message`,
  `metadata` (original ChunkMetadata as dict).
- `EmbeddingResult`: `document_id`, `embeddings: list[ChunkEmbedding]`,
  `processing` (timing + counts + warnings); computed properties
  `total_embeddings`, `successful_count`, `failed_count`,
  `skipped_count`, `embedding_dimension`. `to_dict()` excludes
  embedding vectors (same rationale as earlier stages — avoid bloating
  `Document.embedding_metadata`); the in-memory `EmbeddingResult`
  (with full vectors) is what gets passed to the future
  `store_in_vector_db`.

**Configuration** (`rag/embeddings/config.py:EmbeddingConfig`):
`model_name` (`EMBEDDING_MODEL_NAME`, default `models/embedding-001`),
`api_key` (`GOOGLE_API_KEY`), `batch_size` (`EMBEDDING_BATCH_SIZE`,
default 20), `max_retries` (`EMBEDDING_MAX_RETRIES`, default 3),
`timeout_seconds` (`EMBEDDING_TIMEOUT_SECONDS`, default 30),
`max_concurrent_requests` (`EMBEDDING_MAX_CONCURRENT_REQUESTS`,
default 5 — reserved for future async), `max_chunk_text_length`
(`EMBEDDING_MAX_CHUNK_TEXT_LENGTH`, default 10000).

**Error handling:**
- `EmbeddingConfigurationError`: missing API key, invalid settings
- `EmbeddingAuthenticationError`: invalid API key (401) — NOT retried
- `EmbeddingRateLimitError`: 429 — retried with extended backoff
- `EmbeddingTimeoutError`: timeout — retried with standard backoff
- `EmbeddingNetworkError`: connection issues — retried
- `EmbeddingAPIError`: unexpected API response — retried
- `EmbeddingValidationError`: invalid input (None collection, empty)
- `EmbeddingError`: base class; raised when ALL chunks fail

**Extension points for future work:**
- **Embedding model swap**: change `EMBEDDING_MODEL_NAME` to use a
  different Google model (e.g. `models/text-embedding-004`) — no code
  changes needed.
- **Different provider**: replace the body of
  `_create_embeddings_model` to use a different LangChain embeddings
  class (e.g. `OpenAIEmbeddings`) — the rest of the service only
  depends on the `embed_documents(texts) -> list[list[float]]`
  interface.
- **Async/concurrent**: `max_concurrent_requests` is configured but
  not yet used; when Celery or async support is introduced, the batch
  loop can be parallelized using this limit.

## 8. Future Development Guidelines

- **Never recreate existing files** unless explicitly instructed — treat
  this document and the current folder structure as the baseline for all
  future work.
- **Never modify completed modules** unless a change is necessary to
  support a new requirement; prefer additive changes.
- When implementing a pending module, **register any new Django app** in
  `backend/config/settings.py` under `LOCAL_APPS`, and add its URLs to
  `backend/config/urls.py`.
- When adding new environment variables, update both `.env.example` (with
  a safe placeholder/default) and the corresponding `env(...)` /
  `env.list(...)` / `env.bool(...)` read in `backend/config/settings.py`.
- When adding new Python dependencies, pin exact versions in
  `requirements.txt`.
- Maintain the layer boundaries described in the Architecture Overview —
  e.g., `agents/` should orchestrate `rag/`, `knowledge_graph/`, and
  `tools/`, but ingestion logic belongs exclusively in `ingestion/`.
- Update the **Completed Modules** and **Pending Modules** tables in this
  file at the end of every development phase so this document remains an
  accurate project memory for future prompts.
- Update the **Architecture Overview** section whenever a new layer or
  significant architectural decision is introduced.
- Shared, cross-app template partials (currently just the Heroicons
  renderer) live in `backend/templates/shared/` and are loaded via
  `{% include "shared/..." %}`. Do not duplicate icon markup into a new
  app's own partials — add missing icons to `shared/_icon.html` instead.
  The landing page's own `landing/partials/_icon.html` is left as-is
  (not migrated) to honor the "do not modify the Landing Page" rule from
  the dashboard development phase; new apps should use the shared one.
- The `dashboard:upload` URL is the permanent, real entry point for the
  Upload Workspace module. When that module is built, replace the body
  of `UploadWorkspaceView` / `upload_workspace.html` — do not change the
  URL name or route, since the dashboard's Upload button and sidebar
  item already link to it by name.
- `apps.documents.services.DocumentProcessingService` is the single
  orchestration seam for all future AI pipeline modules. Each future
  module (Parser, Chunker, Embedding Generator, ChromaDB integration,
  Knowledge Graph integration) should **implement the existing method
  it corresponds to** (`run_parser`, `run_chunker`,
  `run_embedding_generator`, `store_in_vector_db`,
  `update_knowledge_graph`) rather than introducing a parallel
  orchestration path. Use `DocumentStatusService.transition` for every
  status change those implementations make, so status/stage/percentage
  stay consistent with the rest of the app.
- Do not add parsing/chunking/embedding/vector-store/knowledge-graph
  logic directly into `apps.documents` views, serializers, or
  `DocumentUploadService`. That boundary is intentional: `apps.documents`
  owns persistence and orchestration *contracts*, not AI implementations.
- The Document model's schema already includes fields for stages that
  are not implemented yet (`page_count`, `chunk_count`,
  `embedding_status`, `knowledge_graph_status`). Future modules should
  populate these fields rather than adding new ones, and should not
  require a new migration for basic status tracking.
- `apps.documents` is Celery/Redis-ready in the sense that
  `DocumentProcessingService.run_full_pipeline` is a plain synchronous
  method today; when Celery is introduced, wrap its stage calls in
  tasks rather than rewriting the orchestration logic itself.
- The Upload Workspace (`apps/dashboard/templates/dashboard/upload_workspace.html`
  + `static/js/upload-workspace.js`) is the reference pattern for any
  future page that needs to consume `apps.documents` (or another future
  API) client-side rather than via server-rendered context: the view is
  decorated with `@method_decorator(ensure_csrf_cookie, name="dispatch")`
  so the CSRF cookie exists for JS to read, and all API calls go through
  a single `apiFetch()` helper. Follow this same pattern rather than
  inventing a new CSRF strategy per page.
- `static/js/upload-workspace.js` intentionally duplicates a small
  Heroicons subset (`ICONS` object) and the `_status_badge.html` class
  contract (`STATUS_BADGE_VARIANTS`) because Django template partials
  cannot be invoked from client-side JS. When either
  `templates/shared/_icon.html` or `_status_badge.html` gains a new
  icon/status that a client-rendered page also needs, update both the
  Django partial and this JS module's mirrors together.
- Client-side "Queued" and "Deleted" states shown in the Upload
  Workspace are UI-only concepts (a file selected but not yet POSTed;
  a row removed after a successful DELETE) — they do not exist in
  `DocumentStatus` on the backend and should not be added there.
- `POST /api/documents/{id}/parse/` (`DocumentParseView`) is a
  deliberately synchronous trigger, added because no task queue exists
  yet. When Celery/Redis are introduced, prefer changing this view's
  body to enqueue a task (still calling
  `DocumentProcessingService.run_parser`) over inventing a new
  automatic-on-upload code path elsewhere — keep the "how parsing gets
  triggered" decision in one place.
- `ingestion/parsers/__init__.py` importing every parser submodule is
  load-bearing, not decorative: `ParserRegistry` population happens via
  the `@ParserRegistry.register` decorators executing at import time.
  If a future parser module is added but not imported from
  `ingestion/parsers/__init__.py`, `get_parser_for_extension` will
  silently fail to find it outside of test runs (Django's test
  discovery can mask this by importing test modules that happen to
  import the parser directly — this exact bug was caught during this
  sprint's live end-to-end verification, not by the unit tests).
- When implementing the Chunker (Sprint 6), extend
  `apps.documents.tests.test_services.DocumentProcessingServiceTests`
  deliberately (replace its `run_chunker`-raises-`NotImplementedError`
  test with real coverage) rather than leaving it stale — follow the
  same pattern used for `run_parser` in this sprint.
- `POST /api/documents/{id}/parse/` (`DocumentParseView`) now
  auto-chains `run_parser` → `run_chunker` within one request (Sprint
  6). When implementing the Embedding Generator (Sprint 7), decide
  deliberately whether to extend this same endpoint to auto-chain a
  third stage, or introduce Celery task-chaining instead of growing
  this endpoint further — do not silently change its behavior without
  updating `test_parse_api.py` and this document, mirroring how Sprint
  6 updated `test_owner_can_trigger_parse_successfully`'s expected
  final status when chunking was added to the chain.
- When implementing the Embedding Generator (Sprint 7), extend
  `apps.documents.tests.test_services.DocumentProcessingServiceTests`
  deliberately (replace its
  `run_embedding_generator`-raises-`NotImplementedError` test with real
  coverage) — follow the same pattern used for `run_parser` (Sprint 5)
  and `run_chunker` (Sprint 6).
- `POST /api/documents/{id}/parse/` (`DocumentParseView`) now
  auto-chains `run_parser` → `run_chunker` → `run_embedding_generator`
  within one request (Sprint 7). When implementing the ChromaDB
  integration (Sprint 8), decide deliberately whether to extend this
  same endpoint to auto-chain a fourth stage, or introduce Celery
  task-chaining instead of growing this endpoint further — do not
  silently change its behavior without updating `test_parse_api.py`
  and this document.
- When implementing the ChromaDB Vector Store (Sprint 8), extend
  `apps.documents.tests.test_services.DocumentProcessingServiceTests`
  deliberately (replace its
  `store_in_vector_db`-raises-`NotImplementedError` test with real
  coverage) — follow the same pattern used for `run_parser` (Sprint 5),
  `run_chunker` (Sprint 6), and `run_embedding_generator` (Sprint 7).
- `rag/embeddings/` depends only on `ingestion.chunking.result.ChunkCollection`
  (Sprint 6's output contract) and Django settings — it has no
  dependency on `apps.documents`. Keep it that way: any future need to
  reference the `Document` model or its status machine belongs in
  `apps.documents.services.DocumentProcessingService.run_embedding_generator`,
  not inside `rag/embeddings/service.py`.
- `ingestion/chunking/` depends only on `ingestion.result.ParsedDocument`
  (Sprint 5's output contract) and Django settings — it has no
  dependency on `apps.documents`. Keep it that way: any future need to
  reference the `Document` model or its status machine belongs in
  `apps.documents.services.DocumentProcessingService.run_chunker`, not
  inside `ingestion/chunking/service.py`.
- `Chunk.page_number` is `None` for every chunk in this sprint by
  design (see section 7.2's limitation note) — do not "fix" this by
  guessing page numbers heuristically from character offsets; either
  leave it `None` until the Parser's contract is deliberately extended
  to expose real per-page offsets, or solve it at the Parser layer
  first (which would itself be a deliberate, documented change to
  `ingestion/result.py` and every parser in `ingestion/parsers/`, not
  a Chunker-only fix).
