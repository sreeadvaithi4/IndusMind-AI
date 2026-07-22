"""
Quality Intelligence, Regulatory Compliance & QMS Agent.

Functions as an experienced Quality Engineer and Compliance Auditor:
analyzes documentation against standards, detects compliance gaps,
generates audit reports, manages CAPA/NCR, and cross-references
engineering drawings for compliance.

Reuses (does NOT duplicate):
    - RAGRetrievalService (hybrid retrieval)
    - GeminiService (LLM generation)
    - KnowledgeGraphService (equipment/regulation relationships)
    - DrawingAnalysisService (drawing compliance)
    - MaintenanceAgent (maintenance procedure cross-check)
"""

import logging
import re
import time
from dataclasses import dataclass, field

from agents.config import RAGConfig
from agents.llm import GeminiService
from agents.retrieval import RAGRetrievalService, RetrievalResult

logger = logging.getLogger("agents.compliance")


# -------------------------------------------------------------------------
# Regulatory Framework
# -------------------------------------------------------------------------
REGULATORY_STANDARDS = {
    "iso_9001": {"name": "ISO 9001", "scope": "Quality Management Systems"},
    "iso_45001": {"name": "ISO 45001", "scope": "Occupational Health & Safety"},
    "iso_14001": {"name": "ISO 14001", "scope": "Environmental Management"},
    "api": {"name": "API Standards", "scope": "Petroleum & Natural Gas Industry"},
    "asme": {"name": "ASME", "scope": "Mechanical Engineering Standards"},
    "osha": {"name": "OSHA", "scope": "Workplace Safety Regulations"},
    "iec": {"name": "IEC", "scope": "Electrical/Electronic Standards"},
    "nfpa": {"name": "NFPA", "scope": "Fire Protection Standards"},
}

COMPLIANCE_STATUSES = ["compliant", "partially_compliant", "non_compliant", "unknown"]

QMS_DOCUMENT_TYPES = [
    "quality_manual", "sop", "work_instruction", "maintenance_procedure",
    "inspection_report", "audit_report", "capa", "ncr", "deviation_report",
    "calibration_certificate", "risk_assessment", "engineering_standard",
    "oem_manual", "engineering_drawing", "pid", "training_record",
    "regulatory_document",
]

# Pattern-based detection of compliance-related content
COMPLIANCE_PATTERNS = {
    "capa": [re.compile(r"\bCAPA\b"), re.compile(r"\bcorrective\s+(?:and\s+)?preventive\s+action", re.IGNORECASE)],
    "ncr": [re.compile(r"\bNCR\b"), re.compile(r"\bnon[-\s]?conformance\s+report", re.IGNORECASE)],
    "audit": [re.compile(r"\baudit\b", re.IGNORECASE), re.compile(r"\baudit\s+(?:finding|report|evidence)", re.IGNORECASE)],
    "calibration": [re.compile(r"\bcalibrat\w*\b", re.IGNORECASE)],
    "sop": [re.compile(r"\bSOP\b"), re.compile(r"\bstandard\s+operating\s+procedure", re.IGNORECASE)],
    "deviation": [re.compile(r"\bdeviation\b", re.IGNORECASE), re.compile(r"\bnon[-\s]?conform\w*\b", re.IGNORECASE)],
    "gap_analysis": [re.compile(r"\bgaps?\s*(?:analysis|assessment)?\b", re.IGNORECASE), re.compile(r"\bmissing\b", re.IGNORECASE)],
    "standard": [re.compile(r"\b(?:ISO|API|ASME|OSHA|IEC|NFPA)\s*\d*"), re.compile(r"\bstandard\b", re.IGNORECASE)],
}


# -------------------------------------------------------------------------
# Data Models
# -------------------------------------------------------------------------

@dataclass
class ComplianceGap:
    """A detected compliance gap."""
    requirement: str = ""
    standard: str = ""
    status: str = "non_compliant"
    evidence: str = ""
    priority: str = "medium"  # critical, high, medium, low
    required_action: str = ""

    def to_dict(self) -> dict:
        return {
            "requirement": self.requirement,
            "standard": self.standard,
            "status": self.status,
            "evidence": self.evidence,
            "priority": self.priority,
            "required_action": self.required_action,
        }


