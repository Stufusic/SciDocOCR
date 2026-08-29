"""Document Layout Analysis Model and Visual Region Classifier with YOLOv8 ONNX (CPU)."""

from __future__ import annotations
import os
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from PIL import Image
import numpy as np

from app.core.blocks import (
    BaseBlock, HeadingBlock, ParagraphBlock, FormulaBlock,
    TableBlock, FigureBlock, CaptionBlock, BlockType, BoundingBox
)
from app.utils.logging import get_logger

logger = get_logger("DocumentLayoutDetector")

CLASS_NAMES = {
    0: "title",
    1: "text",
    2: "formula",
    3: "table",
    4: "figure",
    5: "caption"
}

# DocLayNet 11-class mapping used by Oblix YOLOv10m
DOCLAYNET_NAMES = {
    0: "caption",
    1: "text",       # Footnote
    2: "formula",    # Formula
    3: "text",       # List-item
    4: "text",       # Page-footer
    5: "text",       # Page-header
    6: "figure",     # Picture
    7: "title",      # Section-header
    8: "table",      # Table
    9: "text",       # Text
    10: "title"      # Title
}

class LayoutRegion:
    """Represents a classified Region of Interest (ROI)."""
    def __init__(self, bbox: BoundingBox, label: str, confidence: float = 0.95):
        self.bbox = bbox
        self.label = label  # 'text', 'title', 'table', 'figure', 'formula', 'caption'
        self.confidence = confidence


class YOLOv8ONNXLayoutDetector:
    """CPU-Optimized ONNX Runtime Inference for YOLOv8 Document Layout Analysis."""

    def __init__(self, onnx_model_path: str, conf_threshold: float = 0.35, iou_threshold: float = 0.45):
        self.model_path = Path(onnx_model_path)
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.session = None
        self._load_session()

    def _load_session(self):
        if not self.model_path.exists():
            return
        try:
            import onnxruntime as ort
            # Ensure CPU-only execution provider
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = min(4, os.cpu_count() or 2)
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            self.session = ort.InferenceSession(
                str(self.model_path),
                sess_options=opts,
                providers=["CPUExecutionProvider"]
            )
            logger.info(f"Loaded YOLOv8 ONNX model on CPU from: {self.model_path}")
        except Exception as e:
            logger.warning(f"Could not load ONNX session ({e}). Fallback to CV layout analyzer.")
            self.session = None

    def is_available(self) -> bool:
        return self.session is not None

    def detect(self, image: Image.Image) -> List[LayoutRegion]:
        """Runs CPU inference on a PIL image and returns layout regions."""
        if not self.is_available():
            return []

        try:
            orig_w, orig_h = image.size
            input_size = 640

            # Preprocess: Letterbox resize to 640x640
            img_rgb = image.convert("RGB")
            scale = min(input_size / orig_w, input_size / orig_h)
            new_w, new_h = int(orig_w * scale), int(orig_h * scale)
            resized = img_rgb.resize((new_w, new_h), Image.Resampling.BILINEAR)

            canvas = Image.new("RGB", (input_size, input_size), (114, 114, 114))
            pad_x = (input_size - new_w) // 2
            pad_y = (input_size - new_h) // 2
            canvas.paste(resized, (pad_x, pad_y))

            img_np = np.array(canvas, dtype=np.float32) / 255.0
            img_np = img_np.transpose(2, 0, 1)  # HWC to CHW
            img_tensor = np.expand_dims(img_np, axis=0)  # Add batch dim

            input_name = self.session.get_inputs()[0].name
            outputs = self.session.run(None, {input_name: img_tensor})
            output = outputs[0]  # Shape: (1, 300, 6) for YOLOv10 or (1, 84, 8400) for YOLOv8

            regions = []

            # Format 1: YOLOv10 NMS-Free Format (1, num_boxes, 6) -> [x0, y0, x1, y1, score, cls_id]
            if len(output.shape) == 3 and output.shape[2] == 6:
                predictions = output[0]
                for row in predictions:
                    score = float(row[4])
                    if score < self.conf_threshold:
                        continue
                    cls_id = int(row[5])
                    x0 = max(0.0, min(float(orig_w), (float(row[0]) - pad_x) / scale))
                    y0 = max(0.0, min(float(orig_h), (float(row[1]) - pad_y) / scale))
                    x1 = max(0.0, min(float(orig_w), (float(row[2]) - pad_x) / scale))
                    y1 = max(0.0, min(float(orig_h), (float(row[3]) - pad_y) / scale))

                    label = DOCLAYNET_NAMES.get(cls_id) or CLASS_NAMES.get(cls_id, "text")
                    regions.append(LayoutRegion(
                        bbox=BoundingBox(x0, y0, x1, y1),
                        label=label,
                        confidence=score
                    ))
                return regions

            # Format 2: YOLOv8 Standard Format (1, 4 + classes, num_boxes)
            if output.shape[1] < output.shape[2]:
                output = output.transpose(0, 2, 1)

            predictions = output[0]  # Shape: (num_boxes, 4 + num_classes)

            for row in predictions:
                box = row[:4]
                scores = row[4:]
                cls_id = int(np.argmax(scores))
                score = float(scores[cls_id])

                if score < self.conf_threshold:
                    continue

                cx, cy, bw, bh = box
                # Convert from canvas coords to original image coords
                x0 = (cx - bw / 2 - pad_x) / scale
                y0 = (cy - bh / 2 - pad_y) / scale
                x1 = (cx + bw / 2 - pad_x) / scale
                y1 = (cy + bh / 2 - pad_y) / scale

                x0 = max(0.0, min(float(orig_w), x0))
                y0 = max(0.0, min(float(orig_h), y0))
                x1 = max(0.0, min(float(orig_w), x1))
                y1 = max(0.0, min(float(orig_h), y1))

                label = DOCLAYNET_NAMES.get(cls_id) or CLASS_NAMES.get(cls_id, "text")
                regions.append(LayoutRegion(
                    bbox=BoundingBox(x0, y0, x1, y1),
                    label=label,
                    confidence=score
                ))

            return regions
        except Exception as e:
            logger.error(f"YOLO ONNX inference failed: {e}")
            return []


