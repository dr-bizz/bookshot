#!/usr/bin/env python3
"""Clean raw Vision OCR output for Speechify playback.

Speechify treats every line break as a sentence boundary, so we reflow wrapped
lines into single-line paragraphs while keeping headings and bullet items on
their own lines.
"""
import re
import sys
from pathlib import Path

if len(sys.argv) != 3:
    sys.stderr.write("usage: clean.py <raw-input> <output>\n")
    sys.exit(2)

RAW = Path(sys.argv[1])
OUT = Path(sys.argv[2])

# ---------- pre-clean ----------
lines = RAW.read_text(encoding="utf-8").splitlines()

pre = []
for line in lines:
    s = line.rstrip()
    # drop image-delimiter so paragraphs flow across page boundaries
    if s.startswith("===== ") and s.endswith(" ====="):
        continue
    # drop blank lines — they're page-split artifacts from the OCR step;
    # real paragraph boundaries come from headings/bullets/allcaps detection
    if not s.strip():
        continue
    # bare page number
    if re.fullmatch(r"\s*\d{1,3}\s*", s):
        continue
    # roman-numeral front-matter page numbers
    if re.fullmatch(r"\s*[ivxlcIVXLC]{1,6}\s*", s):
        continue
    # normalize bullet glyphs to "- "
    s = re.sub(r"^\s*[•○◦●·]\s*", "- ", s)
    pre.append(s)

text = "\n".join(pre)
# rejoin hyphenated line breaks: "pebble-\nlike" → "pebble-like"
text = re.sub(r"(\w)-\n(\w)", r"\1-\2", text)
# collapse runs of blank lines
text = re.sub(r"\n{3,}", "\n\n", text)
processed = text.splitlines()

# ---------- helpers ----------
SENT_END = (".", "!", "?")
TRAIL_STRIP = " \t'\")]”’"

def is_blank(s: str) -> bool:
    return not s.strip()

def is_bullet(s: str) -> bool:
    return s.lstrip().startswith("- ")

def is_allcaps(s: str) -> bool:
    s = s.strip()
    letters = [c for c in s if c.isalpha()]
    return len(letters) >= 2 and all(c.isupper() for c in letters) and len(s) <= 60

def ends_sentence(s: str) -> bool:
    """Line ends a sentence (allowing trailing brackets/quotes after the punct,
    or a closing bracket whose paragraph contains an internal sentence end)."""
    stripped = s.rstrip(TRAIL_STRIP)
    if stripped and stripped[-1] in SENT_END:
        return True
    if s.rstrip() and s.rstrip()[-1] in ")]}\"'”’" and any(c in s for c in SENT_END):
        return True
    return False

def is_heading_shape(s: str) -> bool:
    """Line could be a section heading: short and contains no sentence punctuation."""
    s = s.strip()
    if not s or is_bullet(s) or is_allcaps(s):
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
output: list[str] = []
buffer: list[str] = []  # current paragraph being built
# `prev_was_terminator` is True at start of file and after any
# sentence-end / heading / bullet / blank / allcaps line — the
# point where a new heading or paragraph could legitimately begin.
prev_was_terminator = True

def flush_paragraph():
    if buffer:
        output.append(" ".join(buffer).strip())
        buffer.clear()

def emit_blank():
    if output and output[-1] != "":
        output.append("")

i = 0
while i < len(processed):
    s = processed[i]

    if is_blank(s):
        flush_paragraph()
        emit_blank()
        prev_was_terminator = True
        i += 1
        continue

    stripped = s.strip()

    # all-caps chapter heading
    if is_allcaps(stripped):
        flush_paragraph()
        emit_blank()
        output.append(stripped)
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
        output.append(" ".join(parts))
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
        output.append(" ".join(heading_parts))
        prev_was_terminator = True
        i = j
        continue

    # regular paragraph wrap line
    buffer.append(stripped)
    prev_was_terminator = ends_sentence(stripped)
    i += 1

flush_paragraph()

# ---------- final tidy ----------
final = "\n".join(output)
final = re.sub(r"\n{3,}", "\n\n", final).strip() + "\n"

OUT.write_text(final, encoding="utf-8")
print(f"wrote {OUT} ({len(final)} chars, {final.count(chr(10))} lines)")