@dataclass
class AuditFinding:
    """A structured audit finding."""
    finding: str = ""
    category: str = ""  # major, minor, observation, opportunity
    standard: str = ""
    evidence: str = ""
    required_action: str = ""
    risk_level: str = "medium"

    def to_dict(self) -> dict:
        return {
            "finding": self.finding,
            "category": self.category,
            "standard": self.standard,
            "evidence": self.evidence,
            "required_action": self.required_action,
            "risk_level": self.risk_level,
        }


@dataclass
class ComplianceAnalysisResult:
    """Complete output of the compliance agent."""
    query: str = ""
    compliance_summary: str = ""
    compliance_status: str = "unknown"  # compliant, partially_compliant, non_compliant
    compliance_score: float = 0.0  # 0.0 - 1.0
    applicable_standards: list[dict] = field(default_factory=list)
    compliance_gaps: list[ComplianceGap] = field(default_factory=list)
    audit_findings: list[AuditFinding] = field(default_factory=list)
    required_actions: list[str] = field(default_factory=list)
    missing_documents: list[str] = field(default_factory=list)
    required_evidence: list[str] = field(default_factory=list)
    capa_items: list[dict] = field(default_factory=list)
    ncr_items: list[dict] = field(default_factory=list)
    calibration_status: list[dict] = field(default_factory=list)
    related_sops: list[str] = field(default_factory=list)
    related_equipment: list[str] = field(default_factory=list)
    related_drawings: list[str] = field(default_factory=list)
    knowledge_graph_context: list[dict] = field(default_factory=list)
    supporting_documents: list[str] = field(default_factory=list)
    ai_analysis: str = ""
    confidence: float = 0.0
    evidence_score: float = 0.0
    suggested_followups: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "compliance_summary": self.compliance_summary,
            "compliance_status": self.compliance_status,
            "compliance_score": self.compliance_score,
            "applicable_standards": self.applicable_standards,
            "compliance_gaps": [g.to_dict() for g in self.compliance_gaps],
            "audit_findings": [f.to_dict() for f in self.audit_findings],
            "required_actions": self.required_actions,
            "missing_documents": self.missing_documents,
            "required_evidence": self.required_evidence,
            "capa_items": self.capa_items,
            "ncr_items": self.ncr_items,
            "calibration_status": self.calibration_status,
            "related_sops": self.related_sops,
            "related_equipment": self.related_equipment,
            "related_drawings": self.related_drawings,
            "knowledge_graph_context": self.knowledge_graph_context,
            "supporting_documents": self.supporting_documents,
            "ai_analysis": self.ai_analysis,
            "confidence": self.confidence,
            "evidence_score": self.evidence_score,
            "suggested_followups": self.suggested_followups,
            "duration_seconds": self.duration_seconds,
        }


# -------------------------------------------------------------------------
# Compliance Agent Service
# -------------------------------------------------------------------------

COMPLIANCE_SYSTEM_PROMPT = """You are an expert Quality Engineer and Compliance Auditor with 20+ years of experience in industrial quality management systems (QMS), regulatory compliance, and audit methodology.

Your role:
- Analyze documentation against applicable standards (ISO 9001, ISO 45001, API, ASME, OSHA)
- Identify compliance gaps and non-conformances
- Recommend corrective actions and required evidence
- Assess compliance status with confidence levels
- Reference specific standards, clauses, and requirements

Rules:
- Base your analysis ONLY on the provided context and evidence
- Clearly distinguish between confirmed compliance status and assessment
- Reference specific standard clauses (e.g. "ISO 9001:2015 Clause 7.1.5")
- Never fabricate compliance records, audit results, or CAPA/NCR data
- If evidence is insufficient, clearly state what is missing
- Use [Source N] notation to cite evidence
- Assign confidence levels to all compliance assessments
"""


