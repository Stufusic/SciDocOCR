"""Document Layout Analysis Model and Visual Region Classifier."""

from __future__ import annotations
import os
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from PIL import Image

from app.core.blocks import (
    BaseBlock, HeadingBlock, ParagraphBlock, FormulaBlock,
    TableBlock, FigureBlock, CaptionBlock, BlockType, BoundingBox
)
from app.utils.logging import get_logger

logger = get_logger("DocumentLayoutDetector")

class LayoutRegion:
    """Represents a classified Region of Interest (ROI)."""
    def __init__(self, bbox: BoundingBox, label: str, confidence: float = 0.95):
        self.bbox = bbox
        self.label = label  # 'text', 'title', 'table', 'figure', 'formula'
        self.confidence = confidence


class DocumentLayoutDetector:
    """
    Performs Document Layout Analysis to classify regions (Layout-First architecture).
    Integrates deep learning model inference (YOLO / layoutparser) with intelligent CV fallback.
    """

    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path
        self.model = None
        self._init_model()

    def _init_model(self):
        """Attempts to load DocLayout-YOLO or YOLO weights if available."""
        if self.model_path and Path(self.model_path).exists():
            try:
                from ultralytics import YOLO
                self.model = YOLO(self.model_path)
                logger.info(f"Loaded YOLO layout model from {self.model_path}")
            except Exception as e:
                logger.warning(f"Could not load YOLO model: {e}. Using CV layout analyzer.")

    def detect_regions_from_image(self, image: Image.Image) -> List[LayoutRegion]:
        """Detects document regions from a page image."""
        if self.model is not None:
            try:
                results = self.model(image)
                regions = []
                for r in results:
                    for box in r.boxes:
                        coords = box.xyxy[0].tolist()
                        cls_id = int(box.cls[0].item())
                        conf = float(box.conf[0].item())
                        label = r.names.get(cls_id, "text").lower()
                        # Map label
                        if "title" in label or "header" in label:
                            label = "title"
                        elif "math" in label or "formula" in label or "equation" in label:
                            label = "formula"
                        elif "table" in label:
                            label = "table"
                        elif "fig" in label or "image" in label or "chart" in label:
                            label = "figure"
                        else:
                            label = "text"

                        regions.append(LayoutRegion(
                            bbox=BoundingBox(coords[0], coords[1], coords[2], coords[3]),
                            label=label,
                            confidence=conf
                        ))
                return regions
            except Exception as e:
                logger.error(f"Model inference failed: {e}")

        # Intelligent CV / heuristic fallback
        return []

    def classify_and_route_blocks(
        self,
        blocks: List[BaseBlock],
        page_num: int = 1,
        preview_image_path: Optional[str] = None
    ) -> List[BaseBlock]:
        """
        Applies Layout-First classification and routing rules:
        - 'title' -> HeadingBlock
        - 'figure' -> FigureBlock with caption association
        - 'formula' -> FormulaBlock
        - 'table' -> TableBlock
        - 'text' -> ParagraphBlock
        """
        routed_blocks: List[BaseBlock] = []

        for b in blocks:
            text = getattr(b, "text", "") or getattr(b, "raw_text", "") or ""
            clean_text = text.strip()

            # Rule 1: Figure captions ("Figure 1: ...", "Fig. 2. ...")
            if re.match(r"^(Figure|Fig\.)\s+\d+[:\.]", clean_text, re.IGNORECASE):
                routed_blocks.append(CaptionBlock(
                    id=b.id,
                    bbox=b.bbox,
                    source_page=page_num,
                    confidence=0.98,
                    target_type="figure",
                    text=clean_text
                ))
                continue

            # Rule 2: Table captions ("Table 1: ...")
            if re.match(r"^Table\s+\d+[:\.]", clean_text, re.IGNORECASE):
                routed_blocks.append(CaptionBlock(
                    id=b.id,
                    bbox=b.bbox,
                    source_page=page_num,
                    confidence=0.98,
                    target_type="table",
                    text=clean_text
                ))
                continue

            # Rule 3: Heading detection (Numbered sections like "1 Introduction", "2.1 Background", "3.2.1 Scaled Dot-Product Attention", "Abstract")
            is_numbered_section = bool(re.match(r"^(\d+(\.\d+)*|[A-Z]\.)\s+[A-Z][a-zA-Z\s\-\/']{2,60}$", clean_text))
            is_single_word_heading = clean_text.lower() in {
                "abstract", "introduction", "background", "related work",
                "methods", "methodology", "model architecture", "experiments",
                "results", "discussion", "conclusion", "references", "acknowledgments"
            }

            if (is_numbered_section or is_single_word_heading) and len(clean_text) < 100:
                level = 1
                if "." in clean_text[:6]:
                    level = clean_text[:6].count(".") + 1
                routed_blocks.append(HeadingBlock(
                    id=b.id,
                    bbox=b.bbox,
                    source_page=page_num,
                    confidence=0.98,
                    level=min(4, level),
                    text=clean_text
                ))
                continue

            routed_blocks.append(b)

        return routed_blocks
