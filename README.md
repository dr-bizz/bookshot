# bookshot

Snap photos of a book, get a single plain-text file ready to paste into Speechify (or any text-to-speech app).

Born out of frustration with Speechify's own scan feature after an update broke it. Runs entirely on your Mac using Apple Vision for OCR — no cloud, no API key, no upload. An optional review pass uses your existing Claude Code subscription to fix obvious OCR typos.

## Pipeline

```
photos/ → sips (HEIC→JPG) → Apple Vision OCR → page layout → reflow & clean → speechify.txt
                                                                           ↘ optional Claude Code review
                                                                           ↘ optional emphasis pass → speechify.docx
                                                                           ↘ optional rich text → speechify.html + Apple Note
```

`bookshot.sh` is the orchestrator. Behind it:

1. **`sips`** converts every HEIC/JPG/JPEG/PNG in the input folder to a normalized JPG.
2. **`ocr.swift`** runs Apple Vision text recognition on each image. Two-page spreads are split at the spine: a quick first pass finds the empty gap between the two pages' text, so a photo that isn't centered on the spine doesn't slice the end off every line of one page ("persor" for "personal"). With no clear gap it falls back to the middle of the photo. Every piece of text is written out with its box and type size, measured after rotating the page level, so a photo taken at an angle measures like a square-on one.
3. **`layout.py`** reads the page's structure off those boxes: paragraph breaks (indented first lines, short last lines, extra space), headings (bigger type, or capitals a little bigger than the body; a title set on two or more lines is joined into one), running headers (small title at the top of the page that repeats or names a chapter, allowing a misread letter, dropped), page numbers (dropped, even misread as "5l"), pull quotes (a box beside the text repeating a sentence from the page, dropped), diagram labels (short scattered pieces, dropped), scraps of the facing page caught in the photo (dropped), and print from the other side of the sheet showing through the paper (dropped, by how faint its ink is).
4. **`clean.py`** reflows the text. It first puts back quote marks Vision misread: on macOS 27 a closing quote over its period (`you.”`) often comes out as Vietnamese letters ("youạẠạ"), which also hid the end of the sentence and ran one speaker's paragraph into the next (see `quotemarks.py`). It strips page numbers, joins wrapped lines into single-line paragraphs, keeps headings, sub-headings and bullet items as blocks of their own, and puts a blank line after every block. It also puts back a chapter's first letter when a big decorative drop cap kept OCR from reading it ("fter twenty years" → "After twenty years"; see `dropcap.py`), then fixes words Vision misreads the same way every time ("tocus" → "focus", "T'm" → "I'm", "work-and" → "work—and"; see `ocrfix.py`). It also writes `speechify.txt.blocks.json`, the kind of each block (title, heading, paragraph, bullet).
5. **`review.py`** *(optional, `--review`)* splits the output by chapter, asks `claude -p` for a JSON list of `{find, replace}` OCR fixes, and applies the ones that match uniquely.
6. **`emphasis.py`** *(optional, `--emphasis`)* asks `claude -p` which words a narrator would lean on, and writes them to a `.emphasis.json` sidecar.
7. **`docx_out.py`** *(optional, `--docx`)* writes a `.docx` where those spans are italic runs.
8. **`rich_out.py`** *(optional, `--notes`)* writes the book as rich text (headings, paragraphs, lists and any emphasis) to `speechify.html` and a new Apple Note.

## What Speechify actually honors

Speechify's reader app was probed directly to find out what survives a paste or
an import. Almost nothing does. It derives prosody from the character stream
alone, so anything that lives in the document's *structure* is invisible to it:

| Approach | Result |
|---|---|
| **Bold / italic runs in `.docx`** | ✅ **Audibly stressed** |
| SSML (`<break>`, `<prosody>`, `<emphasis>`) | ❌ Read aloud as literal text |
| Markdown (`**bold**`, `# heading`) | ❌ Read aloud as literal text |
| EPUB headings and chapter spine | ❌ Builds a table of contents; no effect on speech |
| Headings, empty paragraphs, blank lines | ❌ No effect on speech |
| Single line break in pasted text | ⚠️ Lines are merged into one paragraph |
| Blank line in pasted text | ✅ Starts a new paragraph in the reader |
| Rich text pasted from Apple Notes | ✅ Formatting mostly carries over (newer editor) |
| Pause tricks (lone `.`, `,,,`, stacked periods) | ❌ Not reproducible — apparent pauses track Speechify's own chunking, not the text |

Speechify's newer editor (with a formatting toolbar) keeps the formatting of
rich text pasted into it, which is what `--notes` is for. Plain text needs a
blank line between blocks, or headings run into the next sentence.

