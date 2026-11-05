#!/usr/bin/env python3
"""Read a book page's structure off where each piece of OCR'd text sits.

Plain OCR text loses the page's structure: every wrapped line looks the same.
The photo still shows it:

- the first line of a paragraph is indented,
- the last line of a paragraph stops short of the right margin,
- headings and section breaks leave a taller gap above the next line,
- headings are set in bigger type,
- the running header (book or chapter title at the top of most pages) is set
  in smaller type and repeats,
- scraps of the facing page caught in the photo sit outside the block of text.

ocr.swift writes one line per recognized piece of text, measured on the
straightened page, as fractions of the page image (x left to right, y top to
bottom), with the type size last:

    [x0 x1 top bottom size] text

The size may be missing (older raw files); the box height stands in for it.
Untagged lines (error notes, "===== name =====" page delimiters) pass through
unchanged. Every delimiter starts a new page, and everything is measured per
page, because each half of a two-page spread is cropped differently.

to_lines() returns plain text lines with "" at each paragraph break and
headings wrapped by heading_line(). clean.py then decides which breaks to
trust.
"""
import re
from collections import Counter
from statistics import median
from typing import NamedTuple, Optional

import textblocks

NUM = r"(-?\d+\.\d+)"
PIECE_RE = re.compile(rf"^\[{NUM} {NUM} {NUM} {NUM}(?: {NUM})?\] ?(.*)$")

# Margins are judged against nearby lines rather than the whole page, after
# taking out the page's overall slant (see _slant), so a handheld photo where
# each line starts a little further over than the last doesn't hide indents or
# fake them. The window covers what's left: page curl near the spine.
WINDOW = 5
# A paragraph indent is usually 5-8% of the text width.
INDENT_MIN = 0.03
# Justified lines end within about 1% of the right margin. The gap is generous
# so a ragged-right book doesn't break on every short line.
SHORT_MIN = 0.12
# A heading or section break leaves well over one extra line of space.
GAP_FACTOR = 1.7
MIN_ROWS = 3

# Type size, as a multiple of the page's body text. Measured on a real book:
# body lines run 0.85-1.3 (lines nearer the camera come out bigger), chapter
# titles 1.33-1.55, part titles 2-2.9, running headers 0.46-0.80.
HEADING_RATIO = 1.3
TITLE_RATIO = 1.8
HEADER_RATIO = 0.85
# A heading is short. This keeps a body line that's big only because it was
# near the camera from passing as one.
HEADING_MAX_WIDTH = 0.6
# A piece this far outside the block of text is a scrap of the facing page.
STRAY_MARGIN = 0.02
# Body lines span at least this much of the page image (about 0.55-0.65 on
# the half-spreads measured); gutter scraps under 0.05.
MIN_BODY_WIDTH = 0.2
# Within this of the photo's side edge, a piece narrower than EDGE_SCRAP_WIDTH
# is a sliver of the facing page.
EDGE = 0.01
EDGE_SCRAP_WIDTH = 0.08
# A single letter this many times the page's typical type size is a drop cap.
DROP_CAP_RATIO = 1.8

# A private-use character: OCR never produces one, and unlike the ASCII control
# characters Python doesn't treat it as whitespace or a line break, so it
# survives strip() and splitlines() in clean.py.
HEADING_MARK = "\ue000"


class Piece(NamedTuple):
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    size: float


class Row(NamedTuple):
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    size: float = 0.0


def heading_line(text: str, level: int) -> str:
    """Mark a line as a heading (1 = biggest) for clean.py."""
    return f"{HEADING_MARK}{level}{text}"


def parse_heading(line: str) -> Optional[tuple[int, str]]:
    """(level, text) for a line made by heading_line(), else None."""
    if len(line) >= 2 and line[0] == HEADING_MARK and line[1].isdigit():
        return int(line[1]), line[2:]
    return None


# ---------- one page ----------

def _text_block(items) -> Optional[tuple[float, float]]:
    """Left and right edge of the page's main block of text, from its wide
    lines. None when the page has too few to tell (a title page)."""
    widths = sorted(i.x1 - i.x0 for i in items)
    if not widths:
        return None
    reference = widths[int(0.8 * (len(widths) - 1))]
    # Wide relative to the page's other lines, and wide on the page itself:
    # on a title page made mostly of gutter scraps, the scraps are the widest
    # "lines" there are, and mustn't be taken for the text.
    floor = max(0.7 * reference, MIN_BODY_WIDTH)
    wide = [i for i in items if i.x1 - i.x0 >= floor]
    if len(wide) < MIN_ROWS:
        return None
    return median(i.x0 for i in wide), median(i.x1 for i in wide)


