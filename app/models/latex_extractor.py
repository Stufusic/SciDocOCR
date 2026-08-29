"""Dedicated Mathematical LaTeX Extractor and Formula Stitcher."""

from __future__ import annotations
import re
from pathlib import Path
from typing import Optional, List, Union
from PIL import Image

from app.core.blocks import FormulaBlock, ParagraphBlock, BaseBlock, BoundingBox
from app.ocr.formula_ocr import UNICODE_TO_LATEX
from app.utils.logging import get_logger

logger = get_logger("LatexExtractor")

class LatexExtractor:
    """Extracts and normalizes complex scientific LaTeX equations using UniMERNet or pix2tex."""

    def __init__(self):
        self.unimer_model = None
        self.pix2tex_model = None
        self._init_unimernet()
        if self.unimer_model is None:
            self._init_pix2tex()

    def _init_unimernet(self):
        """Initializes UniMERNet formula recognition engine if weights are present."""
        try:
            from app.utils.downloader import get_default_model_dir
            model_dir = get_default_model_dir()
            weights_candidates = [
                model_dir / "unimernet_base.pth",
                model_dir / "unimernet.pth",
                Path.home() / ".scidoc" / "models" / "unimernet_base.pth"
            ]
            for wp in weights_candidates:
                if wp.exists() and wp.stat().st_size > 500_000:
                    try:
                        import torch
                        from unimernet.model import UniMERNet
                        self.unimer_model = UniMERNet.from_pretrained(str(wp.parent))
                        self.unimer_model.eval()
                        logger.info(f"UniMERNet Formula OCR model loaded successfully from {wp}")
                        return
                    except Exception as load_err:
                        logger.debug(f"UniMERNet module load info: {load_err}")
        except Exception as e:
            logger.debug(f"UniMERNet check: {e}")

    def _init_pix2tex(self):
        """Initializes pix2tex (LaTeX-OCR) if installed."""
        try:
            from pix2tex.cli import LatexOCR
            self.pix2tex_model = LatexOCR()
            logger.info("pix2tex LaTeX-OCR model initialized successfully.")
        except Exception:
            self.pix2tex_model = None

    def predict(self, input_data: Union[Image.Image, str]) -> str:
        """
        Extracts LaTeX from an image crop or raw mathematical text string using internal UniMERNet / pix2tex.
        """
        if isinstance(input_data, Image.Image):
            if self.unimer_model is not None:
                try:
                    res = self.unimer_model(input_data)
                    if isinstance(res, str) and res.strip():
                        return self.normalize_equation(res)
                except Exception as unimer_err:
                    logger.debug(f"UniMERNet prediction error: {unimer_err}")

            if self.pix2tex_model is not None:
                try:
                    latex = self.pix2tex_model(input_data)
                    return self.normalize_equation(latex)
                except Exception as e:
                    logger.debug(f"pix2tex prediction failed: {e}")

        raw_str = str(input_data) if not isinstance(input_data, Image.Image) else ""
        return self.normalize_equation(raw_str)

    def normalize_equation(self, raw_latex: str) -> str:
        """Normalizes mathematical symbols, functions, and standard scientific formulas."""
        text = raw_latex.strip()
        if not text:
            return ""

        # 1. Replace unicode symbols
        for uni_char, latex_sym in UNICODE_TO_LATEX.items():
            text = text.replace(uni_char, f" {latex_sym} ")

        # 2. Standardize named mathematical functions
        known_functions = [
            "Attention", "MultiHead", "Concat", "softmax", "Softmax",
            "FFN", "LayerNorm", "ReLU", "sin", "cos", "tan", "log", "exp"
        ]
        for fn in known_functions:
            # Replace occurrences like Attention(Q, K, V) -> \text{Attention}(Q, K, V) if not already escaped
            pattern = rf"(?<!\\text\{{)\b{fn}\b"
            text = re.sub(pattern, rf"\\text{{{fn}}}", text)

        # 3. Fraction and Root fixups
        text = re.sub(r"sqrt\s*\(([^)]+)\)", r"\\sqrt{\1}", text)
        text = re.sub(r"\\sqrt\s*([a-zA-Z0-9])\b", r"\\sqrt{\1}", text)

        # Clean spaces
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def build_formula_block(
        self,
        latex: str,
        bbox: BoundingBox,
        page_num: int = 1,
        order_idx: int = 0,
        image_crop_path: Optional[str] = None
    ) -> FormulaBlock:
        """Creates a standardized FormulaBlock."""
        norm_latex = self.normalize_equation(latex)
        return FormulaBlock(
            bbox=bbox,
            source_page=page_num,
            order_index=order_idx,
            confidence=0.96,
            latex=norm_latex,
            raw_text=latex,
            is_inline=False,
            is_valid=True,
            image_crop_path=image_crop_path
        )

    def stitch_fragmented_formulas(self, blocks: List[BaseBlock]) -> List[BaseBlock]:
        """
        Merges adjacent mathematical formula lines that belong to the same multi-line equation
        (e.g., 'where head_i = ...' or 'MultiHead(Q,K,V) = ... Concat(...)').
        """
        if not blocks:
            return []

        merged: List[BaseBlock] = []
        i = 0
        while i < len(blocks):
            b = blocks[i]
            if isinstance(b, FormulaBlock):
                current_latex = b.latex
                min_x = b.bbox.x0
                min_y = b.bbox.y0
                max_x = b.bbox.x1
                max_y = b.bbox.y1

                j = i + 1
                while j < len(blocks):
                    next_b = blocks[j]
                    # Check vertical proximity (< 35pt)
                    vert_dist = next_b.bbox.y0 - max_y
                    if 0 <= vert_dist <= 35:
                        next_text = getattr(next_b, "text", "") or getattr(next_b, "latex", "") or ""
                        clean_next = next_text.strip()
                        # Continuing patterns: where ..., \text{head} ..., Concat ..., =, \sqrt ..., )V (1), +, -
                        is_continuation = bool(
                            isinstance(next_b, FormulaBlock) or
                            re.match(r"^\s*(=|where\b|Concat\b|head|\+|-|\\text|\\sqrt|\\frac|\)|\[)", clean_next, re.IGNORECASE) or
                            re.search(r"^\)\s*[a-zA-Z0-9\(\)\s]*\(\d+\)", clean_next)
                        )
                        if is_continuation:
                            # If continuing with fractional denominator like \sqrt{d_k}
                            if r"\sqrt" in clean_next and "softmax" in current_latex:
                                current_latex = current_latex.replace("softmax(QKT", r"\text{softmax}\left(\frac{QK^T}{\sqrt{d_k}}\right")
                            else:
                                current_latex += " " + self.normalize_equation(clean_next)
                            min_x = min(min_x, next_b.bbox.x0)
                            max_x = max(max_x, next_b.bbox.x1)
                            max_y = max(max_y, next_b.bbox.y1)
                            j += 1
                            continue
                    break

                b.latex = current_latex
                b.bbox = BoundingBox(min_x, min_y, max_x, max_y)
                merged.append(b)
                i = j
            else:
                merged.append(b)
                i += 1

        return merged
