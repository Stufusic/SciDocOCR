"""Math Engine: Specialized mathematical formula extractor with Pix2Text and VLM Fallback."""

from __future__ import annotations
import re
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

from config import MATH_CONFIDENCE_THRESHOLD, USE_VLM_MATH_FALLBACK
from src.vlm_client import parse_math_image
from app.utils.logging import get_logger

logger = get_logger("MathEngine")

_p2t_instance = None
_p2t_initialized = False

def get_pix2text_instance():
    global _p2t_instance, _p2t_initialized
    if not _p2t_initialized:
        _p2t_initialized = True
        try:
            from pix2text import Pix2Text
            _p2t_instance = Pix2Text(analyzer_config=dict(model_name='mfd'))
            logger.info("Pix2Text initialized successfully.")
        except Exception as e:
            logger.info(f"Pix2Text not available or failed to initialize ({e}). Using VLM/OCR fallback.")
            _p2t_instance = None
    return _p2t_instance

class MathEngine:
    """Extracts mathematical formulas from crops with Pix2Text and VLM fallback."""

    def __init__(self, confidence_threshold: float = MATH_CONFIDENCE_THRESHOLD):
        self.confidence_threshold = confidence_threshold

    def is_syntax_valid(self, latex: str) -> bool:
        """Verifies bracket balancing and basic LaTeX math syntax."""
        if not latex or not latex.strip():
            return False

        # 1. Bracket counting
        pairs = [('{', '}'), ('(', ')'), ('[', ']')]
        for open_b, close_b in pairs:
            if latex.count(open_b) != latex.count(close_b):
                return False

        # 2. Check broken commands like \frac without arguments
        if r"\frac" in latex and "{" not in latex:
            return False

        return True

    def process_math_crop(
        self,
        image_path: str | Path,
        raw_text_hint: str = "",
        is_inline: bool = False
    ) -> Tuple[str, float, str]:
        """
        Processes a math crop.
        Returns: (latex_code, confidence, method_used)
        """
        img_p = Path(image_path)
        if not img_p.exists():
            return ("", 0.0, "missing_image")

        latex_res = ""
        confidence = 0.0
        method = "fast_ocr"

        # -------------------------------------------------------------
        # PHASE 2: Fast Math OCR (Pix2Text if available)
        # -------------------------------------------------------------
        p2t = get_pix2text_instance()
        if p2t is not None:
            try:
                res = p2t.recognize_formula(str(img_p))
                if isinstance(res, dict):
                    latex_res = res.get("text", "")
                    confidence = float(res.get("score", 0.9))
                elif isinstance(res, str):
                    latex_res = res
                    confidence = 0.9
            except Exception as e:
                logger.warning(f"Pix2Text error on {img_p.name}: {e}")

        # Fallback to text hint if Pix2Text wasn't available or gave empty result
        if not latex_res and raw_text_hint:
            latex_res = raw_text_hint.strip()
            confidence = 0.80

        # Check syntax validity
        syntax_ok = self.is_syntax_valid(latex_res)
        if not syntax_ok:
            confidence = min(confidence, 0.60)

        # -------------------------------------------------------------
        # PHASE 3: Visual Specialist (VLM Fallback)
        # -------------------------------------------------------------
        if USE_VLM_MATH_FALLBACK and (confidence < self.confidence_threshold or not syntax_ok or not latex_res):
            logger.info(f"Math crop {img_p.name} triggered VLM fallback (Confidence: {confidence:.2f}, Valid: {syntax_ok})")
            vlm_res = parse_math_image(img_p)
            if vlm_res:
                latex_res = vlm_res
                confidence = 0.98
                method = "vlm_fallback"

        # Format output
        latex_clean = latex_res.strip().strip("$").strip()
        if is_inline:
            formatted = f"${latex_clean}$"
        else:
            formatted = f"\n$$\n{latex_clean}\n$$\n"

        return (formatted, confidence, method)
