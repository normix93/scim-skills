"""Helpers to read the plain-text RFCs 7643 and 7644: page cleanup, sections, JSON figures.

The RFC text itself is not redistributed by this repository: tools/fetch_rfcs.py downloads it into a cache
directory (default .cache/rfc, git-ignored) and the generators extract facts from it.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(os.environ.get("SCIM_RFC_DIR", ROOT / ".cache" / "rfc"))
SOURCES = {
    "7643": ["https://www.rfc-editor.org/rfc/rfc7643.txt",
             "https://raw.githubusercontent.com/ysoftwareab/know-your-ietf-well/refs/rsync/rfcs/rfc7643.txt"],
    "7644": ["https://www.rfc-editor.org/rfc/rfc7644.txt",
             "https://raw.githubusercontent.com/ysoftwareab/know-your-ietf-well/refs/rsync/rfcs/rfc7644.txt"],
}


def rfc_path(num: str) -> Path:
    return CACHE / f"rfc{num}.txt"


def fetch(num: str) -> Path:
    """Download the RFC into the cache if it is not there yet; returns the path."""
    p = rfc_path(num)
    if p.exists() and p.stat().st_size > 100_000:
        return p
    CACHE.mkdir(parents=True, exist_ok=True)
    last = None
    for url in SOURCES[num]:
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                data = r.read()
            if len(data) > 100_000:
                p.write_bytes(data)
                return p
        except Exception as e:  # try the next mirror
            last = e
    raise RuntimeError(f"cannot download RFC {num}: {last}")


def clean(text: str, num: str) -> list[str]:
    """Lines without page footers/headers and form feeds."""
    out = []
    for line in text.replace("\r", "").split("\n"):
        if "\f" in line:
            line = line.replace("\f", "")
            if not line.strip():
                continue
        if re.match(r"^Hunt, et al\.\s+Standards Track\s+\[Page \d+\]\s*$", line):
            continue
        if re.match(rf"^RFC {num}\s{{2,}}.+\s{{2,}}September 2015\s*$", line):
            continue
        out.append(line)
    return out


def load(num: str) -> list[str]:
    return clean(fetch(num).read_text(encoding="utf-8", errors="replace"), num)


def section(lines: list[str], start: str, end: str | None) -> list[str]:
    """Lines from the heading that starts with `start` (e.g. '8.7.1.') up to the heading `end`."""
    i = next(k for k, l in enumerate(lines) if l.startswith(start + "  "))
    j = len(lines)
    if end:
        j = next(k for k, l in enumerate(lines) if k > i and l.startswith(end + "  "))
    return lines[i:j]


def json_blocks(text: str) -> list[tuple[int, object]]:
    """Every top-level JSON object/array in `text` that parses (strings may contain line breaks)."""
    found, i, n = [], 0, len(text)
    while i < n:
        ch = text[i]
        if ch in "{[":
            depth, instr, esc, j = 0, False, False, i
            while j < n:
                c = text[j]
                if instr:
                    if esc:
                        esc = False
                    elif c == "\\":
                        esc = True
                    elif c == '"':
                        instr = False
                elif c == '"':
                    instr = True
                elif c in "{[":
                    depth += 1
                elif c in "}]":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            blob = text[i:j + 1]
            try:
                found.append((i, json.loads(blob, strict=False)))
                i = j + 1
                continue
            except ValueError:
                pass
        i += 1
    return found
