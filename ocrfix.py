#!/usr/bin/env python3
"""Fix words Apple Vision misreads, using the book itself as the judge.

Vision reads some letters as their look-alikes, steadily, on clean, dark
print: "tocus" for focus, "otten" for often, "T'm" for I'm, and in italic
type "bungry" for hungry. (Quote marks it misreads are quotemarks.py's job.)

Each fix here is narrow, and only changes a word that isn't one:

- "T'm", "TIl", "Ive", "1 think" become I'm, I'll, I've, I think (`fix_pronoun_i`),
- a word that isn't one becomes the single word one look-alike swap makes
  of it ("tocus" -> focus), and a rare word becomes a common one only when the
  book pairs the common one with the same neighbor ("tor your" -> for your)
  (`fix_misreads`),
- a hyphen standing for a dash ("work-and") becomes an em dash (`fix_dashes`).

`is_word` says whether a lowercase string is a dictionary word. The book's own
word counts stand in for names and words the dictionary lacks.
"""
import re
from collections import Counter
from typing import Callable

WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)*")


# ---------- I ----------

# Words that follow the word I where a clause starts ("I think", "And I
# did"). Before anything else a lone 1 is a number: "1 cup", "1 teaspoon".
_AFTER_I = {
    "am", "was", "have", "had", "think", "thought", "know", "knew", "mean",
    "meant", "guess", "did", "do", "don't", "didn't", "can", "can't", "could",
    "couldn't", "would", "wouldn't", "will", "won't", "should", "must", "may",
    "might", "want", "wanted", "need", "needed", "just", "really", "also",
    "never", "always", "still", "feel", "felt", "believe", "hope", "wish",
    "said", "remember", "agree", "understand", "wonder", "suppose", "bet",
    "love", "like", "hate", "see", "saw", "got", "went",
}
# where a clause starts: the start of a line, a quote, after a stop, or after
# a joining word ("And 1 did")
_CLAUSE_ONE = re.compile(
    r"(^|[\"“]|[.?!:;]\s|\b(?:[Aa]nd|[Bb]ut|[Ss]o|[Tt]hat|because|when|if|as)\s)1 ([a-z][a-z']*)\b",
    re.M)


def fix_pronoun_i(text: str, book: "Book | None" = None) -> str:
    """"T'm", "P'd", "TIl", "Ive", "Im" and "1 think" are I'm, I'd, I'll, I've, I'm, I think.

    A lone 1 becomes I only where a clause starts and before a word that
    follows I: one of _AFTER_I, or one the book puts after I at least twice.
    """
    text = re.sub(r"(?<![\w'])[TP1]'(m|d|ll|ve)\b", r"I'\1", text)
    text = re.sub(r"(?<![\w'])[TP1][Il1]l\b", "I'll", text)
    text = re.sub(r"(?<![\w'])Ive\b", "I've", text)
    text = re.sub(r"(?<![\w'])Im\b", "I'm", text)

    def one(m: re.Match) -> str:
        nxt = m.group(2)
        follows_i = nxt in _AFTER_I or bool(book and book.pairs[("i", nxt)] >= 2)
        return m.group(1) + ("I " if follows_i else "1 ") + nxt

    text = _CLAUSE_ONE.sub(one, text)
    # "optimistic, l think": a lone lowercase l where a clause starts (not a
    # unit, "2 l bottle", or a list mark, "(l)")
    return re.sub(r"(?:^|(?<=[\"“])|(?<=[,.?!;:] ))l (?=[a-z])", "I ", text, flags=re.M)


# ---------- short words ----------

# Words that can follow "if" but never "it" where a clause starts.
_AFTER_IF = r"(?:the|a|an|you|we|they|he|she|I|your|this|there)"


