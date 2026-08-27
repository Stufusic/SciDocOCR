from __future__ import annotations
import pymupdf as fitz
from typing import Optional, Tuple
from pathlib import Path
from app.core.blocks import BoundingBox
from app.core.exceptions import PDFProcessingError


class PDFRenderer:
    """Renders PDF pages and crops regions to image files or bytes."""

    def __init__(self, doc: fitz.Document):
        self.doc = doc

    def render_page_to_bytes(self, page_index: int, dpi: int = 150) -> bytes:
        if page_index < 0 or page_index >= len(self.doc):
            raise PDFProcessingError(f"Page index {page_index} out of bounds.")
        page = self.doc[page_index]
        matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        return pix.tobytes("png")

    def render_page_to_file(self, page_index: int, output_path: str, dpi: int = 150) -> str:
        data = self.render_page_to_bytes(page_index, dpi=dpi)
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "wb") as f:
            f.write(data)
        return str(out.resolve())

    def crop_region_to_file(
        self, page_index: int, bbox: BoundingBox, output_path: str, dpi: int = 200, padding_pt: float = 4.0
    ) -> str:
        """Crops a specific bounding box (e.g. formula or table) to an image file."""
        if page_index < 0 or page_index >= len(self.doc):
            raise PDFProcessingError(f"Page index {page_index} out of bounds.")
        page = self.doc[page_index]
        rect = fitz.Rect(
            max(0, bbox.x0 - padding_pt),
            max(0, bbox.y0 - padding_pt),
            min(page.rect.width, bbox.x1 + padding_pt),
            min(page.rect.height, bbox.y1 + padding_pt)
        )
        matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        pix = page.get_pixmap(matrix=matrix, clip=rect, alpha=False)
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        pix.save(str(out.resolve()))
        return str(out.resolve())
