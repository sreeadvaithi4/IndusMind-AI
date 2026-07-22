"""Unit tests for apps.documents.services."""

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.documents.models import Document, DocumentStatus
from apps.documents.services import (
    DocumentProcessingService,
    DocumentStatusService,
    DocumentUploadService,
    DocumentUploadServiceError,
)
from ingestion.chunking.exceptions import ChunkingError
from ingestion.exceptions import ParserError

User = get_user_model()


class DocumentUploadServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alex", password="testpass123")

    def test_upload_creates_document_ready_for_parsing(self):
        uploaded_file = SimpleUploadedFile("report.pdf", b"%PDF-1.4 test content")
        document = DocumentUploadService.upload(uploaded_file, self.user)

        self.assertEqual(document.status, DocumentStatus.READY_FOR_PARSING)
        self.assertEqual(document.original_filename, "report.pdf")
        self.assertEqual(document.extension, "pdf")
        self.assertEqual(document.uploaded_by, self.user)
        self.assertTrue(Document.objects.filter(pk=document.pk).exists())

    def test_upload_rejects_disallowed_extension(self):
        uploaded_file = SimpleUploadedFile("malware.exe", b"binary content")
        with self.assertRaises(DocumentUploadServiceError):
            DocumentUploadService.upload(uploaded_file, self.user)
        self.assertEqual(Document.objects.count(), 0)

    def test_upload_sanitizes_stored_filename(self):
        uploaded_file = SimpleUploadedFile("my report (final)!.pdf", b"content")
        document = DocumentUploadService.upload(uploaded_file, self.user)

        self.assertNotIn(" ", document.stored_filename)
        self.assertNotIn("(", document.stored_filename)

    def test_get_existing_filenames_for_user_scopes_to_user(self):
        other_user = User.objects.create_user(username="priya", password="testpass123")
        DocumentUploadService.upload(
            SimpleUploadedFile("mine.pdf", b"content"), self.user
        )
        DocumentUploadService.upload(
            SimpleUploadedFile("theirs.pdf", b"content"), other_user
        )

        filenames = DocumentUploadService.get_existing_filenames_for_user(self.user)
        self.assertIn("mine.pdf", filenames)
        self.assertNotIn("theirs.pdf", filenames)

    def tearDown(self):
        for document in Document.objects.all():
            if document.file:
                document.file.delete(save=False)


class DocumentStatusServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alex", password="testpass123")
        self.document = Document.objects.create(
            original_filename="report.pdf",
            stored_filename="abc_report.pdf",
            extension="pdf",
            file_size=1024,
            uploaded_by=self.user,
            file=SimpleUploadedFile("report.pdf", b"content"),
        )

    def test_transition_updates_status_and_stage(self):
        DocumentStatusService.transition(self.document, DocumentStatus.STORED)
        self.assertEqual(self.document.status, DocumentStatus.STORED)
        self.assertEqual(self.document.processing_stage, DocumentStatus.STORED)

    def test_transition_updates_percentage(self):
        DocumentStatusService.transition(self.document, DocumentStatus.READY_FOR_PARSING)
        self.assertEqual(self.document.processing_percentage, 25)

    def test_transition_to_failed_requires_error_message(self):
        with self.assertRaises(ValueError):
            DocumentStatusService.transition(self.document, DocumentStatus.FAILED)

    def test_transition_to_failed_preserves_last_stage(self):
        DocumentStatusService.transition(self.document, DocumentStatus.STORED)
        DocumentStatusService.transition(
            self.document, DocumentStatus.FAILED, error_message="Disk full"
        )
        self.assertEqual(self.document.status, DocumentStatus.FAILED)
        self.assertEqual(self.document.processing_stage, DocumentStatus.STORED)
        self.assertEqual(self.document.error_message, "Disk full")

    def test_get_status_returns_expected_keys(self):
        summary = DocumentStatusService.get_status(self.document)
        self.assertEqual(
            set(summary.keys()),
            {
                "id",
                "status",
                "status_display",
                "processing_stage",
                "processing_stage_display",
                "processing_percentage",
                "error_message",
                "is_terminal",
            },
        )

    def tearDown(self):
        if self.document.file:
            self.document.file.delete(save=False)


