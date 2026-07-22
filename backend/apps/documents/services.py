"""
Service layer for the Document Management app.

Views never touch models, storage, or validators directly — they call
into these services. This keeps the API layer thin and gives future
sprints a stable seam to build against.

Services in this module:

    DocumentUploadService      Fully implemented. Validates and stores
                                an uploaded file and creates its
                                `Document` row.

    DocumentStatusService       Fully implemented. Reads and updates a
                                 Document's status/stage/percentage.

    DocumentStorageService        Fully implemented. Thin wrapper around
                                    the storage layer for use by views
                                    (e.g. deletion).

    DocumentProcessingService       Orchestration for the AI pipeline
                                     stages. `run_parser` (Sprint 5),
                                     `run_chunker` (Sprint 6), and
                                     `run_embedding_generator` (Sprint 7)
                                     are fully implemented. ChromaDB and
                                     Knowledge Graph remain
                                     unimplemented — those methods still
                                     raise NotImplementedError.
"""

import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction

from apps.documents.models import Document, DocumentStatus
from apps.documents.storage import DocumentStorage
from apps.documents.validators import validate_upload

logger = logging.getLogger("apps.documents")


class DocumentUploadServiceError(Exception):
    """Raised when an upload cannot be accepted (validation or storage failure)."""


class DocumentUploadService:
    """
    Handles the Upload -> Validate -> Store File -> Ready For Parsing
    portion of the pipeline. This is the only service in this module
    that performs the full upload flow end-to-end.
    """

    @staticmethod
    @transaction.atomic
    def upload(uploaded_file, user):
        """
        Validates and persists an uploaded file, creating its Document
        row in a single transaction.

        Args:
            uploaded_file: a Django `UploadedFile` (e.g. from
                `request.FILES["file"]`).
            user: the authenticated user performing the upload.

        Returns:
            The created `Document` instance, with status
            `READY_FOR_PARSING`.

        Raises:
            DocumentUploadServiceError: if validation fails or the file
                cannot be stored.
        """
        try:
            extension = validate_upload(uploaded_file.name, uploaded_file.size)
        except DjangoValidationError as exc:
            raise DocumentUploadServiceError(str(exc.message)) from exc

        document = Document(
            original_filename=uploaded_file.name,
            extension=extension,
            file_size=uploaded_file.size,
            uploaded_by=user,
            status=DocumentStatus.UPLOADED,
            processing_stage=DocumentStatus.UPLOADED,
        )

        DocumentStatusService.transition(
            document, DocumentStatus.VALIDATING, save=False
        )

        try:
            document.file = uploaded_file
            document.stored_filename = DocumentStorage.stored_filename_from_path(
                document.file.field.generate_filename(document, uploaded_file.name)
            )
            document.save()
        except OSError as exc:
            logger.error(
                "Failed to store uploaded file '%s' for user %s: %s",
                uploaded_file.name,
                user.pk,
                exc,
            )
            raise DocumentUploadServiceError(
                "The file could not be saved due to a storage error. Please try again."
            ) from exc

        DocumentStatusService.transition(document, DocumentStatus.STORED)
        DocumentStatusService.transition(document, DocumentStatus.READY_FOR_PARSING)

        logger.info(
            "Document %s uploaded by user %s (%s, %d bytes) — ready for parsing.",
            document.id,
            user.pk,
            extension,
            document.file_size,
        )

        return document

    @staticmethod
    def get_existing_filenames_for_user(user):
        """
        Returns the set of original filenames this user has previously
        uploaded, for duplicate-filename warning checks performed by
        the caller (e.g. the serializer or a future UI-facing endpoint).
        """
        return set(
            Document.objects.filter(uploaded_by=user).values_list(
                "original_filename", flat=True
            )
        )


