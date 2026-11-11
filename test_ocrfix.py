#!/usr/bin/env python3
"""Tests for the OCR word fixes. Examples are real misreads from a book."""
import unittest

import ocrfix

# a small dictionary standing in for /usr/share/dict/words
DICT = {
    "him", "here", "it", "he", "said", "well", "that", "focus", "on", "the", "team",
    "often", "meet", "will", "for", "your", "tor", "few", "tew", "a", "important",
    "humble", "hungry", "bumble", "smart", "mana", "and", "had", "we", "back", "bad", "to",
    "bac", "transforming", "employee", "the", "so", "work", "life", "world", "of",
    "self", "aware", "day", "to", "if", "right", "isn't", "who", "what", "did", "say",
    "don't", "worry", "about", "man", "mani", "taxi", "tax", "company", "family",
    "matter", "i", "is", "smiled", "let's", "stick", "with", "jackasses", "you",
    "know", "humble", "real", "commitments", "phone",
}
is_word = DICT.__contains__


def book(*texts: str) -> ocrfix.Book:
    return ocrfix.Book(" ".join(texts))


class TestPronounI(unittest.TestCase):
    def test_capital_t_and_p_for_i(self):
        self.assertEqual(ocrfix.fix_pronoun_i('"T\'m sure. T\'d say so. P\'d go. TIl see. PIl see."'),
                         '"I\'m sure. I\'d say so. I\'d go. I\'ll see. I\'ll see."')

    def test_lost_apostrophe(self):
        self.assertEqual(ocrfix.fix_pronoun_i("Ive seen him. Im sorry."), "I've seen him. I'm sorry.")

    def test_one_for_i(self):
        self.assertEqual(ocrfix.fix_pronoun_i('And 1 did enjoy it. "1 think so," she said.'),
                         'And I did enjoy it. "I think so," she said.')

    def test_one_as_a_number_stays(self):
        self.assertEqual(ocrfix.fix_pronoun_i("1 in 5 people, 1 percent"), "1 in 5 people, 1 percent")

    def test_words_with_t_or_p_stay(self):
        text = "Tim's dog, Pat'd, Tilly, Ivey, Imogen"
        self.assertEqual(ocrfix.fix_pronoun_i(text), text)

    def test_one_before_a_noun_stays_a_number(self):
        # from a baby-care book: amounts, times and steps
        for text in ("More than 1 teaspoon a day", "½ - 1 ounce at a time", "by week 1 when newborns",
                     "wake at 1 a.m. for a feed", "Step 1 is to wash", "1 cup of rice cereal",
                     "Table 1 shows the schedule"):
            with self.subTest(text=text):
                self.assertEqual(ocrfix.fix_pronoun_i(text), text)

    def test_one_for_i_with_the_books_own_pairing(self):
        b = book("I demonstrate it daily. I demonstrate it again.")
        self.assertEqual(ocrfix.fix_pronoun_i("15. 1 demonstrate an interest", b),
                         "15. I demonstrate an interest")

    def test_t_apostrophe_re_stays(self):
        self.assertEqual(ocrfix.fix_pronoun_i("T're"), "T're")

    def test_lowercase_l_for_i(self):
        self.assertEqual(ocrfix.fix_pronoun_i("As much as I want to be optimistic, l think it's harder."),
                         "As much as I want to be optimistic, I think it's harder.")

    def test_l_in_a_list_or_unit_stays(self):
        text = "a 2 l bottle, item (l) of the list"
        self.assertEqual(ocrfix.fix_pronoun_i(text), text)


class TestInvertedQuestionMark(unittest.TestCase):
    # Vision reads the capital after an opening quote as "¿", or adds one
    def test_lost_capital_comes_back_from_the_books_own_words(self):
        b = book("You know it. You know them. We are here. We are there. He is.")
        self.assertEqual(ocrfix.fix_lost_capitals('looked at Jeff. "¿ou know something?"', b),
                         'looked at Jeff. "You know something?"')
        self.assertEqual(ocrfix.fix_lost_capitals('"¿e are out of town," she said.', b),
                         '"We are out of town," she said.')

    def test_extra_mark_before_a_capital_goes(self):
        self.assertEqual(ocrfix.fix_lost_capitals('a revelation. "¿Oh, and he hated it."', book()),
                         'a revelation. "Oh, and he hated it."')

    def test_no_clear_letter_leaves_it(self):
        self.assertEqual(ocrfix.fix_lost_capitals('"¿e said so."', book()), '"¿e said so."')


class TestSmallWords(unittest.TestCase):
    # t for f and I for 1 on short words that are words either way: only
    # where the grammar leaves one reading
    def test_it_for_if_at_the_start_of_a_clause(self):
        self.assertEqual(ocrfix.fix_small_words("It the employee is unwilling, stop."),
                         "If the employee is unwilling, stop.")
        self.assertEqual(ocrfix.fix_small_words("For instance, it the first two agree"),
                         "For instance, if the first two agree")
        self.assertEqual(ocrfix.fix_small_words("work. It you have employees"),
                         "work. If you have employees")

    def test_it_mid_clause_stays(self):
        for text in ("Call it the end of an era.", "They made it a rule.", "Give it your best."):
            with self.subTest(text=text):
                self.assertEqual(ocrfix.fix_small_words(text), text)

    def test_number_sign_before_capital_i(self):
        self.assertEqual(ocrfix.fix_small_words("APPLICATION #I: HIRING and #I: Absence of Trust"),
                         "APPLICATION #1: HIRING and #1: Absence of Trust")

    def test_apostrophe_read_as_an_inverted_question_mark(self):
        self.assertEqual(ocrfix.fix_small_words('"I¿ve got to be over at Oak Ridge. We¿ll see."'),
                         '"I\'ve got to be over at Oak Ridge. We\'ll see."')

    def test_contraction_ending_in_c(self):
        self.assertEqual(ocrfix.fix_small_words("it wouldn't make any sense that we'c be better"),
                         "it wouldn't make any sense that we'd be better")


