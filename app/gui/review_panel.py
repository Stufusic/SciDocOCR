"""Review Mode Dialog for inspecting and correcting low-confidence blocks & formulas with live image crops."""

from pathlib import Path
from typing import List, Optional
from PIL import Image
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QGroupBox, QGraphicsView, QGraphicsScene,
    QGraphicsPixmapItem, QWidget
)
from PySide6.QtGui import QPixmap, QFont, QColor, QBrush
from PySide6.QtCore import Qt, Signal
from app.core.blocks import BaseBlock, FormulaBlock, ParagraphBlock, BlockType, BoundingBox
from app.core.project import SciDocProject
from app.ai.router import AIRouter
from app.utils.logging import get_logger

logger = get_logger("ReviewDialog")

class ReviewDialog(QDialog):
    """Interactive side-by-side review tool for low-confidence formulas and OCR text with live PDF crops."""

    block_updated = Signal(object)  # BaseBlock

    def __init__(
        self,
        blocks_to_review: List[BaseBlock],
        ai_router: Optional[AIRouter] = None,
        parent: Optional[QWidget] = None,
        project: Optional[SciDocProject] = None
    ):
        super().__init__(parent)
        self.setWindowTitle("SciDoc OCR - Review Mode")
        self.resize(800, 520)
        self.blocks = blocks_to_review
        self.current_idx = 0
        self.ai_router = ai_router
        self.project = project

        self._init_ui()
        self._load_current_block()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Header Info
        header_layout = QHBoxLayout()
        self.lbl_counter = QLabel("Reviewing Item 1 of 1")
        self.lbl_counter.setStyleSheet("font-weight: bold; color: #60a5fa; font-size: 13px;")
        self.lbl_confidence = QLabel("Confidence: 75%")
        self.lbl_confidence.setStyleSheet("font-weight: bold; color: #f59e0b; font-size: 13px;")

        header_layout.addWidget(self.lbl_counter)
        header_layout.addStretch()
        header_layout.addWidget(self.lbl_confidence)
        layout.addLayout(header_layout)

        # Main Comparison Area
        comp_layout = QHBoxLayout()

        # Left: Original Crop or Info
        left_group = QGroupBox("📄 Original PDF Region")
        left_layout = QVBoxLayout(left_group)
        self.img_scene = QGraphicsScene()
        self.img_scene.setBackgroundBrush(QBrush(QColor("#1e293b")))
        self.img_view = QGraphicsView(self.img_scene)
        self.img_view.setStyleSheet("background-color: #1e293b; border: 1px solid #334155; border-radius: 6px;")
        left_layout.addWidget(self.img_view)
        comp_layout.addWidget(left_group, stretch=1)

        # Right: Detected LaTeX / Text Editor
        right_group = QGroupBox("✏ Detected Content / LaTeX")
        right_layout = QVBoxLayout(right_group)

        self.editor = QPlainTextEdit()
        self.editor.setFont(QFont("Consolas", 12))
        right_layout.addWidget(self.editor)

        self.lbl_issues = QLabel("")
        self.lbl_issues.setStyleSheet("color: #ef4444; font-size: 11px;")
        self.lbl_issues.setWordWrap(True)
        right_layout.addWidget(self.lbl_issues)

        comp_layout.addWidget(right_group, stretch=1)
        layout.addLayout(comp_layout)

        # Action Buttons
        btn_layout = QHBoxLayout()

        self.btn_ai_repair = QPushButton("✨ AI Auto-Repair")
        self.btn_ai_repair.setObjectName("secondaryBtn")
        self.btn_ai_repair.clicked.connect(self._ai_repair)

        self.btn_prev = QPushButton("◀ Previous")
        self.btn_prev.setObjectName("secondaryBtn")
        self.btn_prev.clicked.connect(self._prev)

        self.btn_accept = QPushButton("✓ Accept & Next ▶")
        self.btn_accept.setObjectName("accentBtn")
        self.btn_accept.clicked.connect(self._accept_and_next)

        btn_layout.addWidget(self.btn_ai_repair)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_prev)
        btn_layout.addWidget(self.btn_accept)
        layout.addLayout(btn_layout)

    def _get_or_create_crop(self, block: BaseBlock) -> Optional[str]:
        """Ensures an image crop exists for the given block bounding box."""
        # 1. Check existing crop path
        if hasattr(block, "image_crop_path") and block.image_crop_path:
            if Path(block.image_crop_path).exists():
                return block.image_crop_path

        # 2. Generate crop from project preview images if available
        if not self.project or not self.project.document:
            return None

        page_num = block.source_page
        page_data = self.project.document.get_page(page_num)
        if not page_data or not page_data.preview_image_path or not Path(page_data.preview_image_path).exists():
            # Check default preview image file
            default_preview = self.project.images_dir / f"page_{page_num}.png"
            if default_preview.exists():
                preview_path = str(default_preview)
            else:
                return None
        else:
            preview_path = page_data.preview_image_path

        try:
            img = Image.open(preview_path)
            img_w, img_h = img.size
            page_w = page_data.width_pt if page_data and page_data.width_pt > 0 else 595.0
            page_h = page_data.height_pt if page_data and page_data.height_pt > 0 else 842.0

            scale_x = img_w / page_w
            scale_y = img_h / page_h

            bbox = block.bbox
            pad_x = 12.0
            pad_y = 8.0

            # If bbox is too small or default, give a reasonable viewing window
            x0 = max(0, int((bbox.x0 - pad_x) * scale_x))
            y0 = max(0, int((bbox.y0 - pad_y) * scale_y))
            x1 = min(img_w, int((bbox.x1 + pad_x) * scale_x))
            y1 = min(img_h, int((bbox.y1 + pad_y) * scale_y))

            if x1 <= x0 or y1 <= y0 or (x1 - x0) < 10:
                # Default viewing window around center
                x0 = max(0, int(bbox.x0 * scale_x) - 100)
                y0 = max(0, int(bbox.y0 * scale_y) - 40)
                x1 = min(img_w, x0 + 400)
                y1 = min(img_h, y0 + 120)

            cropped = img.crop((x0, y0, x1, y1))
            out_crop_file = self.project.images_dir / f"review_crop_p{page_num}_{block.id}.png"
            out_crop_file.parent.mkdir(parents=True, exist_ok=True)
            cropped.save(str(out_crop_file), "PNG")

            crop_str = str(out_crop_file.resolve())
            if hasattr(block, "image_crop_path"):
                block.image_crop_path = crop_str
            return crop_str
        except Exception as e:
            logger.warning(f"Failed to generate review crop for block {block.id}: {e}")
            return None

    def _load_current_block(self):
        if not self.blocks or self.current_idx >= len(self.blocks):
            self.accept()
            return

        block = self.blocks[self.current_idx]
        self.lbl_counter.setText(f"Reviewing Item {self.current_idx + 1} of {len(self.blocks)} (Page {block.source_page})")
        self.lbl_confidence.setText(f"Confidence: {int(block.confidence * 100)}%")

        if block.block_type == BlockType.FORMULA and isinstance(block, FormulaBlock):
            self.editor.setPlainText(block.latex)
            issues_text = "\n".join(block.issues) if block.issues else "Valid syntax"
            self.lbl_issues.setText(f"Issues: {issues_text}")
        elif block.block_type == BlockType.PARAGRAPH and isinstance(block, ParagraphBlock):
            self.editor.setPlainText(block.text)
            self.lbl_issues.setText("")
        else:
            text = getattr(block, "text", "") or getattr(block, "latex", "") or ""
            self.editor.setPlainText(text)
            self.lbl_issues.setText("")

        # Display crop image
        self.img_scene.clear()
        crop_path = self._get_or_create_crop(block)
        if crop_path and Path(crop_path).exists():
            pix = QPixmap(crop_path)
            if not pix.isNull():
                self.img_scene.addPixmap(pix)
                self.img_scene.setSceneRect(0, 0, pix.width(), pix.height())
                self.img_view.fitInView(self.img_scene.sceneRect(), Qt.KeepAspectRatio)
        else:
            # Fallback text in scene
            txt_item = self.img_scene.addText(f"Page {block.source_page} Region: [{block.bbox.x0:.0f}, {block.bbox.y0:.0f}, {block.bbox.x1:.0f}, {block.bbox.y1:.0f}]")
            txt_item.setDefaultTextColor(QColor("#94a3b8"))

    def _ai_repair(self):
        if not self.ai_router or self.current_idx >= len(self.blocks):
            return
        block = self.blocks[self.current_idx]
        try:
            if block.block_type == BlockType.FORMULA and isinstance(block, FormulaBlock):
                provider = self.ai_router.get_active_provider()
                repaired = provider.repair_formula(block.latex, block.issues)
                if repaired:
                    self.editor.setPlainText(repaired)
            elif block.block_type == BlockType.PARAGRAPH:
                provider = self.ai_router.get_active_provider()
                repaired = provider.correct_text(block.text)
                if repaired:
                    self.editor.setPlainText(repaired)
        except Exception as e:
            self.lbl_issues.setText(f"AI Repair error: {e}")

    def _accept_and_next(self):
        if self.current_idx < len(self.blocks):
            block = self.blocks[self.current_idx]
            new_text = self.editor.toPlainText().strip()
            if block.block_type == BlockType.FORMULA and isinstance(block, FormulaBlock):
                block.latex = new_text
                block.confidence = 1.0
                block.is_reviewed = True
                block.issues = []
            elif block.block_type == BlockType.PARAGRAPH and isinstance(block, ParagraphBlock):
                block.text = new_text
                block.confidence = 1.0
                block.is_reviewed = True

            self.block_updated.emit(block)

        self.current_idx += 1
        if self.current_idx < len(self.blocks):
            self._load_current_block()
        else:
            self.accept()

    def _prev(self):
        if self.current_idx > 0:
            self.current_idx -= 1
            self._load_current_block()
