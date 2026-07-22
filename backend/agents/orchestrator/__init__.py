"""
Query Orchestrator — the central coordinator for the RAG pipeline.

Receives a user query, determines intent, selects retrieval strategy,
performs hybrid retrieval, builds context, invokes the LLM, and returns
a structured response with citations and confidence.
"""

import logging
import re
import time
from dataclasses import dataclass, field

from agents.config import QUERY_INTENTS, RAGConfig
from agents.context import BuiltContext, Citation, ContextBuilder
from agents.exceptions import AgentError, OrchestrationError
from agents.llm import GeminiService, LLMResponse
from agents.memory import ConversationMemory
from agents.retrieval import RAGRetrievalService, RetrievalResult

logger = logging.getLogger("agents.orchestrator")


@dataclass
class QueryIntent:
    """Detected intent of a user query."""

    intent: str = "general_question"
    confidence: float = 0.5
    entities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "confidence": self.confidence,
            "entities": self.entities,
        }


@dataclass
class OrchestratorResponse:
    """Structured response from the orchestrator."""

    answer: str = ""
    confidence: float = 0.0
    citations: list[dict] = field(default_factory=list)
    related_documents: list[str] = field(default_factory=list)
    related_equipment: list[str] = field(default_factory=list)
    knowledge_graph_references: list[str] = field(default_factory=list)
    drawing_references: list[str] = field(default_factory=list)
    suggested_followups: list[str] = field(default_factory=list)
    intent: QueryIntent = field(default_factory=QueryIntent)
    retrieval_summary: dict = field(default_factory=dict)
    maintenance_analysis: dict | None = None
    compliance_analysis: dict | None = None
    operations_report: dict | None = None
    duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        result = {
            "answer": self.answer,
            "confidence": self.confidence,
            "citations": self.citations,
            "related_documents": self.related_documents,
            "related_equipment": self.related_equipment,
            "knowledge_graph_references": self.knowledge_graph_references,
            "drawing_references": self.drawing_references,
            "suggested_followups": self.suggested_followups,
            "intent": self.intent.to_dict(),
            "retrieval_summary": self.retrieval_summary,
            "duration_seconds": self.duration_seconds,
        }
        if self.maintenance_analysis:
            result["maintenance_analysis"] = self.maintenance_analysis
        if self.compliance_analysis:
            result["compliance_analysis"] = self.compliance_analysis
        if self.operations_report:
            result["operations_report"] = self.operations_report
        return result


# Intent detection patterns
INTENT_PATTERNS: dict[str, list[re.Pattern]] = {
    "maintenance": [
        re.compile(r"\b(?:maintenance|repair|overhaul|replace|lubricate|service)\b", re.IGNORECASE),
        re.compile(r"\b(?:preventive|corrective|predictive|PM|CM)\b", re.IGNORECASE),
        re.compile(r"\b(?:vibrat\w*|overheat\w*|leak\w*|cavitat\w*|corrosion|fatigue|misalign\w*|bearing)", re.IGNORECASE),
        re.compile(r"\b(?:fail\w*|broke\w*|broken|damage\w*|worn|defect\w*)", re.IGNORECASE),
        re.compile(r"\b(?:inspection|inspect\w*|checklist|schedule)", re.IGNORECASE),
    ],
    "compliance": [
        re.compile(r"\b(?:compliance|regulation|standard|ISO|API|OSHA|ASME|IEC|NFPA|code)\b", re.IGNORECASE),
        re.compile(r"\b(?:audit|certification|inspection\s+requirement)\b", re.IGNORECASE),
        re.compile(r"\b(?:CAPA|NCR|non[-\s]?conform\w*|deviation)\b", re.IGNORECASE),
        re.compile(r"\b(?:quality|QMS|calibrat\w*|SOP\b)", re.IGNORECASE),
        re.compile(r"\b(?:complian\w*|gap\s+analysis|missing\s+document)\b", re.IGNORECASE),
    ],
    "drawing_lookup": [
        re.compile(r"\b(?:P&ID|drawing|diagram|schematic|PFD|SLD|GA)\b", re.IGNORECASE),
        re.compile(r"\b(?:piping|instrumentation|electrical)\s+(?:drawing|diagram)\b", re.IGNORECASE),
    ],
    "equipment_lookup": [
        re.compile(r"\b(?:pump|valve|compressor|motor|tank|heat\s+exchanger|instrument)\b", re.IGNORECASE),
        re.compile(r"\b[A-Z]{1,3}[-_]\d{3,}[A-Z]?\b"),
    ],
    "document_lookup": [
        re.compile(r"\b(?:document|manual|procedure|SOP|report|datasheet)\b", re.IGNORECASE),
    ],
    "incident_lookup": [
        re.compile(r"\b(?:incident|failure|breakdown|trip|alarm|shutdown)\b", re.IGNORECASE),
    ],
}


