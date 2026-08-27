"""Document-level validation & health metrics."""

from typing import List, Dict, Any
from app.core.document import Document
from app.core.blocks import BlockType, FormulaBlock
from app.validation.formula import FormulaValidator

class DocumentValidator:
    """Validates entire Document AST consistency."""

    def __init__(self):
        self.formula_validator = FormulaValidator()

    def validate_document(self, doc: Document) -> Dict[str, Any]:
        invalid_formulas = []
        low_confidence_blocks = []

        for page in doc.pages:
            for block in page.blocks:
                if block.block_type == BlockType.FORMULA and isinstance(block, FormulaBlock):
                    self.formula_validator.validate_formula_block(block)
                    if not block.is_valid:
                        invalid_formulas.append(block)

                if block.confidence < 0.85:
                    low_confidence_blocks.append(block)

            page.recompute_metrics()

        stats = doc.get_stats()
        stats["invalid_formulas_count"] = len(invalid_formulas)
        stats["needs_review"] = len(low_confidence_blocks) > 0 or len(invalid_formulas) > 0

        return stats