The practical consequence: **you can control emphasis, but not pacing.** For real
pause control you need Speechify's TTS API, which does support SSML and renders
to MP3 — a different product from the reader app.

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
- `--docx` — also write a `.docx` alongside the `.txt`
- `--emphasis` — AI pass marking which words to stress, rendered as italics (implies `--docx`)
- `--notes`: also write the book as rich text: `speechify.html` and a new Apple Note. Copy from the note (on the Mac, or on your phone once it syncs) into Speechify to keep the headings. The first run asks for permission to control Notes.

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

# with narrator-style emphasis, for import into Speechify as a Word file
./bookshot.sh ~/Documents/my-book --emphasis

# formatted, as an Apple Note to copy into Speechify
./bookshot.sh ~/Documents/my-book --notes
```

The `.txt` output is unchanged by `--emphasis` — the spans live in a sidecar, so
you can regenerate or discard the `.docx` without re-running OCR.

### Convenience alias

Add to `~/.zshrc` to run from anywhere:

```bash
alias bookshot="$HOME/path/to/bookshot/bookshot.sh"
```

## How to take the photos

- **Two-page spreads** are easier — open the book flat, photograph the whole spread, move on. The script splits each photo at the spine, found from the gap between the two pages' text.
- Sort the photos in the order they were taken (iPhone's default filename order works).
- Keep the spine near the middle of the photo (within about a fifth of the width either way) so the split can find it. Slight tilt is fine.
- Avoid fingers, glare, and shadows on the text. Vision is robust but not magic.

## Limitations

- Designed for prose books with chapter headings, paragraphs, and bullet lists. Novels with stylized typography or textbooks with multi-column layouts may produce mixed-up output.
- The single OCR pass on a half-spread reads top-to-bottom in a single column. Side-by-side text blocks within one page will interleave (rare in trade paperbacks).
- Headings are found by type size, so a heading set in body-size bold type isn't recognized as one; short unpunctuated lines still get a block of their own, and so does a short title-case line the page sets apart (a sub-heading). A sub-heading run into its paragraph on the same line stays glued to it. In an Apple Note, headings show as bold, larger text: Notes turns heading tags into that.
- Paragraph breaks are only kept after a finished sentence, so a misread on a noisy page can't cut a sentence in two. A paragraph that ends without `.`, `!` or `?` may run into the next one.
- A quote mark Vision drops entirely, with nothing left in its place, stays missing. Where a misread quote's stop can't be seen, `?` or `.` is chosen from how the sentence starts ("What did he...", "Do you..."), so a question worded like a statement gets a period.
- A misread word is only fixed when one look-alike swap (t read for f, i for l, rn for m, italic b for h...) makes a word the book itself uses elsewhere, or, for a long word read with t for f, a dictionary word ("transtorming"). A real word that is rare in the book ("tor", "bumble") changes only when the book pairs the common word with the same neighbor ("for your", "humble, hungry"). So a word misread two ways, or one the book uses only once, stays as read. A lone "1" becomes "I" only where a clause starts and before a word that follows I ("And 1 did"), so "1 cup" stays.
- Pull quotes are found only when set beside the text; one set full width between paragraphs stays. A diagram with fewer than five lines of labels stays.
- A running header is only dropped once it repeats or matches a chapter title, so on a short run of photos it may stay.
- A letter lost to a drop cap is chosen from the book's own wording (which letter makes a word, or a name, that fits the words after it), so it's a well-informed guess, not a reading of the letter. When the book gives no way to choose ("ark": Bark or Dark?) the word is left as it is.
- Line-break hyphens are resolved against the macOS system dictionary: if the joined form is a real word, the hyphen is dropped (`peo-\nple` → `people`); if both halves are real words but the joined form isn't, the hyphen is kept (`Personal-\nBest`, `self-\naware`). Edge cases with rare/coined words may guess wrong but read fine in TTS.

## Files

| File | Purpose |
|------|---------|
| `bookshot.sh` | Orchestrates the pipeline |
| `ocr.swift` | Apple Vision OCR with two-page split at the spine and portrait fallback |
| `layout.py` | Reads paragraphs, headings, running headers, drop caps and stray scraps off the page geometry |
| `dropcap.py` | Puts back a chapter's first letter when a drop cap kept OCR from reading it |
| `quotemarks.py` | Puts back quote marks Vision reads as Vietnamese letters (`company."` → "companyiạẠạ") |
| `ocrfix.py` | Fixes words Vision misreads ("tocus", "T'm"), and hyphens read for dashes, using the book's own words as the judge |
| `clean.py` | Reflows raw OCR into Speechify-ready paragraphs and records each block's kind |
| `textblocks.py` | Shared line classifiers and chapter chunking |
| `claude_cli.py` | Shared `claude -p` plumbing and JSON-array parsing |
| `review.py` | Optional `claude -p` typo-fix pass |
| `emphasis.py` | Optional `claude -p` pass picking words to stress |
| `docx_out.py` | Writes the `.docx` with emphasis as italic runs |
| `rich_out.py` | Writes the rich-text `.html` and the Apple Note |
| `test_*.py` | Test suite — `python3 -m unittest discover` |