class TestMisreads(unittest.TestCase):
    def fix(self, text, b):
        return ocrfix.fix_misreads(text, is_word, b)

    def test_t_for_f_fixed_to_a_word_the_book_uses(self):
        b = book("focus on the team " * 3, "focus")
        self.assertEqual(self.fix("and tocus on the team", b), "and focus on the team")

    def test_long_t_for_f_word_needs_only_the_dictionary(self):
        self.assertEqual(self.fix("about actually transtorming the employee", book("the employee")),
                         "about actually transforming the employee")

    def test_name_from_the_book(self):
        b = book("Jeff " * 20)
        self.assertEqual(self.fix("and then turned to Jeft.", b), "and then turned to Jeff.")

    def test_capital_b_for_f(self):
        b = book("Finally, " * 5, "team. Finally")
        self.assertEqual(self.fix("for the good of the team. Binally, they", b), "for the good of the team. Finally, they")

    def test_possessive_keeps_its_s(self):
        b = book("at Maria's " * 3, "Maria's " * 2)
        self.assertEqual(self.fix("a busy day at Mana's.", b), "a busy day at Maria's.")

    def test_rare_real_word_changes_with_the_books_pairing(self):
        b = book("for your " * 12, "a few " * 12, "tor", "tew")
        self.assertEqual(self.fix("Jim Levine, tor your commitment", b), "Jim Levine, for your commitment")

    def test_misread_neighbors_fix_each_other(self):
        b = book("humble, hungry, and smart " * 12, "bumble bungry")
        self.assertEqual(self.fix("the words bumble, bungry, and smart", b), "the words humble, hungry, and smart")

    def test_scrap_cut_at_the_photos_edge_stays(self):
        # "bac" is the start of "back": swapping it to "bad" would hide the cut
        b = book("back to that " * 3, "bad " * 30, "bad to")
        self.assertEqual(self.fix("So we're bac to that.", b), "So we're bac to that.")

    def test_swap_to_a_word_the_book_never_uses_stays(self):
        # "relied" isn't in the 1934 dictionary; "relled" is a swap away and is
        self.assertEqual(self.fix("who had relied on", book("who had")), "who had relied on")

    def test_word_the_book_uses_often_stays(self):
        b = book("Okay " * 5, "Ohay")
        self.assertEqual(self.fix("Okay, fine.", b), "Okay, fine.")

    def test_short_name_part_stays(self):
        b = book("fill " * 5)
        self.assertEqual(self.fix("Chick-fil-A", b), "Chick-fil-A")

    def test_log_lists_each_change(self):
        log = []
        ocrfix.fix_misreads("will otten meet", is_word, book("often " * 3, "will often meet"), log)
        self.assertEqual(log, [("otten", "often")])


class TestDashes(unittest.TestCase):
    def fix(self, text, b=None):
        return ocrfix.fix_dashes(text, is_word, b or book())

    def test_prefixes_before_a_capital_stay_hyphens(self):
        b = book("January English Christmas " * 5)
        for text in ("in mid-January", "a non-English speaker", "the post-Christmas rush"):
            with self.subTest(text=text):
                self.assertEqual(self.fix(text, b), text)

    def test_suspended_hyphens_stay(self):
        for text in ("short- and long-term goals", "first- and second-graders", "help them self- soothe"):
            with self.subTest(text=text):
                self.assertEqual(self.fix(text), text)

    def test_hyphen_before_a_joining_word_is_a_dash(self):
        self.assertEqual(self.fix("the world of work-and for that matter"), "the world of work—and for that matter")

    def test_hyphen_with_a_space_after_a_word(self):
        self.assertEqual(self.fix("for that matter, life- I would"), "for that matter, life—I would")

    def test_chains_and_compounds_stay(self):
        for text in ("day-to-day", "pie-in-the-sky", "self-aware", "a go-to guy"):
            with self.subTest(text=text):
                self.assertEqual(self.fix(text), text)

    def test_hyphen_before_a_name_the_book_uses(self):
        b = book("Jeff " * 25)
        self.assertEqual(self.fix("make us think-Jeff interrupted", b), "make us think—Jeff interrupted")

    def test_hyphen_before_a_closing_quote(self):
        self.assertEqual(self.fix('"I need to ask-" Jeff'), '"I need to ask—" Jeff')

    def test_closing_quote_read_as_i_after_a_dash(self):
        # Vision read `ask—"` as "ask-i.": a speech app would say "i"
        self.assertEqual(self.fix('"I need to ask-i. Jeff interrupted'), '"I need to ask—" Jeff interrupted')
        self.assertEqual(self.fix('"and that he-i."'), '"and that he—"')

    def test_word_after_a_dash_that_starts_with_i_stays(self):
        self.assertEqual(self.fix("a mix-in. Then"), "a mix-in. Then")


if __name__ == "__main__":
    unittest.main()
