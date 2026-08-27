"""Layout Detector: analyzes margins, header/footer regions, and main text areas."""

from typing import List, Tuple
from app.core.blocks import BaseBlock, BoundingBox

class LayoutDetector:
    """Detects page layout zones (header, footer, margins, body)."""

    def __init__(self, page_width: float, page_height: float):
        self.page_width = page_width
        self.page_height = page_height
        # Standard margin boundaries (in points, 72 pt = 1 inch)
        self.header_cutoff = page_height * 0.08  # top 8%
        self.footer_cutoff = page_height * 0.92  # bottom 8%

    def is_header_or_footer(self, block: BaseBlock) -> bool:
        """Determines if a block is located in header or footer margin."""
        bbox = block.bbox
        # Top header region
        if bbox.y1 <= self.header_cutoff and bbox.height < 30:
            return True
        # Bottom footer region (page numbers, running footer)
        if bbox.y0 >= self.footer_cutoff and bbox.height < 30:
            return True
        return False

    def filter_noise_blocks(self, blocks: List[BaseBlock]) -> List[BaseBlock]:
        """Filters out zero-area or tiny artifact noise blocks."""
        cleaned = []
        for b in blocks:
            if b.bbox.width < 2 and b.bbox.height < 2:
                continue
            cleaned.append(b)
        return cleaned
