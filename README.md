# IndusMind AI

Enterprise Industrial Intelligence Platform powered by AI.

IndusMind AI is a Django-based platform designed to ingest industrial
documents, build a searchable knowledge base (RAG + knowledge graph),
and expose AI-powered reasoning through agents and chat — for
enterprise industrial intelligence use cases.

> **Status:** The **complete enterprise industrial intelligence platform**
> is implemented — including an **Operations Command Center** dashboard
> with Executive AI Briefings, real-time KPI cards, Alert Center,
> multi-agent status panel, interactive operations reports, and
> **Enhanced Drawing Intelligence** with Gemini Vision analysis,
> structured warnings, caching, and RAG context bridging. See
> [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) and
> [`PROJECT_CONTEXT.md`](./PROJECT_CONTEXT.md) for full detail.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Django Templates, HTML5, Tailwind CSS, JavaScript (ES6), GSAP, Lottie, Chart.js |
| Backend | Django, Django REST Framework |
| AI | LangChain, Google Gemini (embeddings + LLM generation implemented) |
| Vector Database | ChromaDB (implemented — local persistent storage with semantic search) |
| Knowledge Graph | NetworkX (implemented — entity extraction + graph construction) |
| Database | SQLite (development), PostgreSQL (production-ready) |
| OCR | Tesseract OCR + pdf2image (optional fallback during parsing) |
| Document Processing | PyMuPDF, python-docx, pandas, openpyxl, chardet, langdetect |

## What's Implemented

- **Landing page** (`apps/landing`) — public marketing site.
- **Dashboard & Upload Workspace** (`apps/dashboard`) — authenticated
  workspace shell with a drag-and-drop Upload Workspace wired to the
  real document API (real upload progress, search/filter/sort,
  cancel/retry).
- **Document Management API** (`apps/documents`) — `Document` model,
  secure upload/storage/validation, and a REST API
  (upload/list/retrieve/delete/status/parse/supported-formats),
  gated by authentication and per-document ownership.
- **Document Parser** (`ingestion/`) — extracts text, tables, and
  metadata from PDF, DOCX, TXT, CSV, and XLSX files, with an optional
  Tesseract-based OCR fallback for scanned PDFs.
- **Document Chunker** (`ingestion/chunking/`) — splits parsed
  documents into standardized, retrieval-sized chunks (header-aware,
  recursive text splitting, and table-aware strategies), ready for
  embedding.
- **Embedding Generator** (`rag/embeddings/`) — generates vector
  embeddings for document chunks using the Google Gemini Embedding API
  via LangChain, with batch processing, retry/rate-limit handling,
  duplicate detection, and metadata preservation.
- **ChromaDB Vector Store** (`rag/vectorstore/`) — persists embedding
  vectors into ChromaDB for semantic search, with batch indexing,
  metadata filtering (document type, date, source), duplicate
  prevention via upsert, automatic cleanup on document deletion,
  collection management, and health checks.
- **Knowledge Graph** (`knowledge_graph/`) — pattern-based entity
  extraction (30+ industrial entity types: equipment, pumps, valves,
  regulations, failure modes, maintenance activities, etc.) and
  relationship extraction (20+ relationship types), backed by a
  NetworkX directed graph with node/edge CRUD, search, traversal,
  deduplication, and document cleanup.
- **Computer Vision / Drawing Analysis** (`vision/`) — engineering
  drawing classification (P&ID, mechanical, electrical, instrumentation,
  general arrangement), enhanced OCR extraction (equipment tags, drawing
  numbers, revisions, instrument IDs, BOM, notes, dimensions), symbol
  detection (20+ symbol types), equipment extraction, relationship
  inference, and Knowledge Graph integration.
- **Hybrid RAG Pipeline** (`agents/`) — multi-source retrieval
  combining ChromaDB semantic search + Knowledge Graph + metadata,
  configurable ranking weights, intent detection, context building with
  citations and token limits, session-level conversation memory, and
  Google Gemini LLM integration with retries.
- **Search & Query REST API** (`api/`) — DRF endpoints for semantic
  search, knowledge graph search, drawing search, and full hybrid
  RAG query with structured responses (answer, citations, confidence,
  related equipment, follow-up suggestions).
- **Enterprise AI Copilot Chat** (`dashboard/chat/`) — modern chat
  interface with structured AI responses (confidence badges, source
  citations, related equipment/drawings, Knowledge Graph references,
  suggested follow-ups), markdown rendering, typing indicators,
  session memory, suggestion chips, and responsive design.

`POST /api/query/` runs the full RAG pipeline: intent detection →
hybrid retrieval → context building → LLM generation → structured
response with citations.

The chat UI is at `/dashboard/chat/` (requires an authenticated session).

