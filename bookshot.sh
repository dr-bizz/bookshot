#!/usr/bin/env bash
# bookshot
#
# Converts a folder of book-page photos (HEIC/JPG/PNG) into a single plain-text
# file ready to paste or upload into Speechify.
#
# Usage:
#   bookshot.sh <input-folder> [output-file] [--no-split] [--keep-temp] [--review]
#                                             [--docx] [--emphasis] [--notes]
#
#   --review additionally runs an AI cleanup pass via Claude Code (`claude -p`)
#   to fix OCR typos, quote marks and dashes the rules left. Uses your
#   existing Claude Code subscription — no separate API billing.
#
#   At the end, any problems with the photos are listed: pages missing,
#   repeated or out of order, and photos to retake (blurry, cut off).
#
#   --docx also writes a .docx. Speechify ignores SSML, markdown and document
#   structure, but it does audibly stress bold/italic runs in a Word file.
#   --emphasis adds an AI pass that picks which words to stress (implies --docx).
#
#   --notes writes the book as rich text (headings, paragraphs, lists read off
#   the page photos) to a .html file and a new Apple Note. Speechify keeps the
#   formatting of rich text pasted into it, e.g. copied from Notes.
#
# Requires: macOS (uses sips + Apple Vision via swift), python3.
# --review additionally requires the Claude Code CLI (`claude`) on PATH.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: bookshot.sh <input-folder> [output-file] [--no-split] [--keep-temp]
                   [--review] [--docx] [--emphasis] [--notes]

  <input-folder>   Folder containing page photos, sorted in reading order.
  [output-file]    Output .txt path. Default: <input-folder>/speechify.txt
  --no-split       Treat each photo as a single page (default: two-page spreads).
  --keep-temp      Keep the intermediate _book_tmp/ folder for inspection.
  --review         AI pass via Claude Code to fix OCR typos.
  --docx           Also write a .docx alongside the .txt. Speechify stresses
                   bold/italic runs in a Word file; it ignores everything else.
  --emphasis       AI pass marking which words to stress. Implies --docx.
  --notes          Also write the book as rich text: a .html file and a new
                   Apple Note, with the headings and paragraphs from the photos.
                   Copy from the note into Speechify to keep the formatting.
EOF
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

# handle help before the first argument is claimed as the input folder
if [[ "$1" == "-h" || "$1" == "--help" ]]; then
  usage
  exit 0
fi

INPUT_DIR="$1"; shift || true
OUTPUT_FILE=""
SPLIT_FLAG=""
KEEP_TEMP=0
REVIEW=0
DOCX=0
EMPHASIS=0
NOTES=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-split)  SPLIT_FLAG="--no-split"; shift ;;
    --keep-temp) KEEP_TEMP=1; shift ;;
    --review)    REVIEW=1; shift ;;
    --docx)      DOCX=1; shift ;;
    --emphasis)  EMPHASIS=1; DOCX=1; shift ;;
    --notes)     NOTES=1; shift ;;
    -h|--help)   usage; exit 0 ;;
    -*) echo "unknown flag: $1" >&2; exit 2 ;;
    *)  OUTPUT_FILE="$1"; shift ;;
  esac
done

if [[ ! -d "$INPUT_DIR" ]]; then
  echo "not a directory: $INPUT_DIR" >&2
  exit 1
fi

INPUT_DIR="$(cd "$INPUT_DIR" && pwd)"
[[ -z "$OUTPUT_FILE" ]] && OUTPUT_FILE="$INPUT_DIR/speechify.txt"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP_DIR="$INPUT_DIR/_book_tmp"
mkdir -p "$TMP_DIR"

cleanup() {
  if [[ $KEEP_TEMP -eq 0 && -n "${TMP_DIR:-}" && -d "$TMP_DIR" ]]; then
    rm -rf "$TMP_DIR"
  fi
}
trap cleanup EXIT INT TERM

# The photos' long side, in pixels, for OCR. At 4000 Vision read lines of a
# curled page it skipped at 2000, and misread fewer quote marks and letters,
# in about the same time; at 6000 it took several times as long.
PHOTO_SIZE="${BOOKSHOT_PHOTO_SIZE:-4000}"

