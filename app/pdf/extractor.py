from __future__ import annotations
import pymupdf as fitz
from typing import List, Dict, Any, Tuple, Optional
from app.core.blocks import (
    BaseBlock, HeadingBlock, ParagraphBlock, FormulaBlock,
    TableBlock, FigureBlock, BoundingBox, BlockType
)
from app.core.exceptions import PDFProcessingError


class RawPDFSpan:
    def __init__(self, text: str, bbox: Tuple[float, float, float, float], size: float, flags: int, font: str):
        self.text = text
        self.bbox = bbox
        self.size = size
        self.flags = flags
        self.font = font
        self.is_bold = bool(flags & 2 or "bold" in font.lower())
        self.is_italic = bool(flags & 1 or "italic" in font.lower())


class PDFExtractor:
    """Extracts structured text blocks and images from a PDF page."""

    def __init__(self, doc: fitz.Document):
        self.doc = doc

    def extract_raw_blocks(self, page_index: int) -> List[Dict[str, Any]]:
        page = self.doc[page_index]
        # Text page dict format with detailed span information
        page_dict = page.get_text("dict", flags=fitz.TEXTFLAGS_SEARCH)
        return page_dict.get("blocks", [])

    def extract_page_blocks(self, page_index: int) -> List[BaseBlock]:
        """Extracts initial AST blocks from the PDF native text layer."""
        if page_index < 0 or page_index >= len(self.doc):
            raise PDFProcessingError(f"Page index {page_index} out of bounds.")

        page = self.doc[page_index]
        raw_blocks = self.extract_raw_blocks(page_index)
        extracted_blocks: List[BaseBlock] = []

        # First calculate median body font size
        font_sizes: List[float] = []
        for block in raw_blocks:
            if block.get("type") == 0:  # Text block
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        if span.get("text", "").strip():
                            font_sizes.append(span.get("size", 10.0))

        body_font_size = 10.0
        if font_sizes:
            font_sizes.sort()
            body_font_size = font_sizes[len(font_sizes) // 2]

        for b_idx, block in enumerate(raw_blocks):
            b_type = block.get("type", 0)
            bbox_tuple = block.get("bbox", (0, 0, 0, 0))
            bbox = BoundingBox.from_tuple(bbox_tuple)

            if b_type == 0:  # Text block
                lines = block.get("lines", [])
                full_text_lines = []
                max_size = 0.0
                has_bold = False

                for line in lines:
                    line_spans = []
                    for span in line.get("spans", []):
                        text = span.get("text", "")
                        size = span.get("size", body_font_size)
                        flags = span.get("flags", 0)
                        font = span.get("font", "")
                        if size > max_size:
                            max_size = size
                        if flags & 2 or "bold" in font.lower():
                            has_bold = True
                        line_spans.append(text)
                    line_text = "".join(line_spans).strip()
                    if line_text:
                        full_text_lines.append(line_text)

                if not full_text_lines:
                    continue

                combined_text = " ".join(full_text_lines)

                # Heuristic: Heading detection (significantly larger font or bold title)
                if max_size > body_font_size * 1.3 and len(combined_text) < 150:
                    level = 1 if max_size > body_font_size * 1.6 else 2
                    extracted_blocks.append(HeadingBlock(
                        bbox=bbox,
                        source_page=page_index + 1,
                        confidence=0.98,
                        level=level,
                        text=combined_text
                    ))
                else:
                    extracted_blocks.append(ParagraphBlock(
                        bbox=bbox,
                        source_page=page_index + 1,
                        confidence=0.95,
                        text=combined_text,
                        original_text=combined_text
                    ))

            elif b_type == 1:  # Image block
                extracted_blocks.append(FigureBlock(
                    bbox=bbox,
                    source_page=page_index + 1,
                    confidence=0.90,
                    caption="",
                    width_pt=bbox.width,
                    height_pt=bbox.height
                ))

        return extracted_blocks
