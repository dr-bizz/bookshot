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
INFLECTIONS = ("s", "es", "ed", "d", "ing", "er", "est", "ly", "ies", "ier", "iest")


def looks_like_word(w: str) -> bool:
    if not WORDS:
        return False
    w = w.lower()
    if w in WORDS:
        return True
    for suf in INFLECTIONS:
        if w.endswith(suf) and len(w) > len(suf):
            base = w[: -len(suf)]
            if base in WORDS:
                return True
            # -ies → -y (babies → baby)
            if suf in ("ies", "ier", "iest") and (base + "y") in WORDS:
                return True
            # consonant doubling (running → run, bigger → big)
            if suf in ("ed", "ing", "er", "est") and len(base) >= 2 and base[-1] == base[-2] and base[:-1] in WORDS:
                return True
    return False


def rejoin_hyphenated_breaks(text: str) -> str:
    """Decide for each "<word>-\\n<word>" whether the hyphen was a wrap
    artifact ("peo-\\nple" → "people") or part of a real compound
    ("Personal-\\nBest" → "Personal-Best")."""

    def replace(m: re.Match) -> str:
        left, right = m.group(1), m.group(2)
        # joined form is a real word → it was a wrap break
        if looks_like_word(left + right):
            return left + right
        # both halves are real words on their own → real hyphenated compound
        if looks_like_word(left) and looks_like_word(right):
            return f"{left}-{right}"
        # both halves capitalized → likely a proper-noun compound (e.g. "T-Mobile")
        if left[:1].isupper() and right[:1].isupper():
            return f"{left}-{right}"
        # default: assume wrap artifact (most common case)
        return left + right

    return HYPHEN_BREAK_RE.sub(replace, text)

# ---------- helpers ----------
SENT_END = (".", "!", "?")
TRAIL_STRIP = " \t'\")]”’"

def is_blank(s: str) -> bool:
    return not s.strip()

# shared with review.py and docx_out.py so every stage agrees on what counts
# as a chapter heading
is_bullet = textblocks.is_bullet
is_allcaps = textblocks.is_chapter_heading

def ends_sentence(s: str) -> bool:
    """Line ends a sentence (allowing trailing brackets/quotes after the punct,
    or a closing bracket whose paragraph contains an internal sentence end)."""
    stripped = s.rstrip(TRAIL_STRIP)
    if stripped and stripped[-1] in SENT_END:
        return True
    # closing bracket/quote with internal sentence-ending punctuation
    if s.rstrip() and s.rstrip()[-1] in ")]}\"'”’" and any(c in s for c in SENT_END):
        return True
    return False

# ---------- pre-clean ----------
# strips the bounding-box tags and marks paragraph breaks as blank lines
lines = layout.to_lines(RAW.read_text(encoding="utf-8"))

pre = []
# A blank line in the raw OCR is a paragraph break that layout.py read off the
# page geometry. Held as pending until the next kept line, so a page number
# sitting between two paragraphs doesn't swallow the break.
pending_break = False
# set after a heading, which always stands alone
force_break = False
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
        continue
    # bare page number
    if re.fullmatch(r"\s*\d{1,3}\s*", s):
        continue
    # roman-numeral front-matter page numbers (strict pattern, must be a real
    # roman number — keeps words like "civil", "ill", "ivy" from being eaten)
    if ROMAN_RE.fullmatch(s):
        continue
    # normalize bullet glyphs to "- "
    s = re.sub(r"^\s*[•○◦●·]\s*", "- ", s)
    # Only honor a break after a finished sentence. Layout guesses can be
    # wrong on noisy pages (running headers, bleed-through from the facing
    # page, hanging-indent bullets), and a break mid-sentence is worse than
    # a missed one.
    if pre and (force_break or (pending_break and ends_sentence(pre[-1]))):
        pre.append("")
    pending_break = force_break = False
    pre.append(s)

text = "\n".join(pre)
text = rejoin_hyphenated_breaks(text)
# collapse runs of blank lines
text = re.sub(r"\n{3,}", "\n\n", text)
processed = text.splitlines()

def is_heading_shape(s: str) -> bool:
    """Line could be a section heading: short and contains no sentence punctuation."""
    s = s.strip()
    if not s or is_bullet(s) or is_allcaps(s):
        return False
    if s.startswith(('"', "'", "“", "‘")):
        return False
    if len(s) > 35:
        return False
    if any(ch in s for ch in ".!?"):
        return False
    if s.endswith((",", ";", ":", "-")):
        return False
    return True

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
        flush_paragraph()
        heading_parts = [stripped]
        j = i + 1
        while j < len(processed):
            nxt = processed[j].strip()
            if not nxt or is_bullet(nxt) or is_allcaps(nxt):
                break
            if not is_heading_shape(nxt):
                break
            heading_parts.append(nxt)
            j += 1
        # Short and unpunctuated, so its own block, but only a guess at a
        # heading: in photos these are as often stray scraps of text. Rich
        # text formats it as a plain paragraph.
        output.append(("p", " ".join(heading_parts)))
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
final = "\n\n".join(text for _, text in blocks) + "\n"

OUT.write_text(final, encoding="utf-8")
Path(str(OUT) + ".blocks.json").write_text(json.dumps([kind for kind, _ in blocks]), encoding="utf-8")
print(f"wrote {OUT} ({len(final)} chars, {final.count(chr(10))} lines, "
      f"{initials} drop-cap letters put back)")
