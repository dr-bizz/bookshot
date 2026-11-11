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

    def test_one_line_replies_at_the_bottom_of_a_page_each_start_a_paragraph(self):
        # dialogue: near the page bottom the nearby lines are mostly indented
        # first lines, so their middle is the indent, not the margin
        # (measured on a real page)
        indent = LEFT + 0.05
        rows = page(
            full("sound confident. But I need to talk to you about some new"),
            ("challenges and opportunities.", LEFT, 0.50),
            ("As concerned as he was, Jeff laughed out loud.", indent, RIGHT),
            ("think I like the sound of this.", LEFT, 0.50),
            ('"Oh, you\'ll be fine. This is just how it works."', indent, RIGHT),
            ("The waitress brought Jeff's beer and Bob's water.", indent, RIGHT - 0.08),
            ('"So what kind of challenges and opportunities are we', indent, RIGHT),
            ('talking about?" Jeff asked.', LEFT, 0.48),
        )
        self.assertIn('"So what kind of challenges and opportunities are we',
                      breaks_before(layout.paragraph_lines(rows)))

    def test_lines_wrapped_under_a_bullet_are_not_indents(self):
        # measured on a real page: text under a bullet hangs right of the
        # bullet sign, about as far as a paragraph indent
        rows = [
            layout.Row(text, x0, x1, top, top + 0.022, 0.02)
            for text, x0, x1, top in [
                ("• A baby cannot handle the hustle and bustle of the", 0.3858, 0.9688, 0.25),
                ("adult lifestyle. Make sure that all the naps are not", 0.4220, 0.9704, 0.27),
                ("in the car or on the run.", 0.4184, 0.6990, 0.29),
                ("• Be aware of your child's limitations.", 0.3769, 0.8165, 0.31),
                ("Have at least two naps a day in the crib.", 0.4040, 0.8592, 0.33),
                ("• Keep the room dark and cool, and keep the white noise", 0.3858, 0.9600, 0.35),
                ("machine running for the whole nap, every single time.", 0.4200, 0.9650, 0.37),
            ]
        ]
        after = breaks_before(layout.paragraph_lines(rows))
        self.assertNotIn("Have at least two naps a day in the crib.", after)
        self.assertNotIn("adult lifestyle. Make sure that all the naps are not", after)

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

    def test_curled_line_and_short_line_under_it_stay_separate_rows(self):
        # measured on a real spread: the top line curls near the spine, so its
        # box is three lines tall and its middle sits close to the next line's
        curled = "[0.3704 0.9351 0.1054 0.1739 0.0259 0.69] Clare shrugged again, a little"
        short = "[0.3248 0.6882 0.1359 0.1669 0.0166 0.71] to that."
        self.assertEqual(layout.to_lines(curled + "\n" + short),
                         ["Clare shrugged again, a little", "to that."])

    def test_label_overlapping_the_start_of_its_line_stays_on_it(self):
        # a margin label ("Days 10-12") whose box runs into the line beside
        # it, at the same height: one line, not a label dropped mid-sentence
        label = tag("Days 10-12", 0.05, 0.20, 0.3000)
        line = tag("Now we add apples to the morning feeding.", 0.15, 0.90, 0.3002)
        self.assertEqual(layout.to_lines(label + "\n" + line),
                         ["Days 10-12 Now we add apples to the morning feeding."])


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


class TestCapitalsHeadings(unittest.TestCase):
    # a line in capitals has no descenders, so its box measures small for
    # its type: a 3-letter chapter title came out 1.28x body

    def test_short_capitals_title_a_little_bigger_than_body_is_a_heading(self):
        raw = "\n".join([tag("TED", 0.45, 0.55, 0.05, 0.025)] + body())
        self.assertIn(layout.heading_line("TED", 2), layout.to_lines(raw))

    def test_mixed_case_line_that_size_is_not(self):
        raw = "\n".join([tag("Ted", 0.45, 0.55, 0.05, 0.025)] + body())
        self.assertIn("Ted", layout.to_lines(raw))

    def test_capitals_line_at_body_size_is_left_to_clean(self):
        # clean.py's capitals rule still decides it; layout doesn't mark it
        raw = "\n".join([tag("APPLICATION #1: HIRING", 0.10, 0.40, 0.05, 0.02)] + body())
        self.assertIn("APPLICATION #1: HIRING", layout.to_lines(raw))

    def test_wide_capitals_title_is_a_heading(self):
        # the width limit keeps big body lines near the camera out; body
        # lines aren't set in capitals
        raw = "\n".join([tag("ADDITION BY ADDITION", LEFT, RIGHT - 0.05, 0.05, 0.03)] + body())
        self.assertIn(layout.heading_line("ADDITION BY ADDITION", 2), layout.to_lines(raw))

    def test_wide_capitals_title_keeps_the_level_cleans_rule_gives_it(self):
        # big enough to be a top-level title by size, but only found as a
        # capitals line, like the chapter titles around it
        raw = "\n".join([tag("ABOUT A MONTH LATER", LEFT, RIGHT - 0.05, 0.05, 0.043)] + body())
        self.assertIn(layout.heading_line("ABOUT A MONTH LATER", 2), layout.to_lines(raw))


