"""Unit tests for the Document Management REST API endpoints."""

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.documents.models import Document, DocumentStatus

User = get_user_model()


class DocumentUploadAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alex", password="testpass123")

    def test_anonymous_user_cannot_upload(self):
        url = reverse("documents:upload")
        response = self.client.post(
            url, {"file": SimpleUploadedFile("report.pdf", b"content")}, format="multipart"
        )
        # DRF's default SessionAuthentication does not issue a
        # WWW-Authenticate challenge, so unauthenticated requests are
        # rejected with 403 (Forbidden) rather than 401 (Unauthorized).
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_authenticated_user_can_upload(self):
        self.client.force_authenticate(self.user)
        url = reverse("documents:upload")
        response = self.client.post(
            url, {"file": SimpleUploadedFile("report.pdf", b"content")}, format="multipart"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], DocumentStatus.READY_FOR_PARSING)
        self.assertEqual(response.data["original_filename"], "report.pdf")

    def test_upload_rejects_disallowed_extension(self):
        self.client.force_authenticate(self.user)
        url = reverse("documents:upload")
        response = self.client.post(
            url, {"file": SimpleUploadedFile("malware.exe", b"content")}, format="multipart"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_without_file_returns_400(self):
        self.client.force_authenticate(self.user)
        url = reverse("documents:upload")
        response = self.client.post(url, {}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def tearDown(self):
        for document in Document.objects.all():
            if document.file:
                document.file.delete(save=False)


class DocumentListAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alex", password="testpass123")
        self.other_user = User.objects.create_user(username="priya", password="testpass123")

    def _create_document(self, user, filename="report.pdf", **overrides):
        defaults = {
            "original_filename": filename,
            "stored_filename": f"abc_{filename}",
            "extension": filename.rsplit(".", 1)[-1],
            "file_size": 1024,
            "uploaded_by": user,
            "file": SimpleUploadedFile(filename, b"content"),
        }
        defaults.update(overrides)
        return Document.objects.create(**defaults)

    def test_anonymous_user_cannot_list(self):
        url = reverse("documents:list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_only_returns_own_documents(self):
        self._create_document(self.user, "mine.pdf")
        self._create_document(self.other_user, "theirs.pdf")

        self.client.force_authenticate(self.user)
        response = self.client.get(reverse("documents:list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        filenames = [doc["original_filename"] for doc in response.data["results"]]
        self.assertIn("mine.pdf", filenames)
        self.assertNotIn("theirs.pdf", filenames)

    def test_list_filters_by_status(self):
        self._create_document(self.user, "ready.pdf", status=DocumentStatus.READY_FOR_PARSING)
        self._create_document(self.user, "uploaded.pdf", status=DocumentStatus.UPLOADED)

        self.client.force_authenticate(self.user)
        response = self.client.get(
            reverse("documents:list"), {"status": DocumentStatus.READY_FOR_PARSING}
        )

        filenames = [doc["original_filename"] for doc in response.data["results"]]
        self.assertEqual(filenames, ["ready.pdf"])

    def tearDown(self):
        for document in Document.objects.all():
            if document.file:
                document.file.delete(save=False)


class DocumentDetailAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alex", password="testpass123")
        self.other_user = User.objects.create_user(username="priya", password="testpass123")
        self.document = Document.objects.create(
            original_filename="report.pdf",
            stored_filename="abc_report.pdf",
            extension="pdf",
            file_size=1024,
            uploaded_by=self.user,
            file=SimpleUploadedFile("report.pdf", b"content"),
        )

    def test_owner_can_retrieve(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(
            reverse("documents:detail", kwargs={"id": self.document.id})
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["original_filename"], "report.pdf")

    def test_non_owner_non_staff_cannot_retrieve(self):
        self.client.force_authenticate(self.other_user)
        response = self.client.get(
            reverse("documents:detail", kwargs={"id": self.document.id})
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_owner_can_delete_and_file_is_removed(self):
        self.client.force_authenticate(self.user)
        file_path = self.document.file.path
        response = self.client.delete(
            reverse("documents:detail", kwargs={"id": self.document.id})
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Document.objects.filter(pk=self.document.pk).exists())

    def test_status_endpoint_returns_summary(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(
            reverse("documents:status", kwargs={"id": self.document.id})
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("processing_percentage", response.data)

    def tearDown(self):
        if self.document.file:
            try:
                self.document.file.delete(save=False)
            except ValueError:
                pass


class SupportedFormatsAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alex", password="testpass123")

    def test_returns_allowed_extensions(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse("documents:supported-formats"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("pdf", response.data["allowed_extensions"])
        self.assertIn("docx", response.data["allowed_extensions"])
