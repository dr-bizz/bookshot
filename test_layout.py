#!/usr/bin/env python3
"""Tests for reading paragraph breaks off the page geometry.

Coordinates are fractions of the page image: x runs left to right, y runs top
to bottom. A typical body line spans x 0.10..0.90.
"""
import unittest

import layout

LEFT, RIGHT = 0.10, 0.90
PITCH = 0.03  # top-to-top distance between ordinary lines


def page(*specs):
    """Build one page of rows from (text, x0, x1) tuples, evenly spaced."""
    return [
        layout.Row(text, x0, x1, 0.10 + i * PITCH, 0.12 + i * PITCH)
        for i, (text, x0, x1) in enumerate(specs)
    ]


def full(text):
    return (text, LEFT, RIGHT)


def breaks_before(lines):
    """Texts that directly follow a paragraph break."""
    return [lines[i + 1] for i, line in enumerate(lines[:-1]) if line == ""]


class TestParagraphLines(unittest.TestCase):
    def test_full_width_lines_have_no_breaks(self):
        rows = page(*(full(f"line {i}") for i in range(6)))
        self.assertNotIn("", layout.paragraph_lines(rows))

    def test_indented_line_starts_a_new_paragraph(self):
        rows = page(
            full("a"), full("b"), full("c"),
            ("To be fair,", LEFT + 0.04, RIGHT),
            full("e"), full("f"),
        )
        self.assertEqual(breaks_before(layout.paragraph_lines(rows)), ["To be fair,"])

    def test_short_line_ends_a_paragraph_even_without_an_indent(self):
        # block-style books skip the indent; the short last line still shows it
        rows = page(
            full("a"), full("b"),
            ("make a change.", LEFT, 0.50),
            full("next"), full("e"), full("f"),
        )
        self.assertEqual(breaks_before(layout.paragraph_lines(rows)), ["next"])

    def test_large_vertical_gap_starts_a_new_block(self):
        rows = [
            layout.Row(text, LEFT, RIGHT, top, top + 0.02)
            for text, top in [("a", 0.10), ("b", 0.13), ("c", 0.16),
                              ("after gap", 0.30), ("e", 0.33), ("f", 0.36)]
        ]
        self.assertEqual(breaks_before(layout.paragraph_lines(rows)), ["after gap"])

    def test_gradual_tilt_does_not_read_as_indents(self):
        # a photo taken at a slight angle shifts every line a little
        rows = page(*((f"line {i}", LEFT + i * 0.004, RIGHT + i * 0.004) for i in range(10)))
        self.assertNotIn("", layout.paragraph_lines(rows))

    def test_indent_near_the_bottom_of_a_steeply_tilted_page_is_found(self):
        # every line starts 1% of the text width further left than the one
        # above it (a real handheld photo); near the page bottom the window of
        # nearby lines only reaches upward, which used to hide the indent
        drift = 0.008
        specs = [(f"line {i}", LEFT - i * drift, RIGHT - i * drift) for i in range(12)]
        specs[10] = ("For a moment,", LEFT - 10 * drift + 0.045, RIGHT - 10 * drift)
        self.assertEqual(breaks_before(layout.paragraph_lines(page(*specs))), ["For a moment,"])

    def test_short_last_line_on_a_page_ends_with_a_break(self):
        # the paragraph ends at the bottom of this page; the next page's first
        # line can't be judged against anything on this one
        rows = page(full("a"), full("b"), full("c"), ("low next door.", LEFT, 0.30))
        self.assertEqual(layout.paragraph_lines(rows)[-1], "")

    def test_indented_first_line_on_a_page_starts_with_a_break(self):
        rows = page(("When Kathryn retired,", LEFT + 0.04, RIGHT), full("b"), full("c"), full("d"))
        self.assertEqual(layout.paragraph_lines(rows)[:2], ["", "When Kathryn retired,"])

    def test_too_few_rows_to_judge_get_no_breaks(self):
        rows = page(full("a"), ("b", LEFT + 0.2, 0.5))
        self.assertEqual(layout.paragraph_lines(rows), ["a", "b"])

    def test_every_row_text_is_kept_in_order(self):
        rows = page(full("a"), full("b"), ("c.", LEFT, 0.4), ("d", LEFT + 0.04, RIGHT), full("e"))
        self.assertEqual([t for t in layout.paragraph_lines(rows) if t], ["a", "b", "c.", "d", "e"])


