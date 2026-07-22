"""
Unit tests for OCR fallback configurability and the should-attempt
heuristic.

Since the Tesseract binary is not guaranteed to be installed in every
environment that runs this test suite (and is not part of this
project's Python dependency set — it's a system binary), these tests
verify the *fallback logic and configurability* using mocks, rather
than asserting on real OCR text output. This matches the sprint
requirement that OCR be "optional and configurable" — that contract
must be verifiable even where Tesseract itself is absent.
"""

from unittest import mock

from django.test import TestCase, override_settings

from ingestion.exceptions import OcrFailureError
from ingestion.ocr import (
    MIN_CHARACTERS_PER_PAGE_THRESHOLD,
    is_ocr_available,
    run_ocr_on_pdf,
    should_attempt_ocr,
)


class ShouldAttemptOcrTests(TestCase):
    def test_returns_true_when_zero_pages(self):
        self.assertTrue(should_attempt_ocr("", page_count=0))

    def test_returns_true_when_text_density_is_low(self):
        sparse_text = "x" * (MIN_CHARACTERS_PER_PAGE_THRESHOLD - 1)
        self.assertTrue(should_attempt_ocr(sparse_text, page_count=1))

    def test_returns_false_when_text_density_is_sufficient(self):
        dense_text = "word " * 100
        self.assertFalse(should_attempt_ocr(dense_text, page_count=1))


class OcrAvailabilityTests(TestCase):
    @override_settings(OCR_ENABLED=False)
    def test_disabled_by_setting_even_if_dependencies_present(self):
        self.assertFalse(is_ocr_available())

    @override_settings(OCR_ENABLED=True)
    def test_enabled_when_setting_true_and_dependencies_importable(self):
        # pytesseract/Pillow/pdf2image were installed for this test run
        # (see requirements.txt); if they are genuinely absent in some
        # other environment, this assertion legitimately becomes False,
        # which is exactly the "gracefully unavailable" behavior being
        # verified elsewhere in this file.
        self.assertTrue(is_ocr_available())


class RunOcrOnPdfTests(TestCase):
    @override_settings(OCR_ENABLED=False)
    def test_returns_not_used_when_ocr_disabled(self):
        text, ocr_info = run_ocr_on_pdf("/nonexistent/path.pdf", page_count=1)
        self.assertEqual(text, "")
        self.assertFalse(ocr_info.used)
        self.assertIsNotNone(ocr_info.reason)

    @override_settings(OCR_ENABLED=True)
    def test_raises_ocr_failure_error_when_rasterization_fails(self):
        with mock.patch(
            "pdf2image.convert_from_path", side_effect=Exception("poppler not found")
        ):
            with self.assertRaises(OcrFailureError):
                run_ocr_on_pdf("/nonexistent/path.pdf", page_count=1)

    @override_settings(OCR_ENABLED=True)
    def test_successful_ocr_returns_used_true_with_page_numbers(self):
        fake_image = object()

        with mock.patch("pdf2image.convert_from_path", return_value=[fake_image, fake_image]):
            with mock.patch(
                "pytesseract.image_to_string", side_effect=["page one text", "page two text"]
            ):
                text, ocr_info = run_ocr_on_pdf("/fake/path.pdf", page_count=2)

        self.assertTrue(ocr_info.used)
        self.assertEqual(ocr_info.engine, "tesseract")
        self.assertEqual(ocr_info.pages_ocred, [1, 2])
        self.assertIn("page one text", text)
        self.assertIn("page two text", text)

    @override_settings(OCR_ENABLED=True)
    def test_raises_ocr_failure_error_when_tesseract_engine_fails(self):
        fake_image = object()

        with mock.patch("pdf2image.convert_from_path", return_value=[fake_image]):
            with mock.patch(
                "pytesseract.image_to_string",
                side_effect=Exception("tesseract binary not found"),
            ):
                with self.assertRaises(OcrFailureError):
                    run_ocr_on_pdf("/fake/path.pdf", page_count=1)