def attach_drop_caps(pieces: list[Piece]) -> list[Piece]:
    """Join a big decorative initial to the first line beside it.

    Left alone, a drop cap three lines tall gets grouped with whichever line
    its middle lines up with ("A his fair share") or stands as a one-letter
    heading. The line keeps its own box: the initial often hangs in the
    margin, and widening the line to include it would make it look
    out-dented, and the lines around it indented.
    """
    if not pieces:
        return pieces
    typical = median(p.size for p in pieces)
    caps = [p for p in pieces
            if len(p.text.strip()) == 1 and p.text.strip().isalpha()
            and p.size >= DROP_CAP_RATIO * typical]
    if not caps:
        return pieces
    out = [p for p in pieces if p not in caps]
    for cap in caps:
        beside = [
            (p.top, p.x0, i) for i, p in enumerate(out)
            if p.top < cap.bottom and p.bottom > cap.top and p.x0 >= (cap.x0 + cap.x1) / 2
        ]
        if not beside:
            out.append(cap)
            continue
        i = min(beside)[2]
        out[i] = out[i]._replace(text=cap.text.strip() + out[i].text)
    return out


def _edge_scrap(p: Piece) -> bool:
    """A sliver touching the photo's side edge: where a spread is split down
    the spine, that's the facing page peeking in."""
    touches = p.x0 <= EDGE or p.x1 >= 1 - EDGE
    return touches and p.x1 - p.x0 < EDGE_SCRAP_WIDTH


def drop_strays(pieces: list[Piece]) -> list[Piece]:
    """Drop scraps of the facing page: slivers at the photo's edge, and
    pieces lying wholly outside the block of text."""
    pieces = [p for p in pieces if not _edge_scrap(p)]
    block = _text_block(pieces)
    if block is None:
        return pieces
    left, right = block
    margin = STRAY_MARGIN * (right - left)
    return [p for p in pieces if p.x1 >= left - margin and p.x0 <= right + margin]


def group_rows(pieces: list[Piece]) -> list[Row]:
    """Join pieces sharing a line into rows, top to bottom, left to right."""
    lines: list[list[Piece]] = []
    for p in sorted(pieces, key=lambda p: (p.top + p.bottom) / 2):
        center = (p.top + p.bottom) / 2
        if lines:
            first = lines[-1][0]
            tolerance = 0.5 * max(p.size, max(q.size for q in lines[-1]))
            if abs(center - (first.top + first.bottom) / 2) <= tolerance:
                lines[-1].append(p)
                continue
        lines.append([p])

    rows = []
    for line in lines:
        line.sort(key=lambda p: p.x0)
        # type size comes from the widest piece, so a scrap sharing the line
        # doesn't decide it
        main = max(line, key=lambda p: p.x1 - p.x0)
        rows.append(Row(
            " ".join(p.text for p in line),
            min(p.x0 for p in line), max(p.x1 for p in line),
            min(p.top for p in line), max(p.bottom for p in line),
            main.size,
        ))
    return rows


def _slant(ys: list[float], xs: list[float]) -> float:
    """How far x moves per unit of y down the page.

    Siegel's repeated median: for each line, the median slope to every other
    line, then the median of those. Indents, headings and stray fragments from
    the facing page barely move it, even on a short page where they are close
    to half the lines.
    """
    per_line = []
    for j in range(len(ys)):
        slopes = [
            (xs[k] - xs[j]) / (ys[k] - ys[j])
            for k in range(len(ys))
            if k != j and abs(ys[k] - ys[j]) > 1e-6
        ]
        if slopes:
            per_line.append(median(slopes))
    return median(per_line) if per_line else 0.0


def _breaks(rows: list[Row]) -> tuple[bool, list[bool], bool]:
    """Return (break before the page, break before each row, break after the page)."""
    n = len(rows)
    before = [False] * n
    if n < MIN_ROWS:
        return False, before, False

    # Straighten the page: where each line would start and end if the photo
    # had been taken square-on.
    tops = [r.top for r in rows]
    left_slant = _slant(tops, [r.x0 for r in rows])
    right_slant = _slant(tops, [r.x1 for r in rows])
    lefts = [r.x0 - left_slant * r.top for r in rows]
    rights = [r.x1 - right_slant * r.top for r in rows]
    width = median(r.x1 for r in rows) - median(r.x0 for r in rows)
    if width <= 0:
        return False, before, False

    def window(values, i):
        return values[max(0, i - WINDOW): i + WINDOW + 1]

    def indented(i):
        return lefts[i] - median(window(lefts, i)) > INDENT_MIN * width

    def short(i):
        return median(window(rights, i)) - rights[i] > SHORT_MIN * width

    pitch = median(rows[i].top - rows[i - 1].top for i in range(1, n))

    for i in range(1, n):
        gap = pitch > 0 and rows[i].top - rows[i - 1].top > GAP_FACTOR * pitch
        before[i] = indented(i) or short(i - 1) or gap

    return indented(0), before, short(n - 1)


