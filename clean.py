#!/usr/bin/env python3
"""Clean raw Vision OCR output for Speechify playback.

Reflows wrapped lines into single-line paragraphs, using the paragraph breaks
and headings layout.py read off the page photos, and keeps headings and bullet
items as blocks of their own. Every block is followed by a blank line:
Speechify merges lines separated by a single newline into one paragraph.

Also writes <output>.blocks.json, one kind per block ("h1", "h2", "p", "li"),
which rich_out.py uses to format the book.
"""
import json
import re
import sys
from pathlib import Path

import dropcap
import layout
import ocrfix
import quotemarks
import textblocks

if len(sys.argv) != 3:
    sys.stderr.write("usage: clean.py <raw-input> <output>\n")
    sys.exit(2)

RAW = Path(sys.argv[1])
OUT = Path(sys.argv[2])

ROMAN_RE = re.compile(
    r"\s*(?=[MDCLXVI])M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})\s*",
    re.IGNORECASE,
)

# ---------- hyphen rejoin ----------
DICT_PATH = Path("/usr/share/dict/words")
WORDS: set[str] = set()
if DICT_PATH.exists():
    WORDS = {w.strip().lower() for w in DICT_PATH.read_text().splitlines() if w.strip()}

# ~150 everyday joining words (after, when, there...), used to break ties
# between candidate words when the book itself can't
COMMON_PATH = Path("/usr/share/dict/connectives")
COMMON_WORDS: set[str] = set()
if COMMON_PATH.exists():
    COMMON_WORDS = {w.strip().lower() for w in COMMON_PATH.read_text().splitlines() if w.strip()}

HYPHEN_BREAK_RE = re.compile(r"(\w+)-\n(\w+)")
# common English inflections — macOS dict is base-form-only, so we try stripping
INFLECTIONS = ("s", "es", "ed", "d", "ing", "er", "est", "ly", "ies", "ied", "ier", "iest")


def looks_like_word(w: str, depth: int = 2) -> bool:
    """A dictionary word, or one with up to two endings on one ("rankings")."""
    if not WORDS:
        return False
    w = w.lower()
    if w in WORDS:
        return True
    if depth == 0:
        return False
    for suf in INFLECTIONS:
        if w.endswith(suf) and len(w) > len(suf):
            base = w[: -len(suf)]
            if looks_like_word(base, depth - 1):
                return True
            # -ies → -y (babies → baby)
            if suf in ("ies", "ied", "ier", "iest") and (base + "y") in WORDS:
                return True
            # consonant doubling (running → run, bigger → big)
            if suf in ("ed", "ing", "er", "est") and len(base) >= 2 and base[-1] == base[-2] and base[:-1] in WORDS:
                return True
            # silent e dropped (hiring → hire, overcoming → overcome)
            if suf in ("ed", "ing", "er", "est") and (base + "e") in WORDS:
                return True
    return False


# a line that ends without its hyphen: "dis\ncern", "mod\nerate"
LOST_HYPHEN_RE = re.compile(r"\b([A-Za-z]?[a-z]+)\n([a-z]{2,})\b")