def fix_small_words(text: str) -> str:
    """Short misreads that make another word, fixed only where grammar
    leaves one reading.

    "It the employee is unwilling" is "If the": t read for f, as in "tocus".
    Only where a clause starts ("Call it the end" stays). "#I" is "#1", a
    contraction never ends in "'c" ("we'c" is "we'd"), and a "¿" before a
    contraction's ending is its apostrophe ("I¿ve").
    """
    text = re.sub(rf"(^|[.?!;:]\s+|,\s+|[\"“])([Ii])t (?={_AFTER_IF}\b)",
                  lambda m: m.group(1) + m.group(2) + "f ", text, flags=re.M)
    text = re.sub(r"#I\b", "#1", text)
    text = re.sub(r"(?<=[A-Za-z])¿(?=(?:ve|ll|re|m|d|s|t)\b)", "'", text)
    return re.sub(r"(?<=[A-Za-z])'c\b", "'d", text)


# ---------- letters ----------

# Look-alikes Vision confuses in this kind of type, one way only: (what it
# wrote, what was printed). Italic h reads as b or n; "fi" as n; a doubled
# letter as one. Measured on a real book: t written for f is by far the
# commonest, and the reverse ways (f for t, l for i) never happened, so they
# aren't here.
SWAPS = [
    ("t", "f"), ("ti", "ff"), ("i", "l"), ("rn", "m"), ("m", "rn"), ("v", "y"),
    ("b", "h"), ("n", "h"), ("a", "d"), ("c", "d"), ("u", "i"), ("n", "fi"),
    ("n", "ri"), ("t", "tt"), ("l", "ll"),
]
# A word only one swap away from a dictionary word the book never uses is
# usually a scrap cut off at the photo's edge ("hav", "proces"), or a real
# word the 1934 dictionary lacks ("relied", "paid"). A long one fixed by t->f
# is the exception: "transtorming", "gratitying".
LONG_T_FOR_F = 7


def _with_case(src: str, word: str) -> str:
    if src.isupper() and len(src) > 1:
        return word.upper()
    if src[:1].isupper():
        return word[:1].upper() + word[1:]
    return word


def _swaps(word: str) -> dict[str, tuple[str, str]]:
    """Every word one look-alike swap makes of `word` (lowercase), with the swap."""
    out = {}
    for wrote, printed in SWAPS:
        start = 0
        while (i := word.find(wrote, start)) >= 0:
            out.setdefault(word[:i] + printed + word[i + len(wrote):], (wrote, printed))
            start = i + 1
    out.pop(word, None)
    return out


class Book:
    """Word and word-pair counts of the whole book, lowercased, with "'s" off."""

    def __init__(self, text: str):
        found = [re.sub(r"'s$", "", t) for t in WORD.findall(text.replace("’", "'"))]
        tokens = [t.lower() for t in found]
        self.words = Counter(tokens)
        self.capitalized = Counter(t.lower() for t in found if t[:1].isupper())
        self.pairs = Counter(zip(tokens, tokens[1:]))
        # with the neighbor cut to four letters: "hard work" ~ "hard worker"
        self.before = Counter((a[:4], b) for a, b in zip(tokens, tokens[1:]) if len(a) >= 4)
        self.after = Counter((a, b[:4]) for a, b in zip(tokens, tokens[1:]) if len(b) >= 4)
        self._starts: dict[str, list[str]] = {}

    def pair_count(self, prev: str, word: str, nxt: str) -> tuple[int, int]:
        """How often the book has `word` after `prev`, and before `nxt`."""
        return (max(self.pairs[(prev, word)], self.before[(prev[:4], word)] if len(prev) >= 4 else 0),
                max(self.pairs[(word, nxt)], self.after[(word, nxt[:4])] if len(nxt) >= 4 else 0))

    def starts_word(self, scrap: str) -> list[str]:
        """Words the book uses twice or more that begin with `scrap` and go on."""
        if scrap not in self._starts:
            self._starts[scrap] = [w for w, n in self.words.items()
                                   if n >= 2 and len(w) > len(scrap) and w.startswith(scrap)]
        return self._starts[scrap]


