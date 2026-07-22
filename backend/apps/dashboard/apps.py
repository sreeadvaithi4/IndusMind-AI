from django.apps import AppConfig


class DashboardConfig(AppConfig):
    """Application configuration for the enterprise dashboard app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.dashboard"
    label = "dashboard"
    verbose_name = "Dashboard"
