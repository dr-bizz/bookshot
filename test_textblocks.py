#!/usr/bin/env python3
"""Tests for the shared line classifiers."""
import unittest

import textblocks


class TestChapterHeading(unittest.TestCase):
    def test_allcaps_line_is_a_chapter_heading(self):
        self.assertTrue(textblocks.is_chapter_heading("THE SECOND AGREEMENT"))

    def test_mixed_case_line_is_not(self):
        self.assertFalse(textblocks.is_chapter_heading("The Second Agreement"))

    def test_short_acronym_is_not(self):
        # two-letter initials shouldn't trip the detector
        self.assertFalse(textblocks.is_chapter_heading("J.R."))

    def test_long_allcaps_line_is_not(self):
        # a shouted sentence is prose, not a heading
        self.assertFalse(textblocks.is_chapter_heading("A" * 61))

    def test_quoted_allcaps_is_not(self):
        self.assertFalse(textblocks.is_chapter_heading('"SHOUTING DIALOGUE"'))


class TestBullet(unittest.TestCase):
    def test_dash_space_prefix_is_a_bullet(self):
        self.assertTrue(textblocks.is_bullet("- first item"))

    def test_plain_line_is_not(self):
        self.assertFalse(textblocks.is_bullet("first item"))


if __name__ == "__main__":
    unittest.main()


class TestSplitIntoChunks(unittest.TestCase):
    def test_text_without_headings_is_one_chunk(self):
        self.assertEqual(textblocks.split_into_chunks("just prose\nmore prose"), ["just prose\nmore prose"])

    def test_small_chapters_are_grouped_into_one_chunk(self):
        text = "CHAPTER ONE\nshort\nCHAPTER TWO\nalso short"
        self.assertEqual(len(textblocks.split_into_chunks(text)), 1)

    def test_chapters_are_split_once_they_exceed_the_budget(self):
        body = "x" * 6000
        text = f"CHAPTER ONE\n{body}\nCHAPTER TWO\n{body}"
        self.assertEqual(len(textblocks.split_into_chunks(text, budget=8000)), 2)

    def test_every_chunk_boundary_starts_at_a_chapter_heading(self):
        body = "x" * 6000
        text = f"CHAPTER ONE\n{body}\nCHAPTER TWO\n{body}"
        chunks = textblocks.split_into_chunks(text, budget=8000)
        self.assertTrue(chunks[1].startswith("CHAPTER TWO"))

    def test_no_text_is_lost_when_chunking(self):
        body = "x" * 6000
        text = f"CHAPTER ONE\n{body}\nCHAPTER TWO\n{body}"
        chunks = textblocks.split_into_chunks(text, budget=8000)
        self.assertEqual("\n".join(chunks), text)
