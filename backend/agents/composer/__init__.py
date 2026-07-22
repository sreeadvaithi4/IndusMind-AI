"""
Response Composer Service — transforms multi-agent outputs into
structured enterprise operation reports. Gemini generates reasoning;
this service structures presentation.
"""

from dataclasses import dataclass, field


@dataclass
class AgentStatus:
    """Status of a single agent execution."""
    agent: str = ""
    status: str = "completed"  # completed, partial, skipped, failed
    data_available: bool = False

    def to_dict(self) -> dict:
        return {"agent": self.agent, "status": self.status, "data_available": self.data_available}


@dataclass
class OperationsReport:
    """Structured enterprise operations intelligence report."""
    executive_summary: str = ""
    agent_statuses: list[AgentStatus] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    risk_assessment: dict = field(default_factory=dict)
    maintenance_intelligence: dict | None = None
    compliance_intelligence: dict | None = None
    failure_intelligence: dict | None = None
    trend_analysis: dict | None = None
    knowledge_graph: dict = field(default_factory=dict)
    drawing_analysis: dict | None = None
    evidence: dict = field(default_factory=dict)
    suggested_actions: list[str] = field(default_factory=list)
    ai_analysis: str = ""
    confidence: float = 0.0
    duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        result = {
            "executive_summary": self.executive_summary,
            "agent_statuses": [a.to_dict() for a in self.agent_statuses],
            "warnings": self.warnings,
            "risk_assessment": self.risk_assessment,
            "suggested_actions": self.suggested_actions,
            "ai_analysis": self.ai_analysis,
            "confidence": self.confidence,
            "duration_seconds": self.duration_seconds,
        }
        if self.maintenance_intelligence:
            result["maintenance_intelligence"] = self.maintenance_intelligence
        if self.compliance_intelligence:
            result["compliance_intelligence"] = self.compliance_intelligence
        if self.failure_intelligence:
            result["failure_intelligence"] = self.failure_intelligence
        if self.trend_analysis:
            result["trend_analysis"] = self.trend_analysis
        if self.knowledge_graph:
            result["knowledge_graph"] = self.knowledge_graph
        if self.drawing_analysis:
            result["drawing_analysis"] = self.drawing_analysis
        if self.evidence:
            result["evidence"] = self.evidence
        return result


class ResponseComposerService:
    """Composes structured reports from multi-agent outputs."""

    @classmethod
    def compose(
        cls,
        query: str,
        ai_answer: str = "",
        maintenance_data: dict | None = None,
        compliance_data: dict | None = None,
        failure_data: dict | None = None,
        trend_data: dict | None = None,
        warnings: list[dict] | None = None,
        kg_context: list[dict] | None = None,
        drawing_data: dict | None = None,
        retrieval_hits: list[dict] | None = None,
        confidence: float = 0.0,
        duration: float = 0.0,
    ) -> OperationsReport:
        """Composes a full operations report from agent outputs."""

        # Agent statuses
        statuses = [
            AgentStatus("Maintenance Agent", "completed" if maintenance_data else "skipped", bool(maintenance_data)),
            AgentStatus("Compliance Agent", "completed" if compliance_data else "skipped", bool(compliance_data)),
            AgentStatus("Failure Intelligence", "completed" if failure_data else "skipped", bool(failure_data)),
            AgentStatus("Knowledge Graph", "completed" if kg_context else "skipped", bool(kg_context)),
            AgentStatus("Drawing Analysis", "completed" if drawing_data else "skipped", bool(drawing_data)),
        ]

        # Risk assessment
        risk = cls._build_risk_assessment(maintenance_data, compliance_data, trend_data, confidence)

        # Executive summary
        summary = cls._build_executive_summary(query, ai_answer, risk, warnings or [])

        # Evidence compilation
        evidence = cls._compile_evidence(retrieval_hits or [])

        # Suggested actions
        actions = cls._generate_suggested_actions(maintenance_data, compliance_data, failure_data)

        # Knowledge graph section
        kg_section = {"entities": kg_context[:5]} if kg_context else {}

        return OperationsReport(
            executive_summary=summary,
            agent_statuses=statuses,
            warnings=warnings or [],
            risk_assessment=risk,
            maintenance_intelligence=maintenance_data,
            compliance_intelligence=compliance_data,
            failure_intelligence=failure_data,
            trend_analysis=trend_data,
            knowledge_graph=kg_section,
            drawing_analysis=drawing_data,
            evidence=evidence,
            suggested_actions=actions,
            ai_analysis=ai_answer,
            confidence=confidence,
            duration_seconds=duration,
        )

    @classmethod
    def _build_risk_assessment(cls, maint: dict | None, comp: dict | None, trend: dict | None, confidence: float) -> dict:
        risk_level = "low"
        if maint and maint.get("risk_level") in ("critical", "high"):
            risk_level = maint["risk_level"]
        elif comp and comp.get("compliance_status") == "non_compliant":
            risk_level = "high"
        elif trend and trend.get("overall_risk") in ("critical", "high"):
            risk_level = trend["overall_risk"]
        return {
            "overall_risk": risk_level,
            "confidence": confidence,
            "evidence_score": min(confidence * 1.2, 1.0),
        }

    @classmethod
    def _build_executive_summary(cls, query: str, ai_answer: str, risk: dict, warnings: list) -> str:
        parts = []
        if ai_answer:
            parts.append(ai_answer[:300])
        if risk["overall_risk"] in ("critical", "high"):
            parts.append(f"⚠️ Risk Level: {risk['overall_risk'].upper()}")
        if warnings:
            parts.append(f"{len(warnings)} warning(s) generated.")
        return " | ".join(parts) if parts else f"Analysis complete for: {query[:80]}"

    @classmethod
    def _compile_evidence(cls, hits: list[dict]) -> dict:
        sources: dict[str, list] = {"documents": [], "knowledge_graph": [], "drawings": []}
        for hit in hits[:10]:
            source = hit.get("source", "")
            if source == "chromadb":
                sources["documents"].append(hit.get("document_id", ""))
            elif source == "knowledge_graph":
                sources["knowledge_graph"].append(hit.get("entity_id", ""))
        return sources

    @classmethod
    def _generate_suggested_actions(cls, maint: dict | None, comp: dict | None, failure: dict | None) -> list[str]:
        actions = []
        if maint:
            actions.append("Generate detailed RCA report")
            actions.append("Show maintenance plan")
        if comp:
            actions.append("Generate audit report")
            actions.append("Show CAPA status")
        if failure:
            actions.append("Show similar historical incidents")
            actions.append("Compare with previous failures")
        actions.extend(["Open engineering drawing", "Show knowledge graph", "Export report"])
        return actions[:8]
