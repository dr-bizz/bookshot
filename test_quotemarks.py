#!/usr/bin/env python3
"""Tests for putting back the quote marks Vision reads as Vietnamese letters.

Every garbled line here is real OCR from The Ideal Team Player, checked
against the photo.
"""
import unittest

import quotemarks

WORDS = {"company", "disaster", "it", "she", "hawaii", "family", "here"}


def fix(text, before="", after=""):
    return quotemarks.fix_line(text, before, after, WORDS.__contains__)


class TestClosingQuoteAtLineEnd(unittest.TestCase):
    def test_letters_for_a_period_and_quote(self):
        self.assertEqual(fix("excited these past couple months than I have been in yearsạẠạ"),
                         'excited these past couple months than I have been in years."')

    def test_stray_i_before_the_letters_goes(self):
        self.assertEqual(fix("CEO like me, this could be a recipe for disasteriẠại"),
                         'CEO like me, this could be a recipe for disaster."')

    def test_a_final_y_swallowed_by_the_letters_comes_back(self):
        self.assertEqual(fix("You've already been a blessing to me and the companịằ_"),
                         'You\'ve already been a blessing to me and the company."')

    def test_a_question_gets_a_question_mark(self):
        self.assertEqual(fix("this jobạẠại", before='"I mean, do you guys feel like one of you should have gotten'),
                         'this job?"')
        self.assertEqual(fix("differentiại", before='"And how do you think this one will be'),
                         'different?"')

    def test_a_question_word_starting_a_statement_is_no_question(self):
        self.assertEqual(fix("find you, and he asked who Kim wasạ",
                             before='"When I dropped him off ten minutes ago, I told him to'),
                         'find you, and he asked who Kim was."')
        self.assertEqual(fix("senior in the companyiịằi",
                             before='"Which is why we need to be really careful about this when we are hiring someone so'),
                         'senior in the company."')

    def test_punctuation_vision_did_read_is_kept(self):
        self.assertEqual(fix("don't we just-ại"), 'don\'t we just-"')

    def test_speech_tag_on_the_next_line_takes_a_comma(self):
        self.assertEqual(fix("I think I like the sound of thisạ", after="she said, smiling."),
                         'I think I like the sound of this,"')

    def test_an_i_after_the_period(self):
        self.assertEqual(fix("We're all screwed.ii This only made them laugh"),
                         'We\'re all screwed." This only made them laugh')

    def test_french_style_closing_mark(self):
        self.assertEqual(fix('"Listen, I didn\'t expect-»'), '"Listen, I didn\'t expect-"')


class TestQuoteInsideALine(unittest.TestCase):
    def test_closing_quote_before_narration(self):
        self.assertEqual(fix("I'm not going to get to work with youạẠạHe paused to avoid get-",
                             before='Suddenly, Bob smiled. "You know something? One of the worst things is that'),
                         'I\'m not going to get to work with you." He paused to avoid get-')

    def test_closing_quote_before_a_speech_tag_takes_a_comma(self):
        self.assertEqual(fix("truth about our confidence in youạẠạBobby added with",
                             before='"We need to tell you the'),
                         'truth about our confidence in you," Bobby added with')
        self.assertEqual(fix("morningiỊạishe explained, a little sadly.", before='"I found out this'),
                         'morning," she explained, a little sadly.')

    def test_opening_quote_after_narration(self):
        self.assertEqual(fix("Clare explainedẠWe said we need sixty more people to"),
                         'Clare explained. "We said we need sixty more people to')
        self.assertEqual(fix("Jeff smiled.ẠạLet's stick with jackasses for right now"),
                         'Jeff smiled. "Let\'s stick with jackasses for right now')


class TestOpeningQuoteAtLineStart(unittest.TestCase):
    def test_letters_at_the_start(self):
        self.assertEqual(fix("ạWell, I'll take all the help I can get."), '"Well, I\'ll take all the help I can get.')
        self.assertEqual(fix("ạiIt's very exciting."), '"It\'s very exciting.')

    def test_french_style_opening_mark(self):
        self.assertEqual(fix("«Here's the deal. I am ridiculously happy"), '"Here\'s the deal. I am ridiculously happy')

    def test_an_i_for_an_opening_quote(self):
        self.assertEqual(fix("iNo, that's not what I meant."), '"No, that\'s not what I meant.')


