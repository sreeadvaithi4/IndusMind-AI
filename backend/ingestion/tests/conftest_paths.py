"""
Shared test helpers for the ingestion test suite: path to the sample
document fixtures in dataset/sample_documents/.
"""

from pathlib import Path

# backend/ingestion/tests/ -> backend/ingestion -> backend -> project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_DOCUMENTS_DIR = PROJECT_ROOT / "dataset" / "sample_documents"


def sample_path(filename: str) -> str:
    return str(SAMPLE_DOCUMENTS_DIR / filename)
