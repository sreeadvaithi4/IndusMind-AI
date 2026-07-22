"""
Document Management application for IndusMind AI.

This app owns the `Document` model and the backend foundation for the
document ingestion pipeline: secure upload storage, validation, REST
API, and the service-layer orchestration architecture that future AI
modules (Parser, Chunker, Embedding Generator, ChromaDB integration,
Knowledge Graph integration) will plug into.

As of this sprint, only the pipeline stages up to and including
"Ready For Parsing" are implemented. Parsing, chunking, embedding,
vector-store indexing, and knowledge-graph indexing are intentionally
NOT implemented here — see `services.DocumentProcessingService` for the
documented extension points those future modules will implement.
"""