`POST /api/documents/{id}/parse/` runs parsing, chunking, embedding
generation, vector storage, and knowledge graph construction
automatically, in sequence, within a single request. Documents reach
`INDEXED` status on success.

## What's Not Implemented Yet

- Authentication UI (login/logout — use Django admin for now)
- Asynchronous pipeline execution (Celery/Redis)
- Production deployment tooling (Docker, gunicorn config)

## Project Structure

```
indusmind-ai/
├── backend/
│   ├── config/            # Django settings, root URLconf, WSGI/ASGI entry points
│   ├── apps/
│   │   ├── landing/        # Marketing landing page
│   │   ├── dashboard/       # Workspace shell + Upload Workspace UI
│   │   └── documents/        # Document model, REST API, pipeline orchestration
│   ├── ingestion/            # Document Parser
│   │   └── chunking/          # Document Chunker
│   ├── rag/                    # Embedding Generator + ChromaDB Vector Store (implemented)
│   │   ├── embeddings/          # Embedding Generator module
│   │   └── vectorstore/          # ChromaDB Vector Store module
│   ├── knowledge_graph/          # Entity extraction + NetworkX knowledge graph (implemented)
│   ├── vision/                    # Computer Vision / Drawing Analysis (implemented)
│   ├── agents/                    # Hybrid RAG Pipeline + Orchestrator (implemented)
│   │   ├── retrieval/              # RAG Retrieval Service (ChromaDB + KG + metadata)
│   │   ├── llm/                     # Google Gemini LLM Service
│   │   ├── orchestrator/            # Query Orchestrator (intent → retrieval → response)
│   │   ├── context/                  # Context Builder (prompts, citations, token limits)
│   │   └── memory/                    # Session conversation memory
│   ├── api/                          # Search & Query REST API (implemented)
│   ├── tools/                      # LangChain tools — not yet implemented
│   ├── templates/shared/               # Cross-app template partials
│   ├── static/                          # CSS, JS, images, animations
│   ├── media/                            # User-facing uploaded/generated media
│   ├── uploads/                           # Raw documents pending ingestion
│   ├── tests/                              # (project-level; see per-app tests/ dirs)
│   └── manage.py
├── docs/
│   └── ARCHITECTURE.md                       # System architecture reference
├── dataset/
│   └── sample_documents/                       # Parser/Chunker test fixtures
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
└── PROJECT_CONTEXT.md                            # Full project memory
```

## Getting Started

### Quick Start (Docker — Recommended)

```bash
# Clone and start
cp .env.example .env
# Set GOOGLE_API_KEY in .env for full AI capabilities (optional)

make setup
# Or manually: docker compose build && docker compose up -d

# Create admin user
make createsuperuser

# Load demo data (populates Knowledge Graph with sample equipment)
docker compose exec web python manage.py load_demo_data
```

The platform is available at `http://localhost:8000/`.
Login at `/accounts/login/` then explore the Operations Command Center.

### Local Development (without Docker)

```bash
python -m venv venv
source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env

cd backend
python manage.py migrate
python manage.py createsuperuser
python manage.py load_demo_data   # Pre-populate Knowledge Graph
python manage.py runserver
```

Visit `http://127.0.0.1:8000/` → Login → Operations Command Center.

### Running Tests

```bash
cd backend
python manage.py test    # 528 automated tests
```

### Key URLs

| URL | Purpose |
|-----|---------|
| `/` | Landing page |
| `/accounts/login/` | Login |
| `/dashboard/command-center/` | Operations Command Center |
| `/dashboard/chat/` | AI Expert Copilot |
| `/dashboard/upload/` | Document Upload |
| `/api/query/` | Hybrid RAG API |
| `/api/briefing/` | Executive Briefing |
| `/admin/` | Django Admin |

### Environment Variables

See `.env.example` for the full list. Key variables:
- `GOOGLE_API_KEY` — enables Gemini LLM generation (optional; platform works without it)
- `DATABASE_URL` — PostgreSQL for production (defaults to SQLite)
- `CHROMA_PERSIST_DIRECTORY` — ChromaDB storage path

## Development Standards

- Clean Architecture: clear separation between configuration,
  ingestion (parsing/chunking), AI/RAG logic, knowledge graph, API,
  and presentation layers.
- SOLID principles applied throughout.
- No placeholders or TODO comments in committed code — modules are
  only added when fully implemented; unimplemented pipeline stages
  raise a documented `NotImplementedError` rather than faking success.
- All environment-specific configuration is externalized via
  environment variables (12-factor app methodology).

## Documentation

- [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) — system
  architecture: app structure, the document pipeline, and what
  is/isn't implemented.
- [`PROJECT_CONTEXT.md`](./PROJECT_CONTEXT.md) — the full project
  memory: technology stack, coding standards, completed/pending
  modules, and detailed extension-point guidance for every module.

## License

Proprietary — internal enterprise project. Not licensed for external use.
