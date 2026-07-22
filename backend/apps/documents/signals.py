"""
Signal handlers for the Document Management app.

Currently:
    - Automatic cleanup of the stored file on disk when its owning
      `Document` row is deleted.
    - Automatic cleanup of ChromaDB vectors for the deleted document
      (Sprint 8).
    - Automatic cleanup of Knowledge Graph entities for the deleted
      document (Sprint 9 stabilization).
"""

import logging

from django.db.models.signals import post_delete
from django.dispatch import receiver

from apps.documents.models import Document
from apps.documents.services import DocumentStorageService

logger = logging.getLogger("apps.documents")


@receiver(post_delete, sender=Document)
def delete_document_file_on_delete(sender, instance, **kwargs):
    """Removes the stored file from disk after its Document row is deleted."""
    try:
        DocumentStorageService.delete_document_file(instance)
    except OSError as exc:
        logger.error(
            "Failed to delete stored file for document %s during cleanup: %s",
            instance.pk,
            exc,
        )


@receiver(post_delete, sender=Document)
def delete_document_vectors_on_delete(sender, instance, **kwargs):
    """
    Removes all ChromaDB vectors for this document after deletion.
    """
    try:
        from rag.vectorstore.service import VectorStoreService

        deleted = VectorStoreService.delete_document_vectors(str(instance.pk))
        if deleted > 0:
            logger.info(
                "Cleaned up %d vector(s) from ChromaDB for deleted document %s.",
                deleted,
                instance.pk,
            )
    except Exception as exc:
        logger.warning(
            "Failed to clean up ChromaDB vectors for document %s: %s",
            instance.pk,
            exc,
        )


@receiver(post_delete, sender=Document)
def delete_document_kg_entities_on_delete(sender, instance, **kwargs):
    """
    Removes Knowledge Graph entities exclusively sourced from this
    document after deletion.
    """
    try:
        from knowledge_graph.service import KnowledgeGraphService

        removed = KnowledgeGraphService.delete_document(str(instance.pk))
        if removed > 0:
            logger.info(
                "Cleaned up %d KG node(s) for deleted document %s.",
                removed,
                instance.pk,
            )
    except Exception as exc:
        logger.warning(
            "Failed to clean up KG entities for document %s: %s",
            instance.pk,
            exc,
        )
