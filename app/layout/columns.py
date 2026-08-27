"""Column Layout Analyzer: detects 1-column vs 2-column vs multi-column layouts."""

from typing import List, Tuple, Optional
from app.core.blocks import BaseBlock

class ColumnDetector:
    """Detects multi-column structure and assigns blocks to columns."""

    def __init__(self, page_width: float):
        self.page_width = page_width

    def detect_columns(self, blocks: List[BaseBlock]) -> Tuple[int, Optional[float]]:
        """
        Analyzes block horizontal positions to determine column count and gutter x-coordinate.
        Returns: (column_count, gutter_x_split)
        """
        if len(blocks) < 4:
            return (1, None)

        mid_x = self.page_width / 2.0
        left_blocks = 0
        right_blocks = 0
        spanning_blocks = 0

        left_bound = self.page_width * 0.45
        right_bound = self.page_width * 0.55

        for b in blocks:
            # Check if block spans across the middle margin
            if b.bbox.x0 < left_bound and b.bbox.x1 > right_bound:
                spanning_blocks += 1
            elif b.bbox.x1 <= right_bound:
                left_blocks += 1
            elif b.bbox.x0 >= left_bound:
                right_blocks += 1

        total_side_blocks = left_blocks + right_blocks
        if total_side_blocks >= 4 and left_blocks >= 2 and right_blocks >= 2:
            if left_blocks / total_side_blocks > 0.20 and right_blocks / total_side_blocks > 0.20:
                return (2, mid_x)

        return (1, None)

    def assign_column_indices(self, blocks: List[BaseBlock], column_count: int, gutter_x: Optional[float]) -> None:
        """Assigns column_index (0 for left/full-width, 1 for right column) to each block."""
        if column_count <= 1 or gutter_x is None:
            for b in blocks:
                b.column_index = 0
            return

        for b in blocks:
            if b.bbox.x0 >= gutter_x - (self.page_width * 0.05):
                b.column_index = 1
            else:
                # Full spanning block or left column
                b.column_index = 0
