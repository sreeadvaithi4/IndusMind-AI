"""
Warning Engine — generates evidence-backed operational warnings
from agent outputs. NEVER fabricates warnings without evidence.
"""

from dataclasses import dataclass, field


@dataclass
class Warning:
    """A single operational warning."""
    warning_type: str = ""  # early, compliance, trend, maintenance, quality, safety, inspection, calibration, operational_risk
    severity: str = "LOW"  # LOW, MEDIUM, HIGH, CRITICAL
    title: str = ""
    reason: str = ""
    evidence: str = ""
    recommended_action: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "warning_type": self.warning_type,
            "severity": self.severity,
            "title": self.title,
            "reason": self.reason,
            "evidence": self.evidence,
            "recommended_action": self.recommended_action,
            "confidence": self.confidence,
        }


class WarningEngine:
    """
    Generates warnings from agent outputs. Every warning requires evidence.
    """

    @classmethod
    def generate_warnings(
        cls,
        maintenance_data: dict | None = None,
        compliance_data: dict | None = None,
        failure_data: dict | None = None,
    ) -> list[Warning]:
        """Generates warnings from all agent outputs."""
        warnings: list[Warning] = []

        if maintenance_data:
            warnings.extend(cls._maintenance_warnings(maintenance_data))
        if compliance_data:
            warnings.extend(cls._compliance_warnings(compliance_data))
        if failure_data:
            warnings.extend(cls._failure_warnings(failure_data))

        # Sort by severity
        severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        warnings.sort(key=lambda w: severity_order.get(w.severity, 4))
        return warnings

    @classmethod
    def _maintenance_warnings(cls, data: dict) -> list[Warning]:
        warnings = []
        risk = data.get("risk_level", "")
        if risk == "critical":
            warnings.append(Warning(
                warning_type="maintenance",
                severity="CRITICAL",
                title="Critical Equipment Risk Detected",
                reason=data.get("problem_summary", "Critical maintenance issue identified"),
                evidence=f"Failure modes: {', '.join(data.get('detected_failure_modes', []))}",
                recommended_action="Immediate inspection and corrective action required",
                confidence=data.get("confidence", 0.5),
            ))
        elif risk == "high":
            warnings.append(Warning(
                warning_type="maintenance",
                severity="HIGH",
                title="High Maintenance Risk",
                reason=data.get("problem_summary", "High-risk maintenance issue"),
                evidence=f"Root causes: {len(data.get('root_causes', []))} identified",
                recommended_action="Schedule priority maintenance intervention",
                confidence=data.get("confidence", 0.5),
            ))
        return warnings

    @classmethod
    def _compliance_warnings(cls, data: dict) -> list[Warning]:
        warnings = []
        status = data.get("compliance_status", "")
        if status == "non_compliant":
            warnings.append(Warning(
                warning_type="compliance",
                severity="HIGH",
                title="Non-Compliance Detected",
                reason=f"Compliance status: {status}",
                evidence=f"Gaps: {len(data.get('compliance_gaps', []))} identified",
                recommended_action="Address compliance gaps immediately",
                confidence=data.get("confidence", 0.5),
            ))
        gaps = data.get("compliance_gaps", [])
        for gap in gaps[:2]:
            if gap.get("priority") in ("critical", "high"):
                warnings.append(Warning(
                    warning_type="compliance",
                    severity="HIGH" if gap["priority"] == "high" else "CRITICAL",
                    title=f"Compliance Gap: {gap.get('requirement', '')[:60]}",
                    reason=gap.get("evidence", ""),
                    evidence=f"Standard: {gap.get('standard', '')}",
                    recommended_action=gap.get("required_action", ""),
                    confidence=0.7,
                ))
        missing = data.get("missing_documents", [])
        if missing:
            warnings.append(Warning(
                warning_type="quality",
                severity="MEDIUM",
                title="Missing Quality Documents",
                reason=f"Documents not found: {', '.join(missing[:3])}",
                evidence="Document search returned no results",
                recommended_action="Upload or create the missing documents",
                confidence=0.6,
            ))
        return warnings

    @classmethod
    def _failure_warnings(cls, data: dict) -> list[Warning]:
        warnings = []
        recurring = data.get("recurring_failures", [])
        if recurring:
            top = recurring[0]
            warnings.append(Warning(
                warning_type="trend",
                severity="MEDIUM",
                title=f"Recurring Failure Pattern: {top.get('pattern', '')}",
                reason=f"Detected {top.get('occurrences', 0)} occurrences in documentation",
                evidence="Pattern detected across multiple documents",
                recommended_action="Investigate root cause of recurring pattern",
                confidence=0.6,
            ))
        incidents = data.get("historical_incidents", [])
        if len(incidents) >= 3:
            warnings.append(Warning(
                warning_type="early",
                severity="MEDIUM",
                title="Multiple Historical Incidents Found",
                reason=f"{len(incidents)} related incidents in documentation",
                evidence="Multiple incident records retrieved",
                recommended_action="Review historical patterns and update prevention plan",
                confidence=0.5,
            ))
        return warnings
