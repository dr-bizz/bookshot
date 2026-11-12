#!/usr/bin/env python3
"""Tests for the photo check: missing, repeated and out-of-order pages, and
photos to retake."""
import unittest

import pagecheck

WORDS = ("the quick brown fox jumps over a lazy dog while Jeff and Clare talk about "
         "hiring people who are humble hungry and smart for the company Valley Builders").split()


def body(seed: int, lines: int = 12) -> list[str]:
    """A page of body text, different for each seed."""
    out = []
    for i in range(lines):
        words = [WORDS[(seed * 7 + i * 3 + k * (seed + 2)) % len(WORDS)] for k in range(9)]
        out.append(f"[0.1000 0.9000 {0.1 + i * 0.05:.4f} {0.12 + i * 0.05:.4f} 0.0180 0.5000] "
                   + " ".join(words) + f" {seed}x{i}")
    return out


def folio(n) -> str:
    return f"[0.4800 0.5200 0.9000 0.9150 0.0150 0.6000] {n}"


def spread(name, left, right, blur=(0.2, 0.2), spine=True):
    """One photo of two pages. left/right: (seed, page number or None),
    or None for a blank page."""
    lines = [f"===== {name}.jpg ====="]
    for side, page, b in (("left", left, blur[0]), ("right", right, blur[1])):
        extra = "" if spine or side == "right" else " spine=none"
        lines.append(f"===== {side} page blur={b:.3f}{extra} =====")
        if page:
            seed, n = page
            lines += body(seed)
            if n is not None:
                lines.append(folio(n))
    return lines


def run(*photos):
    raw = "\n".join(line for p in photos for line in p)
    return pagecheck.check(raw)


class TestPageNumbers(unittest.TestCase):
    def test_folio_reading(self):
        for text, n in (("31", 31), ("3 l", 31), ("5l", 51), ("• 150", 150), ("- 133", 133),
                        ("1O", 10), ("T15", 115), ("IO", None), ("xi", None), ("Clare", None)):
            with self.subTest(text=text):
                self.assertEqual(pagecheck.folio_number(text), n)

    def test_pages_in_order_say_nothing(self):
        _, notes = run(spread("IMG_1", (1, 24), (2, 25)), spread("IMG_2", (3, 26), (4, 27)),
                       spread("IMG_3", (5, 28), (6, 29)))
        self.assertEqual(notes, [])

    def test_missing_spread(self):
        _, notes = run(spread("IMG_1", (1, 24), (2, 25)), spread("IMG_2", (3, 26), (4, 27)),
                       spread("IMG_3", (5, 30), (6, 31)))
        self.assertEqual(len(notes), 1)
        self.assertIn("Pages 28-29", notes[0])
        self.assertIn("IMG_2", notes[0])
        self.assertIn("IMG_3", notes[0])

    def test_unnumbered_pages_are_not_missing(self):
        # chapter openings and blank pages carry no number
        _, notes = run(spread("IMG_1", (1, 24), (2, None)), spread("IMG_2", None, (4, 27)),
                       spread("IMG_3", (5, 28), (6, 29)))
        self.assertEqual(notes, [])

    def test_a_misread_number_is_ignored(self):
        _, notes = run(spread("IMG_1", (1, 24), (2, 25)), spread("IMG_2", (3, 26), (4, 72)),
                       spread("IMG_3", (5, 28), (6, 29)))
        self.assertEqual(notes, [])

    def test_gap_across_unnumbered_photos(self):
        _, notes = run(spread("IMG_1", (1, 24), (2, 25)), spread("IMG_2", (3, None), (4, None)),
                       spread("IMG_3", (5, 32), (6, 33)))
        self.assertEqual(len(notes), 1)
        self.assertIn("4 pages", notes[0])
        self.assertIn("IMG_1", notes[0])
        self.assertIn("IMG_3", notes[0])

    def test_out_of_order(self):
        _, notes = run(spread("IMG_1", (1, 24), (2, 25)), spread("IMG_2", (3, 40), (4, 41)),
                       spread("IMG_3", (5, 26), (6, 27)), spread("IMG_4", (7, 28), (8, 29)))
        self.assertTrue(any("out of order" in n for n in notes), notes)

    def test_out_of_order_says_where_it_belongs(self):
        # IMG_5 holds pages 30-31, shot late: one note, not "missing" as well
        _, notes = run(spread("IMG_1", (1, 24), (2, 25)), spread("IMG_2", (3, 26), (4, 27)),
                       spread("IMG_3", (5, 28), (6, 29)), spread("IMG_4", (7, 32), (8, 33)),
                       spread("IMG_5", (9, 30), (10, 31)), spread("IMG_6", (11, 34), (12, 35)))
        self.assertEqual(notes, ["IMG_5 (pages 30-31) is out of order: it belongs between IMG_3 and IMG_4."])

    def test_out_of_order_next_to_a_gap_blames_the_fewest_photos(self):
        # IMG_6 (pages 30-31) was shot late, and pages 38-39 were skipped:
        # one photo is out of place, not the three it jumped
        _, notes = run(spread("IMG_1", (1, 24), (2, 25)), spread("IMG_2", (3, 26), (4, 27)),
                       spread("IMG_3", (5, 28), (6, 29)), spread("IMG_4", (7, 32), (8, 33)),
                       spread("IMG_5", (9, 34), (10, 35)), spread("IMG_5b", (11, 36), (12, 37)),
                       spread("IMG_6", (13, 30), (14, 31)), spread("IMG_7", (15, 40), (16, 41)),
                       spread("IMG_8", (17, 42), (18, 43)))
        self.assertIn("IMG_6 (pages 30-31) is out of order: it belongs between IMG_3 and IMG_4.", notes)
        self.assertTrue(any("Pages 38-39" in n for n in notes), notes)
        self.assertEqual(len(notes), 2, notes)

    def test_a_misread_last_number_going_back_is_ignored(self):
        # a broken photo at the end read "48" as "18"
        _, notes = run(spread("IMG_1", (1, 44), (2, 45)), spread("IMG_2", (3, 46), (4, 47)),
                       spread("IMG_3", (5, None), (6, 18)))
        self.assertEqual(notes, [])

    def test_roman_numbered_front_matter_is_left_alone(self):
        _, notes = run(spread("IMG_1", (1, "x"), (2, "xi")), spread("IMG_2", (3, None), (4, 5)),
                       spread("IMG_3", (5, 6), (6, 7)))
        self.assertEqual(notes, [])