def paragraph_lines(rows: list[Row], levels: Optional[dict[int, int]] = None) -> list[str]:
    """One page of rows as text lines, with "" wherever a paragraph breaks.

    `levels` maps row index to heading level; heading rows always stand alone.
    """
    levels = levels or {}
    lead, before, trail = _breaks(rows)
    out = [""] if lead else []
    for i, (row, brk) in enumerate(zip(rows, before)):
        if brk or i in levels or (i - 1) in levels:
            if not out or out[-1] != "":
                out.append("")
        out.append(heading_line(row.text, levels[i]) if i in levels else row.text)
    if trail or (len(rows) - 1) in levels:
        out.append("")
    return out


# ---------- the whole book ----------

def _wide_rows(rows: list[Row]) -> list[Row]:
    block = _text_block(rows)
    if block is None:
        return []
    return [r for r in rows if r.x1 - r.x0 >= 0.5 * (block[1] - block[0])]


def _key(text: str) -> str:
    """Compare titles ignoring case, spacing and punctuation."""
    return "".join(c for c in text.lower() if c.isalpha())


def _heading_levels(rows: list[Row], body_size: Optional[float]) -> dict[int, int]:
    if not body_size:
        return {}
    block = _text_block(rows)
    levels = {}
    for i, r in enumerate(rows):
        ratio = r.size / body_size
        if ratio < HEADING_RATIO or not _key(r.text):
            continue
        if block and r.x1 - r.x0 > HEADING_MAX_WIDTH * (block[1] - block[0]):
            continue
        levels[i] = 1 if ratio >= TITLE_RATIO else 2
    return levels


def _header_candidate(rows: list[Row], body_size: Optional[float]) -> Optional[str]:
    """Key of the page's first line if it looks like a running header."""
    if not rows or not body_size:
        return None
    first = rows[0]
    if first.size / body_size >= HEADER_RATIO:
        return None
    if any(c in first.text for c in ".!?") or textblocks.is_bullet(first.text):
        return None
    return _key(first.text) or None


def to_lines(raw: str) -> list[str]:
    """Turn raw OCR output into plain lines with paragraph breaks and
    headings marked, and running headers and stray scraps removed."""
    segments: list = []  # a page (list of Pieces) or a line passed through
    for line in raw.splitlines():
        m = PIECE_RE.match(line)
        if m:
            x0, x1, top, bottom, size, text = m.groups()
            top, bottom = float(top), float(bottom)
            piece = Piece(text, float(x0), float(x1), top, bottom,
                          float(size) if size else bottom - top)
            if segments and isinstance(segments[-1], list):
                segments[-1].append(piece)
            else:
                segments.append([piece])
        else:
            segments.append(line)

    pages = {
        i: group_rows(drop_strays(attach_drop_caps(s)))
        for i, s in enumerate(segments) if isinstance(s, list)
    }

    # Body type size per page, falling back to the whole book's on a page
    # with too little body text to measure (a title page).
    wide = {i: _wide_rows(rows) for i, rows in pages.items()}
    book_sizes = [r.size for rows in wide.values() for r in rows]
    book_size = median(book_sizes) if book_sizes else None
    body_size = {
        i: median(r.size for r in wide[i]) if len(wide[i]) >= MIN_ROWS else book_size
        for i in pages
    }

    levels = {i: _heading_levels(rows, body_size[i]) for i, rows in pages.items()}
    heading_keys = {_key(pages[i][r].text) for i in pages for r in levels[i]}

    # A small first line is a running header when the same words top more
    # than one page, or they name a chapter. A one-off small line, like
    # "PART ONE" above a part title, stays.
    candidates = {i: _header_candidate(rows, body_size[i]) for i, rows in pages.items()}
    seen = Counter(k for k in candidates.values() if k)
    for i, key in candidates.items():
        if key and (seen[key] >= 2 or key in heading_keys):
            pages[i] = pages[i][1:]
            levels[i] = {r - 1: lvl for r, lvl in levels[i].items() if r > 0}

    out: list[str] = []
    for i, seg in enumerate(segments):
        if isinstance(seg, list):
            out.extend(paragraph_lines(pages[i], levels[i]))
        else:
            out.append(seg)
    return out