class TestToLines(unittest.TestCase):
    def test_tagged_row_is_unwrapped_to_its_text(self):
        self.assertEqual(layout.to_lines("[0.1000 0.9000 0.1000 0.1200] hello there"), ["hello there"])

    def test_tagged_row_with_negative_coordinate_is_unwrapped(self):
        # Vision boxes can poke slightly past the image edge
        self.assertEqual(layout.to_lines("[-0.0014 0.6000 0.1551 0.1707] ould call"), ["ould call"])

    def test_untagged_lines_pass_through_unchanged(self):
        raw = "plain line one\nplain line two"
        self.assertEqual(layout.to_lines(raw), ["plain line one", "plain line two"])

    def test_page_delimiters_are_kept(self):
        raw = "[0.1000 0.9000 0.1000 0.1200] a\n===== IMG_1.jpg =====\n[0.1000 0.9000 0.1000 0.1200] b"
        self.assertIn("===== IMG_1.jpg =====", layout.to_lines(raw))

    def test_margins_are_judged_per_page(self):
        # the right half of a spread is cropped differently, so its text sits
        # further right; that must not read as every line being indented
        def tagged(x0, x1, i, text):
            top = 0.10 + i * PITCH
            return f"[{x0:.4f} {x1:.4f} {top:.4f} {top + 0.02:.4f}] {text}"

        left_page = [tagged(0.10, 0.80, i, f"left {i}") for i in range(6)]
        right_page = [tagged(0.20, 0.95, i, f"right {i}") for i in range(6)]
        raw = "\n".join(left_page + ["===== split ====="] + right_page)
        self.assertNotIn("", layout.to_lines(raw))



def tag(text, x0, x1, top, size=0.02):
    """One OCR piece as ocr.swift writes it: box, then type size."""
    return f"[{x0:.4f} {x1:.4f} {top:.4f} {top + size:.4f} {size:.4f}] {text}"


def body(n=6, start=0.20, size=0.02):
    """Full-width body lines with no sentence ends, one per PITCH."""
    return [tag(f"body line {i} runs the full width of the page", LEFT, RIGHT, start + i * PITCH, size)
            for i in range(n)]


def text_of(lines):
    """Every line's text, with heading marks unwrapped."""
    return [layout.parse_heading(l)[1] if layout.parse_heading(l) else l for l in lines]


class TestRowGrouping(unittest.TestCase):
    def test_pieces_on_one_line_join_left_to_right(self):
        raw = "\n".join([tag("BOB", 0.40, 0.60, 0.100, 0.03), tag("call", 0.10, 0.30, 0.104, 0.02)])
        self.assertEqual(layout.to_lines(raw), ["call BOB"])

    def test_pieces_a_line_apart_stay_separate_rows(self):
        raw = "\n".join([tag("first", LEFT, RIGHT, 0.10), tag("second", LEFT, RIGHT, 0.13)])
        self.assertEqual(layout.to_lines(raw), ["first", "second"])


class TestStrayFragments(unittest.TestCase):
    # bleed-through and the edge of the facing page show up as scraps of
    # text in the gutter, outside the block of real text

    def test_fragment_outside_the_text_block_is_dropped(self):
        raw = "\n".join(body() + [tag("ould", -0.01, 0.03, 0.26)])
        self.assertNotIn("ould", " ".join(layout.to_lines(raw)))

    def test_fragment_overlapping_the_text_block_is_kept(self):
        raw = "\n".join(body() + [tag("ould", 0.05, 0.15, 0.80)])
        self.assertIn("ould", layout.to_lines(raw))

    def test_page_with_too_few_full_lines_keeps_everything(self):
        raw = "\n".join([tag("PART ONE", 0.35, 0.50, 0.20), tag("scrap", 0.80, 0.84, 0.40)])
        self.assertIn("scrap", layout.to_lines(raw))

    def test_scraps_alone_do_not_make_a_text_block(self):
        # a part-title page with no body text, just gutter scraps: the scraps
        # mustn't become "the text" and push the real titles out as strays
        scraps = [tag(t, 0.00, 0.03, 0.15 + i * PITCH, 0.012) for i, t in enumerate(["om", "e a", "eff", "ne", "ne", "ey"])]
        raw = "\n".join(scraps + [tag("PART TWO", 0.41, 0.57, 0.40), tag("Diagnosis", 0.35, 0.67, 0.50, 0.057)])
        lines = text_of(layout.to_lines(raw))
        self.assertIn("PART TWO", lines)
        self.assertIn("Diagnosis", lines)

    def test_narrow_scrap_touching_the_photo_edge_is_dropped_on_a_title_page(self):
        # where the spread was split down the spine, the facing page's edge
        # shows up as tiny scraps touching the image edge
        raw = "\n".join([tag("e a", 0.001, 0.029, 0.40, 0.013), tag("PART TWO", 0.41, 0.57, 0.40)])
        self.assertEqual(text_of(layout.to_lines(raw)), ["PART TWO"])

    def test_wide_line_touching_the_photo_edge_is_kept(self):
        # a tightly cropped photo: real text running off the edge
        raw = tag("a real line of text cut off at the edge", 0.0, 0.6, 0.40)
        self.assertEqual(layout.to_lines(raw), ["a real line of text cut off at the edge"])


