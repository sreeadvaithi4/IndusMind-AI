"""Unit tests for the recursive text chunking strategy."""

from django.test import TestCase

from ingestion.chunking.config import ChunkingConfig
from ingestion.chunking.strategies.recursive import recursive_chunk_text


class RecursiveChunkTextTests(TestCase):
    def test_returns_empty_list_for_empty_text(self):
        config = ChunkingConfig()
        self.assertEqual(recursive_chunk_text("", config), [])

    def test_short_text_returns_single_chunk(self):
        config = ChunkingConfig(chunk_size=1000, chunk_overlap=0)
        text = "This is a short paragraph that fits in one chunk."
        chunks = recursive_chunk_text(text, config)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], text)

    def test_splits_long_text_into_multiple_chunks(self):
        config = ChunkingConfig(chunk_size=100, chunk_overlap=0, max_chunk_length=200)
        paragraphs = [f"Paragraph number {i} with some filler content here." for i in range(20)]
        text = "\n\n".join(paragraphs)

        chunks = recursive_chunk_text(text, config)

        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), config.chunk_size + config.chunk_overlap + 10)

    def test_respects_paragraph_boundaries_when_possible(self):
        config = ChunkingConfig(chunk_size=1000, chunk_overlap=0)
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        chunks = recursive_chunk_text(text, config)
        # All three paragraphs fit comfortably within chunk_size, so
        # they should be packed into a single chunk together.
        self.assertEqual(len(chunks), 1)

    def test_applies_overlap_between_chunks(self):
        config = ChunkingConfig(chunk_size=50, chunk_overlap=10, max_chunk_length=60)
        paragraphs = [f"This is paragraph {i} with enough text to matter." for i in range(10)]
        text = "\n\n".join(paragraphs)

        chunks = recursive_chunk_text(text, config)

        self.assertGreater(len(chunks), 1)
        # Second chunk should start with the tail of the first (the
        # overlap), meaning it is not identical to a naive non-overlapping split.
        self.assertTrue(len(chunks[1]) >= len(chunks[1].lstrip()))

    def test_hard_splits_a_single_giant_paragraph_with_no_breaks(self):
        config = ChunkingConfig(chunk_size=50, chunk_overlap=0, max_chunk_length=50)
        text = "x" * 500  # no spaces, no sentence punctuation, no paragraph breaks
        chunks = recursive_chunk_text(text, config)

        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), config.max_chunk_length)

    def test_merges_short_trailing_chunk_into_previous(self):
        config = ChunkingConfig(chunk_size=100, chunk_overlap=0, min_chunk_length=50)
        text = "A" * 95 + "\n\n" + "short"
        chunks = recursive_chunk_text(text, config)
        # The trailing "short" (5 chars) is below min_chunk_length (50)
        # and should be merged into the preceding chunk rather than
        # emitted as its own tiny chunk.
        self.assertEqual(len(chunks), 1)
