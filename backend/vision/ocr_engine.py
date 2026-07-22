"""
Enhanced OCR Engine for Engineering Drawings.

Extracts structured engineering information from drawing text:
equipment tags, drawing numbers, revision info, instrument IDs,
pipe/line numbers, BOM text, labels, and notes — each with a
confidence score and extraction type classification.

Operates on already-parsed text (from ParsedDocument.text) using
pattern-based extraction. This is NOT a replacement for Tesseract OCR
— it is a post-OCR structured extraction layer that identifies
engineering-specific content within OCR output.
"""

import re
from vision.models import OCRExtraction, DrawingMetadata


# -------------------------------------------------------------------------
# Extraction patterns for drawing-specific content
# -------------------------------------------------------------------------
EXTRACTION_PATTERNS: dict[str, list[re.Pattern]] = {
    "equipment_tag": [
        re.compile(r"\b([A-Z]{1,4}[-_]\d{3,}[A-Z]?(?:/[A-Z])?)\b"),
        re.compile(r"\b((?:P|V|C|E|T|M|HX|TK|FV|PV|TV|LV)[-_]\d{3,}[A-Z]?)\b"),
    ],
    "drawing_number": [
        re.compile(r"\b(DWG[-\s]?[#]?\s*[\w\-]+)\b", re.IGNORECASE),
        re.compile(r"\b((?:drawing|drg)[\s:#]+[\w\-\.]+)\b", re.IGNORECASE),
        re.compile(r"\b(\d{4,}[-_]\w{2,}[-_]\d+)\b"),
    ],
    "revision_number": [
        re.compile(r"\b(?:REV|REVISION)[\s.:]*([A-Z0-9]+)\b", re.IGNORECASE),
    ],
    "instrument_id": [
        re.compile(r"\b((?:PT|TT|FT|LT|AT|PI|TI|FI|LI|PDI|FIC|TIC|LIC|PIC)[-_]\d{3,}[A-Z]?)\b"),
    ],
    "pipe_id": [
        re.compile(r"\b(\d+[\"\']?[-]?\s*(?:inch|in|mm)\s*(?:line|pipe)[-\s]?[\w]*)\b", re.IGNORECASE),
        re.compile(r"\b(LINE[-\s]?\d+[\w\-]*)\b", re.IGNORECASE),
    ],
    "line_number": [
        re.compile(r"\b(\d+[-\"]\s*[\w\-]+[-]\d+[-][\w]+)\b"),
        re.compile(r"\b((?:line\s+(?:no|number|#))[\s.:]*[\w\-]+)\b", re.IGNORECASE),
    ],
    "sheet_number": [
        re.compile(r"\b((?:SHEET|SHT)[\s.:]*\d+\s*(?:OF|/)\s*\d+)\b", re.IGNORECASE),
        re.compile(r"\b((?:page|pg)[\s.:]*\d+)\b", re.IGNORECASE),
    ],
    "note": [
        re.compile(r"\bNOTE[\s.:]+(.{10,80})", re.IGNORECASE),
    ],
    "label": [
        re.compile(r"\b((?:INLET|OUTLET|SUCTION|DISCHARGE|DRAIN|VENT|SUPPLY|RETURN))\b", re.IGNORECASE),
    ],
    "dimension": [
        re.compile(r"\b(\d+(?:\.\d+)?\s*(?:mm|cm|m|in|ft|inch|inches))\b", re.IGNORECASE),
    ],
    "manufacturer": [
        re.compile(r"\b(?:MFR|MANUFACTURER|MAKE)[\s.:]+(.+?)(?:\n|$)", re.IGNORECASE),
    ],
    "bom_text": [
        re.compile(r"\b(?:ITEM|QTY|DESCRIPTION|MATERIAL|PART\s*NO)[\s.:]+(.+?)(?:\n|$)", re.IGNORECASE),
    ],
}


def extract_drawing_ocr(text: str, confidence_threshold: float = 0.3) -> list[OCRExtraction]:
    """
    Extracts structured engineering information from text.

    Args:
        text: The full document/drawing text.
        confidence_threshold: Minimum confidence for inclusion.

    Returns:
        List of OCRExtraction objects with classified text fragments.
    """
    if not text or not text.strip():
        return []

    extractions: list[OCRExtraction] = []
    seen: set[str] = set()

    for extraction_type, patterns in EXTRACTION_PATTERNS.items():
        for pattern in patterns:
            for match in pattern.finditer(text):
                extracted_text = match.group(1) if match.lastindex else match.group(0)
                extracted_text = extracted_text.strip()

                if not extracted_text or len(extracted_text) < 1:
                    continue

                # Dedup
                dedup_key = f"{extraction_type}:{extracted_text.lower()}"
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                # Assign confidence based on pattern specificity
                confidence = _estimate_confidence(extraction_type, extracted_text)

                if confidence < confidence_threshold:
                    continue

                extractions.append(OCRExtraction(
                    text=extracted_text,
                    extraction_type=extraction_type,
                    confidence=confidence,
                ))

    return extractions


def extract_drawing_metadata(text: str) -> DrawingMetadata:
    """
    Extracts drawing metadata (number, revision, author, etc.) from text.
    """
    metadata = DrawingMetadata()

    # Drawing number
    dwg_patterns = EXTRACTION_PATTERNS["drawing_number"]
    for pattern in dwg_patterns:
        match = pattern.search(text)
        if match:
            metadata.drawing_number = match.group(1).strip() if match.lastindex else match.group(0).strip()
            break

    # Revision
    rev_patterns = EXTRACTION_PATTERNS["revision_number"]
    for pattern in rev_patterns:
        match = pattern.search(text)
        if match:
            metadata.revision = match.group(1).strip()
            break

    # Sheet number
    sheet_patterns = EXTRACTION_PATTERNS["sheet_number"]
    for pattern in sheet_patterns:
        match = pattern.search(text)
        if match:
            metadata.sheet_number = match.group(0).strip()
            break

    # Scale
    scale_match = re.search(r"\bSCALE[\s.:]*(\d+\s*:\s*\d+|NTS|NOT\s+TO\s+SCALE)\b", text, re.IGNORECASE)
    if scale_match:
        metadata.scale = scale_match.group(1).strip()

    # Author / Drawn by
    author_match = re.search(r"\b(?:DRAWN\s+BY|DRN|DESIGNER)[\s.:]+([^\n]{2,30}?)(?:\n|$)", text, re.IGNORECASE)
    if author_match:
        metadata.author = author_match.group(1).strip()

    # Project
    project_match = re.search(r"\b(?:PROJECT|PROJ)[\s.:]+(.+?)(?:\n|$)", text, re.IGNORECASE)
    if project_match:
        metadata.project = project_match.group(1).strip()[:100]

    # Title
    title_match = re.search(r"\b(?:TITLE|DESCRIPTION)[\s.:]+(.+?)(?:\n|$)", text, re.IGNORECASE)
    if title_match:
        metadata.title = title_match.group(1).strip()[:200]

    return metadata


def _estimate_confidence(extraction_type: str, text: str) -> float:
    """
    Estimates confidence based on extraction type and text characteristics.
    Equipment tags and instrument IDs get higher confidence (structured format).
    Notes and labels get lower confidence (less structured).
    """
    high_confidence_types = {"equipment_tag", "instrument_id", "revision_number"}
    medium_confidence_types = {"drawing_number", "pipe_id", "line_number", "sheet_number"}

    if extraction_type in high_confidence_types:
        return 0.85
    elif extraction_type in medium_confidence_types:
        return 0.7
    elif extraction_type == "dimension":
        return 0.6
    else:
        return 0.5