class TestShowThrough(unittest.TestCase):
    # print from the other side of the sheet, seen through the paper: a
    # faint mirror image that OCR reads as gibberish like "₴180ng"

    def test_faint_piece_is_dropped(self):
        raw = "\n".join(body() + ["[0.4541 0.6740 0.2621 0.2884 0.0263 0.0510] ₴180ng"])
        self.assertNotIn("₴180ng", " ".join(layout.to_lines(raw)))

    def test_dark_piece_is_kept(self):
        raw = "[0.3120 0.5647 0.1734 0.2073 0.0257 0.4275] THE ROPES"
        self.assertEqual(text_of(layout.to_lines(raw)), ["THE ROPES"])

    def test_light_gray_running_header_is_kept_as_text(self):
        # the faintest real text in a measured book: small gray headers
        raw = "[0.3966 0.4765 0.0803 0.0973 0.0132 0.2353] Regrouping"
        self.assertEqual(layout.to_lines(raw), ["Regrouping"])

    def test_piece_without_an_ink_reading_is_kept(self):
        # older raw files have no ink measurement
        self.assertEqual(layout.to_lines(tag("THE ROPES", 0.31, 0.56, 0.17)), ["THE ROPES"])


class TestDropCaps(unittest.TestCase):
    # a big initial letter spanning the first few lines of a chapter

    def test_big_initial_joins_the_first_line_beside_it(self):
        lines = [
            tag("A", 0.04, 0.09, 0.20, 0.075),
            tag("fter twenty years, Jeff Shanley had", LEFT, RIGHT, 0.20),
            tag("his fair share of the Silicon Valley", LEFT, RIGHT, 0.23),
            tag("pretentiousness of it all wore thin", LEFT, RIGHT, 0.26),
        ] + body(4, start=0.29)
        out = layout.to_lines("\n".join(lines))
        self.assertIn("After twenty years, Jeff Shanley had", out)
        self.assertIn("his fair share of the Silicon Valley", out)
        self.assertNotIn("A", out)

    def test_big_initial_does_not_shift_the_line_it_joins(self):
        # it hangs in the margin; the line must not look out-dented, or
        # every other line would look indented against it
        lines = [
            tag("A", 0.04, 0.09, 0.20, 0.075),
            tag("fter twenty years, Jeff Shanley had", LEFT, RIGHT, 0.20),
        ] + body(5, start=0.23)
        self.assertNotIn("", layout.to_lines("\n".join(lines)))


class TestHeadings(unittest.TestCase):
    def test_heading_mark_round_trips(self):
        self.assertEqual(layout.parse_heading(layout.heading_line("ENOUGH", 2)), (2, "ENOUGH"))

    def test_plain_line_is_not_a_heading(self):
        self.assertIsNone(layout.parse_heading("ENOUGH"))

    def test_large_short_line_becomes_a_heading(self):
        raw = "\n".join([tag("ENOUGH", 0.35, 0.65, 0.05, 0.028)] + body())
        self.assertIn(layout.heading_line("ENOUGH", 2), layout.to_lines(raw))

    def test_very_large_line_is_a_top_level_heading(self):
        raw = "\n".join([tag("The Situation", 0.30, 0.70, 0.05, 0.040)] + body())
        self.assertIn(layout.heading_line("The Situation", 1), layout.to_lines(raw))

    def test_large_full_width_line_is_not_a_heading(self):
        # lines nearer the camera come out a little bigger in the photo
        lines = body()
        lines[3] = tag("closer to the camera, this line is bigger", LEFT, RIGHT, 0.20 + 3 * PITCH, 0.027)
        self.assertNotIn(layout.heading_line("closer to the camera, this line is bigger", 2),
                         layout.to_lines("\n".join(lines)))

    def test_heading_is_set_off_by_breaks(self):
        raw = "\n".join(body(3, start=0.05) + [tag("ENOUGH", 0.35, 0.65, 0.15, 0.028)] + body(3, start=0.20))
        lines = layout.to_lines(raw)
        i = lines.index(layout.heading_line("ENOUGH", 2))
        self.assertEqual((lines[i - 1], lines[i + 1]), ("", ""))


class TestRunningHeaders(unittest.TestCase):
    # the small line at the top of most pages: the book or chapter title

    def test_small_first_line_repeated_on_two_pages_is_dropped(self):
        page = [tag("The Ideal Team Player", 0.35, 0.65, 0.05, 0.014)] + body()
        raw = "\n".join(page + ["===== IMG_2.jpg ====="] + page)
        self.assertNotIn("The Ideal Team Player", text_of(layout.to_lines(raw)))

    def test_small_first_line_matching_a_chapter_title_is_dropped(self):
        opening = [tag("DRAMA", 0.35, 0.65, 0.05, 0.028)] + body()
        later = [tag("Drama", 0.40, 0.60, 0.05, 0.014)] + body()
        lines = text_of(layout.to_lines("\n".join(opening + ["===== IMG_2.jpg ====="] + later)))
        self.assertIn("DRAMA", lines)
        self.assertNotIn("Drama", lines)

    def test_small_first_line_seen_once_is_kept(self):
        raw = "\n".join([tag("PART ONE", 0.35, 0.50, 0.05, 0.015)] + body())
        self.assertIn("PART ONE", text_of(layout.to_lines(raw)))


if __name__ == "__main__":
    unittest.main()