class DocumentStatusService:
    """
    Owns all status/stage/percentage transitions for a Document. Other
    services and views must go through this class rather than setting
    `document.status` directly, so every transition is logged
    consistently and the processing_percentage stays in sync with the
    stage.
    """

    # Maps each stage to its overall pipeline completion percentage.
    # Percentages for not-yet-implemented stages are reserved here so
    # the mapping doesn't need to change again as those modules land.
    STAGE_PERCENTAGE = {
        DocumentStatus.UPLOADED: 5,
        DocumentStatus.VALIDATING: 10,
        DocumentStatus.STORED: 20,
        DocumentStatus.READY_FOR_PARSING: 25,
        DocumentStatus.PARSING: 35,
        DocumentStatus.PARSED: 45,
        DocumentStatus.CHUNKING: 55,
        DocumentStatus.CHUNKED: 65,
        DocumentStatus.EMBEDDING: 75,
        DocumentStatus.EMBEDDED: 85,
        DocumentStatus.INDEXING_VECTOR_DB: 90,
        DocumentStatus.VECTOR_INDEXED: 95,
        DocumentStatus.INDEXING_KNOWLEDGE_GRAPH: 98,
        DocumentStatus.INDEXED: 100,
        DocumentStatus.FAILED: 0,
    }

    @classmethod
    def transition(cls, document, new_status, *, save=True, error_message=None):
        """
        Moves `document` to `new_status`, updating `processing_stage`
        and `processing_percentage` accordingly.

        FAILED transitions preserve the last active `processing_stage`
        (rather than overwriting it with FAILED) so callers can display
        "Failed while Parsing" instead of just "Failed", and require an
        `error_message`.
        """
        if new_status == DocumentStatus.FAILED:
            if not error_message:
                raise ValueError("error_message is required when transitioning to FAILED.")
            document.status = DocumentStatus.FAILED
            document.error_message = error_message
            logger.warning(
                "Document %s failed at stage %s: %s",
                document.pk,
                document.processing_stage,
                error_message,
            )
        else:
            document.status = new_status
            document.processing_stage = new_status
            document.processing_percentage = cls.STAGE_PERCENTAGE.get(new_status, 0)
            document.error_message = ""

        if save:
            document.save()

        return document

    @staticmethod
    def get_status(document):
        """
        Returns a plain dict summary of a document's current status,
        used by both the `status` and `processing-status` API actions.
        """
        return {
            "id": str(document.id),
            "status": document.status,
            "status_display": document.get_status_display(),
            "processing_stage": document.processing_stage,
            "processing_stage_display": document.get_processing_stage_display(),
            "processing_percentage": document.processing_percentage,
            "error_message": document.error_message,
            "is_terminal": document.is_terminal,
        }


class DocumentStorageService:
    """
    Thin service-layer wrapper around the storage layer, so views never
    import `DocumentStorage` (or touch the filesystem) directly.
    """

    @staticmethod
    def delete_document_file(document):
        """Deletes the stored file for `document` from disk, if present."""
        DocumentStorage.delete_file(document.file)


