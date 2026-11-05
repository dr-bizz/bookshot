#!/usr/bin/env python3
"""Tests for the emphasis pass."""
import unittest

import emphasis


class TestParseSpans(unittest.TestCase):
    def test_array_of_strings(self):
        self.assertEqual(emphasis.parse_spans('["never", "always"]'), ["never", "always"])

    def test_non_string_entries_are_dropped(self):
        self.assertEqual(emphasis.parse_spans('["ok", 42, null]'), ["ok"])

    def test_empty_strings_are_dropped(self):
        self.assertEqual(emphasis.parse_spans('["ok", ""]'), ["ok"])

    def test_unparseable_response_yields_no_spans(self):
        self.assertEqual(emphasis.parse_spans("sorry!"), [])


class TestSpanSanity(unittest.TestCase):
    def test_span_longer_than_the_cap_is_rejected(self):
        # a narrator stresses words, not whole sentences
        long_span = " ".join(["word"] * 20)
        self.assertEqual(emphasis.usable_spans(long_span + " here", [long_span]), [])

    def test_span_absent_from_the_text_is_rejected(self):
        self.assertEqual(emphasis.usable_spans("the quick fox", ["slow"]), [])

    def test_span_present_in_the_text_is_kept(self):
        self.assertEqual(emphasis.usable_spans("the quick fox", ["quick"]), ["quick"])

    def test_duplicate_spans_are_collapsed(self):
        self.assertEqual(emphasis.usable_spans("a quick fox", ["quick", "quick"]), ["quick"])