class TestOnlyInsideAQuote(unittest.TestCase):
    """The same marks after a sentence are footnote numbers in nonfiction."""

    def test_a_lone_i_for_a_closing_quote(self):
        words = {"kinds", "him", "putt"}.__contains__
        self.assertEqual(quotemarks.fix_line("kindsi She shook her head", '"And about fifty contractors, of all', "", words),
                         'kinds." She shook her head')
        self.assertEqual(quotemarks.fix_line("I wish I were like himi", '"I remember thinking,', "", words),
                         'I wish I were like him."')
        # outside a quote it's a word cut off at the spine ("suggesti[on]")
        self.assertEqual(quotemarks.fix_line("Clare made a suggesti", "", "", {"suggest"}.__contains__),
                         "Clare made a suggesti")

    def test_period_question_mark_closes_an_open_quote(self):
        self.assertEqual(fix('"Jeff, we just landed two great projects.?'),
                         '"Jeff, we just landed two great projects."')

    def test_footnote_number_outside_a_quote_stays(self):
        self.assertEqual(fix("than their counterparts.* The Five Practices"),
                         "than their counterparts.* The Five Practices")
        self.assertEqual(fix("being with the organization.? how valued people"),
                         "being with the organization.? how valued people")

    def test_trademark_sign_after_a_sentence_is_dropped(self):
        self.assertEqual(fix("Explain that.®"), "Explain that.")


class TestOrdinaryTextIsLeftAlone(unittest.TestCase):
    def test_plain_english(self):
        for text in ['"Is it okay?" she asked.', "He bought an iPad and an iPhone.",
                     "It was Mr. Phạm who answered.", "That's it, the end.",
                     "a real competi- ¿ive advantage", "Coca-Cola® is sold here."]:
            self.assertEqual(fix(text), text)


class TestFixLines(unittest.TestCase):
    def test_paragraph_context_carries_across_lines_and_pages(self):
        lines = ['"So, is there any truth, even a little, to what you',
                 "===== right page =====",
                 "were sayingạ"]
        self.assertEqual(quotemarks.fix_lines(lines, skip=lambda s: s.startswith("=====")),
                         ['"So, is there any truth, even a little, to what you',
                          "===== right page =====",
                          'were saying?"'])

    def test_a_blank_line_after_a_sentence_starts_a_new_paragraph(self):
        lines = ['"Is it done?"', "", "Bob was sure it would workạ"]
        self.assertEqual(quotemarks.fix_lines(lines)[2], 'Bob was sure it would work."')

    def test_a_blank_line_after_a_closing_quote_starts_a_new_paragraph(self):
        # Vision lost the question mark, but the closing quote still ends the
        # speech: the next speaker's line isn't a question
        lines = ['"Okay, but how do you feel about me sitting in it"', "",
                 "Well, we'd be lying if we didn't admit that we had concernsạẠạiClare said."]
        self.assertEqual(quotemarks.fix_lines(lines)[2],
                         "Well, we'd be lying if we didn't admit that we had concerns,\" Clare said.")

    def test_a_blank_line_mid_sentence_keeps_the_context(self):
        # clean.py ignores a break mid-sentence, so the question goes on
        lines = ['"How do I know if the baby is getting', "", "any betterạẠạẠạ"]
        self.assertEqual(quotemarks.fix_lines(lines)[2], 'any better?"')


class TestLoneI(unittest.TestCase):
    def test_a_name_ending_in_i_keeps_it(self):
        # clean.py's dictionary lookup ignores case
        words = lambda w: w.lower() in {"al", "ton", "jod", "said"}
        for name in ("Ali", "Toni", "Jodi"):
            with self.subTest(name=name):
                self.assertEqual(quotemarks.fix_line(f"I was there with {name}", '"Well,', "", words),
                                 f"I was there with {name}")


if __name__ == "__main__":
    unittest.main()
