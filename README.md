# bookshot

Snap photos of a book, get a single plain-text file ready to paste into Speechify (or any text-to-speech app).

Born out of frustration with Speechify's own scan feature after an update broke it. Runs entirely on your Mac using Apple Vision for OCR — no cloud, no API key, no upload. An optional review pass uses your existing Claude Code subscription to fix obvious OCR typos.

## Pipeline

```
photos/  →  sips (HEIC→JPG)  →  Apple Vision OCR  →  reflow & clean  →  speechify.txt
                                                                    ↘ optional Claude Code review
```

`bookshot.sh` is the orchestrator. Behind it:

1. **`sips`** converts every HEIC/JPG/JPEG/PNG in the input folder to a normalized JPG.
2. **`ocr.swift`** runs Apple Vision text recognition on each image. Two-page spreads are split down the middle and each page is OCR'd top-to-bottom.
3. **`clean.py`** reflows the raw OCR — strips page numbers and per-page headers, joins wrapped paragraph lines into single-line paragraphs (Speechify treats every line break as a sentence boundary), keeps headings and bullet items on their own lines.
4. **`review.py`** *(optional, `--review`)* splits the output by chapter, asks `claude -p` for a JSON list of `{find, replace}` OCR fixes, and applies the ones that match uniquely.

## Requirements

- macOS (uses `sips` and Apple's Vision framework via Swift)
- `python3` (stdlib only)
- `--review` requires the [Claude Code](https://claude.ai/code) CLI on your `PATH`. It runs `claude -p` headlessly against your existing Claude Code subscription — no separate API key or billing.

## Usage

```bash
./bookshot.sh <input-folder> [output-file] [flags]
```

Flags:

- `--no-split` — treat each photo as a single page (default assumes two-page spreads)
- `--keep-temp` — keep the intermediate `_book_tmp/` directory for inspection
- `--review` — run the AI cleanup pass (chunked, parallelized, ~1 minute per 20 chapters)

Examples:

```bash
# basic run — output goes to <folder>/speechify.txt
./bookshot.sh ~/Documents/my-book

# custom output path
./bookshot.sh ~/Documents/my-book ~/Desktop/my-book.txt

# single-page photos (e.g., from a book scanner app)
./bookshot.sh ~/Documents/my-book --no-split

# with AI typo cleanup
./bookshot.sh ~/Documents/my-book --review
```

### Convenience alias

Add to `~/.zshrc` to run from anywhere:

```bash
alias bookshot="$HOME/path/to/bookshot/bookshot.sh"
```

## How to take the photos

- **Two-page spreads** are easier — open the book flat, photograph the whole spread, move on. The script splits each photo down the middle.
- Sort the photos in the order they were taken (iPhone's default filename order works).
- Make sure the spine is roughly centered so the split lines up. Slight tilt is fine.
- Avoid fingers, glare, and shadows on the text. Vision is robust but not magic.

## Limitations

- Designed for prose books with chapter headings, paragraphs, and bullet lists. Novels with stylized typography or textbooks with multi-column layouts may produce mixed-up output.
- The single OCR pass on a half-spread reads top-to-bottom in a single column. Side-by-side text blocks within one page will interleave (rare in trade paperbacks).
- The heading detector caps section headings at 35 characters; longer ones get folded into the next paragraph (still readable, just not visually split).
- Hyphenated line breaks are rejoined by removing the newline only — `pebble-\nlike` becomes `pebble-like` (correct), but `hap-\npened` becomes `hap-pened` (cosmetic only — Speechify still reads it correctly).

## Files

| File | Purpose |
|------|---------|
| `bookshot.sh` | Orchestrates the pipeline |
| `ocr.swift` | Apple Vision OCR with two-page split and portrait fallback |
| `clean.py` | Reflows raw OCR into Speechify-ready paragraphs |
| `review.py` | Optional `claude -p` typo-fix pass |