class TestHeadingRuns(unittest.TestCase):
    # a heading set on two or more lines is one heading

    def test_two_line_capitals_heading_is_one_heading(self):
        raw = "\n".join([
            tag("THE THREE VIRTUES OF", 0.15, 0.85, 0.05, 0.036),
            tag("AN IDEAL TEAM PLAYER", 0.15, 0.85, 0.09, 0.034),
        ] + body(start=0.25))
        lines = layout.to_lines(raw)
        self.assertIn(layout.heading_line("THE THREE VIRTUES OF AN IDEAL TEAM PLAYER", 2), lines)
        self.assertNotIn(layout.heading_line("AN IDEAL TEAM PLAYER", 2), lines)

    def test_small_capitals_heading_on_two_lines_is_one_heading(self):
        raw = "\n".join(body(3, start=0.05) + [
            tag("APPLICATION #3: DEVELOPING EMPLOYEES WHO", LEFT, 0.80, 0.15, 0.02),
            tag("ARE LACKING IN ONE OR MORE OF THE VIRTUES", LEFT, 0.80, 0.17, 0.02),
        ] + body(4, start=0.21))
        text = "APPLICATION #3: DEVELOPING EMPLOYEES WHO ARE LACKING IN ONE OR MORE OF THE VIRTUES"
        self.assertIn(layout.heading_line(text, 2), layout.to_lines(raw))

    def test_big_line_beside_a_heading_joins_it(self):
        # a hair too wide to pass as a heading by itself
        raw = "\n".join([
            tag("The Five Dysfunctions", 0.25, 0.75, 0.05, 0.031),
            tag("of a Team Summary", 0.30, 0.70, 0.09, 0.030),
        ] + body(start=0.20))
        self.assertIn(layout.heading_line("The Five Dysfunctions of a Team Summary", 2), layout.to_lines(raw))

    def test_dash_at_the_end_of_a_heading_line_joins_without_a_space(self):
        raw = "\n".join([
            tag("A FINAL THOUGHT-", 0.30, 0.70, 0.05, 0.03),
            tag("BEYOND WORK TEAMS", 0.30, 0.70, 0.09, 0.03),
        ] + body(start=0.20))
        self.assertIn(layout.heading_line("A FINAL THOUGHT-BEYOND WORK TEAMS", 2), layout.to_lines(raw))

    def test_body_text_below_a_chapter_title_is_not_joined(self):
        # the first line sits well below the title, and near the camera it
        # can measure almost as big
        raw = "\n".join([tag("RESEARCH", 0.35, 0.65, 0.05, 0.027)]
                        + [tag("Jeff decided to go back to the site", LEFT, RIGHT, 0.20, 0.027)] + body(start=0.23))
        lines = layout.to_lines(raw)
        self.assertIn(layout.heading_line("RESEARCH", 2), lines)
        self.assertIn("Jeff decided to go back to the site", lines)

    def test_separate_headings_far_apart_stay_separate(self):
        raw = "\n".join([tag("PART ONE", 0.35, 0.50, 0.20, 0.015), tag("The Situation", 0.30, 0.70, 0.37, 0.040)])
        lines = text_of(layout.to_lines(raw))
        self.assertIn("PART ONE", lines)
        self.assertIn("The Situation", lines)


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

    # A section only two pages long shows its header once, so it has to be
    # matched to the chapter title, however that title is set.

    def _opening_then_header(self, title_lines, header, header_size=0.014):
        opening = title_lines + body(start=0.25)
        later = [tag(header, 0.40, 0.60, 0.05, header_size)] + body()
        return text_of(layout.to_lines("\n".join(opening + ["===== IMG_2.jpg ====="] + later)))

    def test_header_matching_a_title_too_wide_for_a_heading_is_dropped(self):
        # letter-spaced capitals: wider than a heading may be, so not marked one
        lines = self._opening_then_header([tag("FIRST MEETING", 0.10, 0.85, 0.05, 0.028)], "First Meeting")
        self.assertIn("FIRST MEETING", lines)
        self.assertNotIn("First Meeting", lines)

    def test_header_matching_a_title_just_under_heading_size_is_dropped(self):
        lines = self._opening_then_header([tag("ANGST", 0.40, 0.55, 0.05, 0.0246)], "Angst")
        self.assertIn("ANGST", lines)
        self.assertNotIn("Angst", lines)

    def test_header_matching_a_title_set_over_two_lines_is_dropped(self):
        title = [tag("THE HISTORY OF", 0.30, 0.70, 0.05, 0.03), tag("THE MODEL", 0.35, 0.65, 0.09, 0.03)]
        lines = self._opening_then_header(title, "The History of the Model")
        self.assertNotIn("The History of the Model", lines)

    def test_title_in_type_near_body_size_repeated_as_a_header_is_dropped(self):
        # a long title in small type measures almost as big as the body
        title = [tag("CONNECTING THE", 0.30, 0.70, 0.05, 0.03), tag("FIVE DYSFUNCTIONS", 0.30, 0.70, 0.09, 0.03)]
        lines = self._opening_then_header(title, "Connecting the Five Dysfunctions", header_size=0.0174)
        self.assertNotIn("Connecting the Five Dysfunctions", lines)

    def test_first_line_near_body_size_without_a_title_is_kept(self):
        page = [tag("Leading on", 0.40, 0.60, 0.05, 0.0174)] + body()
        raw = "\n".join(page + ["===== IMG_2.jpg ====="] + page)
        self.assertEqual(text_of(layout.to_lines(raw)).count("Leading on"), 2)

    def test_misread_header_is_dropped_with_the_one_it_repeats(self):
        pages = [[tag(h, 0.40, 0.60, 0.05, 0.014)] + body() for h in ["Application", "Application", "Appliaation"]]
        raw = "\n===== IMG_n.jpg =====\n".join("\n".join(p) for p in pages)
        self.assertNotIn("Appliaation", text_of(layout.to_lines(raw)))

    def test_heading_differing_from_a_title_only_by_its_numbers_is_kept(self):
        # a schedule book: "TYPICAL DAY 4-8 WEEKS" is one section's title, and
        # "TYPICAL DAY 2-4 WEEKS" heading the next page is another section
        lines = self._opening_then_header([tag("TYPICAL DAY 4-8 WEEKS", 0.30, 0.70, 0.05, 0.03)],
                                          "TYPICAL DAY 2-4 WEEKS", header_size=0.0164)
        self.assertIn("TYPICAL DAY 2-4 WEEKS", lines)

    def test_header_with_its_page_number_still_matches_the_title(self):
        lines = self._opening_then_header([tag("ABOUT A YEAR LATER", 0.20, 0.80, 0.05, 0.03)],
                                          "150 About a Year Later")
        self.assertNotIn("150 About a Year Later", lines)

    def test_short_header_is_not_matched_loosely(self):
        # too short to tell a misread from a different word
        pages = [[tag(h, 0.40, 0.60, 0.05, 0.014)] + body() for h in ["Ted", "Ted", "Tea"]]
        raw = "\n===== IMG_n.jpg =====\n".join("\n".join(p) for p in pages)
        self.assertIn("Tea", text_of(layout.to_lines(raw)))

    def test_small_first_line_matching_a_wide_capitals_title_is_dropped(self):
        # the title was too wide for the size rule, so it used to leave its
        # running header behind
        opening = [tag("FIRST MEETING", LEFT, RIGHT - 0.1, 0.05, 0.03)] + body()
        later = [tag("First Meeting", 0.40, 0.60, 0.05, 0.012)] + body()
        lines = text_of(layout.to_lines("\n".join(opening + ["===== IMG_2.jpg ====="] + later)))
        self.assertNotIn("First Meeting", lines)

    def test_small_first_line_matching_a_two_line_title_is_dropped(self):
        opening = [tag("THE HISTORY OF", 0.30, 0.70, 0.05, 0.03), tag("THE MODEL", 0.35, 0.65, 0.09, 0.03)] + body(start=0.20)
        later = [tag("The History of the Model", 0.35, 0.65, 0.05, 0.012)] + body()
        lines = text_of(layout.to_lines("\n".join(opening + ["===== IMG_2.jpg ====="] + later)))
        self.assertNotIn("The History of the Model", lines)

    def test_running_header_with_a_misread_letter_is_dropped(self):
        def page_with(header):
            return [tag(header, 0.40, 0.55, 0.05, 0.012)] + body()
        raw = "\n".join(page_with("Application") + ["===== 2 ====="] + page_with("Application")
                        + ["===== 3 ====="] + page_with("Appliaation"))
        self.assertNotIn("Appliaation", text_of(layout.to_lines(raw)))

    def test_one_off_first_line_unlike_the_running_header_is_kept(self):
        def page_with(header):
            return [tag(header, 0.40, 0.55, 0.05, 0.012)] + body()
        raw = "\n".join(page_with("PART TWO") + ["===== 2 ====="] + page_with("PART TWO")
                        + ["===== 3 ====="] + page_with("PART ONE"))
        self.assertIn("PART ONE", text_of(layout.to_lines(raw)))


