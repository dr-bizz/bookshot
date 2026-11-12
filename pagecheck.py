#!/usr/bin/env python3
"""Check the photos before the text is built from them.

A book is a hundred photos or more, and nothing in the text says when one
went wrong: a skipped spread just vanishes, a spread shot twice reads twice,
a blurry page loses lines. So this reads the photos' own evidence:

- Page numbers. layout.py finds each page's number (and drops it from the
  text); here they're checked to run in order across the photos, so a gap
  says which pages are missing, and a photo whose pages jump back says it's
  out of order. Pages with no number (chapter openings, blank pages) just
  take their place in the count.
- Repeats. A page whose text matches an earlier photo's is used once, the
  sharper copy kept. It works on books without page numbers too.
- Photos to retake. ocr.swift marks each page with how blurry it is, when
  its text runs off the photo's side, and when it couldn't find the spine
  to cut a spread at; here a line cut by the top or bottom edge is spotted
  too.

check() returns the raw OCR with repeats taken out, and a list of notes for
the person who took the photos.
"""
import re
from typing import NamedTuple, Optional

import layout

# ocr.swift marks the start of each page: "===== left page blur=0.190 =====",
# "===== right page blur=0.188 =====", or "===== page blur=0.190 =====" for a
# photo of one page. Older raw files mark only "===== right page =====".
PAGE_MARK = re.compile(r"===== (left page|right page|page)((?: \w+=\S+)*) =====")
PHOTO_MARK = re.compile(r"===== (.+) =====")

# Blur from ocr.swift: how little the page changes when blurred again (0
# sharp, 1 all blur). Measured on 112 photos of a book: 0.13-0.28. Blurred on
# purpose, Vision read every line up to about 0.5, lost 2-10% of the text at
# 0.53-0.61, and half of it or more from 0.62 up.
BLUR_MAX = 0.55
# Two copies of a page: keep the one that read clearly more text (the other
# read less than this share of it), else the one with fewer problems, else
# the clearly sharper one, else the fuller one.
FULLER = 0.8
BLUR_DIFF = 0.1

# A page repeats another when this share of its word pairs (numbers
# included) are on the other page too. The same page read from two photos
# shared 92% or more; different pages of a novel-like book, 24% at most;
# two pages set on one template in a baby-care book ("Typical Day 2-4
# weeks", "4-8 weeks"), 78%.
REPEAT_MATCH = 0.85
# Pages with fewer word pairs than this (a title, a chapter's last lines)
# are never called repeats: too little to tell.
REPEAT_MIN_PAIRS = 40

# Text this close to the photo's outer edge, top or bottom (fraction of the
# page's half of the photo) is cut off by it. The closest any text came in
# 112 well-framed photos: 0.028 from the top, 0.067 from the side.
EDGE = 0.005
# Lines touching the outer side before the page counts as running off it: a
# stray letter there can be the edge of the page block.
EDGE_LINES = 2
# A line cut by the top or bottom edge is at least this wide (of the page).
EDGE_LINE_WIDTH = 0.25


class Half(NamedTuple):
    side: str            # "left page", "right page", "page"
    mark: Optional[str]  # its marker line, None in older raw files
    meta: dict
    lines: list          # raw lines: pieces and anything else


class Photo(NamedTuple):
    mark: str
    halves: list
    # the photo the pages came from, when a better copy of them was used in
    # this photo's place
    source: Optional[str] = None


def _name(photo: Photo) -> str:
    """IMG_7190.jpg -> IMG_7190, the name the person knows it by: of the
    photo whose pages these are."""
    return PHOTO_MARK.fullmatch(photo.source or photo.mark).group(1).rsplit(".", 1)[0]


def _parse(raw: str) -> tuple[list, list]:
    """Lines before the first photo, and the photos."""
    before: list = []
    photos: list = []
    for line in raw.splitlines():
        page = PAGE_MARK.fullmatch(line)
        if page:
            if not photos:
                before.append(line)
                continue
            meta = dict(kv.split("=", 1) for kv in page.group(2).split())
            halves = photos[-1].halves
            # an older file's left page has no marker: it's what came before
            if halves and halves[-1].mark is None and not halves[-1].lines:
                halves.pop()
            halves.append(Half(page.group(1), line, meta, []))
        elif PHOTO_MARK.fullmatch(line):
            photos.append(Photo(line, [Half("left page", None, {}, [])]))
        elif photos:
            photos[-1].halves[-1].lines.append(line)
        else:
            before.append(line)
    for photo in photos:
        if len(photo.halves) == 1 and photo.halves[0].mark is None:
            # an older file's photo with no right-page marker: one page
            photo.halves[0] = photo.halves[0]._replace(side="page")
    return before, photos


