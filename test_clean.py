#!/usr/bin/env python3
"""Characterization tests for the OCR reflow.

These lock in clean.py's existing behavior so the shared-classifier refactor
can't change the output.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import layout

HERE = Path(__file__).parent


def clean_with_kinds(raw: str) -> tuple[str, list[str]]:
    """Cleaned text, plus the block kinds clean.py writes beside it."""
    tmp = Path(tempfile.mkdtemp())
    src, dst = tmp / "raw.txt", tmp / "out.txt"
    src.write_text(raw, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(HERE / "clean.py"), str(src), str(dst)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    kinds = json.loads(Path(str(dst) + ".blocks.json").read_text(encoding="utf-8"))
    return dst.read_text(encoding="utf-8"), kinds


def clean(raw: str) -> str:
    return clean_with_kinds(raw)[0]


class TestReflow(unittest.TestCase):
    def test_wrapped_lines_join_into_one_paragraph(self):
        # first line must exceed the 35-char heading cap, or it is read as a heading
        out = clean("The quick brown fox jumped over the lazy dog and kept\nrunning toward the river.\n")
        self.assertIn("kept running toward the river.", out)

    def test_short_opening_line_is_treated_as_a_section_heading(self):
        # documented limitation: the heading detector caps headings at 35 chars
        out = clean("A Short Line\nThe body text follows on the next line.\n")
        self.assertIn("A Short Line\n", out)

    def test_allcaps_heading_gets_its_own_line(self):
        out = clean("THE SECOND AGREEMENT\nBody text follows here.\n")
        self.assertIn("THE SECOND AGREEMENT\n", out)

    def test_blank_line_is_emitted_before_a_heading(self):
        out = clean("The body text ends right here.\nTHE SECOND AGREEMENT\nMore body text here.\n")
        self.assertIn("here.\n\nTHE SECOND AGREEMENT", out)

    def test_blank_line_is_emitted_after_a_heading(self):
        # Speechify merges lines split by a single newline into one paragraph,
        # so without the blank line the heading runs into the first sentence
        out = clean("THE SECOND AGREEMENT\nThe body text follows on this line.\n")
        self.assertIn("THE SECOND AGREEMENT\n\nThe body text", out)

    def test_leaked_running_header_is_its_own_block(self):
        out = clean("the bungalow next door and its lawn.\nThe Ideal Team Player\nJeff was definitely ready for a change of pace.\n")
        self.assertIn("lawn.\n\nThe Ideal Team Player\n\nJeff was", out)

    def test_bare_page_numbers_are_dropped(self):
        out = clean("Some prose here.\n42\nMore prose here.\n")
        self.assertNotIn("42", out)

    def test_image_delimiters_are_dropped(self):
        out = clean("===== page1.jpg =====\nSome prose here.\n")
        self.assertNotIn("=====", out)

    def test_bullets_are_separated_by_blank_lines(self):
        out = clean("- first item\n- second item\n")
        self.assertIn("- first item\n\n- second item", out)

    def test_bullet_glyphs_are_normalized_to_dashes(self):
        out = clean("• first item\n• second item\n")
        self.assertIn("- first item", out)

    def test_paragraph_break_after_a_sentence_splits_paragraphs(self):
        # a blank line in the raw OCR is a paragraph break found by layout.py
        out = clean("It was time to make a change of some kind now.\n\nTo be fair, it wasn't really the work that Jeff\nhad grown tired of.\n")
        self.assertIn("some kind now.\n\nTo be fair", out)

    def test_paragraph_break_mid_sentence_is_ignored(self):
        # a break the layout pass guessed wrong must not cut a sentence in two
        out = clean("he was fortunate enough to get demoted when the board of\n\ndirectors hired what they called a grown-up CEO.\n")
        self.assertIn("board of directors hired", out)

    def test_paragraph_break_survives_a_dropped_page_number(self):
        out = clean("the over-priced bungalow next door and its lawn.\n\n5\n\nJeff was definitely ready for a change of pace.\n")
        self.assertIn("lawn.\n\nJeff was", out)

    def test_page_delimiter_alone_does_not_break_a_paragraph(self):
        out = clean("the over-priced bungalow next door and its lawn,\n===== IMG_1.jpg =====\nand Jeff was definitely ready for a change of pace.\n")
        self.assertIn("lawn, and Jeff was", out)

    def test_indented_line_in_tagged_ocr_starts_a_new_paragraph(self):
        # end to end with the bounding-box tags ocr.swift writes
        rows = [
            (0.10, 0.90, "After twenty years, Jeff Shanley had experienced more than"),
            (0.10, 0.90, "his fair share of the Silicon Valley. The hours. The traffic. The"),
            (0.10, 0.55, "pretentiousness. It was time to make a change."),
            (0.14, 0.90, "To be fair, it wasn't really the work that Jeff had grown"),
            (0.10, 0.90, "tired of. In fact, he had enjoyed an interesting and successful"),
            (0.10, 0.90, "career after a few jobs in high-tech marketing."),
        ]
        raw = "\n".join(
            f"[{x0:.4f} {x1:.4f} {0.10 + i * 0.03:.4f} {0.12 + i * 0.03:.4f}] {text}"
            for i, (x0, x1, text) in enumerate(rows)
        )
        out = clean(raw + "\n")
        self.assertIn("make a change.\n\nTo be fair", out)
        self.assertNotIn("[0.", out)

    def test_wrap_hyphen_is_rejoined_into_one_word(self):
        out = clean("The peo-\nple gathered here.\n")
        self.assertIn("people", out)
        self.assertNotIn("peo-", out)

    def test_real_compound_hyphen_survives(self):
        out = clean("A self-\naware person spoke.\n")
        self.assertIn("self-aware", out)


    def test_letter_lost_to_a_drop_cap_is_put_back(self):
        out = clean("ENOUGH\nfter twenty years, Jeff Shanley had seen enough of the valley.\n")
        self.assertIn("ENOUGH\n\nAfter twenty years", out)


class TestBlockKinds(unittest.TestCase):
    # the rich-text writer formats each block by the kind recorded here

    def test_one_kind_per_block(self):
        text, kinds = clean_with_kinds("THE SECOND AGREEMENT\nThe body text follows on this line.\n- an item\n")
        self.assertEqual(len(kinds), len(text.strip().split("\n\n")))

    def test_kinds_name_paragraphs_bullets_and_chapter_headings(self):
        _, kinds = clean_with_kinds("THE SECOND AGREEMENT\nThe body text follows on this line.\n- an item\n")
        self.assertEqual(kinds, ["h2", "p", "li"])

    def test_layout_heading_keeps_its_level(self):
        raw = layout.heading_line("The Situation", 1) + "\nThe body text follows on this line.\n"
        text, kinds = clean_with_kinds(raw)
        self.assertEqual(text, "The Situation\n\nThe body text follows on this line.\n")
        self.assertEqual(kinds, ["h1", "p"])

    def test_layout_heading_stands_alone_even_after_an_unfinished_line(self):
        # type size says heading, so it doesn't need the sentence-end check
        raw = "the long line that runs on and on without an end\n" + layout.heading_line("BOB", 2) + "\nRobert Shanley had been the most prominent builder.\n"
        text, kinds = clean_with_kinds(raw)
        self.assertIn("without an end\n\nBOB\n\nRobert", text)
        self.assertEqual(kinds, ["p", "h2", "p"])


if __name__ == "__main__":
    unittest.main()
