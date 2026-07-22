"""
Operations Intelligence Orchestrator — executes multiple expert agents,
collects evidence, generates warnings, detects trends, and produces
structured enterprise operations reports.

This is the top-level intelligence layer. It does NOT duplicate retrieval;
it coordinates existing agents and composes their outputs.
"""

import logging
import time
from dataclasses import dataclass, field

from agents.composer import OperationsReport, ResponseComposerService
from agents.config import RAGConfig
from agents.failure import FailureIntelligenceAgent
from agents.llm import GeminiService
from agents.retrieval import RAGRetrievalService
from agents.trends import TrendAnalysisEngine
from agents.warnings import WarningEngine

logger = logging.getLogger("agents.operations")


OPS_SYSTEM_PROMPT = """You are IndusMind AI Operations Intelligence — an enterprise industrial operations command center.

You have access to outputs from multiple expert agents:
- Maintenance Intelligence (root cause analysis, risk, recommendations)
- Quality & Compliance (regulatory status, gaps, audit findings)
- Failure Intelligence (historical incidents, lessons learned, patterns)
- Knowledge Graph (equipment relationships, connected assets)
- Engineering Drawings (components, connections, standards)

Your role:
- Synthesize insights across ALL agent outputs into a coherent analysis
- Identify cross-domain risks (e.g. maintenance issue → compliance gap → safety risk)
- Prioritize actions based on combined evidence
- Generate an executive summary for operations management
- Reference specific evidence using [Source N] notation
- NEVER fabricate data — only reason over provided agent outputs
"""


