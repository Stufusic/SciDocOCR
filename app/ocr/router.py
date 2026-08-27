"""OCR Router: dispatches to Online AI Vision/Markdown reconstruction or Local Scientific OCR."""

from typing import List, Optional, Any
from pathlib import Path
from app.ocr.base import BaseOCR
from app.ocr.local_ocr import LocalOCR
from app.markdown.parser import MarkdownParser
from app.core.blocks import BaseBlock, ParagraphBlock, FormulaBlock, HeadingBlock, BlockType
from app.utils.logging import get_logger

logger = get_logger("OCRRouter")

class OCRRouter:
    """Routes OCR tasks according to user mode (Offline / Online / Auto)."""

    def __init__(self, mode: str = "auto", ai_router: Optional[Any] = None):
        self.mode = mode.lower()  # auto, local_only, online_only
        self.ai_router = ai_router
        self.local_ocr = LocalOCR()
        self.markdown_parser = MarkdownParser()

    def process_page(
        self,
        blocks: List[BaseBlock],
        page_index: int,
        page_width: float = 595.0,
        page_height: float = 842.0,
        image_bytes: Optional[bytes] = None,
        preview_image_path: Optional[str] = None,
        image_dir: Optional[Path] = None
    ) -> List[BaseBlock]:
        page_num = page_index + 1
        logger.info(f"Processing page {page_num} with OCR mode: {self.mode}")

        # Local OCR fallback engine
        local_engine = LocalOCR(page_width, page_height)

        # -------------------------------------------------------------
        # AI-POWERED EXTRACTION (Local Model mineru / Online AI)
        # -------------------------------------------------------------
        if self.ai_router is not None:
            engine_name = "Local Model" if self.mode == "local_only" else "Online AI"
            try:
                logger.info(f"Page {page_num}: Sending page content to {engine_name} for structured Markdown extraction...")
                
                # Prepare raw page representation (filter matrix noise)
                text_parts = []
                matrix_noise = {"<pad>", "<eos>", "<unk>", "-", ".", ","}
                for b in blocks:
                    t = (getattr(b, "text", "") or getattr(b, "raw_text", "") or "").strip()
                    if t and t.lower() not in matrix_noise and len(t) > 1:
                        text_parts.append(t)
                raw_page_text = "\n\n".join(text_parts)

                # Guard against context length overflow in local models
                if len(raw_page_text) > 6000:
                    raw_page_text = raw_page_text[:6000]

                if raw_page_text:
                    # Call active AI engine (qwen/qwen3.5-9b in LM Studio or Online API)
                    md_result = self.ai_router.document_to_markdown(raw_page_text)
                    if md_result and len(md_result.strip()) > 10:
                        parsed_blocks = self.markdown_parser.parse_page_blocks(md_result, page_number=page_num)
                        if parsed_blocks:
                            logger.info(f"Page {page_num}: Successfully extracted {len(parsed_blocks)} blocks via {engine_name} Markdown.")
                            return parsed_blocks
            except Exception as e:
                logger.warning(f"Page {page_num}: {engine_name} extraction failed ({e}). Falling back to Local OCR Engine.")

        # -------------------------------------------------------------
        # LOCAL OCR PROCESSING (Layout-First + Formula + Table + Chart Filter)
        # -------------------------------------------------------------
        return local_engine.process_page_blocks(
            blocks=blocks,
            page_index=page_index,
            image_bytes=image_bytes,
            preview_image_path=preview_image_path,
            image_dir=image_dir
        )