def rejoin_hyphenated_breaks(text: str, book: "ocrfix.Book | None" = None) -> str:
    """Decide for each "<word>-\\n<word>" whether the hyphen was a wrap
    artifact ("peo-\\nple" → "people") or part of a real compound
    ("Personal-\\nBest" → "Personal-Best").

    With the book's word counts, a joined word the book uses elsewhere is
    one too ("Mau-\\nrine" → "Maurine"), and a line break whose hyphen OCR
    lost is closed up when one side is no word the book uses and the two
    make one ("dis\\ncern" → "discern", but not "some\\nthing").
    """
    used = (lambda w: book.words[w.lower()]) if book else (lambda w: 0)

    def replace(m: re.Match) -> str:
        left, right = m.group(1), m.group(2)
        # joined form is a real word → it was a wrap break
        if looks_like_word(left + right) or used(left + right) >= 2:
            return left + right
        # both halves are real words on their own → real hyphenated compound
        if looks_like_word(left) and looks_like_word(right):
            return f"{left}-{right}"
        # both halves capitalized → likely a proper-noun compound (e.g. "T-Mobile")
        if left[:1].isupper() and right[:1].isupper():
            return f"{left}-{right}"
        # default: assume wrap artifact (most common case)
        return left + right

    text = HYPHEN_BREAK_RE.sub(replace, text)
    if not book:
        return text

    def lost(m: re.Match) -> str:
        left, right = m.group(1), m.group(2)
        joined = left + right
        # a printer never breaks a word after its first letter, so "a" at a
        # line's end is the word a ("a\nround of golf")
        if len(left) < 2:
            return m.group(0)
        # the second half of a hyphenated word is never one on its own
        # ("ing", "cern", "erate"); a word on the next line after a scrap cut
        # at the photo's edge ("ret\nin") is.
        # the 1934 dictionary has "ing" and "cern": the book has to use it too
        right_is_word = right.lower() not in ("ing", "ings") and (
            used(right) >= 3 or (used(right) >= 2 and looks_like_word(right)))
        # and the two make a word the book uses, or a dictionary headword
        # ("moderate"), not one the suffix rules let by ("hi\nately")
        if len(joined) >= 5 and (used(joined) >= 1 or joined.lower() in WORDS) and not right_is_word:
            return joined
        return m.group(0)

    return LOST_HYPHEN_RE.sub(lost, text)

# ---------- helpers ----------
SENT_END = (".", "!", "?")
# closing quotes and brackets, and a footnote mark (*, or ® as Vision reads one)
TRAIL_STRIP = " \t'\")]”’*®"

def is_blank(s: str) -> bool:
    return not s.strip()

# shared with review.py and docx_out.py so every stage agrees on what counts
# as a chapter heading
is_bullet = textblocks.is_bullet
is_allcaps = textblocks.is_chapter_heading

def ends_sentence(s: str) -> bool:
    """Line ends a sentence (allowing trailing brackets/quotes after the punct,
    or a closing bracket whose paragraph contains an internal sentence end).
    A quote broken off with a dash (`I didn't expect-"`) ends one too."""
    stripped = s.rstrip(TRAIL_STRIP)
    if stripped and stripped[-1] in SENT_END:
        return True
    if re.search(r"[-—–][\"”]\s*$", s):
        return True
    # closing bracket/quote with internal sentence-ending punctuation
    if s.rstrip() and s.rstrip()[-1] in ")]}\"'”’" and any(c in s for c in SENT_END):
        return True
    return False

PAGE_NUMBER_RE = re.compile(r"\s*[•○◦●·\-–—]?\s*\d{1,3}\s*[•○◦●·\-–—]?\s*")

# A guessed heading (a short unpunctuated line of its own) is at most this long.
HEADING_GUESS_MAX_LEN = 35

# A sub-heading set in body-size italic or bold: a block of its own on the page
# that doesn't end a sentence ("Pay Attention to References Who Don't Respond").
SUBHEADING_MAX_LINES = 2
SUBHEADING_MAX_LEN = 80
# words this short ("and", "but", "of") are lowercase in a title
TITLE_WORD_MIN = 4
TITLE_CASE_SHARE = 0.75


def is_title_case(s: str) -> bool:
    """Most of the longer words capitalized, as in a heading."""
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z'’-]*", s) if len(w) >= TITLE_WORD_MIN]
    if not words:
        return False
    return sum(w[0].isupper() for w in words) >= TITLE_CASE_SHARE * len(words)


def reads_as_subheading(block: list[str]) -> bool:
    """Short, title case, no sentence punctuation."""
    text = " ".join(block).strip()
    if not text or len(block) > SUBHEADING_MAX_LINES or len(text) > SUBHEADING_MAX_LEN:
        return False
    if is_bullet(text) or text.startswith(('"', "'", "“", "‘")):
        return False
    if any(c in text for c in SENT_END) or text.endswith((",", ";", ":", "-")):
        return False
    return text[0].isupper() and is_title_case(text)


