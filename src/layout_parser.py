"""Layout Parser: Renders 300 DPI pages, classifies regions, crops components, and generates Draft Skeleton Markdown."""

from __future__ import annotations
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from PIL import Image
import pymupdf as fitz  # PyMuPDF

from config import (
    PAGES_DIR, CROPS_MATH_DIR, CROPS_TABLES_DIR, CROPS_CHARTS_DIR,
    RENDER_DPI, OUTPUT_DIR
)
from app.utils.logging import get_logger

logger = get_logger("LayoutParser")

class LayoutParser:
    """Analyzes document layout, crops visual regions, and builds draft skeleton."""

    def __init__(self, dpi: int = RENDER_DPI):
        self.dpi = dpi

    def render_pdf_page(self, doc: fitz.Document, page_num: int, output_path: Path) -> Tuple[float, float, int, int]:
        """Renders a PDF page to a 300 DPI image."""
        page = doc.load_page(page_num - 1)
        rect = page.rect
        zoom = self.dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pix.save(str(output_path))
        return (rect.width, rect.height, pix.width, pix.height)

    def crop_region(
        self,
        page_img_path: Path,
        bbox: Tuple[float, float, float, float],
        page_w_pt: float,
        page_h_pt: float,
        out_crop_path: Path,
        padding_pt: float = 6.0
    ) -> bool:
        """Crops a bounding box area from the rendered page image."""
        try:
            if not page_img_path.exists():
                return False

            with Image.open(page_img_path) as img:
                img_w, img_h = img.size
                scale_x = img_w / page_w_pt if page_w_pt > 0 else 1.0
                scale_y = img_h / page_h_pt if page_h_pt > 0 else 1.0

                x0 = max(0, int((bbox[0] - padding_pt) * scale_x))
                y0 = max(0, int((bbox[1] - padding_pt) * scale_y))
                x1 = min(img_w, int((bbox[2] + padding_pt) * scale_x))
                y1 = min(img_h, int((bbox[3] + padding_pt) * scale_y))

                if x1 <= x0 or y1 <= y0:
                    return False

                cropped = img.crop((x0, y0, x1, y1)).copy()

            out_crop_path.parent.mkdir(parents=True, exist_ok=True)
            cropped.save(str(out_crop_path), "PNG")
            return True
        except Exception as e:
            logger.error(f"Crop failed for {out_crop_path.name}: {e}")
            return False

    def is_math_block(self, text: str) -> bool:
        """Checks if text contains mathematical operators/syntax."""
        symbols = {"\\sum", "\\int", "\\frac", "\\sqrt", "\\alpha", "\\beta", "\\lambda", "\\theta", "=", "+", "-", "^", "_", "softmax", "attention"}
        count = sum(1 for s in symbols if s in text.lower())
        return count >= 2 or bool(re.search(r"(\b[a-zA-Z]\s*=\s*[\d\w]|\\frac|\\sqrt)", text))

    def is_table_block(self, text: str) -> bool:
        """Checks if text looks like tabular data with column alignments."""
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if len(lines) >= 3 and any("\t" in l or "   " in l for l in lines):
            return True
        return bool(re.match(r"^Table\s+\d+", text, re.IGNORECASE))

    def is_chart_or_figure(self, text: str) -> bool:
        """Checks if block is a chart/figure caption or visual noise block."""
        return bool(re.match(r"^(Figure|Fig\.)\s+\d+", text.strip(), re.IGNORECASE))

    def parse_document(self, pdf_path: str | Path) -> Dict[str, Any]:
        """
        Executes Phase 1:
        1. Renders pages to 300 DPI.
        2. Extracts layout blocks.
        3. Crops math, tables, charts to temp directories.
        4. Emits draft_skeleton.md with placeholders.
        """
        pdf_file = Path(pdf_path).resolve()
        if not pdf_file.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        doc = fitz.open(str(pdf_file))
        try:
            total_pages = len(doc)
            logger.info(f"Parsing {pdf_file.name} ({total_pages} pages) at {self.dpi} DPI...")

            skeleton_chunks: List[str] = []
            crops_metadata: Dict[str, Dict[str, Any]] = {}

            for p_idx in range(total_pages):
                page_num = p_idx + 1
                page_img_file = PAGES_DIR / f"page_{page_num}.png"
                page_w, page_h, img_w, img_h = self.render_pdf_page(doc, page_num, page_img_file)

                page = doc.load_page(p_idx)
                page_dict = page.get_text("blocks")

                for b_idx, block in enumerate(page_dict):
                    # block tuple: (x0, y0, x1, y1, text, block_no, block_type)
                    bbox = (block[0], block[1], block[2], block[3])
                    text = block[4].strip() if len(block) > 4 else ""

                    if not text:
                        continue

                    # 1. Check if Figure / Chart
                    if self.is_chart_or_figure(text):
                        placeholder = f"{{{{CHART_PAGE_{page_num}_ID_{b_idx}}}}}"
                        crop_file = CROPS_CHARTS_DIR / f"chart_p{page_num}_b{b_idx}.png"
                        self.crop_region(page_img_file, bbox, page_w, page_h, crop_file)
                        crops_metadata[placeholder] = {
                            "type": "chart",
                            "page": page_num,
                            "crop_path": str(crop_file),
                            "text_hint": text,
                            "bbox": bbox
                        }
                        skeleton_chunks.append(f"\n{placeholder}\n")

                    # 2. Check if Table
                    elif self.is_table_block(text):
                        placeholder = f"{{{{TABLE_PAGE_{page_num}_ID_{b_idx}}}}}"
                        crop_file = CROPS_TABLES_DIR / f"table_p{page_num}_b{b_idx}.png"
                        self.crop_region(page_img_file, bbox, page_w, page_h, crop_file)
                        crops_metadata[placeholder] = {
                            "type": "table",
                            "page": page_num,
                            "crop_path": str(crop_file),
                            "text_hint": text,
                            "bbox": bbox
                        }
                        skeleton_chunks.append(f"\n{placeholder}\n")

                    # 3. Check if Math Block
                    elif self.is_math_block(text) and len(text.split()) < 25:
                        placeholder = f"{{{{MATH_PAGE_{page_num}_ID_{b_idx}}}}}"
                        crop_file = CROPS_MATH_DIR / f"math_p{page_num}_b{b_idx}.png"
                        self.crop_region(page_img_file, bbox, page_w, page_h, crop_file)
                        crops_metadata[placeholder] = {
                            "type": "math",
                            "page": page_num,
                            "crop_path": str(crop_file),
                            "text_hint": text,
                            "bbox": bbox
                        }
                        skeleton_chunks.append(f"\n{placeholder}\n")

                    # 4. Standard Text Block (Headings, Paragraphs)
                    else:
                        if re.match(r"^(\d+(\.\d+)*|[A-Z]\.)\s+[A-Z]", text):
                            skeleton_chunks.append(f"## {text}\n")
                        else:
                            skeleton_chunks.append(f"{text}\n\n")

            draft_skeleton = "".join(skeleton_chunks)
            skeleton_file = OUTPUT_DIR / "draft_skeleton.md"
            skeleton_file.write_text(draft_skeleton, encoding="utf-8")
            logger.info(f"Draft skeleton generated: {skeleton_file} with {len(crops_metadata)} visual placeholders.")

            return {
                "skeleton_path": str(skeleton_file),
                "draft_skeleton": draft_skeleton,
                "crops_metadata": crops_metadata,
                "total_pages": total_pages
            }
        finally:
            doc.close()