def _pieces(half: Half) -> list:
    out = []
    for line in half.lines:
        m = layout.PIECE_RE.match(line)
        if m:
            x0, x1, top, bottom, size, ink, text = m.groups()
            out.append(layout.Piece(text, float(x0), float(x1), float(top), float(bottom),
                                    float(size) if size else float(bottom) - float(top),
                                    float(ink) if ink else 1.0))
    return [p for p in out if p.ink > layout.SHOW_THROUGH_MAX]


def folio_number(text: str) -> Optional[int]:
    """The page number in a page-number line, reading the letters OCR gives
    for digits back as digits ("5l" 51, "3 l" 31). None for roman numerals
    or anything else."""
    text = text.strip()
    if not layout.FOLIO_RE.fullmatch(text) or not any(c.isdigit() for c in text):
        return None
    digits = text.translate(str.maketrans("lI|TO", "11110"))
    digits = "".join(c for c in digits if c.isdigit())
    return int(digits) if digits else None


def _page_number(half: Half) -> Optional[int]:
    rows = layout.group_rows(layout.drop_strays(layout.attach_drop_caps(_pieces(half))))
    for i in layout.folio_rows(rows):
        n = folio_number(rows[i].text)
        if n is not None:
            return n
    return None


def _pairs(half: Half) -> set:
    words = re.findall(r"[a-z0-9']+", " ".join(p.text.lower() for p in _pieces(half)))
    return set(zip(words, words[1:]))


def _blur(half: Half) -> Optional[float]:
    try:
        return float(half.meta["blur"])
    except (KeyError, ValueError):
        return None


def _same_pages(this: list, other: list) -> bool:
    """Two photos show the same pages: each page with enough text to judge
    matches the page on the same side of the other photo (a spread shot
    again keeps each page on its side), and no page numbers disagree. A
    template page matching on one side is not enough when its facing page
    doesn't."""
    sides = {side: (pairs, n) for side, pairs, n in other}
    matched = 0
    for side, pairs, n in this:
        if side not in sides:
            return False
        their_pairs, their_n = sides[side]
        if n is not None and their_n is not None and n != their_n:
            return False
        if len(pairs) < REPEAT_MIN_PAIRS or len(their_pairs) < REPEAT_MIN_PAIRS:
            continue
        if len(pairs & their_pairs) < REPEAT_MATCH * min(len(pairs), len(their_pairs)):
            return False
        matched += 1
    return matched > 0


def _defects(photo: Photo) -> int:
    """What's wrong with a photo, counted: no spine found, a page cut off by
    the photo's edge, a blurry page."""
    return (any(h.meta.get("spine") == "none" for h in photo.halves)
            + sum(h.meta.get("edge") == "cut" for h in photo.halves)
            + sum((_blur(h) or 0) >= BLUR_MAX for h in photo.halves))


def _better(a: Photo, b: Photo) -> bool:
    """Of two photos of the same pages, `a` is the one to read: the one that
    read clearly more text (a finger or glare can hide lines and leave no
    other mark), else fewer defects, else clearly sharper, else more text."""
    text_a = sum(len(p.text) for h in a.halves for p in _pieces(h))
    text_b = sum(len(p.text) for h in b.halves for p in _pieces(h))
    if min(text_a, text_b) < FULLER * max(text_a, text_b):
        return text_a > text_b
    if _defects(a) != _defects(b):
        return _defects(a) < _defects(b)
    blur_a = [x for x in map(_blur, a.halves) if x is not None]
    blur_b = [x for x in map(_blur, b.halves) if x is not None]
    if blur_a and blur_b:
        mean_a, mean_b = sum(blur_a) / len(blur_a), sum(blur_b) / len(blur_b)
        if abs(mean_a - mean_b) >= BLUR_DIFF:
            return mean_a < mean_b
    return text_a > text_b


