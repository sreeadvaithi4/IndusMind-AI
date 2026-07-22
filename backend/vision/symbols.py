"""
Symbol Detection Architecture for Engineering Drawings.

Provides a modular, extensible architecture for detecting engineering
symbols in drawings. Currently implements text-based symbol detection
(identifying symbol references in OCR text). The architecture is
designed so that future image-based (CNN/YOLO) detection can be added
as an additional detection strategy without changing the interface.

Supported symbols: pumps, valves, tanks, compressors, heat exchangers,
motors, pipelines, flow meters, pressure sensors, temperature sensors,
control valves, junctions, direction arrows, and more.
"""

import re
from vision.models import DetectedSymbol


# -------------------------------------------------------------------------
# Symbol detection patterns (text-based detection from OCR output)
# -------------------------------------------------------------------------
SYMBOL_DETECTION_PATTERNS: dict[str, list[re.Pattern]] = {
    "pump": [
        re.compile(r"\b((?:centrifugal|reciprocating|positive\s+displacement|booster|feed|charge)\s*pump)\b", re.IGNORECASE),
        re.compile(r"\b(P[-_]\d{3,}[A-Z]?)\b"),
    ],
    "valve": [
        re.compile(r"\b((?:gate|globe|ball|butterfly|check|relief|safety|control|solenoid)\s*valve)\b", re.IGNORECASE),
        re.compile(r"\b(V[-_]\d{3,}[A-Z]?)\b"),
        re.compile(r"\b((?:FV|PV|TV|LV|XV|HV)[-_]\d{3,}[A-Z]?)\b"),
    ],
    "tank": [
        re.compile(r"\b((?:storage|process|surge|feed|buffer|day)\s*tank)\b", re.IGNORECASE),
        re.compile(r"\b(T[-_]\d{3,}[A-Z]?)\b"),
        re.compile(r"\b(TK[-_]\d{3,}[A-Z]?)\b"),
    ],
    "compressor": [
        re.compile(r"\b((?:centrifugal|screw|reciprocating|axial)\s*compressor)\b", re.IGNORECASE),
        re.compile(r"\b(C[-_]\d{3,}[A-Z]?)\b"),
    ],
    "heat_exchanger": [
        re.compile(r"\b((?:shell\s+and\s+tube|plate|air\s+cooled|fin\s+fan)\s*(?:heat\s+)?exchanger)\b", re.IGNORECASE),
        re.compile(r"\b((?:E|HX)[-_]\d{3,}[A-Z]?)\b"),
        re.compile(r"\b(cooler|heater|condenser|reboiler)\b", re.IGNORECASE),
    ],
    "motor": [
        re.compile(r"\b((?:electric|induction|synchronous)\s*motor)\b", re.IGNORECASE),
        re.compile(r"\b(M[-_]\d{3,}[A-Z]?)\b"),
    ],
    "pipeline": [
        re.compile(r"\b(\d+[\"\']?\s*(?:inch|in|mm)\s*(?:line|pipe))\b", re.IGNORECASE),
        re.compile(r"\b((?:process|utility|drain|vent|relief)\s*(?:line|header|pipe))\b", re.IGNORECASE),
    ],
    "flow_meter": [
        re.compile(r"\b((?:FT|FE|FI)[-_]\d{3,}[A-Z]?)\b"),
        re.compile(r"\b(flow\s*(?:meter|element|transmitter))\b", re.IGNORECASE),
    ],
    "pressure_sensor": [
        re.compile(r"\b((?:PT|PI|PE|PG|PDT|PIT)[-_]\d{3,}[A-Z]?)\b"),
        re.compile(r"\b(pressure\s*(?:transmitter|gauge|indicator|switch))\b", re.IGNORECASE),
    ],
    "temperature_sensor": [
        re.compile(r"\b((?:TT|TI|TE|TW)[-_]\d{3,}[A-Z]?)\b"),
        re.compile(r"\b((?:temperature|thermocouple|RTD)\s*(?:transmitter|element|indicator|well))\b", re.IGNORECASE),
    ],
    "control_valve": [
        re.compile(r"\b((?:FV|PV|TV|LV|XV)[-_]\d{3,}[A-Z]?)\b"),
        re.compile(r"\b(control\s*valve)\b", re.IGNORECASE),
    ],
    "junction": [
        re.compile(r"\b((?:tee|cross|reducer|elbow|union)\s*(?:joint|junction)?)\b", re.IGNORECASE),
    ],
    "direction_arrow": [
        re.compile(r"\b((?:flow|direction)\s*(?:arrow|indicator))\b", re.IGNORECASE),
        re.compile(r"\b((?:to|from)\s+[\w\-]+)\b", re.IGNORECASE),
    ],
}


def detect_symbols(text: str, confidence_threshold: float = 0.5) -> list[DetectedSymbol]:
    """
    Detects engineering symbols from parsed drawing text.

    This is text-based detection — it identifies references to symbols
    in OCR output. Future extensions can add image-based detection.

    Args:
        text: The full drawing text.
        confidence_threshold: Minimum confidence for inclusion.

    Returns:
        List of DetectedSymbol objects.
    """
    if not text or not text.strip():
        return []

    symbols: list[DetectedSymbol] = []
    seen: set[str] = set()

    for symbol_type, patterns in SYMBOL_DETECTION_PATTERNS.items():
        for pattern in patterns:
            for match in pattern.finditer(text):
                label = match.group(1) if match.lastindex else match.group(0)
                label = label.strip()

                if not label or len(label) < 2:
                    continue

                dedup_key = f"{symbol_type}:{label.lower()}"
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                # Tag-format symbols get higher confidence
                confidence = 0.8 if re.match(r"^[A-Z]{1,3}[-_]\d+", label) else 0.6

                if confidence < confidence_threshold:
                    continue

                symbols.append(DetectedSymbol(
                    symbol_type=symbol_type,
                    label=label,
                    confidence=confidence,
                ))

    return symbols
