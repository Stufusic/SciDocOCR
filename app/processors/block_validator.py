"""Block Validator and False Formula Correction Processor."""

from __future__ import annotations
import re
from typing import List, Dict, Any, Tuple
from app.core.blocks import (
    BaseBlock, ParagraphBlock, FormulaBlock, HeadingBlock,
    BlockType, BoundingBox
)
from app.utils.logging import get_logger

logger = get_logger("BlockValidator")

# Common English sentence starter patterns in scientific papers
SENTENCE_STARTERS = [
    r"^We\s+(call|propose|introduce|present|find|show|observe|use|train|evaluate)\b",
    r"^In\s+this\s+(work|paper|section|study|experiment)\b",
    r"^The\s+(model|architecture|results|experiments|attention|transformer|layer|output)\b",
    r"^To\s+(allow|address|improve|evaluate|prevent|test|demonstrate)\b",
    r"^This\s+(allows|results|proves|means|shows|leads)\b",
    r"^For\s+(each|example|instance|very|any)\b",
    r"^Similar\s+to\b",
    r"^As\s+(shown|discussed|noted|described)\b"
]

class BlockValidator:
    """Validates block classifications and repairs misclassified formulas and LaTeX syntax."""

    def __init__(self):
        pass

    def is_false_formula(self, block: FormulaBlock) -> bool:
        """
        Detects if a block labeled as 'formula' is actually a regular English paragraph.
        """
        raw = (block.raw_text or block.latex or "").strip()
        if not raw:
            return False

        # 1. Check word count of standard English words (3+ chars)
        words = re.findall(r"\b[a-zA-Z]{3,}\b", raw)
        # Filter out common LaTeX math words
        math_keywords = {"sin", "cos", "tan", "log", "exp", "lim", "max", "min", "text", "frac", "sqrt", "alpha", "beta"}
        prose_words = [w for w in words if w.lower() not in math_keywords]

        if len(prose_words) > 10:
            return True

        # 2. Check confidence threshold
        if block.confidence < 0.70 and len(prose_words) >= 4:
            return True

        # 3. Check for complete scientific English sentence starters
        for pattern in SENTENCE_STARTERS:
            if re.search(pattern, raw, re.IGNORECASE):
                return True

        # 4. Check if ends with a period and contains standard sentence structure
        if raw.endswith(".") and len(prose_words) >= 6 and "=" not in raw:
            return True

        return False

    def repair_latex_syntax(self, latex: str) -> str:
        """Repairs common minor LaTeX formatting glitches with Regex."""
        text = latex.strip()

        # Fix missing curly braces in \sqrt e.g., \sqrt x -> \sqrt{x}
        text = re.sub(r"\\sqrt\s*([a-zA-Z0-9])\b", r"\\sqrt{\1}", text)

        # Fix single char subscript/superscript with multiple chars e.g. x_12 -> x_{12}
        text = re.sub(r"([a-zA-Z])_([a-zA-Z0-9]{2,})\b", r"\1_{\2}", text)
        text = re.sub(r"([a-zA-Z])\^([a-zA-Z0-9]{2,})\b", r"\1^{\2}", text)

        # Fix \frac without braces e.g., \frac a b -> \frac{a}{b}
        text = re.sub(r"\\frac\s+([a-zA-Z0-9])\s+([a-zA-Z0-9])", r"\\frac{\1}{\2}", text)

        return text

    def validate_and_correct_blocks(self, blocks: List[BaseBlock]) -> List[BaseBlock]:
        """
        Iterates over all blocks, reverts false formulas to ParagraphBlock,
        and repairs LaTeX syntax.
        """
        corrected_blocks: List[BaseBlock] = []

        for b in blocks:
            if b.block_type == BlockType.FORMULA and isinstance(b, FormulaBlock):
                if self.is_false_formula(b):
                    # Revert to ParagraphBlock
                    recovered_text = b.raw_text or b.latex
                    para_block = ParagraphBlock(
                        id=b.id,
                        bbox=b.bbox,
                        source_page=b.source_page,
                        order_index=b.order_index,
                        column_index=b.column_index,
                        confidence=0.95,
                        text=recovered_text,
                        original_text=recovered_text
                    )
                    corrected_blocks.append(para_block)
                    logger.info(f"Page {b.source_page}: Reverted false formula to paragraph: '{recovered_text[:40]}...'")
                else:
                    # Repair LaTeX syntax
                    b.latex = self.repair_latex_syntax(b.latex)
                    b.confidence = max(0.90, b.confidence)
                    corrected_blocks.append(b)
            else:
                corrected_blocks.append(b)

        return corrected_blocks
