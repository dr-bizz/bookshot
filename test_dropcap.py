#!/usr/bin/env python3
"""Tests for putting back the first letter that a drop cap took with it.

A chapter's opening letter is often set as a big decorative initial that OCR
can't read, so the first word comes out as "fter" or "eff". The missing
letter is chosen from the book itself.
"""
import unittest

import dropcap

WORDS = {"after", "on", "in", "an", "okay", "bark", "dark", "the", "she", "as", "is"}


def restore(blocks, words=WORDS):
    return dropcap.restore_initials(blocks, words.__contains__)


class TestRestoreInitials(unittest.TestCase):
    def test_letter_that_makes_a_real_word_is_put_back(self):
        blocks = [("h2", "ENOUGH"), ("p", "fter twenty years, Jeff left.")]
        self.assertEqual(restore(blocks)[1], ("p", "After twenty years, Jeff left."))

    def test_names_used_elsewhere_in_the_book_count_as_words(self):
        blocks = [("h2", "DRAMA"), ("p", "eff took a deep breath."), ("p", "Clare looked at Jeff.")]
        self.assertEqual(restore(blocks)[1][1], "Jeff took a deep breath.")

    def test_surrounding_words_pick_between_real_words(self):
        # "n the way": On, In and An are all words; the book says "on the way"
        blocks = [
            ("h2", "REGROUPING"), ("p", "n the way home, Jeff called Ben."),
            ("p", "They talked on the way back to the office."),
            ("p", "In the morning, in the office, in the car."),
        ]
        self.assertEqual(restore(blocks)[1][1], "On the way home, Jeff called Ben.")

    def test_opening_already_capitalized_is_left_alone(self):
        blocks = [("h2", "ENOUGH"), ("p", "After twenty years, Jeff left.")]
        self.assertEqual(restore(blocks), blocks)

    def test_lowercase_paragraph_not_after_a_heading_is_left_alone(self):
        # a paragraph split mid-sentence, not a chapter opening
        blocks = [("p", "Jeff walked in and"), ("p", "fter that he sat down.")]
        self.assertEqual(restore(blocks), blocks)

    def test_common_word_wins_a_tie_the_book_cannot_settle(self):
        # the dictionary also has rare words like "ofter"; with no help from
        # the book, the everyday word wins
        blocks = [("h2", "ENOUGH"), ("p", "fter twenty years.")]
        out = dropcap.restore_initials(blocks, {"after", "ofter"}.__contains__, {"after"}.__contains__)
        self.assertEqual(out[1][1], "After twenty years.")

    def test_a_toss_up_is_left_alone(self):
        # bark or dark, and nothing in the book to tell them apart
        blocks = [("h2", "NIGHT"), ("p", "ark clouds rolled over.")]
        self.assertEqual(restore(blocks), blocks)

    def test_fragment_with_no_possible_word_is_left_alone(self):
        blocks = [("h2", "NIGHT"), ("p", "zzq clouds rolled over.")]
        self.assertEqual(restore(blocks), blocks)

    def test_opening_quote_stays_in_front(self):
        blocks = [("h2", "THE HAMMER"), ("p", "“kay, I'm going to be direct.”")]
        self.assertEqual(restore(blocks)[1][1], "“Okay, I'm going to be direct.”")

    def test_count_of_restored_letters_is_reported(self):
        blocks = [("h2", "ENOUGH"), ("p", "fter twenty years."), ("h2", "NIGHT"), ("p", "ark clouds.")]
        self.assertEqual(dropcap.count_restored(blocks, restore(blocks)), 1)


if __name__ == "__main__":
    unittest.main()
