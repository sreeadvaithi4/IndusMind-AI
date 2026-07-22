"""API tests for the DocumentParseView endpoint (POST /api/documents/{id}/parse/)."""

import shutil
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files import File
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.documents.models import Document, DocumentStatus

User = get_user_model()

PROJECT_ROOT = Path(__file__).resolve().parents[4]
SAMPLE_DOCUMENTS_DIR = PROJECT_ROOT / "dataset" / "sample_documents"


@override_settings(GOOGLE_API_KEY="test-api-key-for-parse-api")
class DocumentParseAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alex", password="testpass123")
        self.other_user = User.objects.create_user(username="priya", password="testpass123")

    def _make_document(self, sample_filename, extension, user=None):
        source_path = SAMPLE_DOCUMENTS_DIR / sample_filename
        document = Document(
            original_filename=sample_filename,
            stored_filename=f"{uuid.uuid4().hex[:8]}_{sample_filename}",
            extension=extension,
            file_size=source_path.stat().st_size,
            uploaded_by=user or self.user,
            status=DocumentStatus.READY_FOR_PARSING,
            processing_stage=DocumentStatus.READY_FOR_PARSING,
        )
        with open(source_path, "rb") as f:
            document.file.save(sample_filename, File(f), save=True)
        return document

    def test_anonymous_user_cannot_trigger_parse(self):
        document = self._make_document("sample.txt", "txt")
        response = self.client.post(reverse("documents:parse", kwargs={"id": document.id}))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("rag.embeddings.service.EmbeddingGeneratorService._create_embeddings_model")
    def test_owner_can_trigger_parse_successfully(self, mock_create_model):
        # As of Sprint 9, this endpoint auto-chains Parser → Chunker →
        # Embedding Generator → Vector Store → Knowledge Graph, so the
        # final status is INDEXED.
        mock_model = MagicMock()
        mock_model.embed_documents.side_effect = (
            lambda texts: [[0.1] * 768 for _ in texts]
        )
        mock_create_model.return_value = mock_model

        document = self._make_document("sample.txt", "txt")
        self.client.force_authenticate(self.user)

        response = self.client.post(reverse("documents:parse", kwargs={"id": document.id}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], DocumentStatus.INDEXED)
        self.assertGreater(response.data["chunk_count"], 0)
        self.assertEqual(response.data["embedding_status"], "completed")

    def test_non_owner_cannot_trigger_parse(self):
        document = self._make_document("sample.txt", "txt")
        self.client.force_authenticate(self.other_user)

        response = self.client.post(reverse("documents:parse", kwargs={"id": document.id}))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_parsing_corrupted_file_returns_422_with_detail(self):
        document = self._make_document("corrupted.pdf", "pdf")
        self.client.force_authenticate(self.user)

        response = self.client.post(reverse("documents:parse", kwargs={"id": document.id}))

        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertIn("detail", response.data)

        document.refresh_from_db()
        self.assertEqual(document.status, DocumentStatus.FAILED)

    def tearDown(self):
        for document in Document.objects.all():
            if document.file:
                document.file.delete(save=False)
