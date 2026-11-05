#!/usr/bin/env python3
"""Line classifiers shared by clean.py, review.py and docx_out.py.

These rules decide what a line of cleaned OCR text *is*, and several stages of
the pipeline need the same answer — the chapter-heading rule in particular
drives paragraph breaks in clean.py, chunk splitting in review.py and run
styling in docx_out.py.
"""

CHAPTER_MAX_LEN = 60
CHAPTER_MIN_LETTERS = 4
_OPENING_MARKS = ('"', "'", "“", "‘", "—", "–", "-")


def is_chapter_heading(s: str) -> bool:
    """An ALL-CAPS line short enough to be a chapter title.

    Requires at least CHAPTER_MIN_LETTERS letters so two-letter acronyms and
    initials don't qualify, and caps the length so shouted dialogue doesn't.
    """
    s = s.strip()
    if not s or s.startswith(_OPENING_MARKS):
        return False
    letters = [c for c in s if c.isalpha()]
    return (
        len(letters) >= CHAPTER_MIN_LETTERS
        and all(c.isupper() for c in letters)
        and len(s) <= CHAPTER_MAX_LEN
    )


def is_bullet(s: str) -> bool:
    """A normalized bullet item (clean.py rewrites all bullet glyphs to "- ")."""
    return s.lstrip().startswith("- ")


CHUNK_TARGET_CHARS = 8000  # rough size budget per Claude call


def split_into_chunks(text: str, budget: int = CHUNK_TARGET_CHARS) -> list[str]:
    """Split text on chapter headings, then group small chapters back together
    so each chunk is roughly `budget` characters.

    Joining the result with newlines reproduces the input exactly — no text is
    dropped, so a chunked pass can't silently lose a paragraph.
    """
    chapters: list[list[str]] = []
    current: list[str] = []
    for line in text.splitlines():
        if is_chapter_heading(line) and current:
            chapters.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        chapters.append(current)

    chunks: list[str] = []
    buffer: list[str] = []
    buffer_size = 0
    for chapter in chapters:
        chapter_text = "\n".join(chapter)
        if buffer and buffer_size + len(chapter_text) > budget:
            chunks.append("\n".join(buffer))
            buffer = []
            buffer_size = 0
        buffer.append(chapter_text)
        buffer_size += len(chapter_text) + 1
    if buffer:
        chunks.append("\n".join(buffer))
    return chunks
