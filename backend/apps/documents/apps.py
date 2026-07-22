from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    """Application configuration for the document management app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.documents"
    label = "documents"
    verbose_name = "Document Management"

    def ready(self):
        # Import signal handlers so they are registered when the app
        # loads. Imported here (not at module top-level) to avoid
        # premature app-registry access, per Django convention.
        from apps.documents import signals  # noqa: F401