def is_subheading_block(block: list[str], following: str) -> bool:
    """The lines of one layout block read as a sub-heading for the paragraph
    after them, which starts a sentence and reads as prose. A block that runs
    into the next line mid-sentence ("the board of" / "directors hired")
    isn't title case and is followed by a lowercase word; the scattered
    labels of a diagram ("Humble Hungry" / "The" / "Ideal") are followed by
    more labels. A sentence starts with a capital and goes on in lowercase
    ("People who...", "When I..."); a title carried over a line break
    ("...our Baby Food" / "Introduction Calendar, a...") doesn't."""
    words = following.lstrip("\"'“‘").split()
    if not words or not words[0][:1].isupper():
        return False
    if len(words) > 1 and not (words[1][:1].islower() or words[1] in ("I", "I'm", "I've", "I'd", "I'll")):
        return False
    return reads_as_subheading(block) and not reads_as_subheading([following])


def continues_subheading(block: list[str], following: str) -> bool:
    """The next line is the rest of a sub-heading that wrapped
    ("... The Accidental" / "Mess-Maker"), not the paragraph under it."""
    return reads_as_subheading(block) and reads_as_subheading(block + [following])

# ---------- pre-clean ----------
# strips the bounding-box tags and marks paragraph breaks as blank lines
lines = layout.to_lines(RAW.read_text(encoding="utf-8"))
# quote marks and end punctuation Vision read as Vietnamese letters, so a
# closing quote ends its sentence and the paragraph break after it holds
lines = quotemarks.fix_lines(
    lines, looks_like_word,
    skip=lambda s: s.startswith("===== ") or layout.parse_heading(s) is not None)

pre = []
# A blank line in the raw OCR is a paragraph break that layout.py read off the
# page geometry. Held as pending until the next kept line, so a page number
# sitting between two paragraphs doesn't swallow the break.
pending_break = False
# set after a heading, which always stands alone
force_break = False
# number of the last numbered-list item seen, and lines read since it
LIST_ITEM_RE = re.compile(r"\s*(\d{1,2})[.)]\s")
# An item continues a list only this many lines after the item before it
# (an item wraps over a line or two; a heading or "My teammates would say:"
# may sit between); after that a number is a new list or just a number.
LIST_ITEM_GAP = 6
last_item = 0
lines_since_item = 0
# lines since the last paragraph break kept in `pre`, while they are all one
# block on the page (None once a break inside them was ignored)
block = []
for line in lines:
    s = line.rstrip()
    # drop image-delimiter so paragraphs flow across page boundaries
    if s.startswith("===== ") and s.endswith(" ====="):
        continue
    if not s.strip():
        pending_break = True
        continue
    # a heading by type size: set it off without the sentence-end check
    if layout.parse_heading(s):
        if pre and pre[-1] != "":
            pre.append("")
        pre.append(s)
        force_break = True
        pending_break = False
        block = []
        continue
    # bare page number, or one with the dot or dash a book sets beside it
    # ("• 150"), which would otherwise pass for a bullet and swallow the next
    # page's text. layout.py drops misread ones ("5l") off the page geometry.
    if PAGE_NUMBER_RE.fullmatch(s):
        continue
    # roman-numeral front-matter page numbers (strict pattern, must be a real
    # roman number — keeps words like "civil", "ill", "ivy" from being eaten)
    if ROMAN_RE.fullmatch(s):
        continue
    # normalize bullet glyphs to "- "
    s = re.sub(r"^\s*[•○◦●·]\s*", "- ", s)
    # The next item of a numbered list ("2. I easily admit...") starts a block
    # of its own even when the item before it doesn't end a sentence. A "1."
    # starts the count; it is set apart only where layout saw a break before
    # it after a finished sentence or a colon, since a number can also just
    # end a line ("the count came to / 1.").
    item = LIST_ITEM_RE.match(s)
    number = int(item.group(1)) if item else None
    lines_since_item += 1
    next_item = False
    if number == 1:
        next_item = pending_break and bool(pre) and (
            ends_sentence(pre[-1]) or pre[-1].rstrip().endswith(":"))
        last_item, lines_since_item = 1, 0
    elif number is not None and number == last_item + 1 and lines_since_item <= LIST_ITEM_GAP:
        next_item = True
        last_item, lines_since_item = number, 0
    # Only honor a break after a finished sentence. Layout guesses can be
    # wrong on noisy pages (running headers, bleed-through from the facing
    # page, hanging-indent bullets), and a break mid-sentence is worse than
    # a missed one. A sub-heading is the exception: it ends without a stop,
    # but it's a block of its own.
    honored = force_break or next_item or (pending_break and bool(pre) and ends_sentence(pre[-1]))
    if pending_break and not honored and block:
        if continues_subheading(block, s):
            pending_break = False
        elif is_subheading_block(block, s):
            honored = True
    if pre and honored:
        pre.append("")
        block = []
    elif pending_break and pre:
        block = None
    pending_break = force_break = False
    pre.append(s)
    if block is not None:
        block.append(s)

