"""OCR Router: dispatches to YOLO Crop-guided Vision OCR or Local Scientific OCR with parallel execution."""

import io
import concurrent.futures
from typing import List, Optional, Any, Tuple, Dict
from pathlib import Path
from PIL import Image

from app.ocr.base import BaseOCR
from app.ocr.local_ocr import LocalOCR
from app.markdown.parser import MarkdownParser
from app.models.layout_detector import DocumentLayoutDetector, LayoutRegion
from app.core.blocks import (
    BaseBlock, ParagraphBlock, FormulaBlock, HeadingBlock,
    TableBlock, FigureBlock, CaptionBlock, BlockType, BoundingBox
)
from app.utils import get_logger, clean_latex_math

logger = get_logger("OCRRouter")


def match_native_text_for_bbox(
    region_bbox: BoundingBox,
    native_blocks: List[BaseBlock],
    img_width: float,
    img_height: float,
    page_width: float,
    page_height: float
) -> str:
    """
    Finds native PDF digital text blocks that spatially intersect with this YOLO bounding box.
    Returns matched text instantly without requiring slow vision API round-trips.
    """
    if not native_blocks:
        return ""

    scale_x = img_width / max(1.0, page_width)
    scale_y = img_height / max(1.0, page_height)

    # Convert YOLO region bbox (in image pixels) to PDF points
    rx0 = region_bbox.x0 / scale_x
    ry0 = region_bbox.y0 / scale_y
    rx1 = region_bbox.x1 / scale_x
    ry1 = region_bbox.y1 / scale_y

    matched_items = []
    for b in native_blocks:
        bx = b.bbox
        overlap_x0 = max(rx0, bx.x0)
        overlap_y0 = max(ry0, bx.y0)
        overlap_x1 = min(rx1, bx.x1)
        overlap_y1 = min(ry1, bx.y1)

        if overlap_x1 > overlap_x0 and overlap_y1 > overlap_y0:
            overlap_area = (overlap_x1 - overlap_x0) * (overlap_y1 - overlap_y0)
            b_area = max(1.0, (bx.x1 - bx.x0) * (bx.y1 - bx.y0))
            if (overlap_area / b_area) >= 0.30:
                t = (getattr(b, "text", "") or getattr(b, "raw_text", "") or "").strip()
                if t and t not in {"<pad>", "<eos>", "<unk>"}:
                    matched_items.append((bx.y0, bx.x0, t))

    if not matched_items:
        return ""

    matched_items.sort(key=lambda item: (item[0], item[1]))
    return "\n\n".join(item[2] for item in matched_items)


