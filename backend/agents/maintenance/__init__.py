"""
Maintenance Intelligence & Root Cause Analysis Agent.

Acts as an experienced maintenance engineer: analyzes equipment issues,
performs structured RCA, generates recommendations, and retrieves
maintenance history — all grounded in the existing Knowledge Graph,
ChromaDB, and document corpus.

Reuses:
    - RAGRetrievalService (hybrid retrieval)
    - GeminiService (LLM generation)
    - KnowledgeGraphService (equipment relationships)
    - ConversationMemory (session context)

Does NOT duplicate any existing retrieval or generation logic.
"""

import logging
import re
import time
from dataclasses import dataclass, field

from agents.config import RAGConfig
from agents.llm import GeminiService
from agents.retrieval import RAGRetrievalService, RetrievalResult

logger = logging.getLogger("agents.maintenance")


# -------------------------------------------------------------------------
# Failure Mode Taxonomy
# -------------------------------------------------------------------------
FAILURE_MODES = [
    "bearing_wear",
    "seal_leakage",
    "corrosion",
    "fatigue",
    "misalignment",
    "cavitation",
    "overheating",
    "vibration",
    "lubrication_failure",
    "sensor_failure",
    "electrical_failure",
    "mechanical_failure",
    "erosion",
    "fouling",
    "blockage",
]

FAILURE_PATTERNS: dict[str, list[re.Pattern]] = {
    "bearing_wear": [re.compile(r"\b(?:bearing|bearings)\s*(?:\w+\s+)?(?:wear|worn|failure|noise|hot|damage)\b", re.IGNORECASE)],
    "seal_leakage": [re.compile(r"\b(?:seal|seals|gasket)\s*(?:\w+\s+)?(?:leak|leaking|failed|damaged)\b", re.IGNORECASE)],
    "corrosion": [re.compile(r"\b(?:corrosion|corroded|rusted|pitting|rust)\b", re.IGNORECASE)],
    "fatigue": [re.compile(r"\b(?:fatigue|crack|cracked|fracture)\b", re.IGNORECASE)],
    "misalignment": [re.compile(r"\b(?:misalign|misalignment|offset|angular)\b", re.IGNORECASE)],
    "cavitation": [re.compile(r"\b(?:cavitation|cavitating|low\s+suction|NPSH)\b", re.IGNORECASE)],
    "overheating": [re.compile(r"\b(?:overheat|overheating|hot|temperature\s+high|thermal)\b", re.IGNORECASE)],
    "vibration": [re.compile(r"\b(?:vibrat\w*|shaking|unbalance|imbalance)\b", re.IGNORECASE)],
    "lubrication_failure": [re.compile(r"\b(?:lubricat|lubrication|oil\s+low|grease|dry\s+running)\b", re.IGNORECASE)],
    "sensor_failure": [re.compile(r"\b(?:sensor\s+fail|false\s+reading|instrument\s+error|calibrat)\b", re.IGNORECASE)],
    "electrical_failure": [re.compile(r"\b(?:electrical|winding|insulation|motor\s+trip|overcurrent)\b", re.IGNORECASE)],
    "mechanical_failure": [re.compile(r"\b(?:mechanical\s+fail|shaft\s+break|coupling|impeller\s+damage)\b", re.IGNORECASE)],
}


# -------------------------------------------------------------------------
# Data Models
# -------------------------------------------------------------------------

@dataclass
class RootCause:
    """A single possible root cause."""
    cause: str = ""
    likelihood: str = "medium"  # high, medium, low
    evidence: list[str] = field(default_factory=list)
    confidence: float = 0.5

    def to_dict(self) -> dict:
        return {
            "cause": self.cause,
            "likelihood": self.likelihood,
            "evidence": self.evidence,
            "confidence": self.confidence,
        }


