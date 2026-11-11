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
- print from the other side of the sheet showing through is faint.
- a pull quote is a box beside the text repeating a sentence from the page,
- a diagram's labels are a few words each, scattered rather than set in lines,
- the page number sits alone below (or above) the text.

ocr.swift writes one line per recognized piece of text, measured on the
straightened page, as fractions of the page image (x left to right, y top to
bottom), then the type size and how dark the ink is against the paper (0-1):

    [x0 x1 top bottom size ink] text

Size and ink may be missing (older raw files): the box height stands in for
the size, and the piece is taken to be dark.
Untagged lines (error notes, "===== name =====" page delimiters) pass through
unchanged. Every delimiter starts a new page, and everything is measured per
page, because each half of a two-page spread is cropped differently.

to_lines() returns plain text lines with "" at each paragraph break and
headings wrapped by heading_line(). clean.py then decides which breaks to
trust.
"""
import re
from collections import Counter
from difflib import SequenceMatcher
from statistics import median
from typing import NamedTuple, Optional

import textblocks

NUM = r"(-?\d+\.\d+)"
PIECE_RE = re.compile(rf"^\[{NUM} {NUM} {NUM} {NUM}(?: {NUM})?(?: {NUM})?\] ?(.*)$")

# Margins are judged against nearby lines rather than the whole page, after
# taking out the page's overall slant (see _slant), so a handheld photo where
# each line starts a little further over than the last doesn't hide indents or
# fake them. The window covers what's left: page curl near the spine.
WINDOW = 5
# A paragraph indent is usually 5-8% of the text width.
INDENT_MIN = 0.03
# Where among the nearby left edges the margin is: the lower quarter, so it
# holds even when most nearby lines are indented.
MARGIN_QUANTILE = 0.25
# A line starting with a bullet sign (Vision reads a hollow one as "o"), and
# how far right of the sign the text wrapped under it hangs, of the text width.
BULLET_START = re.compile(r"\s*(?:[•○◦●·▪■*\-–]|o(?=\s))\s")
HANG_MAX = 0.1
# Pieces whose middles are this close, as a fraction of the type size, are
# level: on one line even if their boxes overlap a little.
LEVEL = 0.25
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
# A line in capitals measures small for its type: its box has no descenders,
# while a body line's box runs from ascender to descender. Measured on a real
# book: five chapter titles in capitals ("BOB", "TED AGAIN") came out
# 1.23-1.29, and no body line was in capitals. Body text isn't set in
# capitals, so a capitals line this big is a heading however wide it is, up
# to the length of a chapter title (longer is shouted prose).
CAPS_HEADING_RATIO = 1.15
CAPS_HEADING_MAX_LEN = textblocks.CHAPTER_MAX_LEN
# The lines of one heading sit closer together than a line of their own type
# (measured 1.1-1.5 sizes top to top), and are set in about the same size.
# Below a chapter title the first body line is 4-7 sizes down.
RUN_LEADING = 2.0
RUN_SIZE = 0.8
# A big line this wide can still be the second line of a heading next to it;
# a full body line can't.
RUN_MAX_WIDTH = 0.8
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
# Ink this faint against the paper is print from the other side of the sheet
# showing through. Measured on a real book: show-through 0.05; the faintest
# real text, small gray running headers, 0.24 and up; body text 0.3-0.7.
SHOW_THROUGH_MAX = 0.12

# Running headers. A chapter title, matched against the small line at the top
# of later pages, may be set wider than a heading is allowed to be (letter-
# spaced capitals), a little under HEADING_RATIO, or over several lines.
# Measured on a real book: chapter titles 1.23 and up.
TITLE_KEY_RATIO = 1.15
TITLE_MAX_ROWS = 6
# A first line that repeats a chapter title word for word is a header as long
# as it is smaller than the body; a long title in small type measures 0.87.
TITLE_HEADER_RATIO = 1.0
# How alike two header texts must be to count as the same header misread
# ("Appliaation" for "Application"), and how long, so short words don't.
HEADER_FUZZ = 0.85
HEADER_FUZZ_MIN_LEN = 6

# Page numbers: a short number alone on the page's last (or first) line, set
# apart from the text. OCR reads "51" as "5l" and a dot beside the number as a
# bullet ("• 150").
FOLIO_RE = re.compile(r"[^\w]*[\dlIO|]{1,4}[^\w]*")
FOLIO_MAX_WIDTH = 0.15

# Two pieces on one line with a gap this wide (of the text width) between
# them sit side by side: a box beside the text, or labels in a diagram.
# Words in a justified line are never this far apart; the gap beside a
# pull-quote box measured 4-6%.
SIDE_GAP = 0.02
# A pull quote repeats a sentence from the page. This much of the box's text
# (letters only) must be found, in runs at least QUOTE_RUN letters long, in
# the page's other text, and the box must hold at least QUOTE_MIN_LETTERS.
QUOTE_MATCH = 0.8
QUOTE_RUN = 8
QUOTE_MIN_LETTERS = 40

# Diagram labels: a run of lines of at most LABEL_WORDS words each, at least
# FIGURE_MIN_LINES lines and FIGURE_MIN_PIECES pieces, scattered across the
# page (side by side, or starting at very different places).
LABEL_WORDS = 3
FIGURE_MIN_LINES = 5
FIGURE_MIN_PIECES = 6
FIGURE_SPREAD = 0.25

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
    ink: float = 1.0


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
    """Drop what isn't this page's text: show-through from the other side of
    the sheet, slivers of the facing page at the photo's edge, and pieces
    lying wholly outside the block of text."""
    pieces = [p for p in pieces if p.ink > SHOW_THROUGH_MAX and not _edge_scrap(p)]
    block = _text_block(pieces)
    if block is None:
        return pieces
    left, right = block
    margin = STRAY_MARGIN * (right - left)
    return [p for p in pieces if p.x1 >= left - margin and p.x0 <= right + margin]


def _x_overlap(p, q) -> float:
    return min(p.x1, q.x1) - max(p.x0, q.x0)


def _y_overlap(p, q) -> float:
    return min(p.bottom, q.bottom) - max(p.top, q.top)


def _on_line(p: Piece, line: list[Piece]) -> bool:
    """Whether p reads as part of the line: level with it, and beside its
    pieces rather than above or below one of them.

    A long line on a curled page gets a tall box, tall enough to take in a
    short label just above it ("Instructions:"); the label sits over the
    line's start, not beside it. Pieces of one line on a curled page drift
    up or down ("3 = Usually   2 = Sometimes   1 = Rarely"), but each still
    overlaps its neighbor by half its height.
    """
    center = (p.top + p.bottom) / 2
    for q in line:
        # level with it, a piece overlapping a little is still beside it: a
        # margin label ("Days 10-12") whose box runs into its line
        level = abs(center - (q.top + q.bottom) / 2) <= LEVEL * max(p.size, q.size)
        if not level and _x_overlap(p, q) > 0.3 * min(p.x1 - p.x0, q.x1 - q.x0):
            return False
    first = line[0]
    tolerance = 0.5 * max(p.size, max(q.size for q in line))
    if abs((p.top + p.bottom) / 2 - (first.top + first.bottom) / 2) <= tolerance:
        return True
    return any(_y_overlap(p, q) >= 0.5 * min(p.bottom - p.top, q.bottom - q.top) for q in line)


def _lines(pieces: list[Piece]) -> list[list[Piece]]:
    """Pieces sharing a line, top to bottom, each line left to right."""
    lines: list[list[Piece]] = []
    for p in sorted(pieces, key=lambda p: (p.top + p.bottom) / 2):
        if lines and _on_line(p, lines[-1]):
            lines[-1].append(p)
        else:
            lines.append([p])
    for line in lines:
        line.sort(key=lambda p: p.x0)
    return lines


def _letters(text: str) -> str:
    return "".join(c for c in text.lower() if c.isalpha())


def _found(text: str, other: str) -> int:
    """How many letters of `text` appear in `other`, in runs long enough not
    to be chance."""
    if not text or not other:
        return 0
    blocks = SequenceMatcher(None, other, text, autojunk=False).get_matching_blocks()
    return sum(b.size for b in blocks if b.size >= QUOTE_RUN)


def _reading(pieces) -> str:
    return " ".join(p.text for p in sorted(pieces, key=lambda p: ((p.top + p.bottom) / 2, p.x0)))


def _side_columns(pieces: list[Piece], width: float) -> list[list[Piece]]:
    """Columns of text set side by side within the page, like a pull-quote
    box and the narrowed text beside it.

    Pieces that share a line with a wide gap between them are side by side.
    Each stretch of such lines splits at the gap, and each side, with the
    other pieces lying within its span, is a column.
    """
    gap = SIDE_GAP * width
    pairs = []
    for p in pieces:
        for q in pieces:
            if (q.x0 - p.x1 >= gap
                    and _y_overlap(p, q) > 0.25 * min(p.bottom - p.top, q.bottom - q.top)):
                pairs.append((p, q))
    if not pairs:
        return []
    # stretches of side-by-side lines, top to bottom
    pairs.sort(key=lambda pq: min(pq[0].top, pq[1].top))
    pitch = median(p.bottom - p.top for p in pieces)
    stretches: list[list[tuple[Piece, Piece]]] = []
    for pq in pairs:
        top = min(pq[0].top, pq[1].top)
        if stretches and top - max(max(a.bottom, b.bottom) for a, b in stretches[-1]) <= 2 * pitch:
            stretches[-1].append(pq)
        else:
            stretches.append([pq])
    columns = []
    for stretch in stretches:
        if len(stretch) < 2:
            continue
        split = median((p.x1 + q.x0) / 2 for p, q in stretch)
        top = min(min(p.top, q.top) for p, q in stretch)
        bottom = max(max(p.bottom, q.bottom) for p, q in stretch)
        within = [p for p in pieces if p.top >= top - pitch and p.bottom <= bottom + pitch]
        columns.append([p for p in within if p.x1 <= split])
        columns.append([p for p in within if p.x0 >= split])
    return [c for c in columns if len(c) >= 2]


def drop_pull_quotes(pieces: list[Piece], nearby: list[Piece] = ()) -> list[Piece]:
    """Drop pull quotes: a box set beside the text that repeats a sentence
    from the page in bigger or different type.

    Left in, its lines interleave with the narrowed lines beside it ("What's
    amazing is Humility is the single greatest and..."). A box is found by
    being a column of text beside another and by its words being found
    elsewhere on the page (or the pages either side, `nearby`). Where the
    box and the text beside it each repeat the other, the box holds the whole
    passage, so the longer goes; after that the text beside it repeats
    nothing.
    """
    block = _text_block(pieces)
    if block is None:
        return pieces
    columns = _side_columns(pieces, block[1] - block[0])
    dropped: set = set()
    while True:
        best = None
        for column in columns:
            if any(p in dropped for p in column):
                continue
            text = _letters(" ".join(p.text for p in column))
            if len(text) < QUOTE_MIN_LETTERS:
                continue
            others = [p for p in pieces if p not in dropped and p not in column]
            other = _letters(_reading(others) + " " + _reading(nearby))
            if _found(text, other) >= QUOTE_MATCH * len(text):
                if best is None or len(text) > best[0]:
                    best = (len(text), column)
        if best is None:
            break
        dropped.update(best[1])
    return [p for p in pieces if p not in dropped]


def drop_figures(pieces: list[Piece]) -> list[Piece]:
    """Drop the labels of a diagram: a run of lines made only of a few words
    each, scattered over the page rather than set as lines of text.

    Read aloud, a Venn diagram's labels come out as "Humble Hungry The Ideal
    Team Player Smart". Lines of text, even short ones like a run of one-word
    replies, start at the margin or an indent; a diagram's labels sit side by
    side or start all over the place. Headings, in bigger type, end a run, so
    a figure's title stays.
    """
    block = _text_block(pieces)
    if block is None:
        return pieces
    left, right = block
    width = right - left
    typical = median(p.size for p in pieces)

    def label(line):
        return all(len(p.text.split()) <= LABEL_WORDS and p.size < HEADING_RATIO * typical
                   for p in line)

    def figure(run):
        if len(run) < FIGURE_MIN_LINES or sum(len(line) for line in run) < FIGURE_MIN_PIECES:
            return False
        beside = any(b.x0 - a.x1 >= SIDE_GAP * width for line in run for a, b in zip(line, line[1:]))
        starts = [p.x0 for line in run for p in line]
        return beside or max(starts) - min(starts) >= FIGURE_SPREAD * width

    lines = _lines(pieces)
    if len(lines) < 2:
        return pieces
    tops = [min(p.top for p in line) for line in lines]
    pitch = median(b - a for a, b in zip(tops, tops[1:]))

    def hugs(i, j):
        """Line i sits at ordinary line spacing from line j, a full line of
        text: the short last line of a paragraph, not a label."""
        if not 0 <= j < len(lines):
            return False
        full = max(p.x1 for p in lines[j]) - min(p.x0 for p in lines[j]) >= 0.5 * width
        return full and abs(tops[i] - tops[j]) <= GAP_FACTOR * pitch

    dropped: set = set()
    start = 0
    for i in range(len(lines) + 1):
        if i < len(lines) and label(lines[i]):
            continue
        a, b = start, i  # lines[a:b] are all labels
        while a < b and hugs(a, a - 1):
            a += 1
        while b > a and hugs(b - 1, b):
            b -= 1
        if figure(lines[a:b]):
            dropped.update(p for line in lines[a:b] for p in line)
        start = i + 1
    return [p for p in pieces if p not in dropped]


def _folio(row: Row, neighbor: Row, pitch: float, width: float) -> bool:
    text = row.text.strip()
    return (FOLIO_RE.fullmatch(text) is not None and any(c.isdigit() for c in text)
            and row.x1 - row.x0 < FOLIO_MAX_WIDTH * width
            and abs(row.top - neighbor.top) > GAP_FACTOR * pitch)


def drop_folios(rows: list[Row]) -> list[Row]:
    """Drop the page number from the page's last or first line, misread or
    not ("5l", "• 150"), so it can't run into the text."""
    if len(rows) < MIN_ROWS:
        return rows
    block = _text_block(rows)
    if block is None:
        return rows
    width = block[1] - block[0]
    pitch = median(rows[i].top - rows[i - 1].top for i in range(1, len(rows)))
    if _folio(rows[-1], rows[-2], pitch, width):
        rows = rows[:-1]
    if _folio(rows[0], rows[1], pitch, width):
        rows = rows[1:]
    return rows


def group_rows(pieces: list[Piece]) -> list[Row]:
    """Join pieces sharing a line into rows, top to bottom, left to right."""
    rows = []
    for line in _lines(pieces):
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

    # Text wrapped under a bullet hangs right of the bullet sign, about as far
    # as a paragraph indent goes: it carries on the item.
    hanging = [False] * n
    item_left = None
    for i, r in enumerate(rows):
        if BULLET_START.match(r.text):
            item_left = lefts[i]
        elif item_left is not None and 0 < lefts[i] - item_left <= HANG_MAX * width:
            hanging[i] = True
        else:
            item_left = None

    def indented(i):
        # Measured from the margin, taken as the lower quarter of the nearby
        # left edges rather than their middle: in dialogue, most nearby lines
        # can be indented first lines (one-line replies), and near the page's
        # top or bottom the window only reaches one way, so their middle is
        # the indent itself.
        if hanging[i]:
            return False
        nearby = sorted(window(lefts, i))
        margin = nearby[int(MARGIN_QUANTILE * (len(nearby) - 1))]
        return lefts[i] - margin > INDENT_MIN * width

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
    """Compare titles ignoring case, spacing and punctuation, and a page
    number at either end ("150 About a Year Later"). Numbers inside the text
    count: "TYPICAL DAY 2-4 WEEKS" is not "TYPICAL DAY 4-8 WEEKS"."""
    core = re.sub(r"^[\W\d_]+|[\W\d_]+$", "", text)
    return "".join(c for c in core.lower() if c.isalnum())


def _digits(key: str) -> str:
    return "".join(c for c in key if c.isdigit())


def _caps(text: str) -> bool:
    """Set in capitals: two or more letters, none lowercase."""
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 2 and all(c.isupper() for c in letters)


def _heading_levels(rows: list[Row], body_size: Optional[float]) -> dict[int, int]:
    if not body_size:
        return {}
    block = _text_block(rows)
    levels = {}
    for i, r in enumerate(rows):
        ratio = r.size / body_size
        if not _key(r.text):
            continue
        narrow = not block or r.x1 - r.x0 <= HEADING_MAX_WIDTH * (block[1] - block[0])
        if ratio >= HEADING_RATIO and narrow:
            levels[i] = 1 if ratio >= TITLE_RATIO else 2
        elif (ratio >= CAPS_HEADING_RATIO and _caps(r.text)
              and len(r.text.strip()) <= CAPS_HEADING_MAX_LEN):
            # Found only because it's in capitals: clean.py's capitals rule
            # makes the same line a level 2 heading, so it keeps that level.
            levels[i] = 2
    return levels


def join_heading_runs(rows: list[Row], levels: dict[int, int],
                      body_size: Optional[float]) -> tuple[list[Row], dict[int, int]]:
    """Join a heading set on two or more lines into one row.

    Each line of "THE THREE VIRTUES OF / AN IDEAL TEAM PLAYER" would
    otherwise be a heading of its own. Lines join when they sit closer than a
    line of their own type and are about the same size, and the run holds a
    heading found by size, or is all capitals (a small capitals heading like
    "APPLICATION #3: DEVELOPING EMPLOYEES WHO / ARE LACKING IN ...", which
    clean.py's capitals rule would otherwise split, then drop for its length).
    A big line next to a heading joins it, so "The Five Dysfunctions" above
    "of a Team Summary" isn't left behind for being a little too wide.
    """
    if len(rows) < 2:
        return rows, levels
    block = _text_block(rows)

    def headingish(i):
        r = rows[i]
        if i in levels or (_caps(r.text) and len(r.text.strip()) <= CAPS_HEADING_MAX_LEN):
            return True
        if not body_size or r.size < HEADING_RATIO * body_size:
            return False
        return not block or r.x1 - r.x0 <= RUN_MAX_WIDTH * (block[1] - block[0])

    def together(a, b):
        big, small = max(a.size, b.size), min(a.size, b.size)
        return big > 0 and b.top - a.top <= RUN_LEADING * big and small >= RUN_SIZE * big

    runs, i = [], 0
    while i < len(rows):
        j = i + 1
        if headingish(i):
            while j < len(rows) and headingish(j) and together(rows[j - 1], rows[j]):
                j += 1
        runs.append((i, j))
        i = j

    out, new_levels = [], {}
    for i, j in runs:
        span = range(i, j)
        marked = [levels[k] for k in span if k in levels]
        keep = j - i > 1 and (marked or all(_caps(rows[k].text) for k in span))
        if not keep:
            for k in span:
                if k in levels:
                    new_levels[len(out)] = levels[k]
                out.append(rows[k])
            continue
        part = rows[i:j]
        new_levels[len(out)] = min(marked) if marked else 2
        text = ""
        for r in part:
            # a dash at the end of a line ("A FINAL THOUGHT-" / "BEYOND
            # WORK TEAMS") runs straight into the next one
            text += ("" if not text or text.endswith("-") else " ") + r.text.strip()
        out.append(Row(
            text,
            min(r.x0 for r in part), max(r.x1 for r in part),
            part[0].top, part[-1].bottom, max(r.size for r in part),
        ))
    return out, new_levels


def _header_candidate(rows: list[Row], body_size: Optional[float]) -> Optional[tuple[str, float]]:
    """Key and relative type size of the page's first line, if it could be
    a running header: smaller than the body, and not a sentence."""
    if not rows or not body_size:
        return None
    first = rows[0]
    ratio = first.size / body_size
    if ratio >= TITLE_HEADER_RATIO:
        return None
    if any(c in first.text for c in ".!?") or textblocks.is_bullet(first.text):
        return None
    key = _key(first.text)
    return (key, ratio) if key else None


def _title_keys(pages: dict[int, list[Row]], body_size: dict) -> set[str]:
    """Keys of every line, or run of up to TITLE_MAX_ROWS lines, set in type
    well above the body's: chapter titles, whatever their width."""
    keys = set()
    for i, rows in pages.items():
        if not body_size[i]:
            continue
        run: list[str] = []
        for r in rows + [None]:
            if r is not None and r.size / body_size[i] >= TITLE_KEY_RATIO and _key(r.text):
                run.append(_key(r.text))
                continue
            for a in range(len(run)):
                for b in range(a + 1, min(len(run), a + TITLE_MAX_ROWS) + 1):
                    keys.add("".join(run[a:b]))
            run = []
    return keys


def _like(key: str, known: set[str]) -> bool:
    """Key matches one of `known`, allowing a misread letter or two in a
    long enough key."""
    if key in known:
        return True
    if len(key) < HEADER_FUZZ_MIN_LEN:
        return False
    for k in known:
        if abs(len(k) - len(key)) > (1 - HEADER_FUZZ) * len(key):
            continue
        # a misread is a letter or two; different numbers are a different line
        if _digits(k) != _digits(key):
            continue
        m = SequenceMatcher(None, key, k, autojunk=False)
        if m.real_quick_ratio() >= HEADER_FUZZ and m.quick_ratio() >= HEADER_FUZZ and m.ratio() >= HEADER_FUZZ:
            return True
    return False


def to_lines(raw: str) -> list[str]:
    """Turn raw OCR output into plain lines with paragraph breaks and
    headings marked, and running headers and stray scraps removed."""
    segments: list = []  # a page (list of Pieces) or a line passed through
    for line in raw.splitlines():
        m = PIECE_RE.match(line)
        if m:
            x0, x1, top, bottom, size, ink, text = m.groups()
            top, bottom = float(top), float(bottom)
            piece = Piece(text, float(x0), float(x1), top, bottom,
                          float(size) if size else bottom - top,
                          float(ink) if ink else 1.0)
            if segments and isinstance(segments[-1], list):
                segments[-1].append(piece)
            else:
                segments.append([piece])
        else:
            segments.append(line)

    kept = {i: drop_strays(attach_drop_caps(s)) for i, s in enumerate(segments) if isinstance(s, list)}
    order = sorted(kept)
    pages = {}
    for n, i in enumerate(order):
        # a pull quote may repeat a sentence from the page before or after
        nearby = [p for j in order[max(0, n - 1): n + 2] if j != i for p in kept[j]]
        pieces = drop_figures(drop_pull_quotes(kept[i], nearby))
        pages[i] = drop_folios(group_rows(pieces))

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
    titles = _title_keys(pages, body_size) | {_key(pages[i][r].text) for i in pages for r in levels[i]}

    # A small first line is a running header when the same words top more
    # than one page, or they name a chapter (allowing for a misread letter).
    # A one-off small line, like "PART ONE" above a part title, stays.
    candidates = {i: _header_candidate(rows, body_size[i]) for i, rows in pages.items()}
    seen = Counter(c[0] for c in candidates.values() if c and c[1] < HEADER_RATIO)
    repeated = {k for k, n in seen.items() if n >= 2}
    for i, cand in candidates.items():
        if not cand:
            continue
        key, ratio = cand
        # a title in small type, repeated word for word, can be set larger
        # than a header otherwise is
        header = (key in titles if ratio >= HEADER_RATIO
                  else _like(key, repeated) or _like(key, titles))
        if header:
            pages[i] = pages[i][1:]
            levels[i] = {r - 1: lvl for r, lvl in levels[i].items() if r > 0}

    for i in pages:
        pages[i], levels[i] = join_heading_runs(pages[i], levels[i], body_size[i])

    out: list[str] = []
    for i, seg in enumerate(segments):
        if isinstance(seg, list):
            out.extend(paragraph_lines(pages[i], levels[i]))
        else:
            out.append(seg)
    return out
