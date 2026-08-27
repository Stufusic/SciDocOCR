"""Confidence Scoring Engine for Document AST."""

from typing import List, Dict, Any
from app.core.blocks import BaseBlock, BlockType

class ConfidenceEngine:
    """Computes and aggregates confidence scores across AST blocks, pages, and document."""

    LOW_CONFIDENCE_THRESHOLD = 0.85

    @classmethod
    def evaluate_blocks(cls, blocks: List[BaseBlock]) -> Dict[str, Any]:
        if not blocks:
            return {"avg_confidence": 1.0, "low_confidence_blocks": []}

        total_conf = 0.0
        low_conf = []

        for b in blocks:
            total_conf += b.confidence
            if b.confidence < cls.LOW_CONFIDENCE_THRESHOLD:
                low_conf.append(b)

        return {
            "avg_confidence": round(total_conf / len(blocks), 4),
            "low_confidence_count": len(low_conf),
            "low_confidence_blocks": low_conf,
        }
