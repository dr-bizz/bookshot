#!/usr/bin/env python3
"""Put back the first letter of a chapter that a drop cap took with it.

Many books open a chapter with a big decorative initial letter. OCR often
can't read it (in some books it's a faint gray letter printed behind the
text), so the chapter's first word comes out as "fter", "eff" or "n".

The letter is chosen from the book itself. Each letter A-Z is tried in front
of the fragment. Candidates have to be a real word, or a word (often a name)
the book uses elsewhere. The winner is the one whose next few words the book
uses most often ("on the way" vs "in the way"), then the one the book
capitalizes most ("When" vs "Then"), then the commoner word in the book, and
only then an everyday word over a rare dictionary one ("After" vs "Ofter").

Only a paragraph right after a heading that starts with a lowercase letter is
touched. Real prose never starts a paragraph lowercase, while one that
continues a sentence split by a misread is not right after a heading. A
toss-up is left alone: a word that's visibly broken is better than a wrong
one that reads fine.
"""
import re
from collections import Counter
from typing import Callable

WORD_RE = re.compile(r"[A-Za-z']+")
OPENING_RE = re.compile(r"^([\"'“‘]?)([a-z][A-Za-z']*)")
HEADING_KINDS = ("h1", "h2", "h3")


def restore_initials(
    blocks: list[tuple[str, str]],
    is_word: Callable[[str], bool],
    is_common: Callable[[str], bool] = lambda w: False,
) -> list[tuple[str, str]]:
    """Return blocks with chapter-opening fragments completed.

    `blocks` are (kind, text) pairs from clean.py; `is_word` says whether a
    lowercase string is a dictionary word, `is_common` whether it's an
    everyday one.
    """
    tokens = [t for _, text in blocks for t in WORD_RE.findall(text)]
    lower = [t.lower() for t in tokens]
    words = Counter(lower)
    capitalized = Counter(t.lower() for t in tokens if t[0].isupper())
    pairs = Counter(zip(lower, lower[1:]))
    triples = Counter(zip(lower, lower[1:], lower[2:]))

    out = list(blocks)
    for i in range(1, len(blocks)):
        kind, text = blocks[i]
        if kind != "p" or blocks[i - 1][0] not in HEADING_KINDS:
            continue
        m = OPENING_RE.match(text)
        if not m:
            continue
        quote, fragment = m.group(1), m.group(2).lower()
        following = [t.lower() for t in WORD_RE.findall(text[m.end():])[:2]]
        nxt = following[0] if following else None
        after = following[1] if len(following) > 1 else None

        scored = []
        for letter in "abcdefghijklmnopqrstuvwxyz":
            word = letter + fragment
            in_dictionary = is_word(word)
            if not in_dictionary and not words[word]:
                continue
            score = (
                triples[(word, nxt, after)],
                pairs[(word, nxt)],
                capitalized[word],
                words[word],
                is_common(word),
                in_dictionary,
            )
            scored.append((score, letter))
        if not scored:
            continue
        scored.sort(reverse=True)
        if len(scored) > 1 and scored[0][0] == scored[1][0]:
            continue  # nothing in the book to choose between them
        letter = scored[0][1]
        out[i] = (kind, quote + letter.upper() + text[len(quote):])
    return out


def count_restored(before, after) -> int:
    return sum(1 for a, b in zip(before, after) if a != b)
