"""
Document chunking module for IndusMind AI.

This is the second stage of the AI pipeline (Sprint 6): splitting the
`ParsedDocument` the Parser (Sprint 5) produces into standardized,
retrieval-sized `Chunk`s that the future Embedding Generator
(Sprint 7) will consume — one embedding request per chunk.

Architecture:

    exceptions.py    ChunkingError hierarchy.
    config.py        ChunkingConfig — chunk_size, chunk_overlap,
                      max/min_chunk_length, all overridable via Django
                      settings.
    result.py         Chunk / ChunkMetadata / ChunkCollection / ChunkType
                      — the standardized output contract.
    validators.py      Pre-chunk checks (non-empty, well-formed tables).
    strategies/
        header_aware.py   Splits flat text into (section_title, text)
                          pairs using heading-shape heuristics.
        recursive.py       The primary text-splitting algorithm:
                           paragraph -> sentence -> hard-character-split
                           fallback, with configurable size/overlap.
        sentence.py         Regex-based sentence boundary detection,
                            used by recursive.py.
        table.py             Table-aware chunking — tables are always
                             chunked separately from prose text.
    service.py        DocumentChunkerService — the single entry point
                      `apps.documents.services.DocumentProcessingService.run_chunker`
                      calls into.

Consumes `ingestion.result.ParsedDocument` (Sprint 5) directly and
unmodified — this module makes no changes to `ingestion/parsers/`,
`ingestion/service.py`, `ingestion/ocr.py`, or any other Sprint 5 file.

Known limitation (documented, not a bug): `Chunk.page_number` is always
None in this sprint, because `ParsedDocument` does not expose per-page
text offsets for any format (see `ingestion/chunking/service.py`
module docstring for the full explanation). Populating real page
numbers would require extending the Parser's output contract, which is
out of scope for a sprint that is explicitly forbidden from modifying
the Parser.

Deliberately NOT implemented here (future sprints): Embedding
Generator, ChromaDB integration, Knowledge Graph integration,
LangChain, Gemini, AI Agents.
"""
