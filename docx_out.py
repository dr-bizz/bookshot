#!/usr/bin/env python3
"""Write cleaned book text as a .docx for Speechify.

Why .docx at all? Speechify's reader ignores almost everything you can put in
a document — SSML tags get read aloud as literal text, markdown likewise, and
headings, empty paragraphs and EPUB chapter boundaries are silently ignored.
Bold and italic runs in a Word document are the one thing it actually honors:
they come out audibly stressed. So this writer keeps the structure minimal and
spends its whole budget on emphasis.

A .docx is a zip of XML, so this needs nothing outside the stdlib.
"""
import json
import sys
import zipfile
from pathlib import Path

import textblocks

CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    "</Types>"
)

RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/>'
    "</Relationships>"
)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def resolve_emphasis(text: str, spans) -> list[tuple[int, int]]:
    """Turn emphasis substrings into document offsets.

    Same contract as review.py's fixes: a span is used only when it matches
    exactly once, so an ambiguous suggestion is dropped rather than guessed at.
    Overlapping spans keep whichever starts first.
    """
    found: list[tuple[int, int]] = []
    for span in spans:
        if not isinstance(span, str) or not span:
            continue
        if text.count(span) != 1:
            continue
        start = text.find(span)
        found.append((start, start + len(span)))

    found.sort()
    accepted: list[tuple[int, int]] = []
    last_end = -1
    for start, end in found:
        if start < last_end:
            continue
        accepted.append((start, end))
        last_end = end
    return accepted


def split_into_runs(segment: str, segment_start: int, spans) -> list[tuple[str, bool]]:
    """Split one line into (text, emphasized) runs.

    `spans` carry document-wide offsets, so `segment_start` says where this
    line begins in the document.
    """
    segment_end = segment_start + len(segment)
    runs: list[tuple[str, bool]] = []
    cursor = 0
    for start, end in spans:
        if end <= segment_start or start >= segment_end:
            continue
        rel_start = max(start, segment_start) - segment_start
        rel_end = min(end, segment_end) - segment_start
        if rel_start > cursor:
            runs.append((segment[cursor:rel_start], False))
        runs.append((segment[rel_start:rel_end], True))
        cursor = rel_end
    if cursor < len(segment):
        runs.append((segment[cursor:], False))
    return runs


def _run_xml(text: str, bold: bool, italic: bool) -> str:
    props = ""
    if bold or italic:
        props = "<w:rPr>" + ("<w:b/>" if bold else "") + ("<w:i/>" if italic else "") + "</w:rPr>"
    return f'<w:r>{props}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def build_document_xml(text: str, emphasis=()) -> str:
    spans = resolve_emphasis(text, emphasis)

    paragraphs: list[str] = []
    offset = 0
    for line in text.split("\n"):
        line_start = offset
        offset += len(line) + 1  # +1 for the newline that split() consumed

        stripped = line.strip()
        if not stripped:
            # Speechify ignores empty paragraphs entirely, so emitting them
            # would only bloat the file.
            continue

        segment_start = line_start + (len(line) - len(line.lstrip()))
        bold = textblocks.is_chapter_heading(stripped)
        runs = "".join(
            _run_xml(run_text, bold, italic)
            for run_text, italic in split_into_runs(stripped, segment_start, spans)
        )
        paragraphs.append(f"<w:p>{runs}</w:p>")

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<w:document xmlns:w="{W_NS}"><w:body>' + "".join(paragraphs) + "</w:body></w:document>"
    )


def write_docx(text: str, out_path, emphasis=()) -> Path:
    out_path = Path(out_path)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", RELS)
        z.writestr("word/document.xml", build_document_xml(text, emphasis))
    return out_path


def load_emphasis(sidecar: Path) -> list[str]:
    """Read the emphasis sidecar if it exists.

    A missing or unreadable sidecar is not fatal — the .docx is still worth
    producing without italics.
    """
    if not sidecar.exists():
        return []
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        sys.stderr.write(f"    ignoring unreadable emphasis sidecar ({exc})\n")
        return []
    if not isinstance(data, list):
        sys.stderr.write("    ignoring emphasis sidecar: not a JSON array\n")
        return []
    return [s for s in data if isinstance(s, str) and s]


def main() -> int:
    if len(sys.argv) not in (2, 3):
        sys.stderr.write("usage: docx_out.py <text-file> [output.docx]\n")
        return 2

    source = Path(sys.argv[1])
    if not source.is_file():
        sys.stderr.write(f"not a file: {source}\n")
        return 1

    out_path = Path(sys.argv[2]) if len(sys.argv) == 3 else source.with_suffix(".docx")
    text = source.read_text(encoding="utf-8")
    spans = load_emphasis(Path(str(source) + ".emphasis.json"))

    write_docx(text, out_path, spans)
    applied = len(resolve_emphasis(text, spans))
    print(f"wrote {out_path} ({applied} emphasized spans)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
