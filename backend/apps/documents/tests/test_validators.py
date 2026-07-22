"""Unit tests for apps.documents.validators."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.documents.validators import (
    ALLOWED_EXTENSIONS,
    check_duplicate_filename,
    get_file_extension,
    sanitize_filename,
    validate_extension,
    validate_file_size,
    validate_upload,
)


class GetFileExtensionTests(TestCase):
    def test_returns_lowercase_extension(self):
        self.assertEqual(get_file_extension("Report.PDF"), "pdf")

    def test_returns_empty_string_when_no_extension(self):
        self.assertEqual(get_file_extension("README"), "")

    def test_handles_multiple_dots(self):
        self.assertEqual(get_file_extension("archive.tar.gz"), "gz")


class ValidateExtensionTests(TestCase):
    def test_accepts_all_allowed_extensions(self):
        for extension in ALLOWED_EXTENSIONS:
            with self.subTest(extension=extension):
                self.assertEqual(validate_extension(f"file.{extension}"), extension)

    def test_rejects_disallowed_extension(self):
        with self.assertRaises(ValidationError):
            validate_extension("malware.exe")

    def test_rejects_missing_extension(self):
        with self.assertRaises(ValidationError):
            validate_extension("noextension")

    def test_is_case_insensitive(self):
        self.assertEqual(validate_extension("Report.PDF"), "pdf")


class ValidateFileSizeTests(TestCase):
    def test_accepts_size_within_limit(self):
        validate_file_size(1024)  # should not raise

    def test_rejects_zero_size(self):
        with self.assertRaises(ValidationError):
            validate_file_size(0)

    def test_rejects_oversized_file(self):
        from django.conf import settings

        too_large = (settings.DOCUMENT_MAX_UPLOAD_SIZE_MB * 1024 * 1024) + 1
        with self.assertRaises(ValidationError):
            validate_file_size(too_large)


class SanitizeFilenameTests(TestCase):
    def test_preserves_simple_safe_filename(self):
        self.assertEqual(sanitize_filename("report.pdf"), "report.pdf")

    def test_strips_directory_components(self):
        self.assertNotIn("/", sanitize_filename("../../etc/passwd.txt"))

    def test_replaces_unsafe_characters(self):
        result = sanitize_filename("my report (final)!.docx")
        self.assertNotIn(" ", result)
        self.assertNotIn("(", result)
        self.assertNotIn(")", result)
        self.assertNotIn("!", result)

    def test_lowercases_extension(self):
        self.assertTrue(sanitize_filename("Report.PDF").endswith(".pdf"))

    def test_falls_back_to_document_when_name_is_empty_after_sanitizing(self):
        result = sanitize_filename("!!!.pdf")
        self.assertTrue(result.startswith("document"))

    def test_collapses_repeated_underscores(self):
        result = sanitize_filename("a   b   c.txt")
        self.assertNotIn("__", result)


class CheckDuplicateFilenameTests(TestCase):
    def test_detects_case_insensitive_duplicate(self):
        self.assertTrue(
            check_duplicate_filename("Report.PDF", ["report.pdf", "other.docx"])
        )

    def test_returns_false_when_no_match(self):
        self.assertFalse(check_duplicate_filename("new.pdf", ["other.docx"]))


class ValidateUploadTests(TestCase):
    def test_returns_extension_on_success(self):
        self.assertEqual(validate_upload("report.pdf", 1024), "pdf")

    def test_raises_on_bad_extension_before_checking_size(self):
        with self.assertRaises(ValidationError):
            validate_upload("malware.exe", 1024)