text = "\n".join(pre)
text = rejoin_hyphenated_breaks(text, ocrfix.Book(HYPHEN_BREAK_RE.sub(" ", text)))
# collapse runs of blank lines
text = re.sub(r"\n{3,}", "\n\n", text)
processed = text.splitlines()

def is_heading_shape(s: str, first: bool = True) -> bool:
    """Line could be a section heading: short and contains no sentence
    punctuation. `first` is false for a later line of a heading, which may
    go on in lowercase ("Sleep: 3-6 Months (including" / "dropping the
    swaddle)")."""
    s = s.strip()
    if not s or is_bullet(s) or is_allcaps(s):
        return False
    if s.startswith(('"', "'", "“", "‘")):
        return False
    # a heading doesn't start lowercase; a short lowercase line is the end of
    # a sentence broken off by something beside it on the page ("likely
    # responses of their" next to a pull quote)
    if first and s[0].islower():
        return False
    if len(s) > HEADING_GUESS_MAX_LEN:
        return False
    if any(ch in s for ch in ".!?"):
        return False
    if s.endswith((",", ";", ":", "-")):
        return False
    return True

def opens_chapter(heading: str, processed_lines, idx: int) -> bool:
    """A capitals title too short for the chapter-heading rule ("TED"),
    standing alone over a paragraph that starts lowercase: the paragraph's
    first letter was a drop cap OCR couldn't read, which only a chapter
    opening has. dropcap.py then puts the letter back."""
    letters = [c for c in heading if c.isalpha()]
    if len(letters) < 2 or not all(c.isupper() for c in letters):
        return False
    following = next((l.strip() for l in processed_lines[idx:] if l.strip()), "")
    return following[:1].islower()

def carries_on(s: str) -> bool:
    """Line picks up a sentence already under way: it starts with a real
    word in lowercase. A heading never runs into one, but text set in short
    lines (beside a pull quote, say) does. A chapter opening that lost its
    drop cap ("fter twenty years") starts lowercase too, but not with a word."""
    words = s.strip().split()
    if not words or not words[0][:1].islower():
        return False
    return looks_like_word(words[0].rstrip(",;:"))

def heading_run_leads_to_bullet(processed_lines, idx: int, max_lines: int = 3) -> bool:
    """Catches multi-line section headings whose first line is longer than the
    single-line heading cap but whose run still terminates at a bullet."""
    j = idx
    walked = 0
    while j < len(processed_lines) and walked < max_lines:
        nxt = processed_lines[j].strip()
        if not nxt:
            return False
        if is_bullet(nxt):
            return walked > 0
        if is_allcaps(nxt):
            return False
        if any(c in nxt for c in ".!?"):
            return False
        if nxt.endswith((",", ";", ":", "-")):
            return False
        if len(nxt) > 60:
            return False
        j += 1
        walked += 1
    return False

# ---------- reflow ----------
output: list[tuple[str, str]] = []  # (kind, text) per block
buffer: list[str] = []  # current paragraph being built
# `prev_was_terminator` is True at start of file and after any
# sentence-end / heading / bullet / blank / allcaps line — the
# point where a new heading or paragraph could legitimately begin.
prev_was_terminator = True

def flush_paragraph():
    if buffer:
        output.append(("p", " ".join(buffer).strip()))
        buffer.clear()