class OperationsIntelligenceOrchestrator:
    """
    Coordinates parallel agent execution and produces enterprise reports.

    Usage:
        report = OperationsIntelligenceOrchestrator.execute(query, embedding, config)
    """

    @classmethod
    def execute(
        cls,
        query: str,
        query_embedding: list[float] | None = None,
        config: RAGConfig | None = None,
    ) -> OperationsReport:
        """
        Executes the full operations intelligence pipeline.

        1. Run agents (maintenance, compliance, failure intelligence)
        2. Collect structured outputs
        3. Generate warnings from evidence
        4. Analyze trends
        5. Run LLM synthesis (if API key available)
        6. Compose structured report
        """
        start_time = time.time()

        if config is None:
            config = RAGConfig.from_settings()

        if not query or not query.strip():
            return OperationsReport(executive_summary="No query provided.")

        logger.info("Operations Intelligence executing for: %s", query[:100])

        # Step 1: Execute agents (sequential — parallel in future with Celery)
        maintenance_data = cls._run_maintenance(query, query_embedding, config)
        compliance_data = cls._run_compliance(query, query_embedding, config)
        failure_data = cls._run_failure_intelligence(query, query_embedding, config)
        kg_context = cls._run_knowledge_graph(query)

        # Step 2: Generate warnings from agent outputs
        warnings = WarningEngine.generate_warnings(
            maintenance_data=maintenance_data,
            compliance_data=compliance_data,
            failure_data=failure_data,
        )

        # Step 3: Analyze trends
        trend_result = TrendAnalysisEngine.analyze(
            maintenance_data=maintenance_data,
            compliance_data=compliance_data,
            failure_data=failure_data,
        )

        # Step 4: LLM synthesis across all agent outputs
        ai_answer = ""
        confidence = 0.0
        if config.api_key:
            ai_answer, confidence = cls._run_llm_synthesis(
                query, maintenance_data, compliance_data,
                failure_data, kg_context, config
            )
        else:
            ai_answer = cls._build_fallback_synthesis(
                maintenance_data, compliance_data, failure_data
            )
            confidence = 0.4 if (maintenance_data or compliance_data or failure_data) else 0.1

        # Step 5: Get retrieval hits for evidence compilation
        retrieval = RAGRetrievalService.retrieve(query=query, query_embedding=query_embedding, config=config)
        retrieval_hits = [h.to_dict() for h in retrieval.hits]

        duration = round(time.time() - start_time, 3)

        # Step 6: Compose the final report
        report = ResponseComposerService.compose(
            query=query,
            ai_answer=ai_answer,
            maintenance_data=maintenance_data,
            compliance_data=compliance_data,
            failure_data=failure_data,
            trend_data=trend_result.to_dict(),
            warnings=[w.to_dict() for w in warnings],
            kg_context=kg_context,
            retrieval_hits=retrieval_hits,
            confidence=confidence,
            duration=duration,
        )

        logger.info(
            "Operations Intelligence complete: %d warnings, %d trends (%.2fs)",
            len(warnings), len(trend_result.trends), duration
        )

        return report

    @classmethod
    def _run_maintenance(cls, query: str, embedding, config: RAGConfig) -> dict | None:
        try:
            from agents.maintenance import MaintenanceAgent
            result = MaintenanceAgent.analyze(query, embedding, config)
            return result.to_dict() if result.detected_failure_modes or result.root_causes else None
        except Exception as exc:
            logger.warning("Maintenance agent failed in ops: %s", exc)
            return None

    @classmethod
    def _run_compliance(cls, query: str, embedding, config: RAGConfig) -> dict | None:
        try:
            from agents.compliance import QualityComplianceAgent
            result = QualityComplianceAgent.analyze(query, embedding, config)
            return result.to_dict() if result.applicable_standards or result.compliance_gaps else None
        except Exception as exc:
            logger.warning("Compliance agent failed in ops: %s", exc)
            return None

    @classmethod
    def _run_failure_intelligence(cls, query: str, embedding, config: RAGConfig) -> dict | None:
        try:
            result = FailureIntelligenceAgent.analyze(query, embedding, config)
            return result.to_dict() if result.historical_incidents or result.recurring_failures else None
        except Exception as exc:
            logger.warning("Failure intelligence failed in ops: %s", exc)
            return None

    @classmethod
    def _run_knowledge_graph(cls, query: str) -> list[dict]:
        try:
            from knowledge_graph.service import KnowledgeGraphService
            entities = KnowledgeGraphService.search_entities(query)
            context = []
            for e in entities[:5]:
                related = KnowledgeGraphService.get_related_entities(e.get("entity_id", ""))
                context.append({
                    "entity": e.get("name", ""),
                    "type": e.get("entity_type", ""),
                    "related": [r.get("name", "") for r in related[:3]],
                })
            return context
        except Exception:
            return []

    @classmethod
    def _run_llm_synthesis(
        cls, query: str, maint: dict | None, comp: dict | None,
        failure: dict | None, kg: list, config: RAGConfig
    ) -> tuple[str, float]:
        """Synthesizes across all agent outputs using Gemini."""
        sections = []
        if maint:
            sections.append(f"MAINTENANCE: Risk={maint.get('risk_level','?')}, Modes={maint.get('detected_failure_modes',[])}")
        if comp:
            sections.append(f"COMPLIANCE: Status={comp.get('compliance_status','?')}, Gaps={len(comp.get('compliance_gaps',[]))}")
        if failure:
            sections.append(f"FAILURES: Incidents={len(failure.get('historical_incidents',[]))}, Recurring={len(failure.get('recurring_failures',[]))}")
        if kg:
            sections.append(f"KNOWLEDGE GRAPH: {len(kg)} entities found")

        context = "\n".join(sections)
        prompt = f"""Based on the following multi-agent analysis, provide an executive summary.

{context}

Question: {query}

Provide a concise operations intelligence summary covering:
1. Key findings
2. Risk assessment
3. Recommended immediate actions
4. Cross-domain insights
"""
        try:
            response = GeminiService.generate(prompt=prompt, config=config, system_instruction=OPS_SYSTEM_PROMPT)
            return response.text, 0.8
        except Exception as exc:
            logger.warning("LLM synthesis failed: %s", exc)
            return cls._build_fallback_synthesis(maint, comp, failure), 0.4

    @classmethod
    def _build_fallback_synthesis(cls, maint, comp, failure) -> str:
        parts = ["Operations Intelligence Summary:\n"]
        if maint:
            parts.append(f"• Maintenance: {maint.get('problem_summary', 'Analysis available')}")
        if comp:
            parts.append(f"• Compliance: {comp.get('compliance_summary', 'Analysis available')}")
        if failure:
            parts.append(f"• Failure Intelligence: {len(failure.get('historical_incidents', []))} incidents found")
        return "\n".join(parts) if len(parts) > 1 else "Multi-agent analysis complete. Review individual sections."
