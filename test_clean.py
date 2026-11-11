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

    def test_garbled_closing_quote_still_ends_the_paragraph(self):
        # Vision reads `company."` as "companịằ_"; the break after it must hold
        out = clean("\"You've already been a blessing to me and the companịằ_\n\nJeff felt a\nlittle guilty about leaving his job.\n")
        self.assertIn('the company."\n\nJeff felt', out)

    def test_quote_broken_off_with_a_dash_ends_the_paragraph(self):
        # the hyphen Vision read is the dash the speaker broke off with
        out = clean("\"Listen, I didn't expect-\"\n\n\"Jeff, let me finish what I was going\nto say.\"\n")
        self.assertIn('expect—"\n\n"Jeff', out)

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


    def test_wrap_with_the_hyphen_lost_is_closed_up(self):
        # OCR dropped the hyphen; "cern" is no word the book uses on its own
        out = clean("in real-world situations so you can dis\ncern whether they are humble.\n")
        self.assertIn("can discern whether", out)

    def test_a_before_a_line_break_is_not_joined_to_the_next_word(self):
        out = clean("They went out for a\nround of golf after he gave them a\nbroad smile at the door.\n")
        self.assertIn("for a round of golf", out)
        self.assertIn("them a broad smile", out)

    def test_two_words_across_a_line_stay_two(self):
        # "thing" is a word the book uses on its own, so this is two words
        out = clean("The thing is, the main thing we like is the thing we do for some\nthing like that.\n")
        self.assertIn("for some thing like", out)

    def test_wrap_hyphen_joins_into_a_name_the_book_uses(self):
        # "mau" and "rine" are both in the 1934 dictionary, so alone they'd keep the hyphen
        out = clean("Maurine said hello to everyone at the table that night, and Maurine sat.\n"
                    "He was working plenty of weekends, he explained to Mau-\nrine, who agreed with him.\n")
        self.assertIn("explained to Maurine, who", out)

    def test_wrap_hyphen_joins_a_word_with_a_dropped_e(self):
        out = clean("and thus have a little higher likelihood of over-\ncoming their challenges.\n")
        self.assertIn("of overcoming their", out)

    def test_quote_junk_becomes_a_quote_and_keeps_its_paragraph_break(self):
        out = clean("I would never have put you in this dilemmaạẠạ\n\nJeff felt terrible for his uncle and the company.\n")
        self.assertIn('in this dilemma."\n\nJeff felt', out)

    def test_capital_t_for_i_is_fixed(self):
        out = clean('Bobby looked up from the table and said, "T\'m not sure."\n')
        self.assertIn('"I\'m not sure."', out)

    def test_misread_letter_is_fixed_from_the_books_own_words(self):
        out = clean("We want them to focus on results. Then they focus on the team.\n"
                    "So they hold people accountable, and tocus on the team's results.\n")
        self.assertIn("and focus on the team's results", out)

    def test_hyphen_for_a_dash_becomes_one(self):
        out = clean("in order to thrive in the world of work-and for that matter, life.\n")
        self.assertIn("work\u2014and for that matter", out)

    def test_letter_lost_to_a_drop_cap_is_put_back(self):
        out = clean("ENOUGH\nfter twenty years, Jeff Shanley had seen enough of the valley.\n")
        self.assertIn("ENOUGH\n\nAfter twenty years", out)

    def test_short_lines_running_on_into_a_sentence_are_not_a_heading(self):
        # text narrowed beside a pull-quote box comes in short lines
        out = clean("of being a team player.\n\nWhat's amazing is\nthat so many leaders who\n"
                    "value teamwork will tolerate people who aren't humble.\n")
        self.assertIn("What's amazing is that so many leaders who value teamwork", out)

    def test_short_line_over_a_lowercase_start_is_still_set_apart(self):
        # a chapter title over an opening whose drop cap ("O") was lost
        out = clean("and that was the end of the day.\nTED\nn Monday morning, Jeff was sitting in Bob's office.\n")
        self.assertIn("TED\n\n", out)

    def test_numbered_items_are_blocks_of_their_own(self):
        # item 1 lost its period at the page edge; the numbering still shows
        # where each statement starts
        out = clean("My teammates would say:\n\n1. I compliment or praise them without hesitation\n"
                    "2. I easily admit to my mistakes.\n3. I am willing to take on lower-level work for the\n"
                    "good of the team.\n")
        self.assertIn("say:\n\n1. I compliment", out)
        self.assertIn("hesitation\n\n2. I easily", out)
        self.assertIn("mistakes.\n\n3. I am willing to take on lower-level work for the good of the team.", out)

    def test_each_list_counts_from_its_own_one(self):
        # a second list mustn't carry on the first one's count
        out = clean("Steps to bathe the baby are these\n1. Fill the tub with warm water\n"
                    "2. Test the water with your elbow\n3. Lower the baby slowly\n\n"
                    "Steps to feed the baby are these\n1. Warm the bottle in water\n"
                    "2. Test a drop on your wrist\n3. Hold the baby upright\n4. Burp the baby halfway\n")
        for item in ("2. Test the water", "3. Lower", "2. Test a drop", "3. Hold", "4. Burp"):
            with self.subTest(item=item):
                self.assertIn("\n\n" + item, out)

    def test_number_mid_sentence_is_not_an_item(self):
        out = clean("In the end the count of new hires came to\n1. That was less than we hoped for.\n")
        self.assertIn("came to 1. That was", out)

    def test_number_out_of_sequence_at_a_line_start_is_not_an_item(self):
        out = clean("We counted them twice and the total came to\n7. That was more than anyone expected.\n")
        self.assertIn("came to 7. That was", out)

    def test_page_number_with_an_ornament_is_dropped_not_a_bullet(self):
        # "• 150" used to become a bullet that swallowed the next page
        text, kinds = clean_with_kinds("the worksites of Valley Builders.\n\n• 150\n\nOf all the leaders at VB, it was Bobby who said it.\n")
        self.assertNotIn("150", text)
        self.assertNotIn("li", kinds)

    def test_short_lowercase_line_is_not_a_heading_guess(self):
        # the tail of a sentence broken off by a pull quote beside it
        out = clean("The common sense about people.\n\nlikely responses of their\ncolleagues and friends.\n")
        self.assertIn("likely responses of their colleagues and friends.", out)


