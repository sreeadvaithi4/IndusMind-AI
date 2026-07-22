"""Unit tests for the header-aware section splitter."""

from django.test import TestCase

from ingestion.chunking.strategies.header_aware import split_into_sections


class SplitIntoSectionsTests(TestCase):
    def test_returns_empty_list_for_empty_text(self):
        self.assertEqual(split_into_sections(""), [])

    def test_single_section_with_no_headings(self):
        text = "Just a plain paragraph with no headings at all."
        sections = split_into_sections(text)
        self.assertEqual(len(sections), 1)
        self.assertIsNone(sections[0][0])

    def test_detects_markdown_heading(self):
        text = "# Introduction\nSome intro text.\n\n# Conclusion\nSome closing text."
        sections = split_into_sections(text)
        titles = [title for title, _ in sections]
        self.assertIn("Introduction", titles)
        self.assertIn("Conclusion", titles)

    def test_detects_all_caps_heading(self):
        text = "SAFETY PRECAUTIONS\nAlways wear protective equipment.\n\nMAINTENANCE\nCheck the oil level weekly."
        sections = split_into_sections(text)
        titles = [title for title, _ in sections]
        self.assertIn("SAFETY PRECAUTIONS", titles)
        self.assertIn("MAINTENANCE", titles)

    def test_detects_numbered_heading(self):
        text = "1. Overview\nThis document covers turbine maintenance.\n\n2. Procedure\nFollow these steps."
        sections = split_into_sections(text)
        self.assertEqual(len(sections), 2)

    def test_ignores_long_lines_as_headings(self):
        long_line = "A" * 200
        text = f"{long_line}\nBody text here."
        sections = split_into_sections(text)
        self.assertEqual(len(sections), 1)
        self.assertIsNone(sections[0][0])

    def test_content_before_first_heading_has_none_title(self):
        text = "Preamble content.\n\n# First Heading\nBody."
        sections = split_into_sections(text)
        self.assertIsNone(sections[0][0])
        self.assertIn("Preamble", sections[0][1])