class QueryOrchestrator:
    """
    Central RAG orchestrator.

    Usage:
        response = QueryOrchestrator.process_query(
            query="What pump is in area 3?",
            session_id="sess-123",
        )
    """

    @classmethod
    def process_query(
        cls,
        query: str,
        session_id: str = "",
        config: RAGConfig | None = None,
        query_embedding: list[float] | None = None,
    ) -> OrchestratorResponse:
        """
        Full RAG pipeline: intent → retrieval → context → LLM → response.

        Args:
            query: The user's question.
            session_id: Optional session ID for conversation memory.
            config: Optional config override.
            query_embedding: Pre-computed query embedding (if None,
                only KG search is performed — no semantic search).

        Returns:
            OrchestratorResponse with answer, citations, and metadata.
        """
        start_time = time.time()

        if config is None:
            config = RAGConfig.from_settings()

        if not query or not query.strip():
            return OrchestratorResponse(
                answer="Please provide a question.",
                confidence=0.0,
            )

        logger.info("Processing query: %s", query[:100])

        # Step 1: Detect intent
        intent = cls.detect_intent(query)

        # Step 2: Get conversation history
        history = None
        if session_id:
            session = ConversationMemory.get_or_create(session_id)
            history = session.get_history()

        # Step 3: Hybrid retrieval
        retrieval_result = RAGRetrievalService.retrieve(
            query=query,
            query_embedding=query_embedding,
            config=config,
        )

        # Step 4: Build context
        built_context = ContextBuilder.build(
            query=query,
            retrieval_result=retrieval_result,
            config=config,
            conversation_history=history,
        )

        # Step 5: Generate response via LLM (if API key available)
        answer = ""
        llm_confidence = 0.0

        if config.api_key:
            try:
                llm_response = GeminiService.generate(
                    prompt=built_context.user_prompt,
                    config=config,
                    system_instruction=built_context.system_prompt,
                )
                answer = llm_response.text
                llm_confidence = 0.8 if answer else 0.0
            except AgentError as exc:
                logger.warning("LLM generation failed: %s", exc)
                answer = cls._build_fallback_answer(retrieval_result)
                llm_confidence = 0.3
        else:
            # No API key — return retrieval results directly
            answer = cls._build_fallback_answer(retrieval_result)
            llm_confidence = 0.4 if retrieval_result.hits else 0.0

        # Step 6: Build structured response
        citations = [c.to_dict() for c in built_context.citations]
        related_docs = list(set(
            h.document_id for h in retrieval_result.hits if h.document_id
        ))
        related_equipment = list(set(
            h.metadata.get("name", "")
            for h in retrieval_result.hits
            if h.source == "knowledge_graph" and h.metadata.get("name")
        ))
        kg_refs = list(set(
            h.entity_id for h in retrieval_result.hits
            if h.entity_id
        ))
        drawing_refs = list(set(
            h.metadata.get("drawing_number", "")
            for h in retrieval_result.hits
            if h.metadata.get("drawing_number")
        ))

        # Step 7: Update conversation memory
        if session_id:
            session = ConversationMemory.get_or_create(session_id)
            session.add_turn("user", query)
            session.add_turn("assistant", answer[:500])

        # Step 8: Run Maintenance Agent if intent matches
        maintenance_analysis = None
        if intent.intent in ("maintenance", "incident_lookup"):
            try:
                from agents.maintenance import MaintenanceAgent
                maint_result = MaintenanceAgent.analyze(
                    query=query,
                    query_embedding=query_embedding,
                    config=config,
                )
                maintenance_analysis = maint_result.to_dict()
                # Enrich response with maintenance-specific data
                if maint_result.suggested_followups:
                    suggested_followups = maint_result.suggested_followups
                if maint_result.related_equipment:
                    related_equipment = list(set(related_equipment + maint_result.related_equipment))
                if maint_result.related_drawings:
                    drawing_refs = list(set(drawing_refs + maint_result.related_drawings))
            except Exception as exc:
                logger.warning("Maintenance agent failed: %s", exc)

        # Step 9: Run Compliance Agent if intent matches
        compliance_analysis = None
        if intent.intent == "compliance":
            try:
                from agents.compliance import QualityComplianceAgent
                comp_result = QualityComplianceAgent.analyze(
                    query=query,
                    query_embedding=query_embedding,
                    config=config,
                )
                compliance_analysis = comp_result.to_dict()
                # Enrich response
                if comp_result.suggested_followups:
                    suggested_followups = comp_result.suggested_followups
                if comp_result.related_equipment:
                    related_equipment = list(set(related_equipment + comp_result.related_equipment))
                if comp_result.related_drawings:
                    drawing_refs = list(set(drawing_refs + comp_result.related_drawings))
            except Exception as exc:
                logger.warning("Compliance agent failed: %s", exc)

        # Step 10: Run Operations Intelligence for complex industrial queries
        operations_report = None
        is_complex = (
            intent.intent in ("maintenance", "incident_lookup", "compliance")
            and intent.confidence >= 0.3
            and (maintenance_analysis or compliance_analysis)
        )
        if is_complex:
            try:
                from agents.operations import OperationsIntelligenceOrchestrator
                ops_result = OperationsIntelligenceOrchestrator.execute(
                    query=query,
                    query_embedding=query_embedding,
                    config=config,
                )
                operations_report = ops_result.to_dict()
            except Exception as exc:
                logger.warning("Operations intelligence failed: %s", exc)

        duration = round(time.time() - start_time, 3)

        # Generate follow-ups (may be overridden by agents)
        final_followups = cls._generate_followups(intent, retrieval_result)
        if maintenance_analysis and maintenance_analysis.get("suggested_followups"):
            final_followups = maintenance_analysis["suggested_followups"]
        elif compliance_analysis and compliance_analysis.get("suggested_followups"):
            final_followups = compliance_analysis["suggested_followups"]

        return OrchestratorResponse(
            answer=answer,
            confidence=llm_confidence,
            citations=citations,
            related_documents=related_docs[:10],
            related_equipment=related_equipment[:10],
            knowledge_graph_references=kg_refs[:10],
            drawing_references=drawing_refs[:5],
            suggested_followups=final_followups,
            intent=intent,
            retrieval_summary=retrieval_result.to_dict(),
            maintenance_analysis=maintenance_analysis,
            compliance_analysis=compliance_analysis,
            operations_report=operations_report,
            duration_seconds=duration,
        )

    @classmethod
    def detect_intent(cls, query: str) -> QueryIntent:
        """Detects the intent of a user query using pattern matching."""
        scores: dict[str, float] = {}
        entities: list[str] = []

        for intent_type, patterns in INTENT_PATTERNS.items():
            for pattern in patterns:
                matches = pattern.findall(query)
                if matches:
                    scores[intent_type] = scores.get(intent_type, 0) + len(matches)
                    entities.extend(matches[:3])

        if not scores:
            return QueryIntent(
                intent="general_question",
                confidence=0.5,
                entities=entities[:5],
            )

        # Priority: action intents (maintenance, compliance, incident) take
        # precedence over entity-identifying intents (equipment_lookup) when
        # both match, because the user is asking ABOUT the equipment, not
        # just looking it up.
        action_intents = {"maintenance", "compliance", "incident_lookup"}
        entity_intents = {"equipment_lookup"}

        # If an action intent scored AND equipment_lookup also scored,
        # boost the action intent to win the tiebreak.
        if any(i in scores for i in action_intents) and "equipment_lookup" in scores:
            for ai in action_intents:
                if ai in scores:
                    scores[ai] += 1.5  # boost action intent

        best_intent = max(scores, key=scores.get)
        confidence = min(scores[best_intent] / 3.0, 1.0)

        return QueryIntent(
            intent=best_intent,
            confidence=round(confidence, 2),
            entities=list(set(entities))[:5],
        )

    @classmethod
    def _build_fallback_answer(cls, retrieval_result: RetrievalResult) -> str:
        """Builds a direct answer from retrieval results when LLM is unavailable."""
        if not retrieval_result.hits:
            return "No relevant information found for your query."

        parts = ["Based on available information:\n"]
        for i, hit in enumerate(retrieval_result.hits[:5], 1):
            content = hit.content[:200]
            parts.append(f"[Source {i}] {content}")

        return "\n\n".join(parts)

    @classmethod
    def _generate_followups(
        cls, intent: QueryIntent, retrieval: RetrievalResult
    ) -> list[str]:
        """Generates suggested follow-up questions based on context."""
        followups = []

        if intent.intent == "equipment_lookup":
            followups.append("What maintenance is required for this equipment?")
            followups.append("What are the connected systems?")
        elif intent.intent == "maintenance":
            followups.append("What are the safety procedures?")
            followups.append("What spare parts are needed?")
        elif intent.intent == "compliance":
            followups.append("What equipment does this regulation apply to?")
        elif intent.intent == "drawing_lookup":
            followups.append("What equipment is shown in this drawing?")
            followups.append("What are the latest revisions?")

        return followups[:3]