def _merge_repeats(photos: list) -> tuple[list, list]:
    """The photos with each repeat used once, and notes. A repeat keeps the
    first copy's place in the book (a retake shot at the end belongs where
    the page is), with the better copy's text in it."""
    kept: list = []
    pages: list = []  # each kept photo's (side, word pairs, page number)
    notes = []
    for photo in photos:
        mine = [(h.side, _pairs(h), _page_number(h)) for h in photo.halves]
        k = next((k for k in reversed(range(len(kept))) if _same_pages(mine, pages[k])), None)
        if k is None:
            kept.append(photo)
            pages.append(mine)
            continue
        first = kept[k]
        note = f"{_name(photo)} repeats {_name(first)}, so it was used once"
        if _better(photo, first):
            kept[k] = Photo(first.mark, photo.halves, photo.mark)
            pages[k] = mine
            note += f" (the better copy, {_name(photo)})"
        notes.append((k, note + "."))
    return kept, notes


def _retakes(photos: list) -> list:
    notes = []
    for pi, photo in enumerate(photos):
        name = _name(photo)
        if any(h.meta.get("spine") == "none" for h in photo.halves):
            notes.append((pi, f"{name}: couldn't find the spine, so the photo was cut down the "
                              "middle and words near the spine may be cut off. Retake it with the "
                              "spine near the middle."))
        blurry = [h.side for h in photo.halves if (_blur(h) or 0) >= BLUR_MAX]
        if blurry:
            which = "both pages are" if len(blurry) == 2 else f"the {blurry[0]} is"
            notes.append((pi, f"{name}: {which} blurry, so some lines may be missing. Retake it."))
        for half in photo.halves:
            if _runs_off(half):
                notes.append((pi, f"{name}: the {half.side} runs off the edge of the photo, so "
                                  "some text is cut off. Retake it with the whole page in view."))
    return notes


def _runs_off(half: Half) -> bool:
    # ocr.swift looks past where the lines stop for letters the edge cut
    if half.meta.get("edge") == "cut":
        return True
    pieces = [p for p in _pieces(half) if sum(c.isalnum() for c in p.text) >= 3]
    # a line cut by the top or bottom: words across the page, not a scrap of
    # the table or rug beside the book read as "26828"
    if any((p.top < EDGE or p.bottom > 1 - EDGE) and p.x1 - p.x0 >= EDGE_LINE_WIDTH
           and sum(c.isalpha() for c in p.text) >= 3 for p in pieces):
        return True
    if half.side == "left page":
        gaps = [p.x0 for p in pieces]
    elif half.side == "right page":
        gaps = [1 - p.x1 for p in pieces]
    else:
        # one page to a photo: the side edges may hold a scrap of the facing
        # page, which layout.py drops
        return False
    return sum(g < EDGE for g in gaps) >= EDGE_LINES


def _runs(photos: list, leave_out: set = frozenset()) -> tuple[dict, list]:
    """Where each photo's pages fall in the book, and the runs of page
    numbers that keep in step with their place.

    Every page kept takes the next place in the book, numbered or not, so
    number minus place (the run's offset) stays the same while pages run in
    order. Photos in `leave_out` take no place."""
    span = {}  # photo -> (first place, end place)
    known = []  # (place, number, photo)
    place = 0
    for pi, photo in enumerate(photos):
        if pi in leave_out:
            continue
        start = place
        for half in photo.halves:
            n = _page_number(half)
            if n is not None:
                known.append((place, n, pi))
            place += 1
        span[pi] = (start, place)

    # A number out of step with both neighbors, that doesn't fall between
    # them, is misread; so is one at either end out of step and going the
    # wrong way. Not a page out of place, which carries two numbers.
    kept = []
    for i, (p, n, pi) in enumerate(known):
        if 0 < i < len(known) - 1:
            (pp, pn, _), (np_, nn, _) = known[i - 1], known[i + 1]
            if n - p not in (pn - pp, nn - np_) and not pn < n < nn:
                continue
        kept.append((p, n, pi))
    if len(kept) >= 2 and kept[-1][1] - kept[-1][0] != kept[-2][1] - kept[-2][0] and kept[-1][1] < kept[-2][1]:
        kept.pop()
    if len(kept) >= 2 and kept[0][1] - kept[0][0] != kept[1][1] - kept[1][0] and kept[0][1] > kept[1][1]:
        kept.pop(0)

    runs: list = []  # [offset, first entry, last entry]
    for entry in kept:
        offset = entry[1] - entry[0]
        if runs and runs[-1][0] == offset:
            runs[-1][2] = entry
        else:
            runs.append([offset, entry, entry])
    return span, runs


