"""
Document ingestion (Parser) module for IndusMind AI.

This is the first stage of the AI pipeline (Sprint 5): converting raw
uploaded documents (PDF, DOCX, TXT, CSV, XLSX) into structured,
standardized text + metadata that the future Chunker (Sprint 6) will
consume.

Architecture:

    exceptions.py    ParserError hierarchy — every parser failure mode
                     raises one of these, never a raw library exception.
    result.py        ParsedDocument / DocumentMetadata / OcrInfo /
                     ProcessingInfo — the standardized output contract.
    base.py          BaseParser interface + ParserRegistry (factory
                     backing store).
    factory.py       get_parser_for_extension() — the public factory
                     function callers use to obtain a parser.
    validators.py    Pre-parse checks (file exists on disk, non-empty).
    utils.py         Shared helpers: char/word counts, language
                     detection, best-effort text decoding.
    ocr.py           Optional, configurable OCR fallback (Tesseract +
                     pdf2image), invoked only when direct text
                     extraction appears to have failed.
    service.py       DocumentParserService — the single entry point
                     `apps.documents.services.DocumentProcessingService.run_parser`
                     calls into.
    parsers/         One module per supported format, each registering
                     itself with ParserRegistry via `@ParserRegistry.register`.

Deliberately NOT implemented here (future sprints):
    Chunker, Embedding Generator, ChromaDB integration, Knowledge Graph
    integration, LangChain, Gemini, AI Agents.

Legacy .doc note: python-docx (this project's approved dependency)
supports only the modern .docx format. `.doc` is registered with a
parser that raises a clear, actionable error rather than silently
mis-parsing — see `parsers/docx_parser.py:DocParser`.
"""
