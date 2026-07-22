"""
Drawing Classifier — automatically classifies uploaded documents into
engineering drawing types based on textual cues from the parsed content.

Classification is pattern-based (keyword/heuristic), not ML-based,
making it fast, deterministic, and extensible.
"""

import re
from dataclasses import dataclass


# Classification rules: keyword patterns mapped to drawing types.
# Each rule has a list of patterns and a weight — the type with the
# highest total weight across all matched patterns wins.
CLASSIFICATION_RULES: list[dict] = [
    {
        "type": "pid",
        "patterns": [
            re.compile(r"\bP&ID\b", re.IGNORECASE),
            re.compile(r"\bpiping\s+(?:and|&)\s+instrumentation\b", re.IGNORECASE),
            re.compile(r"\bprocess\s+flow\s+diagram\b", re.IGNORECASE),
            re.compile(r"\bPFD\b"),
            re.compile(r"\b(?:control|safety)\s+valve\b", re.IGNORECASE),
            re.compile(r"\b(?:FV|PV|TV|LV|XV)[-_]\d+", re.IGNORECASE),
            re.compile(r"\bprocess\s+line\b", re.IGNORECASE),
        ],
        "weight": 1.0,
    },
    {
        "type": "mechanical",
        "patterns": [
            re.compile(r"\bmechanical\s+(?:drawing|detail|assembly)\b", re.IGNORECASE),
            re.compile(r"\b(?:section|view)\s+[A-Z][-\s][A-Z]\b"),
            re.compile(r"\b(?:tolerance|dimension|bore|shaft|keyway)\b", re.IGNORECASE),
            re.compile(r"\bbill\s+of\s+materials?\b", re.IGNORECASE),
            re.compile(r"\bBOM\b"),
            re.compile(r"\b(?:weld|flange|coupling|bracket)\b", re.IGNORECASE),
        ],
        "weight": 1.0,
    },
    {
        "type": "electrical",
        "patterns": [
            re.compile(r"\belectrical\s+(?:drawing|schematic|diagram|single\s+line)\b", re.IGNORECASE),
            re.compile(r"\bsingle\s+line\s+diagram\b", re.IGNORECASE),
            re.compile(r"\b(?:SLD|MCC|VFD|PLC|DCS)\b"),
            re.compile(r"\b(?:circuit|breaker|transformer|switchgear|busbar)\b", re.IGNORECASE),
            re.compile(r"\b(?:kV|kW|kVA|amp)\b", re.IGNORECASE),
        ],
        "weight": 1.0,
    },
    {
        "type": "instrumentation",
        "patterns": [
            re.compile(r"\binstrumentation\s+(?:drawing|diagram|loop)\b", re.IGNORECASE),
            re.compile(r"\bloop\s+diagram\b", re.IGNORECASE),
            re.compile(r"\b(?:PT|TT|FT|LT|AT)[-_]\d+", re.IGNORECASE),
            re.compile(r"\b(?:transmitter|transducer|PLC\s+input|4[-]20\s*mA)\b", re.IGNORECASE),
            re.compile(r"\binstrument\s+index\b", re.IGNORECASE),
        ],
        "weight": 1.0,
    },
    {
        "type": "general_arrangement",
        "patterns": [
            re.compile(r"\bgeneral\s+arrangement\b", re.IGNORECASE),
            re.compile(r"\bGA\s+drawing\b", re.IGNORECASE),
            re.compile(r"\b(?:plan|elevation|isometric)\s+(?:view|drawing)\b", re.IGNORECASE),
            re.compile(r"\blayout\s+(?:drawing|plan)\b", re.IGNORECASE),
            re.compile(r"\bplot\s+plan\b", re.IGNORECASE),
        ],
        "weight": 1.0,
    },
    {
        "type": "engineering_specification",
        "patterns": [
            re.compile(r"\bspecification\b", re.IGNORECASE),
            re.compile(r"\bdatasheet\b", re.IGNORECASE),
            re.compile(r"\b(?:scope\s+of\s+work|design\s+basis|technical\s+requirement)\b", re.IGNORECASE),
        ],
        "weight": 0.8,
    },
    {
        "type": "standard_document",
        "patterns": [
            re.compile(r"\b(?:ISO|API|ASME|NFPA|IEC|ANSI)\s*\d+"),
            re.compile(r"\bstandard\s+(?:practice|procedure|requirement)\b", re.IGNORECASE),
        ],
        "weight": 0.6,
    },
]


@dataclass
class ClassificationResult:
    """Result of drawing classification."""

    drawing_type: str = "unknown"
    confidence: float = 0.0
    matched_patterns: list[str] = None

    def __post_init__(self):
        if self.matched_patterns is None:
            self.matched_patterns = []


def classify_drawing(text: str) -> ClassificationResult:
    """
    Classifies a document's text into a drawing type.

    Returns the type with the highest cumulative pattern-match score.
    If no patterns match, returns 'unknown' with 0 confidence.
    """
    if not text or not text.strip():
        return ClassificationResult(drawing_type="unknown", confidence=0.0)

    scores: dict[str, float] = {}
    matches: dict[str, list[str]] = {}

    for rule in CLASSIFICATION_RULES:
        dtype = rule["type"]
        weight = rule["weight"]
        type_matches = []

        for pattern in rule["patterns"]:
            found = pattern.findall(text)
            if found:
                type_matches.extend(found[:3])  # cap per-pattern matches
                scores[dtype] = scores.get(dtype, 0) + weight

        if type_matches:
            matches[dtype] = type_matches

    if not scores:
        return ClassificationResult(drawing_type="unknown", confidence=0.0)

    # Winner is the type with the highest score
    best_type = max(scores, key=scores.get)
    max_possible = len(CLASSIFICATION_RULES) * 7  # theoretical max
    confidence = min(scores[best_type] / 5.0, 1.0)  # normalize to ~0–1

    return ClassificationResult(
        drawing_type=best_type,
        confidence=round(confidence, 2),
        matched_patterns=matches.get(best_type, []),
    )
