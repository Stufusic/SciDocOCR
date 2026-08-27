"""Local OCR Pipeline: Combines layout-first analysis, chart noise elimination & cropping, formula extraction, and table recognition."""

from typing import List, Optional
from pathlib import Path
from app.ocr.base import BaseOCR
from app.ocr.formula_ocr import FormulaOCR
from app.ocr.table_ocr import TableOCR
from app.layout.ordering import ReadingOrderReconstructor
from app.models.layout_detector import DocumentLayoutDetector
from app.models.latex_extractor import LatexExtractor
from app.processors.layout_cleaner import LayoutCleaner
from app.processors.block_validator import BlockValidator
from app.core.blocks import BaseBlock

class LocalOCR(BaseOCR):
    """Local Scientific OCR engine with Layout-First processing, Chart Cropping, and Noise Elimination."""

    def __init__(self, page_width: float = 595.0, page_height: float = 842.0):
        self.page_width = page_width
        self.page_height = page_height
        self.layout_detector = DocumentLayoutDetector()
        self.layout_cleaner = LayoutCleaner()
        self.order_reconstructor = ReadingOrderReconstructor(page_width, page_height)
        self.formula_ocr = FormulaOCR()
        self.latex_extractor = LatexExtractor()
        self.table_ocr = TableOCR()
        self.block_validator = BlockValidator()

    def process_page_blocks(
        self,
        blocks: List[BaseBlock],
        page_index: int,
        image_bytes: Optional[bytes] = None,
        preview_image_path: Optional[str] = None,
        image_dir: Optional[Path] = None
    ) -> List[BaseBlock]:
        page_num = page_index + 1

        # 1. Layout-First Classification (Headings, Captions)
        routed_blocks = self.layout_detector.classify_and_route_blocks(
            blocks, page_num=page_num, preview_image_path=preview_image_path
        )

        # 2. Clean Chart & Matrix Noise FIRST:
        #    - Crops complex charts/visualizations directly to FigureBlock
        #    - Separates and preserves CaptionBlock ("Figure X:...")
        #    - Completely removes internal chart noise tokens so they are NEVER processed by Formula/Table OCR
        chart_cleaned_blocks = self.layout_cleaner.clean_chart_noise(
            routed_blocks,
            page_num=page_num,
            page_w_pt=self.page_width,
            page_h_pt=self.page_height,
            preview_image_path=preview_image_path,
            image_dir=image_dir
        )

        # 3. Reconstruct reading order based on column layout
        ordered_blocks = self.order_reconstructor.reconstruct_order(chart_cleaned_blocks)

        # 4. Detect and extract formulas from remaining text
        formula_blocks = self.formula_ocr.detect_and_convert_blocks(ordered_blocks)

        # 5. Stitch multi-line & complex mathematical equations
        stitched_blocks = self.latex_extractor.stitch_fragmented_formulas(formula_blocks)

        # 6. Detect and extract tables
        table_blocks = self.table_ocr.detect_and_convert_blocks(stitched_blocks)

        # 7. Validate and correct false formulas / syntax
        final_blocks = self.block_validator.validate_and_correct_blocks(table_blocks)

        return final_blocks
