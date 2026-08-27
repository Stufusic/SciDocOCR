"""Unit tests for MarkdownChunkMerger."""

import pytest
from app.markdown.merger import MarkdownChunkMerger
from app.services.mineru_service import ChunkResult

def test_markdown_chunk_merger_basic():
    merger = MarkdownChunkMerger()
    c1 = ChunkResult(
        chunk_index=1,
        start_page=1,
        end_page=4,
        markdown_text="# Section 1\nText on page 1-4.\n$$E=mc^2$$\n> 💡 **Mass-Energy** — Energy equals mass times c squared.",
        images_saved=["chunk_1_fig1.png"],
        success=True
    )
    c2 = ChunkResult(
        chunk_index=2,
        start_page=5,
        end_page=8,
        markdown_text="## Section 2\nText on page 5-8.\n![Fig](images/chunk_2_chart.png)",
        images_saved=["chunk_2_chart.png"],
        success=True
    )

    merged = merger.merge_chunks([c1, c2])

    assert "# Section 1" in merged
    assert "## Section 2" in merged
    assert "💡 **Mass-Energy**" in merged
    assert "chunk_2_chart.png" in merged
    assert "Page Range: 1 - 4" in merged
    assert "Page Range: 5 - 8" in merged
