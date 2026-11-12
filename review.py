#!/usr/bin/env python3
"""Optional AI review pass: ask Claude Code to spot OCR typos and propose fixes.

Runs via `claude -p` (Claude Code headless mode) — uses the user's existing
Claude Code subscription, not separate API billing.

The text is split into chapter chunks (by ALL-CAPS headings) and each chunk is
sent in parallel. The model returns a JSON array of {"find": ..., "replace": ...}
pairs so it never has to regenerate the text itself, which keeps responses
small and minimizes content-filter exposure.

Each fix is applied only when its `find` string matches exactly once.
"""
import concurrent.futures
import re
import sys
from pathlib import Path

import claude_cli
import textblocks

PROMPT = """\
You are reviewing OCR'd text from a printed book that will be played back by a
text-to-speech app (Speechify). Spot only OBVIOUS OCR mistakes and propose
literal text fixes.

OUTPUT FORMAT
Output ONLY a JSON array. No prose, no markdown fences. Each element is:
{"find": "<exact substring in the text, including a few surrounding words for uniqueness>",
 "replace": "<corrected substring>"}

If no fixes, output: []

WHAT TO FIX
- Missing spaces between words ("monthsof" -> "months of", "hourto" -> "hour to").
- Misread characters ("naneuver" -> "maneuver", "s best" -> "is best", "avorite" -> "favorite").
- Garbled words clearly produced by OCR.
- Two words run together that should be separate.
- Missing or wrong quotation marks around dialogue. OCR often drops a quote
  mark or reads it as another character: "?", "!", "*", "'", "i" or "i." where
  a closing or opening " belongs. A stray "i" stuck to the last word, even a
  name, is that mark, not a letter of the word ("about Terry Pascali" ending
  a question -> "about Terry Pascal?\"").
  ("projects?\n" ending a line of dialogue -> "projects.\"",
   "*What's up, boss? Bobby's voice" -> "\"What's up, boss?\" Bobby's voice",
   "It's fantastic news, Bob answered" -> "It's fantastic news,\" Bob answered").
- A hyphen used where the book has a dash between two phrases
  ("careful-almost paranoid-about" -> "careful—almost paranoid—about",
   "Dani- -for being" -> "Dani—for being"). Leave real compound words alone
  ("self-assessment", "mess-maker", "fourth-quarter", "team-building").
- The end mark of a line of dialogue. OCR often reads the "?" before a
  closing quote as "." and the other way round: use "?" where the quoted
  sentence is plainly a question ("How about this afternoon instead." ->
  "How about this afternoon instead?") and "." where it is plainly a
  statement. A dash before a closing quote ("arrogant—\" He seemed") belongs
  only where the speaker is cut off mid-sentence; after a finished sentence
  it is a misread period.
- A sentence that starts with a lowercase letter right after a period
  ("smart. when every" -> "smart. When every"). A quote that follows a
  comma may go on lowercase; leave it.

WHAT NOT TO FIX
- Do NOT replace a real word that makes sense where it stands with another
  real word, even one you'd expect more ("civic stuff" stays). Fix a word
  only when it isn't a word, or plainly doesn't fit the sentence.
- Do NOT rewrite passages.
- Do NOT change wording, tone, or meaning.
- Do NOT remove or add information.
- Do NOT correct grammar, spelling that's intentional, or other capitalization choices.
- Do NOT touch proper names unless a letter is plainly misread ("Matthev" -> "Matthew").
- In ALL-CAPS headings, fix only a missing space or a dash; never reword them.

LINE BREAKS
Never add, remove or move a line break. Each line is one paragraph and must
stay one paragraph, even when it looks like two paragraphs were run together:
fix the quote marks and punctuation in place on the same line.

UNIQUENESS RULE
Each `find` must appear exactly once in the document. Include surrounding
context (5-10 words) so the match is unambiguous.

TEXT TO REVIEW (between BEGIN/END markers):

BEGIN
"""

PROMPT_SUFFIX = "\nEND\n"

TIMEOUT_SECS = claude_cli.TIMEOUT_SECS
MAX_WORKERS = 4


