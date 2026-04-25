#!/usr/bin/env python3
"""Clean raw Vision OCR output for Speechify playback."""
import re
import sys
from pathlib import Path

if len(sys.argv) != 3:
    sys.stderr.write("usage: clean.py <raw-input> <output>\n")
    sys.exit(2)

RAW = Path(sys.argv[1])
OUT = Path(sys.argv[2])

lines = RAW.read_text(encoding="utf-8").splitlines()

cleaned = []
for line in lines:
    s = line.rstrip()
    # image-delimiter from the OCR step: turn into a paragraph break
    if s.startswith("===== ") and s.endswith(" ====="):
        cleaned.append("")
        continue
    # bare page number
    if re.fullmatch(r"\s*\d{1,3}\s*", s):
        continue
    # roman-numeral front-matter page number
    if re.fullmatch(r"\s*[ivxlcIVXLC]{1,6}\s*", s):
        continue
    # normalize bullet glyphs to "- "
    s = re.sub(r"^\s*[•○◦●·]\s*", "- ", s)
    cleaned.append(s)

text = "\n".join(cleaned)
# rejoin hyphenated line breaks: "pebble-\nlike" → "pebble-like"
text = re.sub(r"(\w)-\n(\w)", r"\1-\2", text)
# collapse runs of blank lines
text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"

OUT.write_text(text, encoding="utf-8")
print(f"wrote {OUT} ({len(text)} chars, {text.count(chr(10))} lines)")
