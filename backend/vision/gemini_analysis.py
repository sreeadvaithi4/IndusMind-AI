"""
Gemini-powered drawing intelligence — enhances DrawingAnalysisService
with LLM-based analysis of engineering drawing content.

Reuses GeminiService (no duplicate LLM logic). Generates structured
insights that enrich the existing DrawingAnalysisResult without
changing its interface.
"""

import json
import logging

from agents.config import RAGConfig
from agents.llm import GeminiService

logger = logging.getLogger("vision")

DRAWING_ANALYSIS_PROMPT = """You are an expert industrial engineer analyzing an engineering drawing.

Based on the following extracted text from the drawing, provide a structured JSON analysis.

Drawing Text:
{text}

Extracted Equipment Tags: {equipment_tags}
Drawing Type: {drawing_type}

Respond ONLY with valid JSON in this exact format:
{{
  "equipment_summary": [
    {{"tag": "P-101A", "type": "pump", "description": "brief description", "connections": ["V-201"]}}
  ],
  "pipelines": [
    {{"from": "P-101A", "to": "V-201", "type": "process_line"}}
  ],
  "engineering_notes": ["note1", "note2"],
  "warnings": [
    {{"severity": "medium", "issue": "description", "recommendation": "action"}}
  ],
  "insights": "One paragraph summary of the drawing's significance"
}}

If information is unclear, use "unknown". Never fabricate equipment that isn't in the text."""


def analyze_with_gemini(
    text: str,
    equipment_tags: list[str],
    drawing_type: str,
    config: RAGConfig | None = None,
) -> dict:
    """
    Performs Gemini-powered analysis on drawing text.

    Args:
        text: Extracted drawing text (first 3000 chars).
        equipment_tags: Tags already detected by the pattern extractor.
        drawing_type: Classification result.
        config: RAG config.

    Returns:
        Structured dict with equipment_summary, pipelines, notes, warnings, insights.
        Returns empty dict if Gemini is unavailable.
    """
    if config is None:
        config = RAGConfig.from_settings()

    if not config.api_key:
        return {}

    if not text or not text.strip():
        return {}

    prompt = DRAWING_ANALYSIS_PROMPT.format(
        text=text[:3000],
        equipment_tags=", ".join(equipment_tags[:20]) if equipment_tags else "None detected",
        drawing_type=drawing_type,
    )

    try:
        response = GeminiService.generate(
            prompt=prompt, config=config,
            system_instruction="You are an engineering drawing analysis expert. Respond only with valid JSON.",
        )
        # Parse JSON from response
        response_text = response.text.strip()
        # Handle markdown code blocks
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        return json.loads(response_text)
    except json.JSONDecodeError:
        logger.warning("Gemini returned non-JSON for drawing analysis.")
        return {}
    except Exception as exc:
        logger.warning("Gemini drawing analysis failed: %s", exc)
        return {}