class DocumentProcessingServiceTests(TestCase):
    """
    Confirms the orchestration architecture correctly refuses to
    perform AI work that has not been implemented yet.

    As of Sprint 5, `run_parser` is implemented — see
    `test_run_parser_raises_parser_error_for_invalid_file` below (this
    class's fixture uses a fake, non-PDF payload) and
    `apps.documents.tests.test_parser_integration` (full success-path
    coverage against real sample documents).

    As of Sprint 6, `run_chunker` is also implemented — see
    `test_run_chunker_raises_chunking_error_for_none_parsed_content`
    below and `apps.documents.tests.test_chunker_integration` (full
    success-path coverage).

    As of Sprint 7, `run_embedding_generator` is also implemented —
    see `test_run_embedding_generator_raises_embedding_error_for_none`
    below and `apps.documents.tests.test_embedding_integration` (full
    success-path coverage with mocked API).

    As of Sprint 8, `store_in_vector_db` is also implemented — see
    `test_store_in_vector_db_raises_vector_store_error_for_none` below
    and `apps.documents.tests.test_vectorstore_integration` (full
    success-path coverage). The remaining stage method
    (`update_knowledge_graph`) still encodes the "MUST NOT be
    implemented" requirement as an executable contract.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="alex", password="testpass123")
        self.document = Document.objects.create(
            original_filename="report.pdf",
            stored_filename="abc_report.pdf",
            extension="pdf",
            file_size=1024,
            uploaded_by=self.user,
            status=DocumentStatus.READY_FOR_PARSING,
            file=SimpleUploadedFile("report.pdf", b"content"),
        )

    def test_run_parser_raises_parser_error_for_invalid_file(self):
        # As of Sprint 5, run_parser is implemented (see
        # apps.documents.tests.test_parser_integration for full
        # coverage of the success path against real sample documents).
        # This class's fixture document has a fake, non-PDF payload, so
        # it now exercises the real parser's error path
        # (ParserError) rather than the pre-Sprint-5 NotImplementedError.
        with self.assertRaises(ParserError):
            DocumentProcessingService.run_parser(self.document)

    def test_run_chunker_raises_chunking_error_for_none_parsed_content(self):
        # As of Sprint 6, run_chunker is implemented — passing None for
        # parsed_content (which would never happen in the real
        # run_parser -> run_chunker flow) now surfaces as a
        # ChunkingError from the chunking module's own input
        # validation, not NotImplementedError. Full success-path
        # coverage lives in
        # apps.documents.tests.test_chunker_integration.
        with self.assertRaises(ChunkingError):
            DocumentProcessingService.run_chunker(self.document, parsed_content=None)

    def test_run_embedding_generator_raises_embedding_error_for_none(self):
        # As of Sprint 7, run_embedding_generator is implemented —
        # passing None for chunk_collection (which would never happen
        # in the real run_chunker -> run_embedding_generator flow) now
        # surfaces as an EmbeddingValidationError from the embedding
        # module's own input validation, not NotImplementedError. Full
        # success-path coverage lives in
        # apps.documents.tests.test_embedding_integration.
        from rag.embeddings.exceptions import EmbeddingError

        with self.assertRaises(EmbeddingError):
            DocumentProcessingService.run_embedding_generator(
                self.document, chunk_collection=None
            )

    def test_store_in_vector_db_raises_vector_store_error_for_none(self):
        # As of Sprint 8, store_in_vector_db is implemented — passing
        # None for embedding_result (which would never happen in the
        # real flow) now surfaces as a VectorStoreValidationError from
        # the vector store module's own input validation, not
        # NotImplementedError. Full success-path coverage lives in
        # apps.documents.tests.test_vectorstore_integration.
        from rag.vectorstore.exceptions import VectorStoreError

        self.document.status = DocumentStatus.EMBEDDED
        self.document.save()

        with self.assertRaises(VectorStoreError):
            DocumentProcessingService.store_in_vector_db(
                self.document, None
            )

    def test_update_knowledge_graph_processes_empty_content(self):
        # As of Sprint 9, update_knowledge_graph is implemented —
        # passing None for parsed_content results in empty text being
        # passed to the KG service, which gracefully returns an empty
        # ExtractionResult. Full success-path coverage lives in
        # knowledge_graph.tests.test_knowledge_graph.
        self.document.status = DocumentStatus.VECTOR_INDEXED
        self.document.save()

        from knowledge_graph.graph import GraphService
        GraphService.reset()

        result = DocumentProcessingService.update_knowledge_graph(
            self.document, parsed_content=None
        )
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, DocumentStatus.INDEXED)
        self.assertEqual(result.entity_count, 0)

    def test_run_full_pipeline_raises_at_first_stage(self):
        # run_parser now succeeds/fails for real; run_chunker and
        # run_embedding_generator are also implemented. This fixture's
        # fake (non-PDF) file makes run_parser itself fail, which still
        # demonstrates the pipeline halts before reaching any
        # unimplemented stage.
        with self.assertRaises(ParserError):
            DocumentProcessingService.run_full_pipeline(self.document)

    def tearDown(self):
        if self.document.file:
            self.document.file.delete(save=False)
