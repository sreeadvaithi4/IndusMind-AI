"""Unit tests for apps.documents.models."""

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.documents.models import Document, DocumentStatus

User = get_user_model()


class DocumentModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alex", password="testpass123")

    def _make_document(self, **overrides):
        defaults = {
            "original_filename": "report.pdf",
            "stored_filename": "abc123_report.pdf",
            "extension": "pdf",
            "file_size": 2048,
            "uploaded_by": self.user,
            "file": SimpleUploadedFile("report.pdf", b"%PDF-1.4 test content"),
        }
        defaults.update(overrides)
        return Document.objects.create(**defaults)

    def test_default_status_is_uploaded(self):
        document = self._make_document()
        self.assertEqual(document.status, DocumentStatus.UPLOADED)

    def test_str_representation_includes_filename_and_status(self):
        document = self._make_document()
        self.assertIn("report.pdf", str(document))
        self.assertIn(document.status, str(document))

    def test_is_terminal_false_for_ready_for_parsing(self):
        document = self._make_document(status=DocumentStatus.READY_FOR_PARSING)
        self.assertFalse(document.is_terminal)

    def test_is_terminal_true_for_indexed(self):
        document = self._make_document(status=DocumentStatus.INDEXED)
        self.assertTrue(document.is_terminal)

    def test_is_terminal_true_for_failed(self):
        document = self._make_document(status=DocumentStatus.FAILED)
        self.assertTrue(document.is_terminal)

    def test_is_ready_for_parsing_property(self):
        document = self._make_document(status=DocumentStatus.READY_FOR_PARSING)
        self.assertTrue(document.is_ready_for_parsing)

    def test_default_chunk_count_is_zero(self):
        document = self._make_document()
        self.assertEqual(document.chunk_count, 0)

    def test_ordering_is_most_recent_first(self):
        first = self._make_document(original_filename="first.pdf")
        second = self._make_document(original_filename="second.pdf")
        documents = list(Document.objects.all())
        self.assertEqual(documents[0].pk, second.pk)
        self.assertEqual(documents[1].pk, first.pk)

    def tearDown(self):
        for document in Document.objects.all():
            if document.file:
                document.file.delete(save=False)
