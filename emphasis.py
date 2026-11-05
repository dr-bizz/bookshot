#!/usr/bin/env python3
"""Optional AI pass: mark the words a narrator would lean on.

Speechify's reader ignores SSML, markdown and document structure, but it does
audibly stress bold and italic runs in a .docx. This pass asks Claude which
words carry the stress in each sentence; docx_out.py renders them as italics.

Writes a JSON sidecar (<text-file>.emphasis.json) rather than touching the text,
so the .txt output stays byte-identical and the pass can be re-run or discarded.
"""
import concurrent.futures
import json
import sys
from pathlib import Path

import claude_cli
import textblocks

MAX_SPAN_WORDS = 6  # a narrator stresses a word or short phrase, not a sentence
MAX_WORKERS = 4

PROMPT = """\
You are preparing OCR'd text from a printed book for playback in a text-to-speech
app. The app audibly stresses italicized words. Your job is to pick the words a
skilled human narrator would lean on, so the reading doesn't sound flat.

OUTPUT FORMAT
Output ONLY a JSON array of strings. No prose, no markdown fences.
Each string is an EXACT substring of the text below, copied character for character.

If nothing needs emphasis, output: []

WHAT TO PICK
- The single word in a sentence that carries its point ("it was NEVER about the money").
- Contrasts and reversals ("not the what, but the WHY").
- Terms the author is defining or introducing for the first time.
- Words the author is clearly italicizing in the original for stress.

RULES
- Be sparing. At most one span per two or three sentences. Over-marking sounds
  unhinged when read aloud.
- Each span must be 1 to %d words. Never a whole sentence.
- Each span must appear EXACTLY ONCE in the text below. If a word repeats,
  either include enough surrounding words to make it unique, or skip it.
- Never pick words inside an ALL-CAPS heading.
- Copy substrings exactly, including punctuation and capitalization.

TEXT (between BEGIN/END markers):

BEGIN
""" % MAX_SPAN_WORDS

PROMPT_SUFFIX = "\nEND\n"


def parse_spans(raw: str) -> list[str]:
    """Extract the emphasis spans from a model response."""
    return [s for s in claude_cli.parse_json_array(raw) if isinstance(s, str) and s]


def usable_spans(text: str, spans) -> list[str]:
    """Drop spans that are too long, absent, or duplicated.

    Uniqueness is enforced later by docx_out.resolve_emphasis — this is the
    cheap sanity filter.
    """
    seen: set[str] = set()
    kept: list[str] = []
    for span in spans:
        if span in seen:
            continue
        if len(span.split()) > MAX_SPAN_WORDS:
            continue
        if span not in text:
            continue
        seen.add(span)
        kept.append(span)
    return kept


def mark_chunk(idx: int, chunk: str) -> tuple[int, list[str], str]:
    raw, err = claude_cli.call_claude(PROMPT + chunk + PROMPT_SUFFIX)
    if err:
        return idx, [], err
    if not raw:
        return idx, [], "empty response"
    return idx, usable_spans(chunk, parse_spans(raw)), "ok"


def sidecar_path(target: Path) -> Path:
    return target.with_suffix(target.suffix + ".emphasis.json")


def main() -> int:
    if len(sys.argv) != 2:
        sys.stderr.write("usage: emphasis.py <text-file>\n")
        return 2

    target = Path(sys.argv[1])
    text = target.read_text(encoding="utf-8")
    chunks = textblocks.split_into_chunks(text)
    print(f"==> emphasis pass ({len(text):,} chars in {len(chunks)} chunks)")

    all_spans: list[str] = []
    failures = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(mark_chunk, i, c) for i, c in enumerate(chunks)]
        for future in concurrent.futures.as_completed(futures):
            idx, spans, status = future.result()
            if status == "ok":
                print(f"    chunk {idx + 1}/{len(chunks)}: {len(spans)} spans")
                all_spans.extend(spans)
            else:
                failures += 1
                print(f"    chunk {idx + 1}/{len(chunks)}: {status}")

    spans = usable_spans(text, all_spans)
    out = sidecar_path(target)
    out.write_text(json.dumps(spans, indent=2), encoding="utf-8")
    print(f"    {len(spans)} spans written to {out.name} ({failures} chunk failures)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
