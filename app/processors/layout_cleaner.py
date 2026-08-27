"""Layout Cleaner: Detects and crops complex charts, attention maps, and matrix noise into FigureBlocks without OCR-ing chart text."""

from __future__ import annotations
import math
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from PIL import Image

from app.core.blocks import (
    BaseBlock, FigureBlock, CaptionBlock, ParagraphBlock, HeadingBlock,
    BlockType, BoundingBox
)
from app.utils.logging import get_logger

logger = get_logger("LayoutCleaner")

class LayoutCleaner:
    """
    Detects complex charts/heatmaps/matrix token clusters.
    Crops the chart area directly into a FigureBlock (with image file path)
    and isolates the caption (e.g., 'Figure X:...'), completely eliminating
    internal chart noise tokens from OCR.
    """

    MATRIX_TOKENS = {
        "<pad>", "<eos>", "<unk>", "<s>", "</s>",
        "-", ".", "...", ":", ";", "|", "/", "\\", ",", "_"
    }

    def __init__(self, proximity_threshold: float = 35.0, min_cluster_size: int = 8, page_noise_threshold: int = 15):
        self.proximity_threshold = proximity_threshold
        self.min_cluster_size = min_cluster_size
        self.page_noise_threshold = page_noise_threshold

    def is_noise_block(self, block: BaseBlock) -> bool:
        """Determines if a block is a chart/matrix noise candidate."""
        # Never treat headings or captions as noise
        if block.block_type in (BlockType.HEADING, BlockType.CAPTION):
            return False

        text = (getattr(block, "text", "") or getattr(block, "raw_text", "") or "").strip()
        if not text:
            return True

        tokens = text.split()

        # 1. Single word or empty
        if len(tokens) <= 1:
            return True

        # 2. Contains tokenizer / matrix symbols
        if any(tok.lower() in self.MATRIX_TOKENS for tok in tokens):
            return True

        # 3. Two short words (each <= 4 chars)
        if len(tokens) <= 2 and all(len(w) <= 5 for w in tokens):
            return True

        # 4. Tiny bounding box with short text
        if block.bbox.width < 60 and block.bbox.height < 25 and len(tokens) <= 3:
            return True

        return False

    def is_caption_block(self, block: BaseBlock) -> bool:
        """Checks if a block is a Figure or Table caption."""
        text = (getattr(block, "text", "") or getattr(block, "raw_text", "") or "").strip()
        return bool(re.match(r"^(Figure|Fig\.|Table)\s+\d+[:\.]", text, re.IGNORECASE))

    def is_heading_block(self, block: BaseBlock) -> bool:
        """Checks if a block is a section heading."""
        if block.block_type == BlockType.HEADING:
            return True
        text = (getattr(block, "text", "") or getattr(block, "raw_text", "") or "").strip()
        return bool(re.match(r"^(\d+(\.\d+)*|[A-Z]\.)\s+[A-Z]", text) or text.startswith("#"))

    def bbox_distance(self, b1: BoundingBox, b2: BoundingBox) -> float:
        """Computes Euclidean distance between two bounding boxes."""
        dx = max(0.0, max(b1.x0, b2.x0) - min(b1.x1, b2.x1))
        dy = max(0.0, max(b1.y0, b2.y0) - min(b1.y1, b2.y1))
        return math.sqrt(dx * dx + dy * dy)

    def cluster_blocks(self, noise_blocks: List[BaseBlock]) -> List[List[BaseBlock]]:
        """Groups nearby noise blocks using connected-component clustering."""
        if not noise_blocks:
            return []

        clusters: List[List[BaseBlock]] = []
        visited = set()

        for i, b in enumerate(noise_blocks):
            if i in visited:
                continue

            current_cluster = [b]
            visited.add(i)
            queue = [b]

            while queue:
                current_b = queue.pop(0)
                for j, other_b in enumerate(noise_blocks):
                    if j in visited:
                        continue
                    dist = self.bbox_distance(current_b.bbox, other_b.bbox)
                    if dist <= self.proximity_threshold:
                        visited.add(j)
                        current_cluster.append(other_b)
                        queue.append(other_b)

            clusters.append(current_cluster)

        return clusters

    def crop_and_save_figure(
        self,
        image_path: str,
        bbox: BoundingBox,
        page_w_pt: float,
        page_h_pt: float,
        output_file: Path
    ) -> Optional[str]:
        """Crops the bounding box area from the preview image and saves it."""
        try:
            if not image_path or not Path(image_path).exists():
                return None

            img = Image.open(image_path)
            img_w, img_h = img.size
            scale_x = img_w / page_w_pt if page_w_pt > 0 else 1.0
            scale_y = img_h / page_h_pt if page_h_pt > 0 else 1.0

            # Add padding around the chart
            pad_pt = 8.0
            crop_box = (
                max(0, int((bbox.x0 - pad_pt) * scale_x)),
                max(0, int((bbox.y0 - pad_pt) * scale_y)),
                min(img_w, int((bbox.x1 + pad_pt) * scale_x)),
                min(img_h, int((bbox.y1 + pad_pt) * scale_y))
            )

            if crop_box[2] <= crop_box[0] or crop_box[3] <= crop_box[1]:
                return None

            cropped = img.crop(crop_box)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            cropped.save(str(output_file.resolve()), "PNG")
            return str(output_file.resolve())
        except Exception as e:
            logger.error(f"Failed to crop chart figure: {e}")
            return None

    def clean_chart_noise(
        self,
        blocks: List[BaseBlock],
        page_num: int = 1,
        page_w_pt: float = 595.0,
        page_h_pt: float = 842.0,
        preview_image_path: Optional[str] = None,
        image_dir: Optional[Path] = None
    ) -> List[BaseBlock]:
        """
        Main entry point for chart filtering and noise elimination:
        1. If page has > page_noise_threshold noise tokens: Whole-Page Chart Filter.
        2. Otherwise: Cluster-based Chart Filter for multi-chart pages.
        3. Isolates Caption ('Figure X:...') and pairs with cropped FigureBlock.
        """
        if not blocks:
            return []

        out_dir = image_dir or (Path(preview_image_path).parent if preview_image_path else Path("images"))

        noise_blocks = [b for b in blocks if self.is_noise_block(b)]
        non_noise_blocks = [b for b in blocks if not self.is_noise_block(b)]

        # -------------------------------------------------------------
        # STRATEGY 1: Full-Page Chart / Heatmap (noise count > 15)
        # -------------------------------------------------------------
        if len(noise_blocks) >= self.page_noise_threshold:
            logger.info(f"Page {page_num}: Detected full-page chart/matrix visualization with {len(noise_blocks)} noise tokens.")

            filtered_blocks: List[BaseBlock] = []
            captions: List[CaptionBlock] = []
            chart_boxes: List[BoundingBox] = []

            for b in blocks:
                text = (getattr(b, "text", "") or getattr(b, "raw_text", "") or "").strip()
                if self.is_caption_block(b):
                    # Convert to dedicated CaptionBlock
                    cap = CaptionBlock(
                        id=f"cap_fig_{page_num}_{len(captions)+1}",
                        bbox=b.bbox,
                        source_page=page_num,
                        confidence=0.99,
                        target_type="figure",
                        text=text
                    )
                    captions.append(cap)
                elif self.is_heading_block(b):
                    filtered_blocks.append(b)
                elif not self.is_noise_block(b):
                    # Keep substantial prose if any exists
                    if len(text.split()) > 10:
                        filtered_blocks.append(b)
                    else:
                        chart_boxes.append(b.bbox)
                else:
                    chart_boxes.append(b.bbox)

            # Build enclosing bounding box for the entire chart area
            if chart_boxes:
                min_x = min(box.x0 for box in chart_boxes)
                min_y = min(box.y0 for box in chart_boxes)
                max_x = max(box.x1 for box in chart_boxes)
                max_y = max(box.y1 for box in chart_boxes)
                enclosing_bbox = BoundingBox(min_x, min_y, max_x, max_y)

                fig_filename = out_dir / f"figure_{page_num}_full_chart.png"
                crop_path = None
                if preview_image_path:
                    crop_path = self.crop_and_save_figure(
                        preview_image_path, enclosing_bbox, page_w_pt, page_h_pt, fig_filename
                    )

                caption_text = captions[0].text if captions else ""
                fig_block = FigureBlock(
                    id=f"fig_{page_num}_main",
                    bbox=enclosing_bbox,
                    source_page=page_num,
                    confidence=0.99,
                    caption=caption_text,
                    image_path=crop_path or str(fig_filename),
                    width_pt=enclosing_bbox.width,
                    height_pt=enclosing_bbox.height
                )

                # Assemble: Headings -> FigureBlock -> CaptionBlock -> Other prose
                result: List[BaseBlock] = []
                headings = [b for b in filtered_blocks if b.block_type == BlockType.HEADING]
                prose = [b for b in filtered_blocks if b.block_type != BlockType.HEADING]

                result.extend(headings)
                result.append(fig_block)
                result.extend(captions)
                result.extend(prose)

                for idx, b in enumerate(result):
                    b.order_index = idx

                logger.info(f"Page {page_num}: Successfully replaced {len(noise_blocks)} noise tokens with 1 FigureBlock + Caption.")
                return result

        # -------------------------------------------------------------
        # STRATEGY 2: Local Cluster Chart Filter (Clusters >= 8 blocks)
        # -------------------------------------------------------------
        if len(noise_blocks) < self.min_cluster_size:
            return blocks

        clusters = self.cluster_blocks(noise_blocks)
        merged_figures: List[FigureBlock] = []
        remaining_noise: List[BaseBlock] = []

        for c_idx, cluster in enumerate(clusters):
            if len(cluster) >= self.min_cluster_size:
                min_x = min(b.bbox.x0 for b in cluster)
                min_y = min(b.bbox.y0 for b in cluster)
                max_x = max(b.bbox.x1 for b in cluster)
                max_y = max(b.bbox.y1 for b in cluster)
                enclosing_bbox = BoundingBox(min_x, min_y, max_x, max_y)

                fig_filename = out_dir / f"figure_{page_num}_cluster_{c_idx+1}.png"
                crop_path = None
                if preview_image_path:
                    crop_path = self.crop_and_save_figure(
                        preview_image_path, enclosing_bbox, page_w_pt, page_h_pt, fig_filename
                    )

                fig_block = FigureBlock(
                    id=f"fig_auto_merged_{page_num}_{c_idx+1}",
                    bbox=enclosing_bbox,
                    source_page=page_num,
                    confidence=0.99,
                    caption="",
                    image_path=crop_path or str(fig_filename),
                    width_pt=enclosing_bbox.width,
                    height_pt=enclosing_bbox.height
                )
                merged_figures.append(fig_block)
                logger.info(f"Page {page_num}: Merged {len(cluster)} noise blocks into FigureBlock at {enclosing_bbox}.")
            else:
                remaining_noise.extend(cluster)

        # Assemble final blocks
        all_blocks = non_noise_blocks + remaining_noise + merged_figures

        # Sort by vertical position
        all_blocks.sort(key=lambda b: (round(b.bbox.y0, 1), round(b.bbox.x0, 1)))
        for idx, b in enumerate(all_blocks):
            b.order_index = idx

        # Caption matching: pair with nearest caption below figure
        for fig in merged_figures:
            for b in all_blocks:
                if self.is_caption_block(b):
                    if 0 <= (b.bbox.y0 - fig.bbox.y1) <= 70:
                        fig.caption = getattr(b, "text", "")
                        b.block_type = BlockType.CAPTION

        return all_blocks
