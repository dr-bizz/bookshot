#!/usr/bin/env python3
"""Tests for the rich-text (HTML / Apple Notes) writer.

Speechify's editor keeps the formatting of rich text pasted into it, so the
book goes to Apple Notes as HTML with real headings, paragraphs and lists.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import rich_out

HERE = Path(__file__).parent


def html(text, kinds=None, emphasis=(), title=None):
    return rich_out.build_html(text, kinds, emphasis, title)


class TestBuildHtml(unittest.TestCase):
    def test_heading_kinds_become_heading_tags(self):
        out = html("The Situation\n\nENOUGH\n", ["h1", "h2"])
        self.assertIn("<h1>The Situation</h1>", out)
        self.assertIn("<h2>ENOUGH</h2>", out)

    def test_paragraph_becomes_its_own_div(self):
        out = html("It was time to make a change.\n", ["p"])
        self.assertIn("<div>It was time to make a change.</div>", out)

    def test_blocks_are_separated_by_an_empty_line(self):
        # matches the blank lines in speechify.txt that split Speechify's
        # paragraphs
        out = html("First.\n\nSecond.\n", ["p", "p"])
        self.assertIn("<div>First.</div><div><br></div><div>Second.</div>", out)

    def test_consecutive_bullets_become_one_list(self):
        out = html("- humble\n\n- hungry\n\n- smart\n", ["li", "li", "li"])
        self.assertIn("<ul><li>humble</li><li>hungry</li><li>smart</li></ul>", out)

    def test_emphasis_becomes_italic(self):
        out = html("This word is critical to the point.\n", ["p"], ["critical"])
        self.assertIn("This word is <i>critical</i> to the point.", out)

    def test_emphasis_in_a_later_block_lands_on_the_right_words(self):
        out = html("First block.\n\nThe second block matters.\n", ["p", "p"], ["matters"])
        self.assertIn("<div>The second block <i>matters</i>.</div>", out)

    def test_special_characters_are_escaped(self):
        out = html("Tom & Jerry <loud>.\n", ["p"])
        self.assertIn("Tom &amp; Jerry &lt;loud&gt;.", out)

    def test_title_comes_first_as_the_top_heading(self):
        out = html("Body.\n", ["p"], title="The Ideal Team Player")
        self.assertTrue(out.startswith("<h1>The Ideal Team Player</h1>"))

    def test_missing_kinds_fall_back_to_guessing_from_the_text(self):
        out = html("ENOUGH\n\nBody text.\n\n- item\n", None)
        self.assertIn("<h2>ENOUGH</h2>", out)
        self.assertIn("<div>Body text.</div>", out)
        self.assertIn("<ul><li>item</li></ul>", out)

    def test_kinds_that_no_longer_line_up_are_ignored(self):
        # e.g. the text was edited by hand after clean.py wrote the kinds
        out = html("ENOUGH\n\nBody text.\n", ["h1"])
        self.assertIn("<h2>ENOUGH</h2>", out)


class TestTitle(unittest.TestCase):
    def test_title_comes_from_the_book_folder_name(self):
        self.assertEqual(rich_out.title_from(Path("/books/The-IDEAL-TEAM-PLAYER/speechify.txt")),
                         "The IDEAL TEAM PLAYER")


class TestNotesCommand(unittest.TestCase):
    def test_html_path_is_passed_as_an_argument_not_spliced_into_the_script(self):
        # a folder name with a quote in it must not break (or inject into)
        # the AppleScript
        path = Path('/tmp/Bob\'s "book"/speechify.html')
        cmd = rich_out.notes_command(path)
        self.assertEqual(cmd[0], "osascript")
        self.assertEqual(cmd[-1], str(path))
        self.assertNotIn(str(path), " ".join(cmd[:-1]))


class TestCli(unittest.TestCase):
    def test_writes_html_next_to_the_text_file(self):
        tmp = Path(tempfile.mkdtemp())
        txt = tmp / "speechify.txt"
        txt.write_text("ENOUGH\n\nIt was time to make a change.\n", encoding="utf-8")
        (tmp / "speechify.txt.blocks.json").write_text(json.dumps(["h2", "p"]), encoding="utf-8")
        result = subprocess.run([sys.executable, str(HERE / "rich_out.py"), str(txt)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        page = (tmp / "speechify.html").read_text(encoding="utf-8")
        self.assertIn("<h2>ENOUGH</h2>", page)
        self.assertIn('<meta charset="utf-8">', page)


if __name__ == "__main__":
    unittest.main()
