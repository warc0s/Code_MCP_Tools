"""
Chunking utilities for splitting markdown into manageable passages.
"""

from __future__ import annotations

import hashlib
import re
from typing import Dict, Iterable, List, Tuple

from utils.config import ChunkingConfig


TOKEN_PATTERN = re.compile(r"\w+|\S")
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)")


def fingerprint_text(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def count_tokens(text: str) -> int:
    return len(TOKEN_PATTERN.findall(text))


def _tail_with_overlap(text: str, overlap_tokens: int) -> str:
    if overlap_tokens <= 0:
        return ""
    tokens = TOKEN_PATTERN.findall(text)
    if not tokens:
        return ""
    tail = tokens[-overlap_tokens:]
    return " ".join(tail)


def _split_sections(markdown: str, respect_headings: bool = True) -> List[Tuple[str, List[str]]]:
    if not respect_headings:
        return [("Document", markdown.splitlines())]

    lines = markdown.splitlines()
    sections: List[Tuple[str, List[str]]] = []
    section_stack: List[str] = []
    current_lines: List[str] = []
    current_path = "Document"

    def flush():
        nonlocal current_lines, current_path
        if current_lines:
            sections.append((current_path, current_lines))
            current_lines = []

    for line in lines:
        heading = HEADING_PATTERN.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            title = heading.group(2).strip()
            while len(section_stack) >= level:
                section_stack.pop()
            section_stack.append(title)
            current_path = " > ".join(section_stack)
            current_lines.append(line)
        else:
            current_lines.append(line)

    flush()
    return sections


def _build_units(lines: List[str], preserve_code_blocks: bool = True) -> List[str]:
    if not preserve_code_blocks:
        units: List[str] = []
        buffer: List[str] = []

        def flush():
            nonlocal buffer
            text = "\n".join(buffer).strip("\n")
            if text:
                units.append(text)
            buffer = []

        for raw_line in lines:
            line = raw_line.rstrip("\n")
            stripped = line.strip()
            if stripped == "":
                buffer.append(line)
                flush()
            else:
                buffer.append(line)
        if buffer:
            flush()
        return [unit for unit in units if unit.strip()]

    units: List[str] = []
    buffer: List[str] = []
    inside_code = False

    def flush():
        nonlocal buffer
        text = "\n".join(buffer).strip("\n")
        if text:
            units.append(text)
        buffer = []

    for raw_line in lines:
        line = raw_line.rstrip("\n")
        stripped = line.strip()
        if stripped.startswith("```"):
            if inside_code:
                buffer.append(line)
                flush()
                inside_code = False
            else:
                if buffer:
                    flush()
                buffer = [line]
                inside_code = True
        elif not inside_code and stripped == "":
            buffer.append(line)
            flush()
        else:
            buffer.append(line)

    if buffer:
        flush()

    return [unit for unit in units if unit.strip()]


def chunk_document(markdown: str, config: ChunkingConfig) -> List[Dict[str, str | int]]:
    chunks: List[Dict[str, str | int]] = []
    position = 0

    for section_path, lines in _split_sections(markdown, respect_headings=config.respect_headings):
        units = _build_units(lines, preserve_code_blocks=config.preserve_code_blocks)
        if not units:
            continue

        current_texts: List[str] = []
        current_tokens = 0

        for unit in units:
            unit_tokens = count_tokens(unit)
            if (
                current_texts
                and current_tokens + unit_tokens > config.max_tokens
                and current_tokens >= config.min_chunk_tokens
            ):
                chunk_text = "\n\n".join(current_texts).strip()
                if chunk_text:
                    chunks.append(
                        {
                            "text": chunk_text,
                            "section_path": section_path,
                            "position": position,
                            "fingerprint": fingerprint_text(chunk_text),
                        }
                    )
                    position += 1
                    tail = _tail_with_overlap(chunk_text, config.overlap_tokens)
                    current_texts = [tail] if tail else []
                    current_tokens = count_tokens("\n\n".join(current_texts)) if current_texts else 0
            current_texts.append(unit)
            current_tokens += unit_tokens

        if current_texts:
            chunk_text = "\n\n".join(current_texts).strip()
            if chunk_text:
                chunks.append(
                    {
                        "text": chunk_text,
                        "section_path": section_path,
                        "position": position,
                        "fingerprint": fingerprint_text(chunk_text),
                    }
                )
                position += 1

    return chunks


__all__ = ["chunk_document", "fingerprint_text", "count_tokens"]
