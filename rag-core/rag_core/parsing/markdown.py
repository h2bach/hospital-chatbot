from __future__ import annotations

import re
from dataclasses import dataclass, field


PAGE_RE = re.compile(r"^\s*<!--\s*page:\s*(\d+)\s*-->\s*$", re.I)
OFFSET_RE = re.compile(r"^\s*<!--\s*source-offset:\s*(\d+)\s*[-:]\s*(\d+)\s*-->\s*$", re.I)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
LIST_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)(.+)$")
FAQ_RE = re.compile(r"^\s*(?:Q|Câu hỏi)\s*[:：]\s*(.+)$", re.I)


@dataclass(slots=True)
class MarkdownNode:
    node_type: str
    text: str
    heading_path: list[str]
    page_start: int | None
    page_end: int | None
    offset_start: int
    offset_end: int
    level: int = 0
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class ParsedMarkdown:
    title: str
    nodes: list[MarkdownNode]
    normalized_markdown: str


def parse_markdown(source: str, fallback_title: str = "Untitled") -> ParsedMarkdown:
    """Parse Markdown into a structure-preserving tree without third-party dependencies.

    The scanner recognizes block structure, not fixed-size regex splitting. Page and
    source offset markers are carried as typed metadata on every content node.
    """
    lines = source.replace("\r\n", "\n").split("\n")
    heading_stack: list[str] = []
    current_page: int | None = None
    pending_offset: tuple[int, int] | None = None
    nodes: list[MarkdownNode] = []
    position = 0
    index = 0

    def add(node_type: str, text: str, start: int, end: int, level: int = 0) -> None:
        nonlocal pending_offset
        explicit = pending_offset
        nodes.append(MarkdownNode(
            node_type=node_type,
            text=text.strip(),
            heading_path=list(heading_stack),
            page_start=current_page,
            page_end=current_page,
            offset_start=explicit[0] if explicit else start,
            offset_end=explicit[1] if explicit else end,
            level=level,
        ))
        pending_offset = None

    while index < len(lines):
        line = lines[index]
        start = position
        position += len(line) + 1
        index += 1
        if match := PAGE_RE.match(line):
            current_page = int(match.group(1))
            continue
        if match := OFFSET_RE.match(line):
            pending_offset = (int(match.group(1)), int(match.group(2)))
            continue
        if not line.strip():
            continue
        if line.lstrip().startswith("```"):
            language = line.strip()[3:].strip()
            block: list[str] = []
            while index < len(lines) and not lines[index].lstrip().startswith("```"):
                block.append(lines[index])
                position += len(lines[index]) + 1
                index += 1
            if index < len(lines):
                position += len(lines[index]) + 1
                index += 1
            add("code", "\n".join(block), start, position, metadata_language(language))
            continue
        if match := HEADING_RE.match(line):
            level, heading = len(match.group(1)), match.group(2).strip()
            heading_stack[level - 1:] = [heading]
            add("heading", heading, start, position, level)
            continue
        if line.lstrip().startswith("|"):
            block = [line]
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                block.append(lines[index])
                position += len(lines[index]) + 1
                index += 1
            add("table", "\n".join(block), start, position)
            continue
        if LIST_RE.match(line):
            block = [line]
            while index < len(lines) and (LIST_RE.match(lines[index]) or lines[index].startswith(("  ", "\t"))):
                block.append(lines[index])
                position += len(lines[index]) + 1
                index += 1
            add("list", "\n".join(block), start, position)
            continue
        block = [line]
        faq = bool(FAQ_RE.match(line))
        while index < len(lines):
            candidate = lines[index]
            if not candidate.strip() or PAGE_RE.match(candidate) or OFFSET_RE.match(candidate) or HEADING_RE.match(candidate):
                break
            if candidate.lstrip().startswith(("```", "|")) or LIST_RE.match(candidate):
                break
            block.append(candidate)
            position += len(candidate) + 1
            index += 1
        add("faq" if faq else "paragraph", "\n".join(block), start, position)

    title = next((n.text for n in nodes if n.node_type == "heading" and n.level == 1), fallback_title)
    return ParsedMarkdown(title=title, nodes=nodes, normalized_markdown="\n".join(lines).strip() + "\n")


def metadata_language(language: str) -> int:
    # Kept as a level-neutral value; language remains in the source code fence.
    return 0