class DocumentLayoutDetector:
    """
    Performs Document Layout Analysis to classify regions (Layout-First architecture).
    Integrates YOLOv8 ONNX CPU model with intelligent CV and typography heuristics.
    """

    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path or str(Path("assets") / "models" / "yolov8_layout.onnx")
        self.onnx_detector = YOLOv8ONNXLayoutDetector(self.model_path)

    def detect_regions_from_image(self, image: Image.Image) -> List[LayoutRegion]:
        """Detects document regions from a page image."""
        if self.onnx_detector.is_available():
            regions = self.onnx_detector.detect(image)
            if regions:
                return regions
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

            # Rule 3: Heading detection (Numbered sections like "1 Introduction", "1. Introduction", "2.1 Background", "3.2.1 Scaled Dot-Product Attention", "Abstract")
            is_numbered_section = bool(re.match(r"^(\d+(?:\.\d+)*\.?|[A-Z]\.)\s+[A-Z][a-zA-Z\s\-\/']{2,60}$", clean_text))
            is_single_word_heading = clean_text.lower() in {
                "abstract", "introduction", "background", "related work",
                "methods", "methodology", "model architecture", "experiments",
                "results", "discussion", "conclusion", "references", "acknowledgments"
            }

            if (is_numbered_section or is_single_word_heading) and len(clean_text) < 100:
                # Correctly calculate level: "1. Introduction" -> Level 1, "1.2 Method" -> Level 2
                num_part_match = re.match(r"^(\d+(?:\.\d+)*)", clean_text)
                if num_part_match:
                    num_str = num_part_match.group(1).rstrip(".")
                    level = num_str.count(".") + 1
                else:
                    level = 1

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

    def sort_regions_reading_order(self, regions: List[LayoutRegion], page_width: float = 600.0) -> List[LayoutRegion]:
        """
        Sorts layout regions in natural human reading order:
        - Spanning blocks (Title, Abstract) are placed at the top.
        - Two-column content is ordered Left Column (top-down) then Right Column (top-down).
        - Single-column content is sorted top-to-bottom.
        """
        if not regions:
            return []

        mid_x = page_width / 2.0
        
        # Check if two-column layout exists
        left_count = sum(1 for r in regions if r.bbox.x1 <= mid_x + 30 and r.bbox.width < page_width * 0.65)
        right_count = sum(1 for r in regions if r.bbox.x0 >= mid_x - 30 and r.bbox.width < page_width * 0.65)
        is_two_column = (left_count >= 2 and right_count >= 2)

        if not is_two_column:
            return sorted(regions, key=lambda r: (r.bbox.y0, r.bbox.x0))

        spanning_top = []
        left_col = []
        right_col = []
        spanning_bottom = []

        for r in regions:
            if r.bbox.width >= page_width * 0.65:
                if r.bbox.y0 < page_width * 0.45:
                    spanning_top.append(r)
                else:
                    spanning_bottom.append(r)
            elif (r.bbox.x0 + r.bbox.x1) / 2.0 < mid_x:
                left_col.append(r)
            else:
                right_col.append(r)

        spanning_top.sort(key=lambda r: r.bbox.y0)
        left_col.sort(key=lambda r: r.bbox.y0)
        right_col.sort(key=lambda r: r.bbox.y0)
        spanning_bottom.sort(key=lambda r: r.bbox.y0)

        return spanning_top + left_col + right_col + spanning_bottom

    def detect_and_crop_regions(
        self,
        pil_image: Image.Image,
        page_num: int = 1,
        image_dir: Optional[Path] = None,
        padding: int = 6
    ) -> List[Tuple[LayoutRegion, bytes, Optional[str]]]:
        """
        Runs YOLO to detect layout bounding boxes, crops each region from the page image,
        and returns a list of (region, crop_bytes, saved_image_rel_path).
        Figures are automatically saved to disk directly.
        """
        regions = self.detect_regions_from_image(pil_image)
        if not regions:
            return []

        sorted_regions = self.sort_regions_reading_order(regions, page_width=float(pil_image.width))
        results: List[Tuple[LayoutRegion, bytes, Optional[str]]] = []
        import io
        fig_counter = 0

        for r in sorted_regions:
            w, h = r.bbox.width, r.bbox.height
            if w < 10 or h < 10:
                continue

            x0 = max(0, int(r.bbox.x0) - padding)
            y0 = max(0, int(r.bbox.y0) - padding)
            x1 = min(pil_image.width, int(r.bbox.x1) + padding)
            y1 = min(pil_image.height, int(r.bbox.y1) + padding)

            if x1 <= x0 or y1 <= y0:
                continue

            cropped = pil_image.crop((x0, y0, x1, y1))
            buf = io.BytesIO()
            cropped.save(buf, format="PNG")
            crop_bytes = buf.getvalue()

            saved_rel_path = None
            if r.label == "figure":
                fig_counter += 1
                fig_filename = f"fig_p{page_num}_{fig_counter}.png"
                if image_dir:
                    image_dir.mkdir(parents=True, exist_ok=True)
                    cropped.save(image_dir / fig_filename, "PNG")
                saved_rel_path = f"images/{fig_filename}"

            results.append((r, crop_bytes, saved_rel_path))

        return results

    def extract_figures_from_page(
        self,
        preview_image_path: Optional[str],
        page_num: int = 1,
        image_dir: Optional[Path] = None
    ) -> List[FigureBlock]:
        """
        Runs YOLO to detect figure/image regions on page image.
        Crops each detected figure into an image file in image_dir and returns FigureBlocks
        so figures are rendered directly without sending their visual contents to VLM text OCR.
        """
        if not preview_image_path or not Path(preview_image_path).exists():
            return []

        try:
            pil_img = Image.open(preview_image_path)
            regions = self.detect_regions_from_image(pil_img)
            figure_regions = [r for r in regions if r.label == "figure"]
            if not figure_regions:
                return []

            fig_blocks: List[FigureBlock] = []
            target_dir = Path(image_dir) if image_dir else Path(preview_image_path).parent

            for idx, r in enumerate(figure_regions):
                bw = r.bbox.width
                bh = r.bbox.height
                if bw < 50 or bh < 50:
                    continue

                x0 = max(0, int(r.bbox.x0))
                y0 = max(0, int(r.bbox.y0))
                x1 = min(pil_img.width, int(r.bbox.x1))
                y1 = min(pil_img.height, int(r.bbox.y1))

                if x1 > x0 and y1 > y0:
                    cropped = pil_img.crop((x0, y0, x1, y1))
                    fig_filename = f"fig_p{page_num}_{idx+1}.png"
                    fig_save_path = target_dir / fig_filename
                    cropped.save(fig_save_path, "PNG")

                    fig_blocks.append(FigureBlock(
                        id=f"fig_{page_num}_{idx+1}",
                        bbox=r.bbox,
                        source_page=page_num,
                        confidence=r.confidence,
                        image_path=f"images/{fig_filename}",
                        caption=f"Figure on page {page_num}"
                    ))

            return fig_blocks
        except Exception as e:
            logger.warning(f"Figure extraction from page {page_num} failed: {e}")
            return []
