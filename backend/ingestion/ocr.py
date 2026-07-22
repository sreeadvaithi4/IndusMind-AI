"""
OCR fallback for the ingestion module.

OCR is only ever invoked by `pdf_parser.py` when direct text extraction
yields suspiciously little text for the page count (see
`should_attempt_ocr`) — never as the primary extraction path. It is
fully optional and configurable:

    - `settings.OCR_ENABLED` (default True) is a hard on/off switch.
    - If `pytesseract`, `PIL`, or `pdf2image` are not installed, or the
      Tesseract binary itself is not available, OCR is skipped with a
      warning rather than raising — a missing optional dependency must
      never take down the primary parsing path.
"""

import logging

from django.conf import settings

from ingestion.exceptions import OcrFailureError
from ingestion.result import OcrInfo

logger = logging.getLogger("ingestion.ocr")

# Below this ratio of (extracted characters / page), a PDF page is
# considered "text extraction likely failed" (e.g. a scanned image
# with no embedded text layer), triggering OCR fallback.
MIN_CHARACTERS_PER_PAGE_THRESHOLD = 20


def is_ocr_available() -> bool:
    """
    Returns True only if OCR is enabled by configuration AND all
    required optional dependencies (pytesseract, Pillow, pdf2image) are
    importable. Does not guarantee the Tesseract binary itself is
    installed — that failure is caught and reported at OCR-attempt time
    via OcrFailureError, since it can only be detected by trying.
    """
    if not getattr(settings, "OCR_ENABLED", True):
        return False

    try:
        import pdf2image  # noqa: F401
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return False

    return True


def should_attempt_ocr(extracted_text: str, page_count: int) -> bool:
    """
    Heuristic: OCR should only run when direct text extraction appears
    to have failed, not on every document. A page count of 0 is
    treated as "extraction failed" (nothing to measure against).
    """
    if page_count <= 0:
        return True

    characters_per_page = len(extracted_text or "") / page_count
    return characters_per_page < MIN_CHARACTERS_PER_PAGE_THRESHOLD


def run_ocr_on_pdf(file_path: str, page_count: int) -> tuple[str, OcrInfo]:
    """
    Runs OCR over every page of the PDF at `file_path` using pdf2image
    (to rasterize pages) + pytesseract (to recognize text).

    Returns:
        (ocr_extracted_text, OcrInfo) — OcrInfo.used is False (with a
        `reason`) if OCR could not run at all, rather than raising, so
        callers can fall back to whatever direct extraction produced.

    Raises:
        OcrFailureError: if OCR was attempted (dependencies present)
            but failed during execution (e.g. Tesseract binary missing
            or a page failed to rasterize).
    """
    if not is_ocr_available():
        return "", OcrInfo(
            used=False,
            reason="OCR is disabled or optional OCR dependencies "
            "(pytesseract, Pillow, pdf2image) are not installed.",
        )

    import pytesseract
    from pdf2image import convert_from_path

    tesseract_cmd = getattr(settings, "TESSERACT_CMD", "") or None
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    try:
        images = convert_from_path(file_path)
    except Exception as exc:
        raise OcrFailureError(f"Failed to rasterize PDF pages for OCR: {exc}") from exc

    extracted_pages = []
    pages_ocred = []

    for index, image in enumerate(images, start=1):
        try:
            page_text = pytesseract.image_to_string(image)
        except Exception as exc:
            raise OcrFailureError(
                f"Tesseract OCR failed on page {index}: {exc}"
            ) from exc

        extracted_pages.append(page_text)
        pages_ocred.append(index)

    logger.info("OCR completed for %d page(s) at '%s'.", len(pages_ocred), file_path)

    return "\n\n".join(extracted_pages), OcrInfo(
        used=True, engine="tesseract", pages_ocred=pages_ocred
    )