def fix_misreads(text: str, is_word: Callable[[str], bool], book: Book,
                 log: list | None = None) -> str:
    """Replace a misread word with the word one look-alike swap makes of it.

    A word that isn't one (not in the dictionary, and used at most twice in
    the book) changes when exactly one swap gives a word the book uses
    elsewhere ("tocus" -> focus, "Jeft" -> Jeff), or, for a long word, a
    dictionary word by t->f ("transtorming"). A real but rare word ("tor",
    "bumble") changes only when the swap gives a word the book uses ten times
    as often and pairs with the same neighbor at least twice ("for your",
    "humble, hungry"), and the rare word's own pairing is a one-off.
    Possessives keep their 's ("Mana's" -> "Maria's").
    """

    def neighbors(s: str, start: int, end: int) -> tuple[str, str]:
        prev = (WORD.findall(s[max(0, start - 40):start]) or [""])[-1].lower()
        nxt = (WORD.findall(s[end:end + 40]) or [""])[0].lower()
        return re.sub(r"'s$", "", prev), re.sub(r"'s$", "", nxt)

    def choose(src: str, prev: str, nxt: str, whole: bool) -> str | None:
        w = src.lower()
        count = book.words[w]
        if count > 2:
            return None
        swaps = _swaps(w)
        if src[:1] == "B":
            swaps.setdefault("f" + w[1:], ("B", "F"))  # "Binally"
        # The start of a word the book uses ("bac" of back, "ana" of analysis)
        # is a scrap cut off at the photo's edge: only finishing it is safe.
        # Not when a stop or 's shows the word is whole ("Mana's").
        if not whole and book.starts_word(w):
            swaps = {c: r for c, r in swaps.items() if c.startswith(w)}
        if not is_word(w):
            cands = [
                c for c, rule in swaps.items()
                if book.words[c] >= 1 or (rule == ("t", "f") and len(c) >= LONG_T_FOR_F and is_word(c))
            ]
            if len(cands) > 1:
                cands = [c for c in cands if book.words[c]]
            if len(cands) != 1:
                return None
            c = cands[0]
            # a short word has to fit beside one of its neighbors somewhere in the book
            if len(c) <= 3 and not any(book.pair_count(prev, c, nxt)):
                return None
            return c
        # a real word, rare here: only with the book's own pairing as evidence
        cands = [
            c for c in swaps
            if book.words[c] >= max(10, 10 * count)
            and max(book.pair_count(prev, c, nxt)) >= 2
            and max(book.pair_count(prev, w, nxt)) <= 1
        ]
        if not cands and src[:1].isupper():
            # a name the book uses (always capitalized), in a spot where it
            # uses it ("at Mana's" -> "at Maria's")
            cands = [
                c for c in swaps
                if book.words[c] >= max(3, 3 * count) and book.capitalized[c] == book.words[c]
                and max(book.pair_count(prev, c, nxt)) >= 1
            ]
        return cands[0] if len(cands) == 1 else None

    def fix(m: re.Match) -> str:
        src = m.group(0)
        stem, poss = (src[:-2], src[-2:]) if src.endswith("'s") else (src, "")
        if len(stem) < 3 or stem.isupper() or "'" in stem:
            return src
        # part of a name like "Chick-fil-A"
        s = m.string
        if len(stem) <= 3 and (s[m.start() - 1:m.start()] == "-" or s[m.end():m.end() + 1] == "-"):
            return src
        prev, nxt = neighbors(m.string, m.start(), m.end())
        whole = bool(poss) or m.string[m.end():m.end() + 1] in tuple(".,;:!?\"”")
        new = choose(stem, prev, nxt, whole)
        if not new:
            return src
        out = _with_case(stem, new) + poss
        if log is not None:
            log.append((src, out))
        return out

    # twice, so a word whose neighbor was misread too sees it fixed ("bumble, bungry")
    return WORD.sub(fix, WORD.sub(fix, text))


# ---------- a capital read as "¿" ----------