class TestRepeats(unittest.TestCase):
    def test_same_spread_twice_is_used_once(self):
        raw, notes = run(spread("IMG_1", (1, 24), (2, 25)), spread("IMG_2", (1, 24), (2, 25)),
                         spread("IMG_3", (5, 26), (6, 27)))
        self.assertEqual(raw.count("1x0"), 1)
        self.assertEqual(raw.count("2x0"), 1)
        self.assertEqual(len(notes), 1)
        self.assertIn("IMG_2", notes[0])
        self.assertIn("IMG_1", notes[0])

    def test_the_sharper_copy_is_kept(self):
        raw, notes = run(spread("IMG_1", (1, 24), (2, 25), blur=(0.5, 0.5)),
                         spread("IMG_2", (1, 24), (2, 25), blur=(0.2, 0.2)))
        self.assertIn("blur=0.200", raw)
        self.assertNotIn("blur=0.500", raw)
        self.assertEqual(raw.count("1x0"), 1)

    def test_a_reshot_page_far_back_keeps_its_first_place(self):
        raw, notes = run(spread("IMG_1", (1, 24), (2, 25)), spread("IMG_2", (3, 26), (4, 27)),
                         spread("IMG_3", (5, 28), (6, 29)), spread("IMG_4", (1, 24), (2, 25), blur=(0.1, 0.1)))
        self.assertIn("1x0", raw.split("===== IMG_2.jpg =====")[0])
        self.assertEqual(raw.count("1x0"), 1)
        self.assertNotIn("IMG_4.jpg", raw)
        self.assertEqual(len(notes), 1)

    def test_a_sharp_retake_at_the_end_replaces_the_blurry_copy_in_its_place(self):
        # the README says to retake blurry photos; a retake shot at the end
        # must win, and read where the blurry one was
        blurry = spread("IMG_2", (3, 26), (4, 27), blur=(0.62, 0.62))
        blurry[3] = blurry[3] + " blurrycopy"
        sharp = spread("IMG_9", (3, 26), (4, 27))
        sharp[3] = sharp[3] + " sharpcopy"
        raw, notes = run(spread("IMG_1", (1, 24), (2, 25)), blurry, spread("IMG_3", (5, 28), (6, 29)),
                         spread("IMG_4", (7, 30), (8, 31)), sharp)
        self.assertNotIn("blurrycopy", raw)
        self.assertLess(raw.index("sharpcopy"), raw.index("5x0"))
        self.assertEqual(len(notes), 1, notes)
        self.assertIn("IMG_9 repeats IMG_2", notes[0])

    def test_a_copy_cut_at_the_spine_loses_to_a_good_one(self):
        raw, notes = run(spread("IMG_1", (1, 24), (2, 25), spine=False), spread("IMG_2", (1, 24), (2, 25)))
        self.assertNotIn("spine=none", raw)
        self.assertEqual(len(notes), 1, notes)

    def test_a_fuller_copy_beats_a_flagged_one_that_lost_lines(self):
        # a finger over the page, say: the unflagged copy read half the lines
        full_copy = spread("IMG_1", (1, 24), (2, 25), spine=False)
        part = spread("IMG_2", (1, 24), (2, 25))
        part = [line for line in part if not any(f"1x{i} " in line + " " for i in range(6, 12))]
        raw, notes = run(full_copy, part)
        self.assertIn("1x11", raw)
        self.assertEqual(len([n for n in notes if "repeats" in n]), 1, notes)

    def test_notes_name_the_photo_whose_pages_are_used(self):
        blurry = spread("IMG_1", (1, 24), (2, 25), blur=(0.7, 0.7), spine=False)
        cut = spread("IMG_1b", (1, 24), (2, 25))
        cut = [line.replace("===== right page blur=0.200 =====", "===== right page blur=0.200 edge=cut =====")
               for line in cut]
        _, notes = run(blurry, cut)
        self.assertTrue(any(n.startswith("IMG_1b: the right page runs off") for n in notes), notes)
        self.assertFalse(any("IMG_1: " in n for n in notes), notes)

    def test_three_shots_of_one_spread_are_used_once(self):
        raw, notes = run(spread("IMG_1", (1, 24), (2, 25)), spread("IMG_2", (1, 24), (2, 25)),
                         spread("IMG_3", (1, 24), (2, 25), blur=(0.05, 0.05)), spread("IMG_4", (5, 26), (6, 27)))
        self.assertEqual(raw.count("1x0"), 1)
        self.assertIn("blur=0.050", raw)
        self.assertEqual(len(notes), 2, notes)

    def test_pages_sharing_a_running_header_are_not_repeats(self):
        header = "[0.3000 0.7000 0.0500 0.0650 0.0150 0.5000] The Ideal Team Player"
        a = spread("IMG_1", (1, 24), (2, 25))
        b = spread("IMG_2", (3, 26), (4, 27))
        a.insert(2, header)
        b.insert(2, header)
        raw, notes = run(a, b)
        self.assertEqual(notes, [])
        self.assertIn("3x0", raw)

    def test_template_pages_are_not_repeats(self):
        # A baby-care book sets each age's "Typical Day" on the same template:
        # 78% of the word pairs match, but the numbers differ, and so does
        # the page number. Dropping one lost a real page.
        def schedule(age, start):
            return [f"[0.1000 0.9000 {0.1 + i * 0.05:.4f} {0.12 + i * 0.05:.4f} 0.0180 0.5000] "
                    + ("Breast or bottle feedings should take no longer than 30 minutes start to finish "
                       f"the bottle contains {start + i} ounces for babies {age} weeks old at this feed")
                    for i in range(12)]
        a = ["===== IMG_1.jpg =====", "===== left page blur=0.200 ====="] + schedule("2-4", 3) + [folio(40),
             "===== right page blur=0.200 ====="] + body(2) + [folio(41)]
        b = ["===== IMG_2.jpg =====", "===== left page blur=0.200 ====="] + schedule("4-8", 4) + [folio(42),
             "===== right page blur=0.200 ====="] + body(4) + [folio(43)]
        raw, notes = run(a, b)
        self.assertIn("4-8 weeks", raw)
        self.assertEqual(notes, [])

    def test_a_page_on_the_other_side_is_not_a_repeat(self):
        # a reshot spread keeps each page on its own side
        raw, notes = run(spread("IMG_1", (1, None), (2, None)), spread("IMG_2", (2, None), (3, None)))
        self.assertEqual(raw.count("2x0"), 2)
        self.assertEqual(notes, [])

    def test_short_pages_are_never_matched(self):
        short = ["===== IMG_1.jpg =====", "===== left page blur=0.200 =====",
                 "[0.1000 0.9000 0.1000 0.1200 0.0180 0.5000] The End",
                 "===== right page blur=0.200 ====="]
        raw, notes = run(short, [line.replace("IMG_1", "IMG_2") for line in short])
        self.assertEqual(raw.count("The End"), 2)
        self.assertEqual(notes, [])