class TestPageNumbers(unittest.TestCase):
    # clean.py drops a line that is a bare number; misread ones got through

    def _with_last(self, text, top):
        return text_of(layout.to_lines("\n".join(body() + [tag(text, 0.48, 0.52, top, 0.015)])))

    def test_misread_page_number_is_dropped(self):
        self.assertNotIn("5l", self._with_last("5l", 0.20 + 6 * PITCH + 0.03))

    def test_page_number_with_a_stray_mark_is_dropped(self):
        self.assertNotIn("• 150", self._with_last("• 150", 0.20 + 6 * PITCH + 0.03))

    def test_number_at_ordinary_line_spacing_is_kept(self):
        # a short last line of the text itself, not set apart
        self.assertIn("1999.", self._with_last("1999.", 0.20 + 6 * PITCH))


def quote_page(box, beside, after):
    """Full lines, then narrowed lines on the left with a box of `box` lines
    on the right, then full lines of `after`."""
    lines = [tag("humility is the single greatest and most indispensable attribute", LEFT, RIGHT, 0.10),
             tag("of being a team player, and it is no great surprise at all", LEFT, RIGHT, 0.13)]
    top = 0.16
    for i, text in enumerate(beside):
        lines.append(tag(text, LEFT, 0.45, top + i * PITCH))
    for i, text in enumerate(box):
        lines.append(tag(text, 0.50, 0.88, top + 0.01 + i * 0.025, 0.017))
    top += max(len(beside) * PITCH, len(box) * 0.025 + 0.01)
    for i, text in enumerate(after):
        lines.append(tag(text, LEFT, RIGHT, top + i * PITCH))
    return "\n".join(lines)