class TestSubheadings(unittest.TestCase):
    # body-size italic or bold sub-headings: a block of their own on the
    # page that doesn't end with a stop

    def test_name_carried_over_a_line_break_is_not_a_subheading(self):
        out = clean("Everyone was there.\n\nScan the QR code for our Baby Food\n\n"
                    "Introduction Calendar, a super easy\nprintable guide on our site.\n")
        self.assertIn("Baby Food Introduction Calendar", out)

    def test_two_line_heading_ending_lowercase_stays_a_heading(self):
        out = clean("That is all for the first weeks.\n\nSleep: 3-6 Months (including\n"
                    "dropping the swaddle)\n\nIf you have not slept well yet, we have great news.\n")
        self.assertIn("Sleep: 3-6 Months (including dropping the swaddle)\n\nIf you have", out)

    def test_long_subheading_is_kept_apart_from_its_paragraph(self):
        raw = ("rather than general assessments.\n\nPay Attention to References Who Don't Respond\n\n"
               "When reference givers do not respond to your requests for a\nreference, it is possible.\n")
        out = clean(raw)
        self.assertIn("Pay Attention to References Who Don't Respond\n\nWhen reference givers", out)

    def test_subheading_on_two_lines_stays_together(self):
        raw = ("building process.\n\nHumble and Hungry, but Not Smart: The Accidental\n\nMess-Maker\n\n"
               "People who are humble and hungry but decidedly not smart\nare the mess-makers.\n")
        out = clean(raw)
        self.assertIn("The Accidental Mess-Maker\n\nPeople who are humble", out)

    def test_break_before_a_lowercase_word_is_still_ignored(self):
        # title case, but the next line carries on the sentence
        out = clean("The board met.\n\nJeff Shanley Was Fortunate Enough to Get Himself\n\ndemoted when the board of directors hired a CEO.\n")
        self.assertIn("Himself demoted", out)

    def test_diagram_labels_are_not_split_into_subheadings(self):
        out = clean("from their managers.\n\nHumble Hungry\nThe\n\nIdeal\nTeam\n\nPlayer Smart\n\nLet's take a look at the categories of people.\n")
        self.assertIn("Humble Hungry The Ideal Team Player Smart", out)


class TestShortChapterTitles(unittest.TestCase):
    # "BOB" and "TED" are too short for the capitals rule (four letters)

    def test_short_capitals_title_over_a_lost_drop_cap_is_a_chapter_heading(self):
        raw = ("Bobby wouldn't disappoint them.\nTED\nn Monday morning, Jeff was sitting in the office.\n"
               "On Monday the crew came back.\n")
        text, kinds = clean_with_kinds(raw)
        self.assertIn("TED\n\nOn Monday morning", text)
        self.assertEqual(kinds[:3], ["p", "h2", "p"])

    def test_short_capitals_line_over_an_ordinary_paragraph_is_not(self):
        _, kinds = clean_with_kinds("The crew was done.\nNBC\nThe network called back the next day.\n")
        self.assertEqual(kinds, ["p", "p", "p"])


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