def fix_lost_capitals(text: str, book: Book) -> str:
    """Vision reads the capital after an opening quote as "¿" ('"¿ou know')
    or puts one before it ('"¿Oh,'). The letter comes back when one makes a
    word the book often has before the next word ("You know", "We are"),
    clearly more than any other letter; else the text is left as read."""
    text = re.sub(r'(?<=["“])¿(?=[A-Z])', "", text)
    # "I'" as one mark: `"¿m fifty-fifty` for `"I'm fifty-fifty`
    text = re.sub(r"(?<![A-Za-z])¿(?=(?:m|ll|ve|d)\b)", "I'", text)

    def lost(m: re.Match) -> str:
        rest = m.group(1)
        after = re.match(r"\W+([A-Za-z']+)", m.string[m.end():])
        nxt = after.group(1).lower() if after else ""
        scored = sorted(
            ((book.pairs[(c + rest, nxt)], book.capitalized[c + rest], c)
             for c in "abcdefghijklmnopqrstuvwxyz" if book.words[c + rest] >= 2),
            reverse=True)
        if not scored or scored[0][0] < 2 or (len(scored) > 1 and scored[0][0] < 2 * scored[1][0]):
            return m.group(0)
        return scored[0][2].upper() + rest

    return re.sub(r"(?<=[\"“])¿([a-z']+)", lost, text)


# ---------- dashes ----------

# A hyphen before one of these, with no hyphen after it, is a dash:
# "the world of work-and for that matter", "a mix-a little".
_DASH_NEXT = {
    "the", "a", "an", "and", "or", "but", "not", "nor", "they", "he", "she",
    "it", "we", "you", "i", "to", "that", "which", "who", "so", "if", "as",
    "because", "even", "just", "especially", "then",
}
# compounds that end in one of them
_COMPOUNDS = {"go-to", "lean-to", "set-to", "so-so", "how-to"}
# A word that is only ever joined to the next by a hyphen, never by a dash:
# "mid-January", "non-English", "self- soothe".
_PREFIXES = {
    "mid", "non", "anti", "pre", "post", "un", "ex", "all", "pro", "semi",
    "sub", "trans", "self", "co", "re", "multi", "over", "under", "half",
    "well", "inter", "extra", "counter", "ultra",
}


def fix_dashes(text: str, is_word: Callable[[str], bool], book: Book) -> str:
    """An em dash Vision read as a hyphen, put back.

    "work-and for" -> "work—and for", "life- I would" -> "life—I would",
    "think-Jeff interrupted" -> "think—Jeff interrupted". A chain like
    "day-to-day" or "pie-in-the-sky" is a compound and stays.
    """
    def inner(m: re.Match) -> str:
        left, right = m.group(1), m.group(2)
        pair = f"{left}-{right}".lower()
        if pair in _COMPOUNDS or left.lower() in _PREFIXES:
            return m.group(0)
        if right.lower() in _DASH_NEXT and is_word(left.lower()) or (
            right[:1].isupper() and left[:1].islower() and book.words[right.lower()] >= 3
        ) or (
            # a name the book uses often: "Ted Montgomery-Jeff corrected her"
            right[:1].isupper() and book.words[right.lower()] >= 20 and not is_word(right.lower())
        ):
            return f"{left}—{right}"
        return m.group(0)

    # a speaker broken off with the closing quote read as "i.": "ask-i." is
    # 'ask—"' (no word ends "-i."). First, before "i" passes for the word I.
    text = re.sub(r'(?<=[A-Za-z])-i\.["”]?(?=\s|$)', '—"', text)
    text = re.sub(r"(?<![\w-])([A-Za-z]+)-([A-Za-z]+)(?![\w-])", inner, text)

    # "life- I would put": a hyphen with a space after it, after a whole word,
    # before a word a dash leads into. Not a hyphen left hanging for a
    # compound after it: "short- and long-term".
    def spaced(m: re.Match) -> str:
        left, nxt, after = m.group(1), m.group(2), m.group(3) or ""
        if len(left) < 3 or not is_word(left.lower()) or left.lower() in _PREFIXES:
            return m.group(0)
        if not (nxt[:1].isupper() or nxt.lower() in _DASH_NEXT):
            return m.group(0)
        if nxt.lower() in ("and", "or", "to") and "-" in after:
            return m.group(0)
        return f"{left}—{nxt}"

    text = re.sub(r"(?<![\w-])([A-Za-z]+)- ([A-Za-z']+)(?=(\s+\S+)?)", spaced, text)
    # a line broken off mid-word: 'I need to ask-" Jeff interrupted'
    return re.sub(r'(?<=[A-Za-z])-(?=["”])', "—", text)