class TestPullQuotes(unittest.TestCase):
    # a box beside the text repeating a sentence from the page

    def test_box_repeating_the_page_is_dropped_and_the_text_beside_it_kept(self):
        raw = quote_page(
            box=["Humility is the single greatest and", "most indispensable attribute of being", "a team player."],
            beside=["What's amazing is", "that so many leaders who", "value teamwork will tol-", "erate people who aren't"],
            after=["humble. They reluctantly hire self-centered people and then",
                   "justify it simply because those people have desired skills.",
                   "Or, they see arrogant behavior in an employee and fail to"])
        lines = text_of(layout.to_lines(raw))
        self.assertNotIn("most indispensable attribute of being", lines)
        self.assertNotIn("a team player.", lines)
        kept = [l for l in lines if l]
        start = kept.index("What's amazing is")
        self.assertEqual(kept[start:start + 5], ["What's amazing is", "that so many leaders who",
                                                 "value teamwork will tol-", "erate people who aren't",
                                                 "humble. They reluctantly hire self-centered people and then"])

    def test_box_repeating_the_text_beside_it_is_dropped_not_the_text(self):
        # each column repeats the other; the box holds the whole passage
        raw = quote_page(
            box=["Many people will try to get a job", "even if they don't fit the company's",
                 "stated values, but very few will do so", "if they know that they're going to be",
                 "held accountable, day in and day out."],
            beside=["Many people will try", "to get a job even if they", "don't fit the company's",
                    "stated values, but very", "few will do so if they", "know that they're going"],
            after=["to be held accountable, day in and day out. Of course, it's",
                   "important that you follow through on that commitment to the",
                   "values in the rare occasion that a candidate calls the bluff."])
        lines = text_of(layout.to_lines(raw))
        self.assertNotIn("Many people will try to get a job", lines)
        self.assertIn("Many people will try", lines)
        self.assertIn("know that they're going", lines)

    def test_side_by_side_text_repeating_nothing_is_kept(self):
        raw = quote_page(
            box=["A sidebar about something else", "entirely, with words that appear", "nowhere else on this page at all."],
            beside=["What's amazing is", "that so many leaders who", "value teamwork will tol-", "erate people who aren't"],
            after=["humble. They reluctantly hire self-centered people and then",
                   "justify it simply because those people have desired skills.",
                   "Or, they see arrogant behavior in an employee and fail to"])
        lines = " ".join(text_of(layout.to_lines(raw)))
        self.assertIn("A sidebar about something else", lines)
        self.assertIn("that so many leaders who", lines)


