"""Project Sidebar Panel showing document statistics, project file queue, and page list."""

from pathlib import Path
from typing import Optional, List, Union
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QGroupBox
)
from PySide6.QtCore import Qt, Signal
from app.core.document import Document, PageData

class ProjectPanel(QWidget):
    """Sidebar widget managing project status, stats, file queue, and page navigation."""

    page_selected = Signal(int)
    file_selected = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumWidth(240)
        self.project_files: List[Path] = []
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # 1. Project Documents Queue Group (Visible in Project Mode)
        self.docs_group = QGroupBox("📚 Danh Sách Tài Liệu Dự Án (0)")
        docs_layout = QVBoxLayout(self.docs_group)
        docs_layout.setContentsMargins(4, 4, 4, 4)

        self.doc_list = QListWidget()
        self.doc_list.currentRowChanged.connect(self._on_doc_row_changed)
        docs_layout.addWidget(self.doc_list)

        self.docs_group.setVisible(False)
        layout.addWidget(self.docs_group)

        # 2. Stats Card
        stats_group = QGroupBox("📊 Thông Tin Tài Liệu")
        stats_layout = QVBoxLayout(stats_group)
        stats_layout.setContentsMargins(8, 8, 8, 8)
        stats_layout.setSpacing(4)

        self.lbl_title = QLabel("Tài liệu: Chưa có")
        self.lbl_title.setStyleSheet("font-weight: bold; color: #60a5fa;")
        self.lbl_title.setWordWrap(True)
        self.lbl_pages = QLabel("Số trang: 0")
        self.lbl_formulas = QLabel("Công thức: 0")
        self.lbl_confidence = QLabel("Độ tin cậy TB: 100%")

        stats_layout.addWidget(self.lbl_title)
        stats_layout.addWidget(self.lbl_pages)
        stats_layout.addWidget(self.lbl_formulas)
        stats_layout.addWidget(self.lbl_confidence)

        layout.addWidget(stats_group)

        # 3. Pages List
        pages_group = QGroupBox("📄 Danh Sách Trang")
        pages_layout = QVBoxLayout(pages_group)
        pages_layout.setContentsMargins(4, 4, 4, 4)

        self.page_list = QListWidget()
        self.page_list.currentRowChanged.connect(self._on_row_changed)
        pages_layout.addWidget(self.page_list)

        layout.addWidget(pages_group)

    def populate_project_files(self, file_paths: List[Path]):
        """Populates the project file list with status badges."""
        self.project_files = list(file_paths)
        self.doc_list.clear()
        self.docs_group.setTitle(f"📚 Tài Liệu Dự Án ({len(self.project_files)})")
        self.docs_group.setVisible(bool(self.project_files))

        for idx, f in enumerate(self.project_files, 1):
            item = QListWidgetItem(f"{idx}. ⏳ [Chờ] {f.name}")
            item.setData(Qt.UserRole, str(f))
            self.doc_list.addItem(item)

        if self.project_files:
            self.doc_list.setCurrentRow(0)

    def update_project_file_status(self, idx: int, status: str):
        """Updates status badge of a project file (waiting, running, done, error)."""
        if 0 <= idx < self.doc_list.count():
            item = self.doc_list.item(idx)
            f_name = self.project_files[idx].name
            if status == "running":
                badge = "⚡ [Đang xử lý]"
            elif status == "done":
                badge = "✓ [Đã xong]"
            elif status == "error":
                badge = "✗ [Lỗi]"
            else:
                badge = "⏳ [Chờ]"
            item.setText(f"{idx + 1}. {badge} {f_name}")

    def update_document(self, doc: Document):
        title = doc.metadata.title or "Document"
        self.lbl_title.setText(f"Tài liệu: {title[:28]}...")
        stats = doc.get_stats()
        self.lbl_pages.setText(f"Số trang: {stats['page_count']}")
        self.lbl_formulas.setText(f"Công thức: {stats['formula_count']}")
        self.lbl_confidence.setText(f"Độ tin cậy TB: {int(stats['avg_confidence'] * 100)}%")

        self.page_list.clear()
        for page in doc.pages:
            badge = "✓" if page.status in ("ocr_done", "validated", "translated") else "⏳"
            if page.avg_confidence < 0.85:
                badge = "⚠"
            item = QListWidgetItem(f"Trang {page.page_number}  [{badge}] ({int(page.avg_confidence*100)}%)")
            self.page_list.addItem(item)

    def update_page_item(self, page_num: int, page_data: PageData):
        idx = page_num - 1
        badge = "✓" if page_data.status in ("ocr_done", "validated", "translated") else "⏳"
        if page_data.avg_confidence < 0.85:
            badge = "⚠"
        text = f"Trang {page_num}  [{badge}] ({int(page_data.avg_confidence*100)}%)"

        if idx < self.page_list.count():
            item = self.page_list.item(idx)
            item.setText(text)
        else:
            item = QListWidgetItem(text)
            self.page_list.addItem(item)

    def _on_row_changed(self, row: int):
        if row >= 0:
            self.page_selected.emit(row + 1)

    def _on_doc_row_changed(self, row: int):
        if 0 <= row < len(self.project_files):
            self.file_selected.emit(str(self.project_files[row]))
