"""Table OCR & Detection for Scientific Documents."""

import re
from typing import List, Tuple, Optional
from app.core.blocks import BaseBlock, TableBlock, ParagraphBlock, BlockType

class TableOCR:
    """Detects tabular data from text layout blocks and builds structured TableBlocks."""

    def __init__(self):
        pass

    def is_tabular_text(self, text: str) -> Tuple[bool, List[List[str]]]:
        """
        Analyzes if a multi-line text block has consistent column alignments.
        Returns: (is_table, parsed_rows)
        """
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if len(lines) < 2:
            return (False, [])

        parsed_rows: List[List[str]] = []
        cell_counts = []

        for line in lines:
            # Check for delimiter patterns: tabs, pipes, or 2+ consecutive spaces
            if "\t" in line:
                cells = [c.strip() for c in line.split("\t") if c.strip()]
            elif "|" in line:
                cells = [c.strip() for c in line.split("|") if c.strip()]
            else:
                cells = [c.strip() for c in re.split(r"\s{2,}", line) if c.strip()]

            if len(cells) >= 2:
                parsed_rows.append(cells)
                cell_counts.append(len(cells))

        if len(parsed_rows) >= 2 and len(parsed_rows) == len(lines):
            # Check if all rows have roughly similar number of columns
            median_cols = sorted(cell_counts)[len(cell_counts) // 2]
            if median_cols >= 2:
                return (True, parsed_rows)

        return (False, [])

    def detect_and_convert_blocks(self, blocks: List[BaseBlock]) -> List[BaseBlock]:
        """Converts tabular paragraphs into TableBlocks."""
        result_blocks: List[BaseBlock] = []

        for b in blocks:
            if b.block_type == BlockType.PARAGRAPH and isinstance(b, ParagraphBlock):
                is_table, rows = self.is_tabular_text(b.text)
                if is_table:
                    result_blocks.append(TableBlock(
                        id=b.id,
                        bbox=b.bbox,
                        source_page=b.source_page,
                        order_index=b.order_index,
                        column_index=b.column_index,
                        confidence=0.90,
                        rows=rows,
                        header_rows=1
                    ))
                else:
                    result_blocks.append(b)
            else:
                result_blocks.append(b)

        return result_blocks
