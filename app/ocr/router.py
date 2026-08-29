"""OCR Router: dispatches to YOLO Crop-guided Vision OCR or Local Scientific OCR."""

import io
from typing import List, Optional, Any
from pathlib import Path
from PIL import Image

from app.ocr.base import BaseOCR
from app.ocr.local_ocr import LocalOCR
from app.markdown.parser import MarkdownParser
from app.models.layout_detector import DocumentLayoutDetector
from app.core.blocks import (
    BaseBlock, ParagraphBlock, FormulaBlock, HeadingBlock,
    TableBlock, FigureBlock, CaptionBlock, BlockType, BoundingBox
)
from app.utils import get_logger, clean_latex_math

logger = get_logger("OCRRouter")

class OCRRouter:
    """Routes OCR tasks with YOLO bounding-box crop extraction and unified LLM transcription."""

    def __init__(
        self,
        mode: str = "auto",
        ai_router: Optional[Any] = None,
        layout_detector: Optional[DocumentLayoutDetector] = None
    ):
        self.mode = mode.lower()  # auto, local_only, online_only
        self.ai_router = ai_router
        self.layout_detector = layout_detector or DocumentLayoutDetector()
        self.markdown_parser = MarkdownParser()

    def process_page(
        self,
        blocks: List[BaseBlock],
        page_index: int,
        page_width: float = 595.0,
        page_height: float = 842.0,
        image_bytes: Optional[bytes] = None,
        preview_image_path: Optional[str] = None,
        image_dir: Optional[Path] = None,
        blocks_dir: Optional[Path] = None,
        doc_stem: str = "doc",
        figure_blocks: Optional[List[BaseBlock]] = None
    ) -> List[BaseBlock]:
        page_num = page_index + 1
        logger.info(f"Processing page {page_num} with OCR mode: {self.mode}")

        local_engine = LocalOCR(page_width, page_height)

        # -------------------------------------------------------------
        # 1. LOAD PAGE IMAGE (For YOLO Bounding Box Detection & Cropping)
        # -------------------------------------------------------------
        pil_img = None
        if preview_image_path and Path(preview_image_path).exists():
            try:
                pil_img = Image.open(preview_image_path)
            except Exception:
                pil_img = None

        if pil_img is None and image_bytes:
            try:
                pil_img = Image.open(io.BytesIO(image_bytes))
            except Exception:
                pil_img = None

        # -------------------------------------------------------------
        # 2. YOLO BOUNDING BOX CROPPING & TARGETED LLM VISION OCR
        # -------------------------------------------------------------
        if self.ai_router is not None and pil_img is not None:
            engine_name = "Local Model" if self.mode == "local_only" else "Online AI"
            try:
                # Run YOLO detection and crop each region into blocks_dir
                crop_results = self.layout_detector.detect_and_crop_regions(
                    pil_img,
                    page_num=page_num,
                    doc_stem=doc_stem,
                    blocks_dir=blocks_dir,
                    image_dir=image_dir,
                    padding=6
                )

                if crop_results:
                    logger.info(f"Page {page_num}: YOLO detected {len(crop_results)} bounding boxes. Processing blocks (tables & figures preserved directly)...")
                    processed_blocks: List[BaseBlock] = []

                    for idx, (region, crop_bytes, saved_img_path) in enumerate(crop_results, 1):
                        lbl = region.label.lower()
                        bbox = region.bbox
                        conf = region.confidence

                        # A. Figure: Direct image path in blocks/ (NO LLM upload!)
                        if lbl == "figure":
                            img_path = saved_img_path or f"blocks/block_{idx:03d}_{doc_stem}_figure.png"
                            processed_blocks.append(FigureBlock(
                                id=f"fig_p{page_num}_{idx}",
                                bbox=bbox,
                                source_page=page_num,
                                confidence=conf,
                                image_path=img_path,
                                caption=f"Figure on page {page_num}"
                            ))

                        # B. Table: Direct image preservation in blocks/ (NO LLM upload!)
                        elif lbl == "table":
                            tbl_path = saved_img_path or f"blocks/block_{idx:03d}_{doc_stem}_table.png"
                            processed_blocks.append(TableBlock(
                                id=f"table_p{page_num}_{idx}",
                                bbox=bbox,
                                source_page=page_num,
                                confidence=conf,
                                image_crop_path=tbl_path,
                                rows=[],
                                caption=f"Table on page {page_num}"
                            ))

                        # C. Formula: Targeted LaTeX Math Transcription via LLM
                        elif lbl == "formula":
                            latex_raw = self.ai_router.ocr_crop_to_markdown(crop_bytes=crop_bytes, block_type="formula")
                            clean_math = clean_latex_math(latex_raw) or latex_raw
                            if clean_math:
                                processed_blocks.append(FormulaBlock(
                                    id=f"formula_p{page_num}_{idx}",
                                    bbox=bbox,
                                    source_page=page_num,
                                    confidence=conf,
                                    latex=clean_math,
                                    image_crop_path=saved_img_path,
                                    is_inline=False
                                ))

                        # D. Section Title / Heading
                        elif lbl in ("title", "section-header"):
                            heading_text = self.ai_router.ocr_crop_to_markdown(crop_bytes=crop_bytes, block_type="text")
                            clean_heading = heading_text.lstrip("#").strip()
                            level = 1 if bbox.y0 < (page_height * 0.3) else 2
                            if clean_heading:
                                processed_blocks.append(HeadingBlock(
                                    id=f"heading_p{page_num}_{idx}",
                                    bbox=bbox,
                                    source_page=page_num,
                                    confidence=conf,
                                    level=level,
                                    text=clean_heading
                                ))

                        # E. Text / Paragraph / Caption
                        else:
                            sec_text = self.ai_router.ocr_crop_to_markdown(crop_bytes=crop_bytes, block_type="text")
                            if sec_text:
                                parsed = self.markdown_parser.parse_page_blocks(sec_text, page_number=page_num)
                                if parsed:
                                    for pb in parsed:
                                        pb.bbox = bbox
                                        processed_blocks.append(pb)
                                else:
                                    processed_blocks.append(ParagraphBlock(
                                        id=f"p_p{page_num}_{idx}",
                                        bbox=bbox,
                                        source_page=page_num,
                                        confidence=conf,
                                        text=sec_text
                                    ))

                    if processed_blocks:
                        logger.info(f"Page {page_num}: Successfully assembled {len(processed_blocks)} blocks from YOLO cropped regions.")
                        return processed_blocks

            except Exception as e:
                logger.warning(f"Page {page_num}: YOLO crop-guided extraction encountered an issue ({e}). Trying fallback...")

        # -------------------------------------------------------------
        # 3. WHOLE-PAGE VISION OCR (Fallback when YOLO has no boxes)
        # -------------------------------------------------------------
        if self.ai_router is not None and image_bytes:
            try:
                engine_name = "Local Model" if self.mode == "local_only" else "Online AI"
                logger.info(f"Page {page_num}: Running fallback page-level Vision OCR via {engine_name}...")
                
                # Raw text hint
                text_parts = [
                    (getattr(b, "text", "") or getattr(b, "raw_text", "") or "").strip()
                    for b in blocks if len(getattr(b, "text", "") or "") > 1
                ]
                raw_page_text = "\n\n".join(text_parts)[:4000]

                md_result = self.ai_router.ocr_image_to_markdown(image_bytes=image_bytes, raw_text_hint=raw_page_text)
                if md_result and len(md_result.strip()) > 10:
                    parsed_blocks = self.markdown_parser.parse_page_blocks(md_result, page_number=page_num)
                    if parsed_blocks:
                        if figure_blocks:
                            parsed_blocks.extend(figure_blocks)
                        return parsed_blocks
            except Exception as e:
                logger.warning(f"Page {page_num}: Page-level Vision OCR fallback failed: {e}")

        # -------------------------------------------------------------
        # 4. LOCAL OCR PROCESSING (CV + Heuristics Fallback)
        # -------------------------------------------------------------
        return local_engine.process_page_blocks(
            blocks=blocks,
            page_index=page_index,
            image_bytes=image_bytes,
            preview_image_path=preview_image_path,
            image_dir=image_dir
        )
