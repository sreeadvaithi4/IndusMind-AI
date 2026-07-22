"""Unit tests for sentence-aware splitting."""

from django.test import TestCase

from ingestion.chunking.strategies.sentence import split_into_sentences


class SplitIntoSentencesTests(TestCase):
    def test_returns_empty_list_for_empty_text(self):
        self.assertEqual(split_into_sentences(""), [])

    def test_splits_multiple_sentences(self):
        text = "This is the first sentence. This is the second sentence. And a third one!"
        sentences = split_into_sentences(text)
        self.assertEqual(len(sentences), 3)

    def test_single_sentence_returns_one_item(self):
        sentences = split_into_sentences("Just one sentence with no other breaks")
        self.assertEqual(len(sentences), 1)

    def test_handles_question_marks(self):
        text = "Is this a question? Yes it is. Great."
        sentences = split_into_sentences(text)
        self.assertEqual(len(sentences), 3)
