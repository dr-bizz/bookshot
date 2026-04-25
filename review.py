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
import json
import re
import subprocess
import sys
from pathlib import Path

if len(sys.argv) != 2:
    sys.stderr.write("usage: review.py <text-file>\n")
    sys.exit(2)

TARGET = Path(sys.argv[1])

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

WHAT NOT TO FIX
- Do NOT rewrite passages.
- Do NOT change wording, tone, or meaning.
- Do NOT remove or add information.
- Do NOT correct grammar, spelling that's intentional, or capitalization choices.
- Do NOT touch ALL-CAPS headings or proper names.

UNIQUENESS RULE
Each `find` must appear exactly once in the document. Include surrounding
context (5-10 words) so the match is unambiguous.

TEXT TO REVIEW (between BEGIN/END markers):

BEGIN
"""

PROMPT_SUFFIX = "\nEND\n"

CHUNK_TARGET_CHARS = 8000  # rough size budget per Claude call
TIMEOUT_SECS = 240
MAX_WORKERS = 4


def split_into_chunks(text: str) -> list[str]:
    """Split on ALL-CAPS heading lines, then group small chapters together so
    each chunk is roughly CHUNK_TARGET_CHARS."""
    lines = text.splitlines()
    chapters: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        s = line.strip()
        if s and not s.startswith(('"', "'", "“", "‘", "—", "–", "-")):
            letters = [c for c in s if c.isalpha()]
            is_chapter = (
                len(letters) >= 4
                and all(c.isupper() for c in letters)
                and len(s) <= 60
            )
        else:
            is_chapter = False
        if is_chapter and current:
            chapters.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        chapters.append(current)

    # group small chapters together up to CHUNK_TARGET_CHARS
    chunks: list[str] = []
    buffer: list[str] = []
    buffer_size = 0
    for chap in chapters:
        chap_text = "\n".join(chap)
        if buffer and buffer_size + len(chap_text) > CHUNK_TARGET_CHARS:
            chunks.append("\n".join(buffer))
            buffer = []
            buffer_size = 0
        buffer.append(chap_text)
        buffer_size += len(chap_text) + 1
    if buffer:
        chunks.append("\n".join(buffer))
    return chunks


def call_claude(prompt: str) -> tuple[str, str]:
    """Returns (stdout, error_msg). error_msg is empty on success."""
    try:
        result = subprocess.run(
            ["claude", "-p"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECS,
        )
    except FileNotFoundError:
        return "", "claude CLI not found"
    except subprocess.TimeoutExpired:
        return "", f"timeout after {TIMEOUT_SECS}s"
    if result.returncode != 0:
        msg = f"exit {result.returncode}"
        if result.stderr:
            msg += f": {result.stderr.strip()[:200]}"
        return "", msg
    return result.stdout, ""


def parse_fixes(raw: str) -> list[dict]:
    raw = raw.strip()
    candidates: list[str] = []
    # 1. plain JSON
    candidates.append(raw)
    # 2. fenced code block
    fence_match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", raw, re.DOTALL)
    if fence_match:
        candidates.append(fence_match.group(1))
    # 3. outermost-bracket slice
    start = raw.find("[")
    end = raw.rfind("]")
    if start != -1 and end > start:
        candidates.append(raw[start : end + 1])

    for c in candidates:
        try:
            data = json.loads(c)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict) and "find" in d and "replace" in d]
    return []


def review_chunk(idx: int, total: int, chunk: str) -> tuple[int, list[dict], str]:
    prompt = PROMPT + chunk + PROMPT_SUFFIX
    raw, err = call_claude(prompt)
    if err:
        return idx, [], err
    if not raw:
        return idx, [], "empty response"
    fixes = parse_fixes(raw)
    return idx, fixes, "ok"


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


def main():
    text = TARGET.read_text(encoding="utf-8")
    chunks = split_into_chunks(text)
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
        return

    new_text, applied, skipped = apply_fixes(text, all_fixes)
    if applied == 0:
        print(f"    {len(all_fixes)} fixes proposed, all skipped (couldn't match uniquely)")
        return

    TARGET.write_text(new_text, encoding="utf-8")
    print(f"    applied {applied} fixes ({skipped} skipped, {fail_count} chunk failures)")


if __name__ == "__main__":
    main()
