"""
Enterprise Drawing Analysis Service.

Orchestrates the full drawing analysis pipeline:
    1. Document Classification (P&ID, mechanical, electrical, etc.)
    2. Enhanced OCR extraction (equipment tags, drawing numbers, etc.)
    3. Symbol Detection
    4. Equipment Extraction
    5. Relationship Extraction
    6. Knowledge Graph Integration

Consumes ParsedDocument.text (already OCR'd by the ingestion parser if
needed) and produces a DrawingAnalysisResult. Does NOT directly touch
the Document model — orchestration belongs in
`apps.documents.services`.
"""

import logging
import time

from knowledge_graph.graph import GraphService
from knowledge_graph.models import Entity, Relationship
from vision.classifier import classify_drawing
from vision.config import VisionConfig
from vision.exceptions import VisionError
from vision.extractor import extract_equipment, extract_relationships
from vision.models import DrawingAnalysisResult
from vision.ocr_engine import extract_drawing_metadata, extract_drawing_ocr
from vision.symbols import detect_symbols

logger = logging.getLogger("vision")


class DrawingAnalysisService:
    """
    Entry point for engineering drawing analysis.

    Usage:
        result = DrawingAnalysisService.analyze_drawing(text, document_id)
    """

    @classmethod
    def analyze_drawing(
        cls,
        text: str,
        document_id: str,
        config: VisionConfig | None = None,
    ) -> DrawingAnalysisResult:
        """
        Performs full drawing analysis on parsed document text.

        Args:
            text: The full document text (from ParsedDocument.text,
                which may already include OCR output).
            document_id: The document UUID string.
            config: Optional config override.

        Returns:
            DrawingAnalysisResult with classification, extractions,
            symbols, equipment, and relationships.

        Raises:
            VisionError: on unrecoverable failures.
        """
        start_time = time.time()
        warnings: list[str] = []

        if config is None:
            config = VisionConfig.from_settings()

        if not text or not text.strip():
            return DrawingAnalysisResult(
                document_id=document_id,
                warnings=["Empty text — no drawing analysis performed."],
            )

        if not document_id:
            raise VisionError("document_id is required for drawing analysis.")

        logger.info("Starting drawing analysis for document %s.", document_id)

        try:
            # Step 1: Classify the drawing
            classification = classify_drawing(text)

            # Step 2: Enhanced OCR extraction
            ocr_extractions = extract_drawing_ocr(
                text, confidence_threshold=config.ocr_confidence_threshold
            )

            # Step 3: Extract drawing metadata
            metadata = extract_drawing_metadata(text)
            metadata.drawing_type = classification.drawing_type
            metadata.upload_date = ""  # Filled by caller

            # Step 4: Symbol detection
            symbols = detect_symbols(
                text, confidence_threshold=config.symbol_confidence_threshold
            )

            # Step 5: Equipment extraction
            equipment = extract_equipment(
                symbols=symbols,
                ocr_extractions=ocr_extractions,
                document_id=document_id,
                drawing_number=metadata.drawing_number,
            )

            # Enforce limits
            if len(equipment) > config.max_equipment_per_drawing:
                warnings.append(
                    f"Equipment count ({len(equipment)}) exceeds maximum "
                    f"({config.max_equipment_per_drawing}); truncated."
                )
                equipment = equipment[:config.max_equipment_per_drawing]

            # Step 6: Relationship extraction
            relationships = extract_relationships(
                equipment=equipment,
                symbols=symbols,
                text=text,
                document_id=document_id,
            )

            if len(relationships) > config.max_relationships_per_drawing:
                warnings.append(
                    f"Relationship count ({len(relationships)}) exceeds maximum "
                    f"({config.max_relationships_per_drawing}); truncated."
                )
                relationships = relationships[:config.max_relationships_per_drawing]

            # Step 7: Integrate with Knowledge Graph
            cls._update_knowledge_graph(
                equipment=equipment,
                relationships=relationships,
                document_id=document_id,
                drawing_type=classification.drawing_type,
                drawing_number=metadata.drawing_number,
            )

        except VisionError:
            raise
        except Exception as exc:
            raise VisionError(
                f"Drawing analysis failed for document {document_id}: {exc}"
            ) from exc

        duration = round(time.time() - start_time, 3)

        logger.info(
            "Drawing analysis complete for document %s: type=%s, "
            "%d symbols, %d equipment, %d relationships (%.2fs).",
            document_id,
            classification.drawing_type,
            len(symbols),
            len(equipment),
            len(relationships),
            duration,
        )

        return DrawingAnalysisResult(
            document_id=document_id,
            drawing_type=classification.drawing_type,
            classification_confidence=classification.confidence,
            metadata=metadata,
            ocr_extractions=ocr_extractions,
            detected_symbols=symbols,
            equipment=equipment,
            relationships=relationships,
            duration_seconds=duration,
            warnings=warnings,
        )

    @classmethod
    def is_engineering_drawing(cls, text: str) -> bool:
        """
        Quick check: is this document likely an engineering drawing?

        Returns True if the classification result is anything other than
        'unknown' or 'standard_document' with reasonable confidence.
        """
        if not text:
            return False
        classification = classify_drawing(text)
        if classification.drawing_type == "unknown":
            return False
        if classification.drawing_type == "standard_document" and classification.confidence < 0.3:
            return False
        return classification.confidence >= 0.2

    @classmethod
    def _update_knowledge_graph(
        cls,
        equipment: list,
        relationships: list,
        document_id: str,
        drawing_type: str,
        drawing_number: str,
    ) -> None:
        """
        Adds extracted equipment and relationships to the Knowledge Graph.
        """
        # Add equipment as entities
        entity_id_map: dict[str, str] = {}  # tag -> entity_id

        for eq in equipment:
            entity = Entity(
                entity_type=eq.equipment_type,
                name=eq.tag,
                aliases=[eq.name] if eq.name != eq.tag else [],
                source_document_ids=[document_id],
                confidence=eq.confidence,
                metadata={
                    "drawing_type": drawing_type,
                    "drawing_number": drawing_number,
                    "source": "drawing_analysis",
                },
            )
            GraphService.add_entity(entity)
            entity_id_map[eq.tag] = entity.entity_id

        # Add relationships as edges
        for rel in relationships:
            source_id = entity_id_map.get(rel.source_equipment, rel.source_equipment)
            target_id = entity_id_map.get(rel.target_equipment, rel.target_equipment)

            graph_rel = Relationship(
                relationship_type=rel.relationship_type,
                source_entity_id=source_id,
                target_entity_id=target_id,
                source_document_id=document_id,
                confidence=rel.confidence,
                metadata={
                    "drawing_type": drawing_type,
                    "source": "drawing_analysis",
                },
            )
            GraphService.add_relationship(graph_rel)

        if equipment:
            GraphService._persist()


    # ------------------------------------------------------------------
    # Enhanced Drawing Intelligence (Sprint 18)
    # ------------------------------------------------------------------

    @classmethod
    def analyze_drawing_enhanced(
        cls,
        text: str,
        document_id: str,
        config: VisionConfig | None = None,
    ) -> dict:
        """
        Enhanced drawing analysis: runs the standard pipeline + Gemini
        Vision analysis + structured warnings + caching.

        Returns a comprehensive dict suitable for embedding into
        operations reports, RAG retrieval, and executive briefings.

        Does NOT change the existing analyze_drawing() interface.
        """
        from agents.config import RAGConfig
        from vision.cache import get_cached_analysis, set_cached_analysis
        from vision.drawing_warnings import generate_drawing_warnings
        from vision.gemini_analysis import analyze_with_gemini

        # Check cache first
        cached = get_cached_analysis(document_id)
        if cached:
            logger.info("Drawing analysis cache hit for %s.", document_id)
            return cached

        # Run standard analysis
        result = cls.analyze_drawing(text, document_id, config)

        # Gemini-powered deep analysis (reuses GeminiService)
        equipment_tags = [eq.tag for eq in result.equipment if eq.tag]
        rag_config = RAGConfig.from_settings()
        gemini_insights = analyze_with_gemini(
            text=text,
            equipment_tags=equipment_tags,
            drawing_type=result.drawing_type,
            config=rag_config,
        )

        # Generate structured warnings
        drawing_warnings = generate_drawing_warnings(result)

        # Compose enhanced result
        enhanced = {
            "document_id": document_id,
            "drawing_type": result.drawing_type,
            "classification_confidence": result.classification_confidence,
            "metadata": result.metadata.to_dict(),
            "equipment": [eq.to_dict() for eq in result.equipment],
            "equipment_count": result.equipment_count,
            "relationships": [r.to_dict() for r in result.relationships],
            "relationship_count": result.relationship_count,
            "symbols": [s.to_dict() for s in result.detected_symbols],
            "symbol_count": result.symbol_count,
            "ocr_extractions": [o.to_dict() for o in result.ocr_extractions],
            "gemini_insights": gemini_insights,
            "drawing_warnings": [w.to_dict() for w in drawing_warnings],
            "warning_count": len(drawing_warnings),
            "duration_seconds": result.duration_seconds,
        }

        # Cache the result
        set_cached_analysis(document_id, enhanced)

        logger.info(
            "Enhanced drawing analysis for %s: %d equipment, %d warnings, "
            "%d Gemini insights.",
            document_id,
            result.equipment_count,
            len(drawing_warnings),
            len(gemini_insights),
        )

        return enhanced

    @classmethod
    def get_drawing_context_for_rag(cls, document_id: str, text: str = "") -> str:
        """
        Produces a text summary of drawing analysis suitable for
        inclusion in RAG context. Called by retrieval services to
        enrich results with drawing knowledge.
        """
        from vision.cache import get_cached_analysis

        cached = get_cached_analysis(document_id)
        if not cached and text:
            cached = cls.analyze_drawing_enhanced(text, document_id)

        if not cached:
            return ""

        parts = [f"Engineering Drawing ({cached.get('drawing_type', 'unknown')})"]

        equipment = cached.get("equipment", [])
        if equipment:
            tags = [e.get("tag", "") for e in equipment[:10] if e.get("tag")]
            parts.append(f"Equipment: {', '.join(tags)}")

        relationships = cached.get("relationships", [])
        if relationships:
            conns = [f"{r.get('source_equipment','?')} → {r.get('target_equipment','?')}" for r in relationships[:5]]
            parts.append(f"Connections: {'; '.join(conns)}")

        warnings = cached.get("drawing_warnings", [])
        if warnings:
            parts.append(f"Warnings: {len(warnings)} ({', '.join(w.get('issue','')[:40] for w in warnings[:3])})")

        insights = cached.get("gemini_insights", {})
        if insights.get("insights"):
            parts.append(f"Analysis: {insights['insights'][:200]}")

        return " | ".join(parts)
