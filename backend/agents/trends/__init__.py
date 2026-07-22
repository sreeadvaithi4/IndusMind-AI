"""
Trend Analysis Engine — detects operational patterns and trends
from agent outputs and historical data.
"""

from dataclasses import dataclass, field


@dataclass
class Trend:
    """A detected operational trend."""
    category: str = ""  # failure, maintenance, compliance, risk, downtime
    title: str = ""
    severity: str = "medium"  # critical, high, medium, low
    description: str = ""
    evidence: list[str] = field(default_factory=list)
    recommendation: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "title": self.title,
            "severity": self.severity,
            "description": self.description,
            "evidence": self.evidence,
            "recommendation": self.recommendation,
            "confidence": self.confidence,
        }


@dataclass
class TrendAnalysisResult:
    """Output of trend analysis."""
    trends: list[Trend] = field(default_factory=list)
    summary: str = ""
    overall_risk: str = "medium"

    def to_dict(self) -> dict:
        return {
            "trends": [t.to_dict() for t in self.trends],
            "summary": self.summary,
            "overall_risk": self.overall_risk,
        }


class TrendAnalysisEngine:
    """Analyzes agent outputs for operational trends."""

    @classmethod
    def analyze(
        cls,
        maintenance_data: dict | None = None,
        compliance_data: dict | None = None,
        failure_data: dict | None = None,
    ) -> TrendAnalysisResult:
        trends: list[Trend] = []

        if failure_data:
            trends.extend(cls._failure_trends(failure_data))
        if maintenance_data:
            trends.extend(cls._maintenance_trends(maintenance_data))
        if compliance_data:
            trends.extend(cls._compliance_trends(compliance_data))

        overall_risk = cls._assess_overall_risk(trends)
        summary = cls._build_summary(trends)

        return TrendAnalysisResult(
            trends=trends[:10],
            summary=summary,
            overall_risk=overall_risk,
        )

    @classmethod
    def _failure_trends(cls, data: dict) -> list[Trend]:
        trends = []
        recurring = data.get("recurring_failures", [])
        for item in recurring[:3]:
            trends.append(Trend(
                category="failure",
                title=f"Recurring: {item.get('pattern', 'unknown')}",
                severity="high" if item.get("occurrences", 0) > 2 else "medium",
                description=f"Pattern '{item.get('pattern', '')}' detected {item.get('occurrences', 0)} times",
                evidence=[f"{item.get('occurrences', 0)} occurrences in documents"],
                recommendation="Investigate root cause and implement permanent fix",
                confidence=0.6,
            ))
        return trends

    @classmethod
    def _maintenance_trends(cls, data: dict) -> list[Trend]:
        trends = []
        modes = data.get("detected_failure_modes", [])
        if len(modes) > 2:
            trends.append(Trend(
                category="maintenance",
                title="Multiple Failure Modes Detected",
                severity="high",
                description=f"Equipment shows {len(modes)} failure modes: {', '.join(modes[:3])}",
                evidence=modes[:3],
                recommendation="Comprehensive equipment condition assessment needed",
                confidence=0.65,
            ))
        return trends

    @classmethod
    def _compliance_trends(cls, data: dict) -> list[Trend]:
        trends = []
        gaps = data.get("compliance_gaps", [])
        if len(gaps) > 2:
            trends.append(Trend(
                category="compliance",
                title="Multiple Compliance Gaps",
                severity="high",
                description=f"{len(gaps)} compliance gaps identified",
                evidence=[g.get("requirement", "") for g in gaps[:3]],
                recommendation="Prioritize gap closure and conduct management review",
                confidence=0.7,
            ))
        return trends

    @classmethod
    def _assess_overall_risk(cls, trends: list[Trend]) -> str:
        if any(t.severity == "critical" for t in trends):
            return "critical"
        if sum(1 for t in trends if t.severity == "high") >= 2:
            return "high"
        if trends:
            return "medium"
        return "low"

    @classmethod
    def _build_summary(cls, trends: list[Trend]) -> str:
        if not trends:
            return "No significant trends detected."
        categories = set(t.category for t in trends)
        return f"{len(trends)} trend(s) detected across {', '.join(categories)}."