def parse_fixes(raw: str) -> list[dict]:
    """Keep only well-formed {"find", "replace"} objects."""
    return [
        d for d in claude_cli.parse_json_array(raw)
        if isinstance(d, dict) and "find" in d and "replace" in d
    ]


def review_chunk(idx: int, total: int, chunk: str) -> tuple[int, list[dict], str]:
    prompt = PROMPT + chunk + PROMPT_SUFFIX
    raw, err = claude_cli.call_claude(prompt)
    if err:
        return idx, [], err
    if not raw:
        return idx, [], "empty response"
    fixes = parse_fixes(raw)
    return idx, fixes, "ok"


def split_long_chunks(chunks: list[str], budget: int = textblocks.CHUNK_TARGET_CHARS) -> list[str]:
    """Cut any chunk far over budget at paragraph breaks. A long chapter with
    no ALL-CAPS heading inside it (39k chars in one test book) otherwise goes
    out as one prompt, and the model finds far fewer typos in it."""
    out: list[str] = []
    for chunk in chunks:
        if len(chunk) <= budget * 3 // 2:
            out.append(chunk)
            continue
        piece = ""
        for para in chunk.split("\n\n"):
            if piece and len(piece) + len(para) + 2 > budget:
                out.append(piece)
                piece = para
            else:
                piece = f"{piece}\n\n{para}" if piece else para
        if piece:
            out.append(piece)
    return out


def apply_fixes(text: str, fixes: list[dict]) -> tuple[str, int, int]:
    """Applies all fixes against the ORIGINAL text. Each fix's `find` must
    occur exactly once. Overlapping edits are dropped (later fix loses)."""
    edits: list[tuple[int, int, str]] = []  # (start, end, replacement)
    skipped = 0
    for fix in fixes:
        find = fix.get("find")
        replace = fix.get("replace")
        if not isinstance(find, str) or not isinstance(replace, str) or not find:
            skipped += 1
            continue
        # A fix inside one paragraph that also splits it (to undo a merged
        # paragraph) still carries a real typo fix: keep the fix, drop the split.
        if "\n" not in find and "\n" in replace:
            replace = re.sub(r"\s*\n+\s*", " ", replace)
        # keeps the text's blocks lined up with clean.py's .blocks.json
        if find.count("\n") != replace.count("\n"):
            skipped += 1
            continue
        if text.count(find) != 1:
            skipped += 1
            continue
        start = text.find(find)
        edits.append((start, start + len(find), replace))

    edits.sort()
    accepted: list[tuple[int, int, str]] = []
    last_end = -1
    for start, end, repl in edits:
        if start < last_end:
            skipped += 1
            continue
        accepted.append((start, end, repl))
        last_end = end

    new_text = text
    for start, end, repl in reversed(accepted):
        new_text = new_text[:start] + repl + new_text[end:]
    return new_text, len(accepted), skipped


def main() -> int:
    if len(sys.argv) != 2:
        sys.stderr.write("usage: review.py <text-file>\n")
        return 2
    target = Path(sys.argv[1])
    text = target.read_text(encoding="utf-8")
    chunks = split_long_chunks(textblocks.split_into_chunks(text))
    print(f"==> AI review pass ({len(text):,} chars in {len(chunks)} chunks)")

    all_fixes: list[dict] = []
    fail_count = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [
            ex.submit(review_chunk, i, len(chunks), c)
            for i, c in enumerate(chunks)
        ]
        for future in concurrent.futures.as_completed(futures):
            idx, fixes, status = future.result()
            if status == "ok":
                print(f"    chunk {idx + 1}/{len(chunks)}: {len(fixes)} fixes")
                all_fixes.extend(fixes)
            else:
                fail_count += 1
                print(f"    chunk {idx + 1}/{len(chunks)}: {status}")

    if not all_fixes:
        print(f"    no fixes applied (failures: {fail_count})")
        return 0

    new_text, applied, skipped = apply_fixes(text, all_fixes)
    if applied == 0:
        print(f"    {len(all_fixes)} fixes proposed, all skipped (couldn't match uniquely)")
        return 0

    target.write_text(new_text, encoding="utf-8")
    print(f"    applied {applied} fixes ({skipped} skipped, {fail_count} chunk failures)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