class TestRetakes(unittest.TestCase):
    def test_both_pages_blurry_is_one_note(self):
        _, notes = run(spread("IMG_1", (1, 24), (2, 25), blur=(0.7, 0.7)))
        self.assertEqual(len(notes), 1)
        self.assertIn("both pages are blurry", notes[0])

    def test_blurry_page(self):
        _, notes = run(spread("IMG_1", (1, 24), (2, 25), blur=(0.2, 0.7)))
        self.assertEqual(len(notes), 1)
        self.assertIn("IMG_1", notes[0])
        self.assertIn("right page", notes[0])
        self.assertIn("blurry", notes[0])

    def test_spine_not_found(self):
        _, notes = run(spread("IMG_1", (1, 24), (2, 25), spine=False))
        self.assertEqual(len(notes), 1)
        self.assertIn("spine", notes[0])

    def test_text_running_off_the_edge(self):
        photo = spread("IMG_1", (1, 24), (2, 25))
        # the left page's outer margin is cut off: lines start at the edge
        photo = [line.replace("[0.1000 0.9000", "[0.0010 0.9000", 1) if i < 8 else line
                 for i, line in enumerate(photo)]
        _, notes = run(photo)
        self.assertEqual(len(notes), 1)
        self.assertIn("left page", notes[0])
        self.assertIn("edge", notes[0])

    def test_page_marked_cut_by_ocr(self):
        # ocr.swift saw letters past where Vision's lines stop at the side
        photo = spread("IMG_1", (1, 24), (2, 25))
        photo = [line.replace("===== right page blur=0.200 =====", "===== right page blur=0.200 edge=cut =====")
                 for line in photo]
        _, notes = run(photo)
        self.assertEqual(len(notes), 1, notes)
        self.assertIn("right page", notes[0])
        self.assertIn("edge", notes[0])

    def test_text_cut_at_the_bottom(self):
        photo = spread("IMG_1", (1, 24), (2, 25))
        photo.append("[0.1000 0.9000 0.9900 0.9995 0.0180 0.5000] the bottom line cut in half")
        _, notes = run(photo)
        self.assertEqual(len(notes), 1)
        self.assertIn("right page", notes[0])
        self.assertIn("edge", notes[0])

    def test_a_scrap_at_the_top_edge_is_not_a_cut_line(self):
        # a pattern on the rug beside the book, read as a number
        photo = spread("IMG_1", (1, 24), (2, 25))
        photo.append("[0.4929 0.6002 -0.0006 0.0173 0.0173 0.6706] 26828")
        _, notes = run(photo)
        self.assertEqual(notes, [])

    def test_faint_show_through_at_the_edge_is_fine(self):
        photo = spread("IMG_1", (1, 24), (2, 25))
        photo.append("[0.7000 0.9995 0.5000 0.5200 0.0180 0.0500] desrever txet")
        photo.append("[0.7000 0.9995 0.5500 0.5700 0.0180 0.0500] desrever txet")
        _, notes = run(photo)
        self.assertEqual(notes, [])