i = 0
while i < len(processed):
    s = processed[i]

    if is_blank(s):
        flush_paragraph()
        prev_was_terminator = True
        i += 1
        continue

    stripped = s.strip()

    # heading found by type size in the photo
    marked = layout.parse_heading(stripped)
    if marked:
        level, heading = marked
        flush_paragraph()
        output.append((f"h{level}", heading.strip()))
        prev_was_terminator = True
        i += 1
        continue

    # all-caps chapter heading
    if is_allcaps(stripped):
        flush_paragraph()
        output.append(("h2", stripped))
        prev_was_terminator = True
        i += 1
        continue

    # bullet — collect with continuation lines
    if is_bullet(stripped):
        flush_paragraph()
        parts = [stripped]
        j = i + 1
        while j < len(processed):
            nxt = processed[j].strip()
            if not nxt or is_bullet(nxt) or is_allcaps(nxt):
                break
            prev_terminated = ends_sentence(parts[-1])
            if prev_terminated and (is_heading_shape(nxt) or heading_run_leads_to_bullet(processed, j)):
                break
            parts.append(nxt)
            j += 1
        output.append(("li", " ".join(parts)))
        prev_was_terminator = ends_sentence(parts[-1])
        i = j
        continue

    # section heading (possibly multi-line)
    if prev_was_terminator and is_heading_shape(stripped):
        heading_parts = [stripped]
        j = i + 1
        while j < len(processed):
            nxt = processed[j].strip()
            if not nxt or is_bullet(nxt) or is_allcaps(nxt):
                break
            if not is_heading_shape(nxt, first=False):
                break
            heading_parts.append(nxt)
            j += 1
        # Short and unpunctuated, so its own block, but only a guess at a
        # heading: in photos these are as often stray scraps of text. Rich
        # text formats it as a plain paragraph. Unless the short lines run on
        # into the next line's sentence: then they were short lines of a
        # paragraph, narrowed beside a box. One short line counts only when
        # the line it runs into is short too: over a full line starting
        # lowercase, it's more often a title over a chapter opening whose
        # drop cap was lost ("TED" over "n Monday morning, Jeff was...").
        nxt = processed[j].strip() if j < len(processed) else ""
        narrowed = carries_on(nxt) and (
            len(heading_parts) >= 2 or len(nxt) <= HEADING_GUESS_MAX_LEN)
        if not narrowed:
            flush_paragraph()
            heading = " ".join(heading_parts)
            output.append(("h2" if opens_chapter(heading, processed, j) else "p", heading))
            prev_was_terminator = True
            i = j
            continue

    # regular paragraph wrap line
    buffer.append(stripped)
    prev_was_terminator = ends_sentence(stripped)
    i += 1

flush_paragraph()

# ---------- final tidy ----------
# Every block gets a blank line on both sides. Speechify merges lines split by
# a single newline into one paragraph, so a heading, bullet or paragraph with
# only one newline after it runs straight into whatever follows.
blocks = [(kind, text) for kind, text in output if text.strip()]
# chapter openings that came out as "fter" or "eff" (see dropcap.py)
restored = dropcap.restore_initials(blocks, looks_like_word, COMMON_WORDS.__contains__)
initials = dropcap.count_restored(blocks, restored)
blocks = restored
# "T'm" for I'm, "It the" for If the, misread letters ("tocus") and dashes
# read as hyphens ("work-and")
book = ocrfix.Book("\n".join(text for _, text in blocks))
fixed: list = []


def fix_words(text: str) -> str:
    text = ocrfix.fix_small_words(ocrfix.fix_pronoun_i(text, book))
    text = ocrfix.fix_lost_capitals(text, book)
    text = ocrfix.fix_misreads(text, looks_like_word, book, fixed)
    return ocrfix.fix_dashes(text, looks_like_word, book)


blocks = [(kind, fix_words(text)) for kind, text in blocks]
final = "\n\n".join(text for _, text in blocks) + "\n"

OUT.write_text(final, encoding="utf-8")
Path(str(OUT) + ".blocks.json").write_text(json.dumps([kind for kind, _ in blocks]), encoding="utf-8")
print(f"wrote {OUT} ({len(final)} chars, {final.count(chr(10))} lines, "
      f"{initials} drop-cap letters put back, {len(fixed)} misread words fixed)")
