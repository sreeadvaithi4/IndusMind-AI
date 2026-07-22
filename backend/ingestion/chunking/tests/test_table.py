"""Unit tests for table-aware chunking."""

from django.test import TestCase

from ingestion.chunking.config import ChunkingConfig
from ingestion.chunking.strategies.table import chunk_table


class ChunkTableTests(TestCase):
    def test_returns_empty_list_for_empty_table(self):
        config = ChunkingConfig()
        self.assertEqual(chunk_table([], config), [])

    def test_returns_empty_list_for_header_only_table(self):
        config = ChunkingConfig()
        table = [["col_a", "col_b"]]
        self.assertEqual(chunk_table(table, config), [])

    def test_small_table_returns_single_chunk(self):
        config = ChunkingConfig(max_chunk_length=2000)
        table = [
            ["equipment_id", "failure_mode"],
            ["EQ-101", "Bearing Failure"],
            ["EQ-102", "Vibration"],
        ]
        chunks = chunk_table(table, config)
        self.assertEqual(len(chunks), 1)
        self.assertIn("equipment_id", chunks[0])
        self.assertIn("EQ-101", chunks[0])

    def test_preserves_header_in_every_chunk_for_large_table(self):
        config = ChunkingConfig(chunk_size=150, chunk_overlap=0, max_chunk_length=150)
        header = ["id", "value"]
        rows = [[str(i), f"value_{i}" * 3] for i in range(50)]
        table = [header] + rows

        chunks = chunk_table(table, config)

        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertIn("id", chunk)
            self.assertIn("value", chunk)

    def test_all_rows_are_represented_across_chunks(self):
        config = ChunkingConfig(chunk_size=150, chunk_overlap=0, max_chunk_length=150)
        header = ["id"]
        rows = [[f"row_{i}"] for i in range(30)]
        table = [header] + rows

        chunks = chunk_table(table, config)
        combined = "\n".join(chunks)

        for i in range(30):
            self.assertIn(f"row_{i}", combined)