@dataclass
class MaintenanceRecommendation:
    """A structured maintenance recommendation."""
    action: str = ""
    priority: str = "medium"  # critical, high, medium, low
    category: str = ""  # corrective, preventive, inspection
    details: str = ""
    spare_parts: list[str] = field(default_factory=list)
    safety_precautions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "priority": self.priority,
            "category": self.category,
            "details": self.details,
            "spare_parts": self.spare_parts,
            "safety_precautions": self.safety_precautions,
        }


@dataclass
class MaintenanceAnalysisResult:
    """Complete output of the maintenance agent."""
    query: str = ""
    equipment_tag: str = ""
    problem_summary: str = ""
    detected_failure_modes: list[str] = field(default_factory=list)
    root_causes: list[RootCause] = field(default_factory=list)
    corrective_actions: list[MaintenanceRecommendation] = field(default_factory=list)
    preventive_actions: list[MaintenanceRecommendation] = field(default_factory=list)
    inspection_recommendations: list[str] = field(default_factory=list)
    risk_level: str = "medium"  # critical, high, medium, low
    confidence: float = 0.0
    maintenance_history: list[dict] = field(default_factory=list)
    supporting_documents: list[str] = field(default_factory=list)
    related_equipment: list[str] = field(default_factory=list)
    related_drawings: list[str] = field(default_factory=list)
    knowledge_graph_context: list[dict] = field(default_factory=list)
    ai_analysis: str = ""
    suggested_followups: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "equipment_tag": self.equipment_tag,
            "problem_summary": self.problem_summary,
            "detected_failure_modes": self.detected_failure_modes,
            "root_causes": [rc.to_dict() for rc in self.root_causes],
            "corrective_actions": [a.to_dict() for a in self.corrective_actions],
            "preventive_actions": [a.to_dict() for a in self.preventive_actions],
            "inspection_recommendations": self.inspection_recommendations,
            "risk_level": self.risk_level,
            "confidence": self.confidence,
            "maintenance_history": self.maintenance_history,
            "supporting_documents": self.supporting_documents,
            "related_equipment": self.related_equipment,
            "related_drawings": self.related_drawings,
            "knowledge_graph_context": self.knowledge_graph_context,
            "ai_analysis": self.ai_analysis,
            "suggested_followups": self.suggested_followups,
            "duration_seconds": self.duration_seconds,
        }


# -------------------------------------------------------------------------
# Maintenance Agent Service
# -------------------------------------------------------------------------

MAINTENANCE_SYSTEM_PROMPT = """You are an expert industrial maintenance engineer with 20+ years of experience in root cause analysis, preventive maintenance, and equipment reliability.

Your role:
- Analyze equipment problems and identify root causes
- Recommend corrective and preventive actions
- Prioritize maintenance activities based on risk
- Reference specific documents, standards, and best practices

Rules:
- Base your analysis ONLY on the provided context and evidence
- Clearly distinguish between confirmed facts and likely causes
- Assign confidence levels to each root cause
- Always recommend safety precautions
- If information is insufficient, say so clearly
- Use [Source N] notation to cite evidence
- Never fabricate maintenance history or inspection results
"""


