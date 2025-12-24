from __future__ import annotations

from utils.chunking import _build_units, chunk_document
from utils.config import ChunkingConfig


def test_chunking_respect_headings_false_forces_document_section():
    md = "# A\n\npara\n\n## B\n\ntext\n"
    config = ChunkingConfig(
        max_tokens=1000,
        overlap_tokens=0,
        min_chunk_tokens=1,
        preserve_code_blocks=True,
        respect_headings=False,
    )
    chunks = chunk_document(md, config)
    assert chunks
    assert all(c["section_path"] == "Document" for c in chunks)


def test_chunking_respect_headings_true_splits_sections():
    md = "# A\n\npara\n\n## B\n\ntext\n"
    config = ChunkingConfig(
        max_tokens=1000,
        overlap_tokens=0,
        min_chunk_tokens=1,
        preserve_code_blocks=True,
        respect_headings=True,
    )
    chunks = chunk_document(md, config)
    paths = {c["section_path"] for c in chunks}
    assert "A" in paths
    assert "A > B" in paths


def test_chunking_preserve_code_blocks_flag_changes_unitization():
    lines = ["```python", "a=1", "", "b=2", "```"]
    preserved = _build_units(lines, preserve_code_blocks=True)
    not_preserved = _build_units(lines, preserve_code_blocks=False)
    assert len(preserved) == 1
    assert len(not_preserved) > 1