class QualityComplianceAgent:
    """
    Quality Intelligence, Regulatory Compliance & QMS Agent.

    Usage:
        result = QualityComplianceAgent.analyze(query, query_embedding, config)
    """

    @classmethod
    def analyze(
        cls,
        query: str,
        query_embedding: list[float] | None = None,
        config: RAGConfig | None = None,
    ) -> ComplianceAnalysisResult:
        """
        Performs full compliance analysis.

        Args:
            query: The user's compliance-related question.
            query_embedding: Pre-computed query embedding.
            config: Optional RAG config override.

        Returns:
            ComplianceAnalysisResult with structured compliance data.
        """
        start_time = time.time()

        if config is None:
            config = RAGConfig.from_settings()

        if not query or not query.strip():
            return ComplianceAnalysisResult(
                query=query,
                compliance_summary="No query provided.",
            )

        logger.info("Compliance agent analyzing: %s", query[:100])

        # Step 1: Detect compliance topics in the query
        topics = cls._detect_compliance_topics(query)

        # Step 2: Identify applicable standards
        applicable_standards = cls._identify_standards(query)

        # Step 3: Hybrid retrieval (reuse existing)
        retrieval_result = RAGRetrievalService.retrieve(
            query=query,
            query_embedding=query_embedding,
            config=config,
        )

        # Step 4: Get KG context
        kg_context = cls._get_compliance_context(query)

        # Step 5: Detect compliance gaps
        gaps = cls._detect_compliance_gaps(query, retrieval_result, applicable_standards)

        # Step 6: Generate audit findings
        findings = cls._generate_audit_findings(topics, retrieval_result, applicable_standards)

        # Step 7: Identify missing documents and required evidence
        missing_docs = cls._identify_missing_documents(topics, retrieval_result)
        required_evidence = cls._identify_required_evidence(topics, applicable_standards)

        # Step 8: CAPA/NCR analysis
        capa_items = cls._extract_capa(retrieval_result)
        ncr_items = cls._extract_ncr(retrieval_result)

        # Step 9: Calibration status
        calibration = cls._extract_calibration_status(retrieval_result)

        # Step 10: Related SOPs
        related_sops = cls._extract_sops(retrieval_result)

        # Step 11: Assess overall compliance
        compliance_status, compliance_score = cls._assess_compliance(gaps, findings, retrieval_result)

        # Step 12: AI-powered analysis via Gemini
        ai_analysis = ""
        confidence = 0.0

        if config.api_key and retrieval_result.hits:
            ai_analysis, confidence = cls._run_llm_analysis(
                query, retrieval_result, applicable_standards, topics, config
            )
        elif retrieval_result.hits:
            ai_analysis = cls._build_evidence_summary(retrieval_result)
            confidence = 0.4
        else:
            ai_analysis = "Insufficient documentation for compliance assessment. Upload relevant quality documents."
            confidence = 0.1

        # Step 13: Generate follow-ups
        followups = cls._generate_followups(topics, applicable_standards)

        # Step 14: Required actions
        required_actions = cls._generate_required_actions(gaps, findings)

        duration = round(time.time() - start_time, 3)

        # Evidence score based on retrieval quality
        evidence_score = min(len(retrieval_result.hits) / config.top_k, 1.0)

        return ComplianceAnalysisResult(
            query=query,
            compliance_summary=cls._build_summary(query, compliance_status, applicable_standards, gaps),
            compliance_status=compliance_status,
            compliance_score=compliance_score,
            applicable_standards=applicable_standards,
            compliance_gaps=gaps,
            audit_findings=findings,
            required_actions=required_actions,
            missing_documents=missing_docs,
            required_evidence=required_evidence,
            capa_items=capa_items,
            ncr_items=ncr_items,
            calibration_status=calibration,
            related_sops=related_sops,
            related_equipment=list(set(
                h.metadata.get("name", "") for h in retrieval_result.hits
                if h.source == "knowledge_graph" and h.metadata.get("name")
            ))[:10],
            related_drawings=[
                h.metadata.get("drawing_number", "") for h in retrieval_result.hits
                if h.metadata.get("drawing_number")
            ][:5],
            knowledge_graph_context=kg_context[:10],
            supporting_documents=list(set(
                h.document_id for h in retrieval_result.hits if h.document_id
            ))[:10],
            ai_analysis=ai_analysis,
            confidence=confidence,
            evidence_score=evidence_score,
            suggested_followups=followups,
            duration_seconds=duration,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @classmethod
    def _detect_compliance_topics(cls, query: str) -> list[str]:
        """Detects compliance topics from query."""
        topics = []
        for topic, patterns in COMPLIANCE_PATTERNS.items():
            for pattern in patterns:
                if pattern.search(query):
                    topics.append(topic)
                    break
        return topics

    @classmethod
    def _identify_standards(cls, query: str) -> list[dict]:
        """Identifies applicable standards from query."""
        standards = []
        for key, info in REGULATORY_STANDARDS.items():
            if re.search(re.escape(info["name"]), query, re.IGNORECASE):
                standards.append({"code": key, "name": info["name"], "scope": info["scope"]})
        # If no specific standard mentioned, suggest common ones
        if not standards:
            if re.search(r"\bquality|QMS|quality\s+management", query, re.IGNORECASE):
                standards.append({"code": "iso_9001", "name": "ISO 9001", "scope": "Quality Management Systems"})
            if re.search(r"\bsafety|health|OHS", query, re.IGNORECASE):
                standards.append({"code": "iso_45001", "name": "ISO 45001", "scope": "Occupational Health & Safety"})
            if re.search(r"\bpump|valve|pressure|vessel", query, re.IGNORECASE):
                standards.append({"code": "api", "name": "API Standards", "scope": "Petroleum & Natural Gas Industry"})
                standards.append({"code": "asme", "name": "ASME", "scope": "Mechanical Engineering Standards"})
        return standards

    @classmethod
    def _get_compliance_context(cls, query: str) -> list[dict]:
        """Gets Knowledge Graph context for compliance."""
        from knowledge_graph.service import KnowledgeGraphService
        entities = KnowledgeGraphService.search_entities(query)
        context = []
        for entity in entities[:5]:
            related = KnowledgeGraphService.get_related_entities(entity.get("entity_id", ""))
            context.append({
                "entity": entity.get("name", ""),
                "type": entity.get("entity_type", ""),
                "related": [r.get("name", "") for r in related[:5]],
            })
        # Also search by keywords
        keywords = [w for w in query.split() if len(w) >= 4 and w.lower() not in {"what", "which", "show", "this", "that", "from", "with"}]
        for kw in keywords[:3]:
            found = KnowledgeGraphService.search_entities(kw)
            for e in found[:2]:
                if not any(c["entity"] == e.get("name") for c in context):
                    context.append({"entity": e.get("name", ""), "type": e.get("entity_type", ""), "related": []})
        return context

    @classmethod
    def _detect_compliance_gaps(
        cls, query: str, retrieval: RetrievalResult, standards: list[dict]
    ) -> list[ComplianceGap]:
        """Detects compliance gaps based on retrieved evidence."""
        gaps = []
        # If standards are referenced but no supporting documents found
        for std in standards:
            if not any(std["name"].lower() in (h.content or "").lower() for h in retrieval.hits):
                gaps.append(ComplianceGap(
                    requirement=f"Documentation referencing {std['name']}",
                    standard=std["name"],
                    status="unknown",
                    evidence="No relevant documentation found in the system.",
                    priority="high",
                    required_action=f"Upload or identify documents referencing {std['name']}.",
                ))
        # Check for common QMS gaps
        if "sop" in cls._detect_compliance_topics(query):
            if not any("sop" in (h.content or "").lower() for h in retrieval.hits):
                gaps.append(ComplianceGap(
                    requirement="Standard Operating Procedure",
                    standard="ISO 9001 Clause 7.5",
                    status="non_compliant",
                    evidence="No SOP found for the referenced process.",
                    priority="high",
                    required_action="Develop and approve applicable SOP.",
                ))
        return gaps[:10]

    @classmethod
    def _generate_audit_findings(
        cls, topics: list[str], retrieval: RetrievalResult, standards: list[dict]
    ) -> list[AuditFinding]:
        """Generates audit findings based on analysis."""
        findings = []
        if "gap_analysis" in topics or "audit" in topics:
            if not retrieval.hits:
                findings.append(AuditFinding(
                    finding="Insufficient documented evidence for compliance verification.",
                    category="major",
                    standard=standards[0]["name"] if standards else "General",
                    evidence="No relevant records retrieved from document system.",
                    required_action="Conduct document review and upload missing records.",
                    risk_level="high",
                ))
            elif len(retrieval.hits) < 3:
                findings.append(AuditFinding(
                    finding="Limited documented evidence available.",
                    category="minor",
                    standard=standards[0]["name"] if standards else "General",
                    evidence=f"Only {len(retrieval.hits)} relevant record(s) found.",
                    required_action="Review completeness of documentation.",
                    risk_level="medium",
                ))
        if "calibration" in topics:
            findings.append(AuditFinding(
                finding="Calibration records should be verified for currency.",
                category="observation",
                standard="ISO 9001 Clause 7.1.5",
                required_action="Verify calibration certificates are within validity period.",
                risk_level="medium",
            ))
        return findings[:10]

    @classmethod
    def _identify_missing_documents(cls, topics: list[str], retrieval: RetrievalResult) -> list[str]:
        """Identifies potentially missing documents."""
        missing = []
        expected_docs = {
            "sop": "Standard Operating Procedure",
            "calibration": "Calibration Certificate",
            "audit": "Audit Report",
            "capa": "CAPA Record",
            "ncr": "Non-Conformance Report",
        }
        for topic in topics:
            if topic in expected_docs:
                doc_type = expected_docs[topic]
                if not any(doc_type.lower() in (h.content or "").lower() for h in retrieval.hits):
                    missing.append(doc_type)
        if not retrieval.hits:
            missing.append("Quality Manual")
            missing.append("Applicable Standards")
        return missing[:10]

    @classmethod
    def _identify_required_evidence(cls, topics: list[str], standards: list[dict]) -> list[str]:
        """Identifies evidence required for compliance."""
        evidence = []
        evidence_map = {
            "iso_9001": ["Quality Policy", "Quality Objectives", "Process Maps", "Internal Audit Records", "Management Review Minutes"],
            "iso_45001": ["Risk Assessment", "Safety Procedures", "Incident Records", "Training Records"],
            "api": ["Equipment Certification", "Inspection Records", "Material Certificates"],
            "asme": ["Design Calculations", "Material Test Reports", "Weld Procedures"],
        }
        for std in standards:
            if std["code"] in evidence_map:
                evidence.extend(evidence_map[std["code"]][:3])
        if "calibration" in topics:
            evidence.append("Calibration Certificates with traceability")
        if "sop" in topics:
            evidence.append("Approved SOP with revision history")
        return list(set(evidence))[:10]

    @classmethod
    def _extract_capa(cls, retrieval: RetrievalResult) -> list[dict]:
        """Extracts CAPA references from retrieval results."""
        items = []
        for hit in retrieval.hits:
            content = (hit.content or "").lower()
            if "capa" in content or "corrective action" in content:
                items.append({
                    "reference": hit.chunk_id or hit.document_id,
                    "source": hit.source,
                    "content": hit.content[:150],
                })
        return items[:5]

    @classmethod
    def _extract_ncr(cls, retrieval: RetrievalResult) -> list[dict]:
        """Extracts NCR references from retrieval results."""
        items = []
        for hit in retrieval.hits:
            content = (hit.content or "").lower()
            if "ncr" in content or "non-conformance" in content:
                items.append({
                    "reference": hit.chunk_id or hit.document_id,
                    "source": hit.source,
                    "content": hit.content[:150],
                })
        return items[:5]

    @classmethod
    def _extract_calibration_status(cls, retrieval: RetrievalResult) -> list[dict]:
        """Extracts calibration status from retrieval."""
        items = []
        for hit in retrieval.hits:
            content = (hit.content or "").lower()
            if "calibrat" in content:
                items.append({
                    "reference": hit.chunk_id or hit.document_id,
                    "content": hit.content[:150],
                    "status": "found",
                })
        return items[:5]

    @classmethod
    def _extract_sops(cls, retrieval: RetrievalResult) -> list[str]:
        """Extracts SOP references from retrieval."""
        sops = []
        sop_pattern = re.compile(r"SOP[-\s]?[\w\-]+", re.IGNORECASE)
        for hit in retrieval.hits:
            matches = sop_pattern.findall(hit.content or "")
            sops.extend(matches)
        return list(set(sops))[:10]

    @classmethod
    def _assess_compliance(
        cls, gaps: list[ComplianceGap], findings: list[AuditFinding], retrieval: RetrievalResult
    ) -> tuple[str, float]:
        """Assesses overall compliance status and score."""
        if not retrieval.hits and not gaps:
            return "unknown", 0.0

        critical_gaps = sum(1 for g in gaps if g.priority == "critical")
        high_gaps = sum(1 for g in gaps if g.priority == "high")
        major_findings = sum(1 for f in findings if f.category == "major")

        if critical_gaps > 0 or major_findings > 0:
            return "non_compliant", 0.3
        elif high_gaps > 0:
            return "partially_compliant", 0.5
        elif gaps:
            return "partially_compliant", 0.7
        elif retrieval.hits:
            return "compliant", 0.85
        return "unknown", 0.0

    @classmethod
    def _run_llm_analysis(
        cls, query: str, retrieval: RetrievalResult,
        standards: list[dict], topics: list[str], config: RAGConfig
    ) -> tuple[str, float]:
        """Runs Gemini for AI-powered compliance analysis."""
        context_parts = []
        for i, hit in enumerate(retrieval.hits[:5], 1):
            if hit.content:
                context_parts.append(f"[Source {i}] {hit.content[:300]}")
        context = "\n\n".join(context_parts)
        standards_str = ", ".join(s["name"] for s in standards) if standards else "General standards"

        prompt = f"""Analyze this compliance question as an expert Quality Auditor.

Applicable Standards: {standards_str}
Topics: {', '.join(topics) if topics else 'General compliance'}

Context from documents:
{context}

Question: {query}

Provide:
1. Compliance assessment summary
2. Applicable standard clauses
3. Compliance gaps identified
4. Required actions
5. Evidence sufficiency assessment
"""
        try:
            response = GeminiService.generate(
                prompt=prompt, config=config,
                system_instruction=COMPLIANCE_SYSTEM_PROMPT,
            )
            return response.text, 0.75
        except Exception as exc:
            logger.warning("LLM compliance analysis failed: %s", exc)
            return cls._build_evidence_summary(retrieval), 0.4

    @classmethod
    def _build_evidence_summary(cls, retrieval: RetrievalResult) -> str:
        """Builds summary from retrieval without LLM."""
        if not retrieval.hits:
            return "No relevant compliance documentation found."
        parts = ["Based on available documentation:\n"]
        for i, hit in enumerate(retrieval.hits[:5], 1):
            parts.append(f"[Source {i}] {hit.content[:200]}")
        return "\n\n".join(parts)

    @classmethod
    def _build_summary(
        cls, query: str, status: str, standards: list[dict], gaps: list[ComplianceGap]
    ) -> str:
        """Builds a concise compliance summary."""
        parts = [f"Status: {status.replace('_', ' ').title()}"]
        if standards:
            parts.append(f"Standards: {', '.join(s['name'] for s in standards)}")
        if gaps:
            parts.append(f"Gaps: {len(gaps)} identified")
        return " | ".join(parts)

    @classmethod
    def _generate_required_actions(
        cls, gaps: list[ComplianceGap], findings: list[AuditFinding]
    ) -> list[str]:
        """Generates required actions from gaps and findings."""
        actions = []
        for gap in gaps:
            if gap.required_action:
                actions.append(gap.required_action)
        for finding in findings:
            if finding.required_action:
                actions.append(finding.required_action)
        return list(set(actions))[:10]

    @classmethod
    def _generate_followups(cls, topics: list[str], standards: list[dict]) -> list[str]:
        """Generates follow-up question suggestions."""
        followups = [
            "Generate compliance checklist",
            "Show audit evidence requirements",
        ]
        if "sop" in topics:
            followups.insert(0, "Show applicable SOPs")
        if "capa" in topics:
            followups.insert(0, "Show open CAPA items")
        if "ncr" in topics:
            followups.insert(0, "Show non-conformance history")
        if "calibration" in topics:
            followups.insert(0, "Show calibration status")
        if standards:
            followups.append(f"Compare against {standards[0]['name']}")
        followups.append("Generate audit report")
        followups.append("Show related engineering drawings")
        return followups[:6]