class MaintenanceAgent:
    """
    Maintenance Intelligence & Root Cause Analysis Agent.

    Usage:
        result = MaintenanceAgent.analyze(query, query_embedding, config)
    """

    @classmethod
    def analyze(
        cls,
        query: str,
        query_embedding: list[float] | None = None,
        config: RAGConfig | None = None,
    ) -> MaintenanceAnalysisResult:
        """
        Performs full maintenance analysis including RCA.

        Args:
            query: The user's maintenance-related question.
            query_embedding: Pre-computed query embedding for semantic search.
            config: Optional RAG config override.

        Returns:
            MaintenanceAnalysisResult with structured analysis.
        """
        start_time = time.time()

        if config is None:
            config = RAGConfig.from_settings()

        if not query or not query.strip():
            return MaintenanceAnalysisResult(
                query=query,
                problem_summary="No query provided.",
            )

        logger.info("Maintenance agent analyzing: %s", query[:100])

        # Step 1: Extract equipment tag from query
        equipment_tag = cls._extract_equipment_tag(query)

        # Step 2: Detect failure modes from query
        failure_modes = cls._detect_failure_modes(query)

        # Step 3: Hybrid retrieval (reuse existing service)
        retrieval_result = RAGRetrievalService.retrieve(
            query=query,
            query_embedding=query_embedding,
            config=config,
        )

        # Step 4: Get KG context for the equipment
        kg_context = cls._get_equipment_context(equipment_tag)

        # Step 5: Generate root causes based on evidence
        root_causes = cls._generate_root_causes(failure_modes, retrieval_result)

        # Step 6: Generate recommendations
        corrective_actions = cls._generate_corrective_actions(failure_modes, root_causes)
        preventive_actions = cls._generate_preventive_actions(equipment_tag, failure_modes)
        inspection_recs = cls._generate_inspection_recommendations(equipment_tag, failure_modes)

        # Step 7: Assess risk
        risk_level = cls._assess_risk(failure_modes, root_causes)

        # Step 8: AI-powered analysis via Gemini (if API key available)
        ai_analysis = ""
        confidence = 0.0

        if config.api_key and retrieval_result.hits:
            ai_analysis, confidence = cls._run_llm_analysis(
                query, retrieval_result, failure_modes, equipment_tag, config
            )
        elif retrieval_result.hits:
            ai_analysis = cls._build_evidence_summary(retrieval_result)
            confidence = 0.4
        else:
            ai_analysis = "Insufficient data for analysis. Upload relevant maintenance documents."
            confidence = 0.1

        # Step 9: Generate follow-ups
        followups = cls._generate_followups(equipment_tag, failure_modes)

        duration = round(time.time() - start_time, 3)

        return MaintenanceAnalysisResult(
            query=query,
            equipment_tag=equipment_tag,
            problem_summary=cls._build_problem_summary(query, equipment_tag, failure_modes),
            detected_failure_modes=failure_modes,
            root_causes=root_causes,
            corrective_actions=corrective_actions,
            preventive_actions=preventive_actions,
            inspection_recommendations=inspection_recs,
            risk_level=risk_level,
            confidence=confidence,
            maintenance_history=[h.to_dict() for h in retrieval_result.hits[:5] if h.source == "chromadb"],
            supporting_documents=list(set(h.document_id for h in retrieval_result.hits if h.document_id))[:10],
            related_equipment=list(set(h.metadata.get("name", "") for h in retrieval_result.hits if h.source == "knowledge_graph" and h.metadata.get("name")))[:10],
            related_drawings=[h.metadata.get("drawing_number", "") for h in retrieval_result.hits if h.metadata.get("drawing_number")][:5],
            knowledge_graph_context=kg_context[:10],
            ai_analysis=ai_analysis,
            suggested_followups=followups,
            duration_seconds=duration,
        )

    @classmethod
    def _extract_equipment_tag(cls, query: str) -> str:
        """Extracts equipment tag from query text."""
        tag_pattern = re.compile(r"\b([A-Z]{1,4}[-_]\d{3,}[A-Z]?)\b")
        match = tag_pattern.search(query)
        if match:
            return match.group(1)
        # Try common equipment names
        equip_pattern = re.compile(r"\b((?:pump|valve|compressor|motor|tank|heat\s+exchanger)\s+[\w\-]+)", re.IGNORECASE)
        match = equip_pattern.search(query)
        return match.group(1).strip() if match else ""

    @classmethod
    def _detect_failure_modes(cls, query: str) -> list[str]:
        """Detects likely failure modes from query text."""
        detected = []
        for mode, patterns in FAILURE_PATTERNS.items():
            for pattern in patterns:
                if pattern.search(query):
                    detected.append(mode)
                    break
        return detected

    @classmethod
    def _get_equipment_context(cls, equipment_tag: str) -> list[dict]:
        """Gets Knowledge Graph context for equipment."""
        if not equipment_tag:
            return []
        from knowledge_graph.service import KnowledgeGraphService
        entities = KnowledgeGraphService.search_entities(equipment_tag)
        context = []
        for entity in entities[:5]:
            related = KnowledgeGraphService.get_related_entities(entity.get("entity_id", ""))
            context.append({
                "entity": entity.get("name", ""),
                "type": entity.get("entity_type", ""),
                "related": [r.get("name", "") for r in related[:5]],
            })
        return context

    @classmethod
    def _generate_root_causes(
        cls, failure_modes: list[str], retrieval: RetrievalResult
    ) -> list[RootCause]:
        """Generates structured root causes based on evidence."""
        root_causes = []
        cause_map = {
            "vibration": [
                RootCause(cause="Bearing wear or damage", likelihood="high", confidence=0.7),
                RootCause(cause="Shaft misalignment", likelihood="high", confidence=0.65),
                RootCause(cause="Impeller imbalance", likelihood="medium", confidence=0.5),
                RootCause(cause="Loose foundation bolts", likelihood="medium", confidence=0.45),
            ],
            "overheating": [
                RootCause(cause="Insufficient lubrication", likelihood="high", confidence=0.7),
                RootCause(cause="Bearing failure", likelihood="high", confidence=0.65),
                RootCause(cause="Overloading", likelihood="medium", confidence=0.5),
                RootCause(cause="Cooling system blockage", likelihood="medium", confidence=0.45),
            ],
            "seal_leakage": [
                RootCause(cause="Seal face wear", likelihood="high", confidence=0.7),
                RootCause(cause="Shaft runout", likelihood="medium", confidence=0.55),
                RootCause(cause="Incorrect seal installation", likelihood="medium", confidence=0.5),
            ],
            "cavitation": [
                RootCause(cause="Low NPSH available", likelihood="high", confidence=0.75),
                RootCause(cause="Suction line restriction", likelihood="high", confidence=0.65),
                RootCause(cause="Excessive flow rate", likelihood="medium", confidence=0.5),
            ],
            "corrosion": [
                RootCause(cause="Chemical attack from process fluid", likelihood="high", confidence=0.7),
                RootCause(cause="Inadequate material selection", likelihood="medium", confidence=0.55),
                RootCause(cause="Environmental exposure", likelihood="medium", confidence=0.5),
            ],
            "bearing_wear": [
                RootCause(cause="End of service life", likelihood="high", confidence=0.7),
                RootCause(cause="Contaminated lubricant", likelihood="high", confidence=0.65),
                RootCause(cause="Excessive loading", likelihood="medium", confidence=0.5),
            ],
            "misalignment": [
                RootCause(cause="Thermal growth", likelihood="high", confidence=0.65),
                RootCause(cause="Foundation settlement", likelihood="medium", confidence=0.55),
                RootCause(cause="Improper coupling installation", likelihood="medium", confidence=0.5),
            ],
            "lubrication_failure": [
                RootCause(cause="Oil degradation", likelihood="high", confidence=0.7),
                RootCause(cause="Incorrect lubricant type", likelihood="medium", confidence=0.55),
                RootCause(cause="Blocked oil passages", likelihood="medium", confidence=0.5),
            ],
        }

        for mode in failure_modes:
            if mode in cause_map:
                for rc in cause_map[mode]:
                    # Add evidence from retrieval hits
                    evidence = [h.content[:100] for h in retrieval.hits[:2] if h.content]
                    rc.evidence = evidence
                    root_causes.append(rc)

        # If no specific failure modes detected, provide general causes
        if not root_causes and retrieval.hits:
            root_causes.append(RootCause(
                cause="Further investigation required — analyze retrieved documents",
                likelihood="medium",
                evidence=[h.content[:100] for h in retrieval.hits[:3]],
                confidence=0.3,
            ))

        return root_causes[:8]

    @classmethod
    def _generate_corrective_actions(
        cls, failure_modes: list[str], root_causes: list[RootCause]
    ) -> list[MaintenanceRecommendation]:
        """Generates corrective action recommendations."""
        actions = []
        action_map = {
            "vibration": MaintenanceRecommendation(
                action="Perform vibration analysis and bearing inspection",
                priority="high", category="corrective",
                details="Check bearing condition, shaft alignment, and foundation bolts.",
                spare_parts=["Bearings", "Coupling elements"],
                safety_precautions=["Lock-out/Tag-out", "Ensure equipment is de-energized"],
            ),
            "overheating": MaintenanceRecommendation(
                action="Inspect cooling system and lubrication",
                priority="critical", category="corrective",
                details="Check oil level, cooling water flow, and bearing temperature.",
                spare_parts=["Lubricant", "Temperature sensor"],
                safety_precautions=["Allow equipment to cool", "Use thermal PPE"],
            ),
            "seal_leakage": MaintenanceRecommendation(
                action="Replace mechanical seal",
                priority="high", category="corrective",
                details="Inspect seal faces, check shaft runout, replace seal assembly.",
                spare_parts=["Mechanical seal kit", "O-rings", "Gaskets"],
                safety_precautions=["Drain process fluid", "Use chemical-resistant PPE"],
            ),
            "cavitation": MaintenanceRecommendation(
                action="Check suction conditions and NPSH",
                priority="high", category="corrective",
                details="Verify suction pressure, check for blocked strainers, reduce flow if needed.",
                spare_parts=["Strainer element", "Suction valve"],
                safety_precautions=["Monitor during adjustment", "Verify process stability"],
            ),
            "corrosion": MaintenanceRecommendation(
                action="Perform thickness inspection and assess material condition",
                priority="high", category="corrective",
                details="UT thickness measurement, visual inspection, assess need for replacement.",
                spare_parts=["Replacement sections", "Coating materials"],
                safety_precautions=["Scaffold safety", "Confined space if applicable"],
            ),
        }

        for mode in failure_modes:
            if mode in action_map:
                actions.append(action_map[mode])

        if not actions:
            actions.append(MaintenanceRecommendation(
                action="Perform general inspection and condition assessment",
                priority="medium", category="corrective",
                details="Visual inspection, operational checks, review maintenance history.",
                safety_precautions=["Follow site safety procedures"],
            ))

        return actions[:5]

    @classmethod
    def _generate_preventive_actions(
        cls, equipment_tag: str, failure_modes: list[str]
    ) -> list[MaintenanceRecommendation]:
        """Generates preventive maintenance recommendations."""
        actions = [
            MaintenanceRecommendation(
                action="Establish regular vibration monitoring",
                priority="medium", category="preventive",
                details="Monthly vibration readings at all bearing locations.",
            ),
            MaintenanceRecommendation(
                action="Review and update lubrication schedule",
                priority="medium", category="preventive",
                details="Verify lubricant type, quantity, and frequency per OEM recommendations.",
            ),
            MaintenanceRecommendation(
                action="Schedule alignment verification",
                priority="low", category="preventive",
                details="Laser alignment check after any maintenance intervention.",
            ),
        ]

        if "corrosion" in failure_modes:
            actions.insert(0, MaintenanceRecommendation(
                action="Implement corrosion monitoring program",
                priority="high", category="preventive",
                details="UT thickness surveys at defined intervals, corrosion coupon program.",
            ))

        return actions[:5]

    @classmethod
    def _generate_inspection_recommendations(
        cls, equipment_tag: str, failure_modes: list[str]
    ) -> list[str]:
        """Generates inspection checklist items."""
        inspections = [
            "Visual inspection of external condition",
            "Check for unusual noise or vibration",
            "Verify operating parameters within normal range",
            "Inspect foundation and mounting bolts",
            "Check for leaks at connections and seals",
        ]

        if "vibration" in failure_modes:
            inspections.insert(0, "Perform vibration spectrum analysis")
            inspections.insert(1, "Check bearing clearances")
        if "overheating" in failure_modes:
            inspections.insert(0, "Record bearing and casing temperatures")
            inspections.insert(1, "Verify cooling water flow")
        if "corrosion" in failure_modes:
            inspections.insert(0, "Ultrasonic thickness measurement")

        return inspections[:10]

    @classmethod
    def _assess_risk(cls, failure_modes: list[str], root_causes: list[RootCause]) -> str:
        """Assesses overall risk level."""
        critical_modes = {"overheating", "electrical_failure", "mechanical_failure"}
        high_modes = {"vibration", "seal_leakage", "cavitation", "corrosion"}

        if any(m in critical_modes for m in failure_modes):
            return "critical"
        if any(m in high_modes for m in failure_modes):
            return "high"
        if root_causes and max(rc.confidence for rc in root_causes) > 0.6:
            return "high"
        return "medium"

    @classmethod
    def _run_llm_analysis(
        cls, query: str, retrieval: RetrievalResult,
        failure_modes: list[str], equipment_tag: str, config: RAGConfig
    ) -> tuple[str, float]:
        """Runs Gemini for AI-powered analysis."""
        context_parts = []
        for i, hit in enumerate(retrieval.hits[:5], 1):
            if hit.content:
                context_parts.append(f"[Source {i}] {hit.content[:300]}")

        context = "\n\n".join(context_parts)
        prompt = f"""Analyze this maintenance question as an expert engineer.

Equipment: {equipment_tag or 'Unknown'}
Detected Issues: {', '.join(failure_modes) if failure_modes else 'None detected'}

Context from documents:
{context}

Question: {query}

Provide:
1. Problem analysis
2. Most likely root cause(s) with confidence
3. Recommended immediate actions
4. Preventive measures
"""
        try:
            response = GeminiService.generate(
                prompt=prompt,
                config=config,
                system_instruction=MAINTENANCE_SYSTEM_PROMPT,
            )
            return response.text, 0.75
        except Exception as exc:
            logger.warning("LLM analysis failed: %s", exc)
            return cls._build_evidence_summary(retrieval), 0.4

    @classmethod
    def _build_evidence_summary(cls, retrieval: RetrievalResult) -> str:
        """Builds a summary from retrieval results without LLM."""
        if not retrieval.hits:
            return "No relevant maintenance data found."
        parts = ["Based on available documentation:\n"]
        for i, hit in enumerate(retrieval.hits[:5], 1):
            parts.append(f"[Source {i}] {hit.content[:200]}")
        return "\n\n".join(parts)

    @classmethod
    def _build_problem_summary(cls, query: str, tag: str, modes: list[str]) -> str:
        """Builds a concise problem summary."""
        parts = []
        if tag:
            parts.append(f"Equipment: {tag}")
        if modes:
            parts.append(f"Detected issues: {', '.join(m.replace('_', ' ') for m in modes)}")
        parts.append(f"Query: {query[:100]}")
        return " | ".join(parts)

    @classmethod
    def _generate_followups(cls, equipment_tag: str, failure_modes: list[str]) -> list[str]:
        """Generates suggested follow-up questions."""
        followups = []
        if equipment_tag:
            followups.append(f"Show maintenance history for {equipment_tag}")
            followups.append(f"What inspections are due for {equipment_tag}?")
            followups.append(f"Show engineering drawing for {equipment_tag}")
        if failure_modes:
            followups.append("What spare parts are needed?")
            followups.append("Generate preventive maintenance checklist")
        followups.append("Find similar failures in other equipment")
        followups.append("Show related safety procedures")
        return followups[:6]