def _page_order(photos: list) -> list:
    """Notes on missing and out-of-order pages, from the page numbers."""
    def name(pi):
        return _name(photos[pi])

    def pages(first, last):
        return f"page {first}" if first == last else f"pages {first}-{last}"

    # Photos shot out of turn. Where the numbers step back, either the run
    # after the step belongs earlier, or the runs it jumped belong later:
    # blame whichever is fewer photos (the run that steps back on a tie),
    # take its places out, and look again.
    span, runs = _runs(photos)
    moved = []  # (first photo, last photo, first page, last page)
    leave_out: set = set()
    for _ in range(len(photos)):
        step = next((i for i in range(len(runs) - 1) if runs[i + 1][1][1] < runs[i][2][1]), None)
        if step is None:
            break
        back = runs[step + 1]
        home = max((j for j in range(step + 1) if runs[j][2][1] < back[1][1]), default=-1)
        jumped = runs[home + 1: step + 1]
        if back[2][2] - back[1][2] <= jumped[-1][2][2] - jumped[0][1][2]:
            # the run that stepped back, with its unnumbered pages too
            first, last = back[1][2], back[2][2]
            lo, hi = span[first][0] + back[0], span[last][1] - 1 + back[0]
        else:
            first, last = jumped[0][1][2], jumped[-1][2][2]
            lo, hi = jumped[0][1][1], jumped[-1][2][1]
        moved.append((first, last, lo, hi))
        leave_out |= {pi for pi in span if first <= pi <= last}
        span, runs = _runs(photos, leave_out)

    notes = []
    gaps = []  # (photo before, photo after, first missing page, how many)
    for i in range(len(runs) - 1):
        a, b = runs[i][2], runs[i + 1][1]
        gap = runs[i + 1][0] - runs[i][0]
        pa, pb = a[2], b[2]
        if pa == pb:
            continue  # two numbers on one photo that disagree: a misread
        if gap > 0:
            # the first page missing is only known when the two photos are
            # next to each other
            first = span[pa][1] + runs[i][0] if span[pa][1] == span[pb][0] else None
            gaps.append([pa, pb, first, gap, a[1], b[1]])
        else:
            notes.append((pb, f"{name(pb)} (page {b[1]}) comes after {name(pa)} (page {a[1]}), "
                              "so the photos may be out of order."))

    for first, last, lo, hi in moved:
        who = name(first) if first == last else f"{name(first)} to {name(last)}"
        home = next((g for g in gaps if g[4] < lo and hi < g[5]), None)
        if home is None:
            notes.append((first, f"{who} ({pages(lo, hi)}) seems to be out of order."))
            continue
        notes.append((first, f"{who} ({pages(lo, hi)}) is out of order: it belongs between "
                             f"{name(home[0])} and {name(home[1])}."))
        home[3] -= hi - lo + 1
        if home[2] is not None and home[2] == lo:
            home[2] = hi + 1

    for pa, pb, first, gap, na, nb in gaps:
        if gap <= 0:
            continue
        if first is not None:
            missing = f"Page {first} seems" if gap == 1 else f"Pages {first}-{first + gap - 1} seem"
            notes.append((pb, f"{missing} to be missing between {name(pa)} and {name(pb)}."))
        else:
            count = "1 page seems" if gap == 1 else f"{gap} pages seem"
            notes.append((pb, f"{count} to be missing between {name(pa)} (page {na}) "
                              f"and {name(pb)} (page {nb})."))
    return notes


def check(raw: str) -> tuple[str, list]:
    """The raw OCR with repeated pages used once, and notes on the photos:
    pages missing, repeated or out of order, and photos to retake."""
    before, found = _parse(raw)
    if not found:
        return raw, []
    photos, notes = _merge_repeats(found)
    notes += _retakes(photos)
    # Older raw files print nothing for a blank page, so its place can't be
    # counted: no page-order notes rather than false ones.
    if any(h.mark is not None and h.side != "right page" for p in photos for h in p.halves):
        notes += _page_order(photos)
    notes = [text for _, text in sorted(notes, key=lambda n: n[0])]
    if photos == found:
        return raw, notes
    out = list(before)
    for photo in photos:
        out.append(photo.mark)
        for half in photo.halves:
            if half.mark is not None:
                out.append(half.mark)
            out.extend(half.lines)
    return "\n".join(out) + ("\n" if raw.endswith("\n") else ""), notes