def figure_page(lead):
    """Body text, then `lead` lines (text, x0, x1, size), then a Venn
    diagram's labels, then body."""
    lines = body(4, start=0.05)
    top = 0.05 + 4 * PITCH
    for text, x0, x1, size in lead:
        lines.append(tag(text, x0, x1, top, size))
        top += PITCH
    top += 0.04
    labels = [("Humble", 0.15, 0.25, 0.0), ("Hungry", 0.72, 0.82, 0.002),
              ("The", 0.47, 0.53, 0.03), ("Ideal", 0.46, 0.54, 0.05), ("Team", 0.46, 0.54, 0.07),
              ("Player", 0.45, 0.55, 0.09), ("Smart", 0.45, 0.55, 0.20)]
    for text, x0, x1, dy in labels:
        lines.append(tag(text, x0, x1, top + dy, 0.016))
    lines += body(4, start=top + 0.27)
    return "\n".join(lines)


class TestFigures(unittest.TestCase):
    # a diagram's labels read aloud are nonsense: "Humble Hungry The Ideal..."

    def test_scattered_labels_of_a_diagram_are_dropped(self):
        lines = text_of(layout.to_lines(figure_page([])))
        for label in ["Humble", "Hungry", "The", "Ideal", "Team", "Player", "Smart"]:
            self.assertNotIn(label, " ".join(lines).split())
        self.assertEqual(sum(l.startswith("body line") for l in lines), 8)

    def test_short_last_line_of_the_paragraph_above_is_kept(self):
        lines = text_of(layout.to_lines(figure_page([("teamwork.", LEFT, 0.22, 0.02)])))
        self.assertIn("teamwork.", lines)

    def test_figure_title_in_big_type_is_kept(self):
        lines = text_of(layout.to_lines(figure_page([("Three Virtues", 0.35, 0.65, 0.03)])))
        self.assertIn("Three Virtues", lines)
        self.assertNotIn("Ideal", lines)

    def test_run_of_short_replies_is_kept(self):
        # short, but each starts at the paragraph indent like any text
        replies = ['"Why?"', '"Because."', '"Of what?"', '"The rain."', '"Okay."', '"Fine."']
        lines = body(3, start=0.05) + [tag(r, LEFT + 0.04, LEFT + 0.16, 0.14 + i * PITCH) for i, r in enumerate(replies)]
        lines += body(3, start=0.14 + len(replies) * PITCH)
        out = text_of(layout.to_lines("\n".join(lines)))
        for r in replies:
            self.assertIn(r, out)


class TestCurledLines(unittest.TestCase):
    # a page curving toward the spine bends lines, and boxes with them

    def test_label_over_the_start_of_a_tall_line_stays_above_it(self):
        raw = "\n".join([
            tag("Instructions:", LEFT, 0.25, 0.100, 0.015),
            "[0.1000 0.9000 0.1050 0.1400 0.0300] Use the scale below to indicate how each statement applies",
            tag("to your actions on the team.", LEFT, 0.60, 0.145),
        ])
        self.assertEqual(text_of(layout.to_lines(raw))[:2],
                         ["Instructions:", "Use the scale below to indicate how each statement applies"])

    def test_pieces_of_a_bent_line_read_left_to_right(self):
        raw = "\n".join([
            "[0.4000 0.5800 0.2250 0.2420 0.0145] 2 = Sometimes",
            "[0.7000 0.8500 0.2240 0.2470 0.0162] 1 = Rarely",
            "[0.1000 0.2500 0.2330 0.2510 0.0162] 3 = Usually",
        ])
        self.assertEqual(layout.to_lines(raw), ["3 = Usually 2 = Sometimes 1 = Rarely"])


if __name__ == "__main__":
    unittest.main()
