"""Project Sidebar Panel showing document statistics and page list."""

from typing import Optional, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QGroupBox
)
from PySide6.QtCore import Qt, Signal
from app.core.document import Document, PageData

class ProjectPanel(QWidget):
    """Sidebar widget managing project status, stats, and page navigation."""

    page_selected = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumWidth(220)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # Stats Card
        stats_group = QGroupBox("📊 Document Info")
        stats_layout = QVBoxLayout(stats_group)
        stats_layout.setContentsMargins(8, 8, 8, 8)
        stats_layout.setSpacing(4)

        self.lbl_title = QLabel("Title: None")
        self.lbl_title.setStyleSheet("font-weight: bold; color: #60a5fa;")
        self.lbl_pages = QLabel("Pages: 0")
        self.lbl_formulas = QLabel("Formulas: 0")
        self.lbl_confidence = QLabel("Avg Confidence: 100%")

        stats_layout.addWidget(self.lbl_title)
        stats_layout.addWidget(self.lbl_pages)
        stats_layout.addWidget(self.lbl_formulas)
        stats_layout.addWidget(self.lbl_confidence)

        layout.addWidget(stats_group)

        # Pages List
        pages_group = QGroupBox("📄 Pages")
        pages_layout = QVBoxLayout(pages_group)
        pages_layout.setContentsMargins(4, 4, 4, 4)

        self.page_list = QListWidget()
        self.page_list.currentRowChanged.connect(self._on_row_changed)
        pages_layout.addWidget(self.page_list)

        layout.addWidget(pages_group)

    def update_document(self, doc: Document):
        self.lbl_title.setText(f"Title: {doc.metadata.title[:20]}...")
        stats = doc.get_stats()
        self.lbl_pages.setText(f"Pages: {stats['page_count']}")
        self.lbl_formulas.setText(f"Formulas: {stats['formula_count']}")
        self.lbl_confidence.setText(f"Avg Confidence: {int(stats['avg_confidence'] * 100)}%")

        self.page_list.clear()
        for page in doc.pages:
            badge = "✓" if page.status in ("ocr_done", "validated", "translated") else "⏳"
            if page.avg_confidence < 0.85:
                badge = "⚠"
            item = QListWidgetItem(f"Page {page.page_number}  [{badge}] ({int(page.avg_confidence*100)}%)")
            self.page_list.addItem(item)

    def update_page_item(self, page_num: int, page_data: PageData):
        idx = page_num - 1
        badge = "✓" if page_data.status in ("ocr_done", "validated", "translated") else "⏳"
        if page_data.avg_confidence < 0.85:
            badge = "⚠"
        text = f"Page {page_num}  [{badge}] ({int(page_data.avg_confidence*100)}%)"

        if idx < self.page_list.count():
            item = self.page_list.item(idx)
            item.setText(text)
        else:
            item = QListWidgetItem(text)
            self.page_list.addItem(item)

    def _on_row_changed(self, row: int):
        if row >= 0:
            self.page_selected.emit(row + 1)
