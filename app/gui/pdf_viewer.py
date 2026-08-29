"""Interactive PDF Page Viewer with Bounding Box Overlay."""

from typing import List, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QGraphicsRectItem, QGraphicsSimpleTextItem
)
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor, QPen, QBrush, QFont
from PySide6.QtCore import Qt, Signal, QRectF
from app.core.document import PageData
from app.core.blocks import BaseBlock, BlockType

class PDFViewer(QWidget):
    """PDF Page viewer with interactive zoom, navigation, and bounding boxes."""

    page_changed = Signal(int)
    block_clicked = Signal(object)  # BaseBlock

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.current_page = 1
        self.total_pages = 1
        self.current_page_data: Optional[PageData] = None
        self.pixmap_item: Optional[QGraphicsPixmapItem] = None
        self.show_bboxes = True
        self.zoom_factor = 1.0

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Control Bar
        ctrl_bar = QHBoxLayout()
        ctrl_bar.setContentsMargins(6, 4, 6, 4)

        self.btn_prev = QPushButton("◀ Prev")
        self.btn_prev.setObjectName("secondaryBtn")
        self.btn_prev.clicked.connect(self.prev_page)

        self.lbl_page = QLabel("Page 1 / 1")
        self.lbl_page.setAlignment(Qt.AlignCenter)
        self.lbl_page.setStyleSheet("font-weight: bold; min-width: 80px;")

        self.btn_next = QPushButton("Next ▶")
        self.btn_next.setObjectName("secondaryBtn")
        self.btn_next.clicked.connect(self.next_page)

        self.btn_zoom_in = QPushButton("🔍 +")
        self.btn_zoom_in.setObjectName("secondaryBtn")
        self.btn_zoom_in.clicked.connect(self.zoom_in)

        self.btn_zoom_out = QPushButton("🔍 -")
        self.btn_zoom_out.setObjectName("secondaryBtn")
        self.btn_zoom_out.clicked.connect(self.zoom_out)

        self.btn_toggle_bbox = QPushButton("Toggle BBoxes")
        self.btn_toggle_bbox.setObjectName("secondaryBtn")
        self.btn_toggle_bbox.clicked.connect(self.toggle_bboxes)

        ctrl_bar.addWidget(self.btn_prev)
        ctrl_bar.addWidget(self.lbl_page)
        ctrl_bar.addWidget(self.btn_next)
        ctrl_bar.addSpacing(12)
        ctrl_bar.addWidget(self.btn_zoom_in)
        ctrl_bar.addWidget(self.btn_zoom_out)
        ctrl_bar.addWidget(self.btn_toggle_bbox)
        ctrl_bar.addStretch()

        layout.addLayout(ctrl_bar)

        # Graphics Scene & View
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.view.setStyleSheet("background-color: #0f172a; border: 1px solid #334155; border-radius: 6px;")

        layout.addWidget(self.view)

    def load_page_image(self, image_path: str, page_data: Optional[PageData] = None, page_num: int = 1, total_pages: int = 1):
        self.current_page = page_num
        self.total_pages = max(1, total_pages)
        self.current_page_data = page_data
        self.lbl_page.setText(f"Page {self.current_page} / {self.total_pages}")

        self.scene.clear()
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return

        self.pixmap_item = self.scene.addPixmap(pixmap)
        self.scene.setSceneRect(QRectF(pixmap.rect()))

        if self.show_bboxes and page_data:
            self._render_bounding_boxes(page_data, pixmap.width(), pixmap.height())

        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def _render_bounding_boxes(self, page_data: PageData, img_w: float, img_h: float):
        scale_x = img_w / page_data.width_pt if page_data.width_pt > 0 else 1.0
        scale_y = img_h / page_data.height_pt if page_data.height_pt > 0 else 1.0

        for block in page_data.blocks:
            bbox = block.bbox
            rx = bbox.x0 * scale_x
            ry = bbox.y0 * scale_y
            rw = bbox.width * scale_x
            rh = bbox.height * scale_y

            if rw <= 0 or rh <= 0:
                continue

            color = QColor(59, 130, 246, 140)  # Default blue for Paragraph
            if block.block_type == BlockType.HEADING:
                color = QColor(16, 185, 129, 170)  # Emerald Green
            elif block.block_type == BlockType.FORMULA:
                color = QColor(168, 85, 247, 180)  # Purple
            elif block.block_type == BlockType.TABLE:
                color = QColor(245, 158, 11, 170)  # Amber
            elif block.block_type == BlockType.FIGURE:
                color = QColor(244, 63, 94, 180)   # Rose / Red
            elif block.block_type == BlockType.CAPTION:
                color = QColor(6, 182, 212, 170)   # Cyan

            pen = QPen(color, 2)
            brush = QBrush(QColor(color.red(), color.green(), color.blue(), 25))
            rect_item = self.scene.addRect(rx, ry, rw, rh, pen, brush)

            # Add confidence tag
            tag_name = block.block_type.value[:4].upper()
            tag = f"{tag_name} {int(block.confidence * 100)}%"
            tag_font = QFont("Segoe UI", 8)
            tag_font.setBold(True)
            text_item = self.scene.addSimpleText(tag, tag_font)
            text_item.setBrush(QBrush(color))
            text_item.setPos(rx + 2, max(0, ry - 14))

    def prev_page(self):
        if self.current_page > 1:
            self.page_changed.emit(self.current_page - 1)

    def next_page(self):
        if self.current_page < self.total_pages:
            self.page_changed.emit(self.current_page + 1)

    def zoom_in(self):
        self.view.scale(1.2, 1.2)

    def zoom_out(self):
        self.view.scale(1 / 1.2, 1 / 1.2)

    def toggle_bboxes(self):
        self.show_bboxes = not self.show_bboxes
        if self.current_page_data and self.current_page_data.preview_image_path:
            self.load_page_image(
                self.current_page_data.preview_image_path,
                self.current_page_data,
                self.current_page,
                self.total_pages
            )
