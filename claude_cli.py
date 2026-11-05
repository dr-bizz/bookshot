#!/usr/bin/env python3
"""Shared plumbing for the optional `claude -p` passes.

Both the typo review and the emphasis pass ask Claude for a JSON array and have
to cope with the model wrapping it in prose or a code fence, so that parsing
lives here rather than in each pass.
"""
import json
import re
import subprocess

TIMEOUT_SECS = 240


def call_claude(prompt: str, timeout: int = TIMEOUT_SECS) -> tuple[str, str]:
    """Run `claude -p` headlessly. Returns (stdout, error_msg);
    error_msg is empty on success."""
    try:
        result = subprocess.run(
            ["claude", "-p"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return "", "claude CLI not found"
    except subprocess.TimeoutExpired:
        return "", f"timeout after {timeout}s"
    if result.returncode != 0:
        msg = f"exit {result.returncode}"
        if result.stderr:
            msg += f": {result.stderr.strip()[:200]}"
        return "", msg
    return result.stdout, ""


def parse_json_array(raw: str) -> list:
    """Pull a JSON array out of a model response, tolerating fences and prose.
    Returns [] if nothing parses as an array."""
    raw = raw.strip()
    candidates = [raw]

    fence = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", raw, re.DOTALL)
    if fence:
        candidates.append(fence.group(1))

    start, end = raw.find("["), raw.rfind("]")
    if start != -1 and end > start:
        candidates.append(raw[start : end + 1])

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            return data
    return []
