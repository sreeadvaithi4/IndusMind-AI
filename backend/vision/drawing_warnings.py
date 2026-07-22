"""
Drawing Warnings — generates structured warnings from drawing analysis
results. Each warning requires evidence (never fabricated).
"""

from dataclasses import dataclass, field

from vision.models import DrawingAnalysisResult, ExtractedEquipment, OCRExtraction


@dataclass
class DrawingWarning:
    """A structured warning from drawing analysis."""
    severity: str = "medium"  # critical, high, medium, low
    issue: str = ""
    reason: str = ""
    confidence: float = 0.5
    recommendation: str = ""
    equipment_tag: str = ""

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "issue": self.issue,
            "reason": self.reason,
            "confidence": self.confidence,
            "recommendation": self.recommendation,
            "equipment_tag": self.equipment_tag,
        }


def generate_drawing_warnings(result: DrawingAnalysisResult) -> list[DrawingWarning]:
    """
    Generates warnings based on drawing analysis results.
    Only produces warnings backed by evidence.
    """
    warnings: list[DrawingWarning] = []

    if not result:
        return warnings

    # 1. Low OCR confidence extractions
    low_conf_extractions = [
        e for e in result.ocr_extractions if e.confidence < 0.4
    ]
    if low_conf_extractions:
        warnings.append(DrawingWarning(
            severity="medium",
            issue="Low OCR confidence on extracted text",
            reason=f"{len(low_conf_extractions)} text extraction(s) have confidence below 40%",
            confidence=0.7,
            recommendation="Verify extracted equipment tags manually against the original drawing",
        ))

    # 2. Equipment without connections (disconnected)
    equipment_with_connections = set()
    for rel in result.relationships:
        equipment_with_connections.add(rel.source_equipment)
        equipment_with_connections.add(rel.target_equipment)

    disconnected = [
        eq for eq in result.equipment
        if eq.tag and eq.tag not in equipment_with_connections
    ]
    if disconnected and len(result.equipment) > 2:
        warnings.append(DrawingWarning(
            severity="medium",
            issue="Disconnected equipment detected",
            reason=f"{len(disconnected)} equipment item(s) have no detected connections: {', '.join(e.tag for e in disconnected[:3])}",
            confidence=0.5,
            recommendation="Verify these items are correctly connected in the drawing",
            equipment_tag=disconnected[0].tag if disconnected else "",
        ))

    # 3. Missing equipment tags (symbols detected but no tag)
    symbols_without_tags = [
        s for s in result.detected_symbols
        if s.label and not any(eq.tag == s.label for eq in result.equipment)
    ]
    # (This is normal for most symbols; only warn if many)
    if len(symbols_without_tags) > 5:
        warnings.append(DrawingWarning(
            severity="low",
            issue="Multiple symbols without equipment registration",
            reason=f"{len(symbols_without_tags)} detected symbols not matched to extracted equipment",
            confidence=0.4,
            recommendation="Review symbol legend and verify all equipment is tagged",
        ))

    # 4. No drawing number detected
    if not result.metadata.drawing_number:
        warnings.append(DrawingWarning(
            severity="high",
            issue="Missing drawing number",
            reason="No drawing number could be extracted from the document",
            confidence=0.8,
            recommendation="Verify drawing has a proper title block with drawing number",
        ))

    # 5. No revision information
    if not result.metadata.revision and result.drawing_type != "unknown":
        warnings.append(DrawingWarning(
            severity="medium",
            issue="Missing revision information",
            reason="No revision number detected — document version cannot be verified",
            confidence=0.6,
            recommendation="Ensure drawing includes revision history in title block",
        ))

    return warnings
