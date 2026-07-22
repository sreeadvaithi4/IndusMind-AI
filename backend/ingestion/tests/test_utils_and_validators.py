"""Unit tests for ingestion.validators and ingestion.utils."""

import tempfile

from django.test import TestCase

from ingestion.exceptions import FileNotFoundOnDiskError
from ingestion.utils import (
    count_characters,
    count_words,
    decode_with_best_effort,
    detect_language,
)
from ingestion.validators import validate_file_exists_on_disk


class ValidateFileExistsOnDiskTests(TestCase):
    def test_raises_when_path_does_not_exist(self):
        with self.assertRaises(FileNotFoundOnDiskError):
            validate_file_exists_on_disk("/definitely/not/a/real/path.pdf")

    def test_raises_when_file_is_empty(self):
        with tempfile.NamedTemporaryFile() as tmp:
            with self.assertRaises(FileNotFoundOnDiskError):
                validate_file_exists_on_disk(tmp.name)

    def test_passes_for_valid_non_empty_file(self):
        with tempfile.NamedTemporaryFile() as tmp:
            tmp.write(b"content")
            tmp.flush()
            validate_file_exists_on_disk(tmp.name)  # should not raise


class CountCharactersTests(TestCase):
    def test_counts_characters(self):
        self.assertEqual(count_characters("hello"), 5)

    def test_returns_zero_for_empty_string(self):
        self.assertEqual(count_characters(""), 0)

    def test_returns_zero_for_none(self):
        self.assertEqual(count_characters(None), 0)


class CountWordsTests(TestCase):
    def test_counts_words(self):
        self.assertEqual(count_words("hello world foo"), 3)

    def test_returns_zero_for_empty_string(self):
        self.assertEqual(count_words(""), 0)

    def test_ignores_extra_whitespace(self):
        self.assertEqual(count_words("hello   world"), 2)


class DetectLanguageTests(TestCase):
    def test_returns_none_for_empty_text(self):
        self.assertIsNone(detect_language(""))

    def test_returns_none_for_very_short_text(self):
        self.assertIsNone(detect_language("hi"))

    def test_detects_english_for_sufficiently_long_text(self):
        text = "This is a reasonably long piece of English text used to test language detection."
        result = detect_language(text)
        # langdetect is installed for this test run; if it's absent in
        # some other environment, detect_language degrades to None
        # (verified by the ImportError path, not re-tested here).
        self.assertEqual(result, "en")


class DecodeWithBestEffortTests(TestCase):
    def test_decodes_utf8_bytes(self):
        text, encoding = decode_with_best_effort("hello world".encode("utf-8"))
        self.assertEqual(text, "hello world")

    def test_decodes_latin1_bytes_without_crashing(self):
        raw = "café".encode("latin-1")
        text, encoding = decode_with_best_effort(raw)
        self.assertIsInstance(text, str)

    def test_never_raises_on_arbitrary_bytes(self):
        random_bytes = bytes([0xFF, 0xFE, 0x00, 0x01, 0x80])
        text, encoding = decode_with_best_effort(random_bytes)
        self.assertIsInstance(text, str)
