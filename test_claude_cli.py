#!/usr/bin/env python3
"""Tests for parsing what `claude -p` hands back."""
import unittest

import claude_cli


class TestParseJsonArray(unittest.TestCase):
    def test_plain_json_array(self):
        self.assertEqual(claude_cli.parse_json_array('["a", "b"]'), ["a", "b"])

    def test_array_inside_a_fenced_code_block(self):
        self.assertEqual(claude_cli.parse_json_array('```json\n["a"]\n```'), ["a"])

    def test_array_surrounded_by_prose(self):
        raw = 'Here are the fixes:\n["a", "b"]\nHope that helps!'
        self.assertEqual(claude_cli.parse_json_array(raw), ["a", "b"])

    def test_empty_array(self):
        self.assertEqual(claude_cli.parse_json_array("[]"), [])

    def test_unparseable_response_yields_empty_list(self):
        self.assertEqual(claude_cli.parse_json_array("I could not do that."), [])

    def test_json_object_instead_of_array_yields_empty_list(self):
        self.assertEqual(claude_cli.parse_json_array('{"a": 1}'), [])