class TestRawFormats(unittest.TestCase):
    def test_older_raw_skips_the_page_count(self):
        # the old ocr.swift printed nothing for a blank page, so pages can't
        # be counted: no notes, rather than false "missing" ones
        raw = "\n".join(["===== IMG_1.jpg ====="] + body(1) + [folio(24), "===== right page ====="]
                        + body(2) + [folio(25), "===== IMG_2.jpg ====="] + body(4) + [folio(27),
                        "===== IMG_3.jpg ====="] + body(5) + [folio(28), "===== right page ====="]
                        + body(6) + [folio(29)])
        self.assertEqual(pagecheck.check(raw)[1], [])

    def test_older_raw_without_page_markers(self):
        raw = "\n".join(["===== IMG_1.jpg ====="] + body(1) + [folio(24), "===== right page ====="]
                        + body(2) + [folio(25), "===== IMG_2.jpg ====="] + body(3) + [folio(26),
                        "===== right page ====="] + body(4) + [folio(27)])
        out, notes = pagecheck.check(raw)
        self.assertEqual(out, raw)
        self.assertEqual(notes, [])

    def test_single_pages(self):
        raw = "\n".join(["===== IMG_1.jpg =====", "===== page blur=0.200 ====="] + body(1) + [folio(24)]
                        + ["===== IMG_2.jpg =====", "===== page blur=0.200 ====="] + body(2) + [folio(25)]
                        + ["===== IMG_3.jpg =====", "===== page blur=0.200 ====="] + body(3) + [folio(27)])
        _, notes = pagecheck.check(raw)
        self.assertEqual(len(notes), 1)
        self.assertIn("Page 26", notes[0])

    def test_text_without_any_markers_passes_through(self):
        raw = "\n".join(body(1))
        self.assertEqual(pagecheck.check(raw), (raw, []))


if __name__ == "__main__":
    unittest.main()
