"""Markdown Chunk Merger: Merges and normalizes multiple processed Markdown chunks into a single document."""

from __future__ import annotations
import re
from typing import List
from app.services.mineru_service import ChunkResult
from app.utils.logging import get_logger

logger = get_logger("MarkdownChunkMerger")

class MarkdownChunkMerger:
    """Merges chunk results into a continuous, well-structured scientific document."""

    def merge_chunks(self, chunk_results: List[ChunkResult], doc_title: str = "Scientific Document") -> str:
        """
        Combines processed markdown text from all chunks, adds page markers,
        and standardizes image references and annotation callouts.
        """
        if not chunk_results:
            return ""

        merged_sections: List[str] = []

        for chunk in sorted(chunk_results, key=lambda c: c.chunk_index):
            text = chunk.markdown_text.strip()
            if not text:
                continue

            # Add chunk/page boundary comment
            boundary = f"\n\n<!-- Page Range: {chunk.start_page} - {chunk.end_page} (Chunk {chunk.chunk_index}) -->\n"
            merged_sections.append(boundary + text)

        full_document = "\n\n".join(merged_sections).strip()

        # Clean excessive blank lines (more than 2 in a row)
        full_document = re.sub(r"\n{3,}", "\n\n", full_document)

        logger.info(f"Merged {len(chunk_results)} chunks into single Markdown document ({len(full_document)} chars).")
        return full_document
