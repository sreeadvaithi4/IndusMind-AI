"""Unit tests for the TXT parser."""

import uuid

from django.test import TestCase

from ingestion.parsers.txt_parser import TxtParser
from ingestion.tests.conftest_paths import sample_path


class TxtParserTests(TestCase):
    def setUp(self):
        self.parser = TxtParser()
        self.document_id = str(uuid.uuid4())

    def test_parses_plain_text_content(self):
        result = self.parser.parse(sample_path("sample.txt"), self.document_id)
        self.assertIn("plain text sample document", result.text)

    def test_computes_character_and_word_counts(self):
        result = self.parser.parse(sample_path("sample.txt"), self.document_id)
        self.assertGreater(result.metadata.character_count, 0)
        self.assertGreater(result.metadata.word_count, 0)

    def test_handles_latin1_encoded_file(self):
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            tmp.write("café résumé naïve".encode("latin-1"))
            tmp_path = tmp.name

        try:
            result = self.parser.parse(tmp_path, self.document_id)
            self.assertGreater(len(result.text), 0)
        finally:
            import os

            os.remove(tmp_path)
