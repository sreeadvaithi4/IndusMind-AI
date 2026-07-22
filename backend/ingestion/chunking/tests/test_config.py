"""Unit tests for ChunkingConfig."""

from django.test import TestCase, override_settings

from ingestion.chunking.config import ChunkingConfig


class ChunkingConfigTests(TestCase):
    def test_defaults(self):
        config = ChunkingConfig()
        self.assertEqual(config.chunk_size, 1000)
        self.assertEqual(config.chunk_overlap, 150)
        self.assertEqual(config.max_chunk_length, 2000)
        self.assertEqual(config.min_chunk_length, 20)

    def test_rejects_zero_or_negative_chunk_size(self):
        with self.assertRaises(ValueError):
            ChunkingConfig(chunk_size=0)

    def test_rejects_negative_overlap(self):
        with self.assertRaises(ValueError):
            ChunkingConfig(chunk_overlap=-1)

    def test_rejects_overlap_greater_than_or_equal_to_chunk_size(self):
        with self.assertRaises(ValueError):
            ChunkingConfig(chunk_size=100, chunk_overlap=100)

    def test_rejects_max_chunk_length_smaller_than_chunk_size(self):
        with self.assertRaises(ValueError):
            ChunkingConfig(chunk_size=1000, max_chunk_length=500)

    def test_rejects_negative_min_chunk_length(self):
        with self.assertRaises(ValueError):
            ChunkingConfig(min_chunk_length=-1)

    @override_settings(
        CHUNKING_CHUNK_SIZE=500,
        CHUNKING_CHUNK_OVERLAP=50,
        CHUNKING_MAX_CHUNK_LENGTH=1000,
        CHUNKING_MIN_CHUNK_LENGTH=10,
    )
    def test_from_settings_reads_django_settings(self):
        config = ChunkingConfig.from_settings()
        self.assertEqual(config.chunk_size, 500)
        self.assertEqual(config.chunk_overlap, 50)
        self.assertEqual(config.max_chunk_length, 1000)
        self.assertEqual(config.min_chunk_length, 10)

    def test_from_settings_falls_back_to_defaults_when_unset(self):
        config = ChunkingConfig.from_settings()
        self.assertEqual(config.chunk_size, 1000)