class OCRRouter:
    """Routes OCR tasks with high-speed YOLO bounding-box crop extraction and parallel LLM transcription."""

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
        # 2. HIGH-SPEED YOLO BOUNDING BOX CROPPING & PARALLEL LLM OCR
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
                    logger.info(f"Page {page_num}: YOLO detected {len(crop_results)} bounding boxes. Fast-routing (tables/figures preserved, native text matched, math in parallel)...")
                    
                    ordered_results: Dict[int, List[BaseBlock]] = {}
                    llm_tasks: List[Tuple[int, LayoutRegion, bytes, str, str, str]] = []  # (order_idx, region, crop_bytes, saved_path, block_type, hint)

                    img_w, img_h = float(pil_img.width), float(pil_img.height)

                    for idx, (region, crop_bytes, saved_img_path) in enumerate(crop_results, 1):
                        lbl = region.label.lower()
                        bbox = region.bbox
                        conf = region.confidence

                        # A. Figure: Direct image in blocks/ (0ms, NO LLM upload!)
                        if lbl == "figure":
                            img_path = saved_img_path or f"blocks/block_{idx:03d}_{doc_stem}_figure.png"
                            ordered_results[idx] = [FigureBlock(
                                id=f"fig_p{page_num}_{idx}",
                                bbox=bbox,
                                source_page=page_num,
                                confidence=conf,
                                image_path=img_path,
                                caption=f"Figure on page {page_num}"
                            )]

                        # B. Table: Direct image in blocks/ (0ms, NO LLM upload!)
                        elif lbl == "table":
                            tbl_path = saved_img_path or f"blocks/block_{idx:03d}_{doc_stem}_table.png"
                            ordered_results[idx] = [TableBlock(
                                id=f"table_p{page_num}_{idx}",
                                bbox=bbox,
                                source_page=page_num,
                                confidence=conf,
                                image_crop_path=tbl_path,
                                rows=[],
                                caption=f"Table on page {page_num}"
                            )]

                        # C. Formula: High-precision LaTeX math (Parallel LLM Vision OCR)
                        elif lbl == "formula":
                            native_hint = match_native_text_for_bbox(bbox, blocks, img_w, img_h, page_width, page_height)
                            llm_tasks.append((idx, region, crop_bytes, saved_img_path, "formula", native_hint))

                        # D. Section Title / Heading: Native text fast-match
                        elif lbl in ("title", "section-header"):
                            native_text = match_native_text_for_bbox(bbox, blocks, img_w, img_h, page_width, page_height)
                            if native_text:
                                level = 1 if bbox.y0 < (page_height * 0.3) else 2
                                ordered_results[idx] = [HeadingBlock(
                                    id=f"heading_p{page_num}_{idx}",
                                    bbox=bbox,
                                    source_page=page_num,
                                    confidence=conf,
                                    level=level,
                                    text=native_text.lstrip("#").strip()
                                )]
                            else:
                                llm_tasks.append((idx, region, crop_bytes, saved_img_path, "text", ""))

                        # E. Text / Paragraph / Caption: Native text fast-match
                        else:
                            native_text = match_native_text_for_bbox(bbox, blocks, img_w, img_h, page_width, page_height)
                            if native_text:
                                ordered_results[idx] = [ParagraphBlock(
                                    id=f"p_p{page_num}_{idx}",
                                    bbox=bbox,
                                    source_page=page_num,
                                    confidence=conf,
                                    text=native_text
                                )]
                            else:
                                llm_tasks.append((idx, region, crop_bytes, saved_img_path, "text", ""))

                    # Execute any needed LLM tasks concurrently in parallel!
                    if llm_tasks:
                        logger.info(f"Page {page_num}: Executing {len(llm_tasks)} vision transcription tasks in parallel (max_workers=6)...")
                        max_workers = min(6, len(llm_tasks))
                        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                            future_to_task = {
                                executor.submit(
                                    self.ai_router.ocr_crop_to_markdown,
                                    crop_bytes,
                                    b_type,
                                    hint
                                ): (order_idx, region, saved_path, b_type)
                                for (order_idx, region, crop_bytes, saved_path, b_type, hint) in llm_tasks
                            }

                            for future in concurrent.futures.as_completed(future_to_task):
                                order_idx, region, saved_path, b_type = future_to_task[future]
                                try:
                                    res_text = future.result()
                                    bbox = region.bbox
                                    conf = region.confidence

                                    if b_type == "formula":
                                        clean_math = clean_latex_math(res_text) or res_text
                                        if clean_math:
                                            ordered_results[order_idx] = [FormulaBlock(
                                                id=f"formula_p{page_num}_{order_idx}",
                                                bbox=bbox,
                                                source_page=page_num,
                                                confidence=conf,
                                                latex=clean_math,
                                                image_crop_path=saved_path,
                                                is_inline=False
                                            )]
                                    else:
                                        parsed = self.markdown_parser.parse_page_blocks(res_text, page_number=page_num)
                                        if parsed:
                                            for pb in parsed:
                                                pb.bbox = bbox
                                            ordered_results[order_idx] = parsed
                                        else:
                                            ordered_results[order_idx] = [ParagraphBlock(
                                                id=f"p_p{page_num}_{order_idx}",
                                                bbox=bbox,
                                                source_page=page_num,
                                                confidence=conf,
                                                text=res_text
                                            )]
                                except Exception as task_err:
                                    logger.warning(f"Page {page_num}: Parallel LLM crop task {order_idx} failed: {task_err}")

                    # Assemble all blocks in strict layout order
                    assembled_blocks: List[BaseBlock] = []
                    for k in sorted(ordered_results.keys()):
                        assembled_blocks.extend(ordered_results[k])

                    if assembled_blocks:
                        logger.info(f"Page {page_num}: Assembled {len(assembled_blocks)} blocks in layout order.")
                        return assembled_blocks

            except Exception as e:
                logger.warning(f"Page {page_num}: YOLO crop-guided extraction encountered an issue ({e}). Trying fallback...")

        # -------------------------------------------------------------
        # 3. WHOLE-PAGE VISION OCR (Fallback when YOLO has no boxes)
        # -------------------------------------------------------------
        if self.ai_router is not None and image_bytes:
            try:
                engine_name = "Local Model" if self.mode == "local_only" else "Online AI"
                logger.info(f"Page {page_num}: Running fallback page-level Vision OCR via {engine_name}...")
                
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
