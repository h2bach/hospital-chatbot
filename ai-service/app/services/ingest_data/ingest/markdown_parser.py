"""
Markdown parser — Markdown -> ordered list of Sections.

Design:
    - Line-based scan over ATX headings (``#`` .. ``######``).
    - Each Section captures its heading, level, full heading path (ancestors),
      body text, and precise line range (for citations).
    - Fenced code blocks are respected so ``#`` inside code is not treated
      as a heading.
    - Content before the first heading becomes a preamble Section (level 0).

Why not a full AST library: we need exact source line numbers for traceable
citations, and the heading hierarchy is the only structure that matters for
chunking. A line scan gives both cheaply and deterministically.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")


@dataclass
class Section:
    """A heading and the body text that belongs to it (until the next heading)."""

    level: int                       # 1..6 for headings, 0 for preamble
    heading: str                     # heading text ("" for preamble)
    heading_path: list[str] = field(default_factory=list)  # ancestors + self
    body: str = ""                   # body text under this heading (no heading line)
    line_start: int = 0              # 1-indexed line of the heading (or first body line)
    line_end: int = 0                # 1-indexed last line of the body


def parse_markdown(text: str) -> list[Section]:
    """
    Parse markdown into an ordered list of Sections.

    Each section owns the text between its heading and the next heading of any
    level. heading_path lists ancestor headings from H1 down to the section's
    own heading.
    """
    lines = text.splitlines()
    sections: list[Section] = []

    # Stack of (level, heading) for building heading paths.
    stack: list[tuple[int, str]] = []

    # Preamble accumulator (content before first heading)
    current: Optional[Section] = None
    body_lines: list[str] = []
    body_first_line = 0

    in_fence = False

    def flush(end_line: int) -> None:
        nonlocal current, body_lines, body_first_line
        if current is None:
            # Preamble: only emit if it has non-whitespace content
            if any(ln.strip() for ln in body_lines):
                sec = Section(
                    level=0,
                    heading="",
                    heading_path=[],
                    body="\n".join(body_lines).strip("\n"),
                    line_start=body_first_line or 1,
                    line_end=end_line,
                )
                sections.append(sec)
        else:
            current.body = "\n".join(body_lines).strip("\n")
            current.line_end = end_line
            sections.append(current)
        body_lines = []
        body_first_line = 0

    for idx, line in enumerate(lines, start=1):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            if not body_lines:
                body_first_line = idx
            body_lines.append(line)
            continue

        heading_match = None if in_fence else _HEADING_RE.match(line)

        if heading_match:
            # Close the previous section (body ends on the line before this heading)
            flush(idx - 1)

            level = len(heading_match.group(1))
            heading = heading_match.group(2).strip()

            # Pop stack to parent level
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, heading))

            current = Section(
                level=level,
                heading=heading,
                heading_path=[h for _, h in stack],
                body="",
                line_start=idx,
                line_end=idx,
            )
        else:
            if not body_lines:
                body_first_line = idx
            body_lines.append(line)

    # Flush trailing content
    flush(len(lines))

    return sections


__all__ = ["Section", "parse_markdown"]
