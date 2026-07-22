"""
Executive Briefing Service — generates concise operations briefings
from an OperationsReport. Reuses GeminiService for text generation.
Does NOT perform its own reasoning; only summarizes existing agent outputs.
"""

import logging
import time
from dataclasses import dataclass, field

from agents.composer import OperationsReport
from agents.config import RAGConfig
from agents.llm import GeminiService

logger = logging.getLogger("agents.briefing")

BRIEFING_SYSTEM_PROMPT = """You are generating a concise executive operations briefing for an industrial plant operations manager. Speak as if you are an AI operations assistant delivering a morning briefing in a control room.

Rules:
- Keep it under 200 words
- Start with a greeting and alert count
- Mention specific equipment tags
- State overall plant health, risk level, and compliance score
- List top 3 recommended priorities
- End with a safety/incident summary
- Be direct, factual, and professional
- Do NOT fabricate data — only summarize what is provided
"""


@dataclass
class ExecutiveBriefing:
    """A generated executive operations briefing."""
    text: str = ""
    timestamp: str = ""
    plant_health: str = "good"  # good, fair, poor, critical
    overall_risk: str = "low"
    compliance_score: float = 0.0
    critical_alert_count: int = 0
    confidence: float = 0.0
    duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "timestamp": self.timestamp,
            "plant_health": self.plant_health,
            "overall_risk": self.overall_risk,
            "compliance_score": self.compliance_score,
            "critical_alert_count": self.critical_alert_count,
            "confidence": self.confidence,
            "duration_seconds": self.duration_seconds,
        }


class ExecutiveBriefingService:
    """
    Generates executive briefings from OperationsReport data.
    Reuses GeminiService — does NOT duplicate LLM logic.
    """

    @classmethod
    def generate(
        cls,
        report: OperationsReport | None = None,
        report_dict: dict | None = None,
        config: RAGConfig | None = None,
    ) -> ExecutiveBriefing:
        """
        Generates an executive briefing from an operations report.

        Args:
            report: An OperationsReport object (preferred).
            report_dict: Alternatively, a report dict (from to_dict()).
            config: RAG config override.
        """
        start_time = time.time()
        from datetime import datetime, timezone

        if config is None:
            config = RAGConfig.from_settings()

        # Extract key metrics from report
        data = report_dict or (report.to_dict() if report else {})
        risk_assessment = data.get("risk_assessment", {})
        warnings = data.get("warnings", [])
        maint = data.get("maintenance_intelligence")
        comp = data.get("compliance_intelligence")

        overall_risk = risk_assessment.get("overall_risk", "low")
        critical_count = sum(1 for w in warnings if w.get("severity") == "CRITICAL")
        high_count = sum(1 for w in warnings if w.get("severity") == "HIGH")
        compliance_score = comp.get("compliance_score", 0.85) if comp else 0.85

        # Determine plant health
        if critical_count > 0:
            plant_health = "critical"
        elif high_count > 1 or overall_risk == "high":
            plant_health = "poor"
        elif high_count == 1 or overall_risk == "medium":
            plant_health = "fair"
        else:
            plant_health = "good"

        # Build briefing prompt from report data
        prompt = cls._build_briefing_prompt(data, critical_count, high_count, compliance_score, plant_health, overall_risk)

        # Generate via Gemini (reuse existing service)
        briefing_text = ""
        confidence = 0.0

        if config.api_key:
            try:
                response = GeminiService.generate(
                    prompt=prompt, config=config,
                    system_instruction=BRIEFING_SYSTEM_PROMPT,
                )
                briefing_text = response.text
                confidence = 0.8
            except Exception as exc:
                logger.warning("Briefing LLM generation failed: %s", exc)
                briefing_text = cls._build_fallback_briefing(critical_count, high_count, plant_health, overall_risk, compliance_score)
                confidence = 0.5
        else:
            briefing_text = cls._build_fallback_briefing(critical_count, high_count, plant_health, overall_risk, compliance_score)
            confidence = 0.5

        duration = round(time.time() - start_time, 3)

        return ExecutiveBriefing(
            text=briefing_text,
            timestamp=datetime.now(timezone.utc).isoformat(),
            plant_health=plant_health,
            overall_risk=overall_risk,
            compliance_score=compliance_score,
            critical_alert_count=critical_count + high_count,
            confidence=confidence,
            duration_seconds=duration,
        )

    @classmethod
    def _build_briefing_prompt(cls, data, critical_count, high_count, compliance_score, plant_health, risk) -> str:
        sections = [f"Generate an executive operations briefing."]
        sections.append(f"\nPlant Health: {plant_health.upper()}")
        sections.append(f"Overall Risk: {risk.upper()}")
        sections.append(f"Compliance Score: {int(compliance_score * 100)}%")
        sections.append(f"Critical Alerts: {critical_count}, High Alerts: {high_count}")

        warnings = data.get("warnings", [])
        if warnings:
            sections.append("\nActive Warnings:")
            for w in warnings[:5]:
                sections.append(f"  - [{w.get('severity', '')}] {w.get('title', '')}")

        maint = data.get("maintenance_intelligence")
        if maint:
            sections.append(f"\nMaintenance: Risk={maint.get('risk_level', '?')}, Equipment={maint.get('equipment_tag', '?')}")

        actions = data.get("suggested_actions", [])
        if actions:
            sections.append(f"\nRecommended Actions: {', '.join(actions[:3])}")

        return "\n".join(sections)

    @classmethod
    def _build_fallback_briefing(cls, critical, high, health, risk, score) -> str:
        lines = []
        lines.append("Good morning. Here is your operations briefing.\n")
        total_alerts = critical + high
        if total_alerts > 0:
            lines.append(f"There {'is' if total_alerts == 1 else 'are'} {total_alerts} active alert{'s' if total_alerts != 1 else ''} requiring attention.\n")
        else:
            lines.append("No critical alerts at this time.\n")
        lines.append(f"Overall plant health is {health.upper()}.")
        lines.append(f"Overall risk level is {risk.upper()}.")
        lines.append(f"Compliance score is {int(score * 100)}%.\n")
        if total_alerts > 0:
            lines.append("Recommended priorities today:")
            lines.append("• Review and address active alerts")
            lines.append("• Verify equipment condition")
            lines.append("• Update maintenance schedule")
        else:
            lines.append("All systems nominal. Continue routine operations.")
        return "\n".join(lines)
