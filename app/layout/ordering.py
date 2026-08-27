"""Reading Order Reconstruction: orders blocks in natural logical reading sequence."""

from typing import List
from app.core.blocks import BaseBlock
from app.layout.columns import ColumnDetector
from app.layout.detector import LayoutDetector

class ReadingOrderReconstructor:
    """Sorts AST blocks into true human reading order across multi-column pages."""

    def __init__(self, page_width: float, page_height: float):
        self.page_width = page_width
        self.page_height = page_height
        self.column_detector = ColumnDetector(page_width)
        self.layout_detector = LayoutDetector(page_width, page_height)

    def reconstruct_order(self, blocks: List[BaseBlock]) -> List[BaseBlock]:
        if not blocks:
            return []

        # 1. Filter noise
        cleaned_blocks = self.layout_detector.filter_noise_blocks(blocks)
        if not cleaned_blocks:
            return []

        # 2. Detect column structure
        col_count, gutter_x = self.column_detector.detect_columns(cleaned_blocks)
        self.column_detector.assign_column_indices(cleaned_blocks, col_count, gutter_x)

        if col_count == 1 or gutter_x is None:
            # Single column: sort by top coordinate y0 with slight tolerance
            sorted_blocks = sorted(cleaned_blocks, key=lambda b: (round(b.bbox.y0, 1), round(b.bbox.x0, 1)))
        else:
            # Two-column layout:
            # Find spanning top blocks (e.g., Title, Abstract spanning full width)
            top_spanning: List[BaseBlock] = []
            col0_blocks: List[BaseBlock] = []
            col1_blocks: List[BaseBlock] = []
            bottom_spanning: List[BaseBlock] = []

            # A spanning block occupies > 70% of page width
            span_thresh = self.page_width * 0.70

            for b in cleaned_blocks:
                is_spanning = (b.bbox.width >= span_thresh) or (b.bbox.x0 < self.page_width * 0.35 and b.bbox.x1 > self.page_width * 0.65)
                if is_spanning:
                    if b.bbox.y0 < self.page_height * 0.35:
                        top_spanning.append(b)
                    else:
                        bottom_spanning.append(b)
                elif b.column_index == 1:
                    col1_blocks.append(b)
                else:
                    col0_blocks.append(b)

            # Sort each group vertically
            top_spanning.sort(key=lambda b: (round(b.bbox.y0, 1), round(b.bbox.x0, 1)))
            col0_blocks.sort(key=lambda b: (round(b.bbox.y0, 1), round(b.bbox.x0, 1)))
            col1_blocks.sort(key=lambda b: (round(b.bbox.y0, 1), round(b.bbox.x0, 1)))
            bottom_spanning.sort(key=lambda b: (round(b.bbox.y0, 1), round(b.bbox.x0, 1)))

            sorted_blocks = top_spanning + col0_blocks + col1_blocks + bottom_spanning

        # Update order_index
        for idx, b in enumerate(sorted_blocks):
            b.order_index = idx

        return sorted_blocks
