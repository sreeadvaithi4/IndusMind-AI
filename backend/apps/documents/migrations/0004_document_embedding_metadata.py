"""
Migration: Add embedding_metadata JSONField to Document model.

Sprint 7 — Embedding Generator module populates this field with a
summary of the embedding generation run (model, dimension, counts,
timing, warnings).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0003_document_chunker_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="embedding_metadata",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Structured metadata returned by the Embedding Generator "
                    "(model, dimension, counts, timing, warnings). Empty until embedded."
                ),
            ),
        ),
    ]