class DocumentProcessingService:
    """
    Orchestration architecture for the AI ingestion pipeline:

        Ready For Parsing -> Parsing -> Parsed -> Chunking -> Chunked
        -> Embedding -> Embedded -> Indexing (ChromaDB)
        -> Vector Indexed -> Indexing (Knowledge Graph) -> Indexed

    This class defines *where* each future module plugs in and *how*
    the orchestrator will sequence and record stage transitions once
    those modules exist.

    As of Sprint 7, `run_parser`, `run_chunker`, and
    `run_embedding_generator` are fully implemented (delegating to
    `ingestion.service.DocumentParserService`,
    `ingestion.chunking.service.DocumentChunkerService`, and
    `rag.embeddings.service.EmbeddingGeneratorService` respectively).
    Vector storage and knowledge graph updates remain unimplemented —
    each of those stage methods still raises NotImplementedError with a
    pointer to the module that will implement it.

    Future modules should implement their corresponding method (or
    register themselves as pluggable strategies here) rather than
    duplicating status-transition logic — that logic already exists in
    `DocumentStatusService` and should continue to be reused.
    """

    @staticmethod
    def run_parser(document):
        """
        Parses `document`'s stored file via `ingestion.service.DocumentParserService`,
        transitioning READY_FOR_PARSING -> PARSING -> PARSED on success,
        or -> FAILED (with processing_stage left at PARSING, so the UI
        can render "Failed while Parsing") on any parser error.

        Persists a summary of the parse result onto
        `document.page_count` and `document.parser_metadata` — the full
        extracted text and tables are NOT persisted onto the Document
        row (they would bloat the database and are only needed
        in-memory by the next pipeline stage); this method returns the
        full in-memory `ParsedDocument` for `run_chunker` to consume
        directly when the pipeline is run end-to-end.

        Returns:
            ingestion.result.ParsedDocument

        Raises:
            ingestion.exceptions.ParserError: re-raised after recording
                the FAILED transition, so callers (e.g. the API view)
                can still report a specific error to the client.
        """
        from ingestion.exceptions import ParserError
        from ingestion.service import DocumentParserService

        DocumentStatusService.transition(document, DocumentStatus.PARSING)

        try:
            parsed_document = DocumentParserService.parse_document(
                file_path=document.file.path,
                extension=document.extension,
                document_id=str(document.id),
            )
        except ParserError as exc:
            DocumentStatusService.transition(
                document, DocumentStatus.FAILED, error_message=str(exc)
            )
            raise

        document.page_count = parsed_document.metadata.page_count
        document.parser_metadata = parsed_document.to_dict()
        DocumentStatusService.transition(document, DocumentStatus.PARSED)

        return parsed_document

    @staticmethod
    def run_chunker(document, parsed_content):
        """
        Chunks `parsed_content` (the `ParsedDocument` returned by
        `run_parser`) via `ingestion.chunking.service.DocumentChunkerService`,
        transitioning PARSED -> CHUNKING -> CHUNKED on success, or ->
        FAILED (with processing_stage left at CHUNKING) on any
        chunking error.

        Persists a summary onto `document.chunk_count`,
        `document.chunking_time_seconds`, and
        `document.chunker_metadata` — the full chunk text is NOT
        persisted onto the Document row (same rationale as
        `run_parser` not persisting parsed text: it would bloat the
        database and is only needed in-memory by the next pipeline
        stage). Returns the full in-memory `ChunkCollection` for
        `run_embedding_generator` to consume directly when the
        pipeline is run end-to-end.

        Args:
            document: the Document being processed.
            parsed_content: the `ingestion.result.ParsedDocument`
                returned by `run_parser` for this document.

        Returns:
            ingestion.chunking.result.ChunkCollection

        Raises:
            ingestion.chunking.exceptions.ChunkingError: re-raised
                after recording the FAILED transition.
        """
        from ingestion.chunking.exceptions import ChunkingError
        from ingestion.chunking.service import DocumentChunkerService

        DocumentStatusService.transition(document, DocumentStatus.CHUNKING)

        try:
            chunk_collection = DocumentChunkerService.chunk_document(
                parsed_document=parsed_content,
                filename=document.original_filename,
            )
        except ChunkingError as exc:
            DocumentStatusService.transition(
                document, DocumentStatus.FAILED, error_message=str(exc)
            )
            raise

        document.chunk_count = chunk_collection.total_chunks
        document.chunking_time_seconds = (
            chunk_collection.processing.duration_seconds
            if chunk_collection.processing
            else None
        )
        document.chunker_metadata = chunk_collection.to_dict()
        DocumentStatusService.transition(document, DocumentStatus.CHUNKED)

        return chunk_collection

    @staticmethod
    def run_embedding_generator(document, chunk_collection):
        """
        Generates vector embeddings for all chunks in `chunk_collection`
        via `rag.embeddings.service.EmbeddingGeneratorService`,
        transitioning CHUNKED -> EMBEDDING -> EMBEDDED on success, or
        -> FAILED (with processing_stage left at EMBEDDING and
        embedding_status=FAILED) on any embedding error.

        Persists a summary onto `document.embedding_metadata` (new
        migration field added Sprint 7) and sets
        `document.embedding_status`; the full in-memory
        `EmbeddingResult` (including embedding vectors) is returned for
        `store_in_vector_db` to consume directly when the pipeline is
        run end-to-end.

        Args:
            document: the Document being processed.
            chunk_collection: the `ingestion.chunking.result.ChunkCollection`
                returned by `run_chunker` for this document.

        Returns:
            rag.embeddings.result.EmbeddingResult

        Raises:
            rag.embeddings.exceptions.EmbeddingError: re-raised after
                recording the FAILED transition.
        """
        from apps.documents.models import EmbeddingStatus as ModelEmbeddingStatus
        from rag.embeddings.exceptions import EmbeddingError
        from rag.embeddings.service import EmbeddingGeneratorService

        DocumentStatusService.transition(document, DocumentStatus.EMBEDDING)
        document.embedding_status = ModelEmbeddingStatus.IN_PROGRESS
        document.save(update_fields=["embedding_status"])

        try:
            embedding_result = EmbeddingGeneratorService.generate_embeddings(
                chunk_collection=chunk_collection,
            )
        except EmbeddingError as exc:
            document.embedding_status = ModelEmbeddingStatus.FAILED
            document.save(update_fields=["embedding_status"])
            DocumentStatusService.transition(
                document, DocumentStatus.FAILED, error_message=str(exc)
            )
            raise

        document.embedding_status = ModelEmbeddingStatus.COMPLETED
        document.embedding_metadata = embedding_result.to_dict()
        document.save(update_fields=["embedding_status", "embedding_metadata"])
        DocumentStatusService.transition(document, DocumentStatus.EMBEDDED)

        return embedding_result

    @staticmethod
    def store_in_vector_db(document, embedding_result):
        """
        Persists embedding vectors into ChromaDB via
        `rag.vectorstore.service.VectorStoreService`, transitioning
        EMBEDDED -> INDEXING_VECTOR_DB -> VECTOR_INDEXED on success, or
        -> FAILED (with processing_stage left at INDEXING_VECTOR_DB) on
        any vector store error.

        Before indexing, deletes any existing vectors for this document
        (idempotent re-indexing support). Stores document-level metadata
        (extension, upload date) alongside each vector for filtering.

        Args:
            document: the Document being processed.
            embedding_result: the `rag.embeddings.result.EmbeddingResult`
                returned by `run_embedding_generator` for this document.

        Returns:
            rag.vectorstore.result.IndexingResult

        Raises:
            rag.vectorstore.exceptions.VectorStoreError: re-raised after
                recording the FAILED transition.
        """
        from rag.vectorstore.exceptions import VectorStoreError
        from rag.vectorstore.service import VectorStoreService

        DocumentStatusService.transition(document, DocumentStatus.INDEXING_VECTOR_DB)

        # Prepare document-level metadata for filtering
        document_metadata = {
            "document_type": document.extension,
            "upload_date": document.created_at.isoformat() if document.created_at else "",
            "original_filename": document.original_filename,
        }

        try:
            # Delete existing vectors first (re-index support)
            VectorStoreService.delete_document_vectors(str(document.id))

            indexing_result = VectorStoreService.index_embeddings(
                embedding_result=embedding_result,
                document_metadata=document_metadata,
            )
        except VectorStoreError as exc:
            DocumentStatusService.transition(
                document, DocumentStatus.FAILED, error_message=str(exc)
            )
            raise

        DocumentStatusService.transition(document, DocumentStatus.VECTOR_INDEXED)

        return indexing_result

    @staticmethod
    def update_knowledge_graph(document, parsed_content):
        """
        Extracts entities and relationships from `parsed_content` and
        populates the knowledge graph via
        `knowledge_graph.service.KnowledgeGraphService`, transitioning
        VECTOR_INDEXED -> INDEXING_KNOWLEDGE_GRAPH -> INDEXED on success,
        or -> FAILED (with processing_stage left at
        INDEXING_KNOWLEDGE_GRAPH and knowledge_graph_status=FAILED) on
        any knowledge graph error.

        Args:
            document: the Document being processed.
            parsed_content: the `ingestion.result.ParsedDocument`
                returned by `run_parser` for this document.

        Returns:
            knowledge_graph.models.ExtractionResult

        Raises:
            knowledge_graph.exceptions.KnowledgeGraphError: re-raised
                after recording the FAILED transition.
        """
        from apps.documents.models import KnowledgeGraphStatus as ModelKGStatus
        from knowledge_graph.exceptions import KnowledgeGraphError
        from knowledge_graph.service import KnowledgeGraphService

        DocumentStatusService.transition(
            document, DocumentStatus.INDEXING_KNOWLEDGE_GRAPH
        )
        document.knowledge_graph_status = ModelKGStatus.IN_PROGRESS
        document.save(update_fields=["knowledge_graph_status"])

        # Extract text from parsed_content
        text = ""
        if parsed_content is not None:
            text = getattr(parsed_content, "text", "") or ""

        try:
            extraction_result = KnowledgeGraphService.process_document(
                text=text,
                document_id=str(document.id),
            )
        except KnowledgeGraphError as exc:
            document.knowledge_graph_status = ModelKGStatus.FAILED
            document.save(update_fields=["knowledge_graph_status"])
            DocumentStatusService.transition(
                document, DocumentStatus.FAILED, error_message=str(exc)
            )
            raise

        document.knowledge_graph_status = ModelKGStatus.COMPLETED
        document.save(update_fields=["knowledge_graph_status"])
        DocumentStatusService.transition(document, DocumentStatus.INDEXED)

        return extraction_result

    @classmethod
    def run_full_pipeline(cls, document):
        """
        End-to-end orchestration sequence for future callers (e.g. a
        Celery task once the project becomes Celery-ready). All stages
        are now implemented: run_parser, run_chunker,
        run_embedding_generator, store_in_vector_db, and
        update_knowledge_graph. The document reaches INDEXED on success.
        """
        parsed_document = cls.run_parser(document)
        chunk_collection = cls.run_chunker(document, parsed_document)
        embeddings = cls.run_embedding_generator(document, chunk_collection)
        cls.store_in_vector_db(document, embeddings)
        cls.update_knowledge_graph(document, parsed_document)