echo "==> converting source photos to JPG in $TMP_DIR"
shopt -s nullglob nocaseglob
src_files=( "$INPUT_DIR"/*.heic "$INPUT_DIR"/*.jpg "$INPUT_DIR"/*.jpeg "$INPUT_DIR"/*.png )
shopt -u nullglob nocaseglob

if [[ ${#src_files[@]} -eq 0 ]]; then
  echo "no HEIC/JPG/PNG files found in $INPUT_DIR" >&2
  exit 1
fi

# Stem collisions (e.g. foo.HEIC + foo.jpg) resolve via the file-existence
# check below — first encountered wins, the second is silently skipped.
count=0
for f in "${src_files[@]}"; do
  base="$(basename "$f")"
  stem="${base%.*}"
  out="$TMP_DIR/${stem}.jpg"
  if [[ ! -f "$out" ]]; then
    # shrink a bigger photo; never enlarge a smaller one (sips -Z would)
    long_side="$(sips -g pixelWidth -g pixelHeight "$f" 2>/dev/null \
      | awk '/pixel(Width|Height)/ { if ($2 > m) m = $2 } END { print m + 0 }')"
    resize=()
    if (( long_side == 0 || long_side > PHOTO_SIZE )); then resize=(-Z "$PHOTO_SIZE"); fi
    if ! sips -s format jpeg ${resize[@]+"${resize[@]}"} "$f" --out "$out" > /dev/null; then
      echo "    failed to convert: $f" >&2
      exit 1
    fi
  fi
  count=$((count+1))
done
echo "    $count photos"

echo "==> running Vision OCR"
RAW="$TMP_DIR/_raw.txt"
SWIFT_LOG="$TMP_DIR/_swift.log"
: > "$RAW"
: > "$SWIFT_LOG"

# Build ocr.swift once and reuse it: `swift ocr.swift` compiles it again for
# every photo, without optimizing (about 1.6 s a photo, against 0.5 s built).
# Kept in the user's cache folder, named by the script's contents, so an
# edited script is built afresh. If building fails, run it the old way.
OCR=(swift "$SCRIPT_DIR/ocr.swift")
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/Library/Caches}/bookshot"
OCR_BIN="$CACHE_DIR/ocr-$(shasum "$SCRIPT_DIR/ocr.swift" | cut -c1-12)"
if [[ -x "$OCR_BIN" ]]; then
  OCR=("$OCR_BIN")
elif mkdir -p "$CACHE_DIR" 2>/dev/null \
    && swiftc -O "$SCRIPT_DIR/ocr.swift" -o "$OCR_BIN.tmp" 2>>"$SWIFT_LOG" \
    && mv "$OCR_BIN.tmp" "$OCR_BIN"; then
  OCR=("$OCR_BIN")
fi

# natural-sort the converted jpgs so page2 < page10
jpgs=()
while IFS= read -r line; do
  jpgs+=("$line")
done < <(printf '%s\n' "$TMP_DIR"/*.jpg | LC_ALL=C sort -V)

i=0
for f in "${jpgs[@]}"; do
  i=$((i+1))
  printf "\r    page %d/%d" "$i" "$count"
  base="$(basename "$f")"
  echo "===== $base =====" >> "$RAW"
  if ! "${OCR[@]}" "$f" $SPLIT_FLAG >> "$RAW" 2>>"$SWIFT_LOG"; then
    echo ""
    echo "    OCR failed on $base — see $SWIFT_LOG" >&2
    exit 1
  fi
done
echo ""

echo "==> cleaning up text for Speechify"
# notes on the photos (pages missing, repeated, to retake), shown at the end
PHOTO_NOTES="$TMP_DIR/_photo_notes.txt"
python3 "$SCRIPT_DIR/clean.py" "$RAW" "$OUTPUT_FILE" "$PHOTO_NOTES"

if [[ $REVIEW -eq 1 ]]; then
  if ! python3 "$SCRIPT_DIR/review.py" "$OUTPUT_FILE"; then
    echo "    review pass had errors — output kept at $OUTPUT_FILE" >&2
  fi
fi

if [[ $EMPHASIS -eq 1 ]]; then
  # Writes a sidecar next to the .txt; docx_out.py picks it up automatically.
  if ! python3 "$SCRIPT_DIR/emphasis.py" "$OUTPUT_FILE"; then
    echo "    emphasis pass had errors — continuing without italics" >&2
  fi
fi

DOCX_FILE=""
if [[ $DOCX -eq 1 ]]; then
  echo "==> writing .docx"
  DOCX_FILE="${OUTPUT_FILE%.*}.docx"
  python3 "$SCRIPT_DIR/docx_out.py" "$OUTPUT_FILE" "$DOCX_FILE"
fi

HTML_FILE=""
if [[ $NOTES -eq 1 ]]; then
  echo "==> writing rich text and creating an Apple Note"
  HTML_FILE="${OUTPUT_FILE%.*}.html"
  if ! python3 "$SCRIPT_DIR/rich_out.py" "$OUTPUT_FILE" --notes; then
    echo "    Apple Notes step failed; the rich text is still in $HTML_FILE" >&2
  fi
fi

if [[ -s "$PHOTO_NOTES" ]]; then
  echo ""
  echo "==> check these photos"
  sed 's/^/    /' "$PHOTO_NOTES"
fi

echo ""
echo "done. output: $OUTPUT_FILE"
# `if`, not `[[ ]] &&`: as the last command, a false test would become the
# script's exit status and make a good run look failed
if [[ -n "$DOCX_FILE" ]]; then echo "            $DOCX_FILE"; fi
if [[ -n "$HTML_FILE" ]]; then echo "            $HTML_FILE"; fi
if [[ $REVIEW -eq 0 ]] && command -v claude > /dev/null 2>&1; then
  echo "tip: add --review to have Claude fix the typos and quote marks left (a few minutes)"
fi
