#!/usr/bin/env python3
"""Write the cleaned book as rich text (HTML), and optionally as an Apple Note.

Speechify's editor keeps the formatting of rich text pasted into it, and
copying from Apple Notes is a path known to carry that formatting across. So
this writer turns the book into HTML with real headings, paragraphs and lists,
taken from what clean.py read off the page photos, and can hand it to Notes,
which syncs it to the phone.

Inputs, all next to the text file:
  <text>.blocks.json    one kind per block from clean.py ("h1", "h2", "p", "li")
  <text>.emphasis.json  words to stress from emphasis.py, set in italics

A missing or stale .blocks.json is not fatal: block kinds are then guessed
from the text the same way clean.py would.
"""
import argparse
import html
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import docx_out
import textblocks

# An empty line between blocks, matching the blank lines in the .txt that
# keep Speechify from running paragraphs together.
SEPARATOR = "<div><br></div>"

# Takes the HTML file as an argument rather than having its path spliced into
# the script, so no folder name can break the AppleScript.
NOTES_SCRIPT = [
    "on run argv",
    "set bodyHTML to read (POSIX file (item 1 of argv)) as «class utf8»",
    'tell application "Notes"',
    "set newNote to make new note at (default folder of default account) with properties {body:bodyHTML}",
    "return name of newNote",
    "end tell",
    "end run",
]


def guess_kind(block: str) -> str:
    if textblocks.is_chapter_heading(block):
        return "h2"
    if textblocks.is_bullet(block):
        return "li"
    return "p"


def _inline(segment: str, start: int, spans) -> str:
    return "".join(
        f"<i>{html.escape(text, quote=False)}</i>" if italic else html.escape(text, quote=False)
        for text, italic in docx_out.split_into_runs(segment, start, spans)
    )


def build_html(text: str, kinds=None, emphasis=(), title=None) -> str:
    """The book as an HTML fragment: the body of the note."""
    spans = docx_out.resolve_emphasis(text, emphasis)

    # each block is one line of the cleaned text; keep its offset so the
    # emphasis spans (document offsets) land on the right words
    blocks: list[tuple[str, int]] = []
    offset = 0
    for line in text.split("\n"):
        if line.strip():
            lead = len(line) - len(line.lstrip())
            blocks.append((line.strip(), offset + lead))
        offset += len(line) + 1

    if not kinds or len(kinds) != len(blocks):
        kinds = [guess_kind(block) for block, _ in blocks]

    items: list[str] = []
    if title:
        items.append(f"<h1>{html.escape(title, quote=False)}</h1>")
    bullets: list[str] = []

    def close_list():
        if bullets:
            items.append("<ul>" + "".join(bullets) + "</ul>")
            bullets.clear()

    for (block, start), kind in zip(blocks, kinds):
        if kind == "li":
            if textblocks.is_bullet(block):
                start += 2
                block = block[2:]
            bullets.append(f"<li>{_inline(block, start, spans)}</li>")
            continue
        close_list()
        inner = _inline(block, start, spans)
        if kind in ("h1", "h2", "h3"):
            items.append(f"<{kind}>{inner}</{kind}>")
        else:
            items.append(f"<div>{inner}</div>")
    close_list()
    return SEPARATOR.join(items)


def html_document(fragment: str, title: str) -> str:
    return (
        '<!doctype html>\n<html><head><meta charset="utf-8">'
        f"<title>{html.escape(title, quote=False)}</title></head>"
        f"<body>{fragment}</body></html>\n"
    )


def title_from(path: Path) -> str:
    """A readable book title: the file's name, or its folder's when the file
    has the default name."""
    name = path.parent.name if path.stem.lower() == "speechify" else path.stem
    return " ".join(name.replace("-", " ").replace("_", " ").split())


def notes_command(html_path: Path) -> list[str]:
    cmd = ["osascript"]
    for line in NOTES_SCRIPT:
        cmd += ["-e", line]
    return cmd + [str(html_path)]


def send_to_notes(fragment: str) -> str:
    """Create a new note holding the fragment; return the note's name."""
    with tempfile.NamedTemporaryFile("w", suffix=".html", encoding="utf-8", delete=False) as f:
        f.write(fragment)
        path = Path(f.name)
    try:
        result = subprocess.run(notes_command(path), capture_output=True, text=True)
    finally:
        path.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "osascript failed")
    return result.stdout.strip()


def load_kinds(sidecar: Path):
    if not sidecar.exists():
        return None
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        sys.stderr.write(f"    ignoring unreadable block kinds ({exc})\n")
        return None
    return data if isinstance(data, list) else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("text_file", type=Path)
    parser.add_argument("--notes", action="store_true", help="also create an Apple Note")
    parser.add_argument("--title", help="title at the top (default: from the file or folder name)")
    args = parser.parse_args()

    source: Path = args.text_file
    if not source.is_file():
        sys.stderr.write(f"not a file: {source}\n")
        return 1

    text = source.read_text(encoding="utf-8")
    kinds = load_kinds(Path(str(source) + ".blocks.json"))
    emphasis = docx_out.load_emphasis(Path(str(source) + ".emphasis.json"))
    title = args.title or title_from(source)

    fragment = build_html(text, kinds, emphasis, title)
    out_path = source.with_suffix(".html")
    out_path.write_text(html_document(fragment, title), encoding="utf-8")
    print(f"wrote {out_path}")

    if args.notes:
        try:
            name = send_to_notes(fragment)
        except RuntimeError as exc:
            sys.stderr.write(
                f"    couldn't create the note: {exc}\n"
                "    If macOS asked to let this app control Notes, allow it in\n"
                "    System Settings > Privacy & Security > Automation, then re-run.\n"
            )
            return 1
        print(f'created Apple Note "{name}"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
