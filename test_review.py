#!/usr/bin/env python3
"""Tests for the OCR typo pass."""
import unittest

import review


class TestParseFixes(unittest.TestCase):
    def test_well_formed_pairs_are_kept(self):
        self.assertEqual(
            review.parse_fixes('[{"find": "teh", "replace": "the"}]'),
            [{"find": "teh", "replace": "the"}],
        )

    def test_objects_missing_a_key_are_dropped(self):
        self.assertEqual(review.parse_fixes('[{"find": "teh"}]'), [])

    def test_bare_strings_are_dropped(self):
        self.assertEqual(review.parse_fixes('["teh"]'), [])


class TestApplyFixes(unittest.TestCase):
    def test_uniquely_matching_fix_is_applied(self):
        text, applied, skipped = review.apply_fixes(
            "the monthsof waiting", [{"find": "monthsof", "replace": "months of"}]
        )
        self.assertEqual(text, "the months of waiting")
        self.assertEqual((applied, skipped), (1, 0))

    def test_ambiguous_fix_is_skipped(self):
        text, applied, skipped = review.apply_fixes(
            "teh and teh", [{"find": "teh", "replace": "the"}]
        )
        self.assertEqual(text, "teh and teh")
        self.assertEqual((applied, skipped), (0, 1))

    def test_fix_that_matches_nothing_is_skipped(self):
        _, applied, skipped = review.apply_fixes("abc", [{"find": "zzz", "replace": "y"}])
        self.assertEqual((applied, skipped), (0, 1))

    def test_overlapping_fixes_keep_only_the_first(self):
        text, applied, skipped = review.apply_fixes(
            "one two three",
            [{"find": "one two", "replace": "1 2"}, {"find": "two three", "replace": "2 3"}],
        )
        self.assertEqual(text, "1 2 three")
        self.assertEqual((applied, skipped), (1, 1))

    def test_multiple_independent_fixes_all_apply(self):
        text, applied, _ = review.apply_fixes(
            "alpha bravo charlie",
            [{"find": "alpha", "replace": "A"}, {"find": "charlie", "replace": "C"}],
        )
        self.assertEqual(text, "A bravo C")
        self.assertEqual(applied, 2)

    def test_fix_that_adds_or_removes_a_line_break_is_skipped(self):
        # clean.py's block kinds line up with the blank-line-separated blocks,
        # so a typo fix may not join or split blocks
        text, applied, skipped = review.apply_fixes(
            "ENOUGH\n\nfter twenty years", [{"find": "ENOUGH\n\nfter", "replace": "ENOUGH After"}]
        )
        self.assertEqual((text, applied, skipped), ("ENOUGH\n\nfter twenty years", 0, 1))

    def test_fix_that_splits_one_paragraph_keeps_the_fix_but_not_the_split(self):
        # the model often bundles a real typo fix with undoing a merged paragraph
        text, applied, skipped = review.apply_fixes(
            '"Are you going to be Okayi "If surgery goes well',
            [{"find": "be Okayi \"If", "replace": "be Okay?\"\n\n\"If"}],
        )
        self.assertEqual(text, '"Are you going to be Okay?" "If surgery goes well')
        self.assertEqual((applied, skipped), (1, 0))

    def test_non_string_fields_are_skipped(self):
        _, applied, skipped = review.apply_fixes("abc", [{"find": 42, "replace": "y"}])
        self.assertEqual((applied, skipped), (0, 1))


class TestSplitLongChunks(unittest.TestCase):
    def test_short_chunks_pass_through(self):
        self.assertEqual(review.split_long_chunks(["a\n\nb"], budget=100), ["a\n\nb"])

    def test_long_chunk_is_cut_at_paragraph_breaks(self):
        paras = ["x" * 40] * 10
        chunks = review.split_long_chunks(["\n\n".join(paras)], budget=100)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c) <= 100 for c in chunks))
        self.assertEqual("\n\n".join(chunks), "\n\n".join(paras))
