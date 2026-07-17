"""
MarkdownParser — Converts a markdown string into a flat list of DocumentNodes.

Each node carries:
  - type        : "heading" | "paragraph" | "table" | "code" | "list"
  - content     : plain text (no markdown syntax, no metadata injected)
  - heading_path: snapshot of the heading stack at the time this node was emitted
  - page        : page number from the nearest preceding <!-- page:N --> comment
  - level       : heading level (1-6) when type == "heading", else None

Page tracking convention:
    The upstream markdown generator must inject HTML comments of the form
        <!-- page:12 -->
    at each page boundary.  The parser detects these comments and updates
    the running page counter.  All nodes emitted after the comment inherit
    that page number.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from markdown_it import MarkdownIt

# Regex that matches the upstream page-boundary comment
_PAGE_COMMENT_RE = re.compile(r"<!--\s*page\s*:\s*(\d+)\s*-->", re.IGNORECASE)


@dataclass
class DocumentNode:
    """A single structural unit extracted from a markdown document."""

    type: str                          # paragraph | heading | table | code | list
    content: str                       # clean text (no markdown, no metadata)
    heading_path: list[str] = field(default_factory=list)
    page: Optional[int] = None
    level: Optional[int] = None        # only set for heading nodes


class MarkdownParser:
    """
    Parses a markdown string into a list of :class:`DocumentNode` objects.

    Usage::

        parser = MarkdownParser()
        nodes  = parser.parse(markdown_text)
    """

    def __init__(self) -> None:
        # "commonmark" preset — gives us clean, predictable token types.
        self._md = MarkdownIt("commonmark")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, markdown_text: str) -> list[DocumentNode]:
        """
        Parse *markdown_text* and return an ordered list of
        :class:`DocumentNode` instances, one per logical block.
        """
        tokens = self._md.parse(markdown_text)
        return self._extract_nodes(tokens)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_nodes(self, tokens: list) -> list[DocumentNode]:
        nodes: list[DocumentNode] = []

        # Mutable parsing state
        heading_stack: list[str] = []
        current_page: Optional[int] = None

        i = 0
        while i < len(tokens):
            token = tokens[i]

            # ── Page comment (HTML inline or block) ──────────────────
            if token.type in ("html_block", "html_inline"):
                page = self._detect_page_comment(token.content)
                if page is not None:
                    current_page = page
                i += 1
                continue

            # ── Heading ───────────────────────────────────────────────
            if token.type == "heading_open":
                level = int(token.tag[1])                  # h1→1, h2→2, …
                inline = tokens[i + 1] if i + 1 < len(tokens) else None
                title = inline.content if inline else ""

                # Trim the stack to (level-1) entries then push new title
                heading_stack = heading_stack[: level - 1]
                heading_stack.append(title)

                nodes.append(
                    DocumentNode(
                        type="heading",
                        content=title,
                        heading_path=list(heading_stack),
                        page=current_page,
                        level=level,
                    )
                )
                i += 3  # heading_open + inline + heading_close
                continue

            # ── Paragraph ─────────────────────────────────────────────
            if token.type == "paragraph_open":
                inline = tokens[i + 1] if i + 1 < len(tokens) else None
                content = inline.content if inline else ""

                # A paragraph-level <!-- page:N --> means update page, skip node
                page = self._detect_page_comment(content)
                if page is not None:
                    current_page = page
                    i += 3
                    continue

                if content.strip():
                    nodes.append(
                        DocumentNode(
                            type="paragraph",
                            content=content,
                            heading_path=list(heading_stack),
                            page=current_page,
                        )
                    )
                i += 3  # paragraph_open + inline + paragraph_close
                continue

            # ── Fenced code block ─────────────────────────────────────
            if token.type == "fence":
                content = token.content.strip()
                if content:
                    nodes.append(
                        DocumentNode(
                            type="code",
                            content=content,
                            heading_path=list(heading_stack),
                            page=current_page,
                        )
                    )
                i += 1
                continue

            # ── Table ─────────────────────────────────────────────────
            if token.type == "table_open":
                table_text, advance = self._extract_table(tokens, i)
                if table_text:
                    nodes.append(
                        DocumentNode(
                            type="table",
                            content=table_text,
                            heading_path=list(heading_stack),
                            page=current_page,
                        )
                    )
                i += advance
                continue

            # ── Bullet / ordered list ──────────────────────────────────
            if token.type in ("bullet_list_open", "ordered_list_open"):
                list_text, advance = self._extract_list(tokens, i)
                if list_text:
                    nodes.append(
                        DocumentNode(
                            type="list",
                            content=list_text,
                            heading_path=list(heading_stack),
                            page=current_page,
                        )
                    )
                i += advance
                continue

            i += 1

        return nodes

    # ------------------------------------------------------------------
    # Block-level extraction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_page_comment(text: str) -> Optional[int]:
        """Return page number if *text* contains a page comment, else None."""
        m = _PAGE_COMMENT_RE.search(text)
        return int(m.group(1)) if m else None

    @staticmethod
    def _extract_table(tokens: list, start: int) -> tuple[str, int]:
        """
        Collect all inline content between table_open … table_close.
        Returns (plain_text_rows, tokens_consumed).
        """
        rows: list[str] = []
        i = start + 1
        depth = 1
        while i < len(tokens) and depth > 0:
            t = tokens[i]
            if t.type == "table_open":
                depth += 1
            elif t.type == "table_close":
                depth -= 1
            elif t.type == "inline" and t.content.strip():
                rows.append(t.content.strip())
            i += 1
        return " | ".join(rows), i - start

    @staticmethod
    def _extract_list(tokens: list, start: int) -> tuple[str, int]:
        """
        Collect inline content from all list items.
        Returns (plain_text, tokens_consumed).
        """
        close_type = (
            "bullet_list_close"
            if tokens[start].type == "bullet_list_open"
            else "ordered_list_close"
        )
        items: list[str] = []
        i = start + 1
        depth = 1
        while i < len(tokens) and depth > 0:
            t = tokens[i]
            if t.type == tokens[start].type:
                depth += 1
            elif t.type == close_type:
                depth -= 1
            elif t.type == "inline" and t.content.strip():
                items.append(t.content.strip())
            i += 1
        return "\n".join(f"- {item}" for item in items), i - start
