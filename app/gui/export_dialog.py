"""Export Dialog for saving Markdown, LaTeX, and compiled PDF artifacts."""

from pathlib import Path
from typing import Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QLineEdit, QPushButton, QFileDialog, QMessageBox, QGroupBox
)

class ExportDialog(QDialog):
    """Export dialog for choosing target file formats and export directory."""

    def __init__(self, default_parent_dir: Optional[Path] = None, base_name: str = "document", parent: Optional[QDialog] = None):
        super().__init__(parent)
        self.setWindowTitle("SciDoc OCR - Xuất Toàn Bộ Tài Liệu")
        self.resize(540, 380)
        self.base_name = base_name
        
        # Default to Documents folder or user home
        if default_parent_dir and default_parent_dir.exists():
            self.default_parent_dir = default_parent_dir
        else:
            doc_dir = Path.home() / "Documents"
            self.default_parent_dir = doc_dir if doc_dir.exists() else Path.home()

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Formats Group
        fmt_group = QGroupBox("Chọn Các Định Dạng Xuất (Export Formats)")
        fmt_layout = QVBoxLayout(fmt_group)

        self.chk_md = QCheckBox("📝 Markdown (.md) kèm công thức LaTeX MathJax")
        self.chk_md.setChecked(True)

        self.chk_tex = QCheckBox("📜 LaTeX Source (.tex) tiêu chuẩn đa ngôn ngữ")
        self.chk_tex.setChecked(True)

        self.chk_pdf = QCheckBox("📄 PDF Document (.pdf) đã biên dịch hoàn chỉnh")
        self.chk_pdf.setChecked(True)

        self.chk_images = QCheckBox("🖼️ Thư mục ảnh trích xuất & biểu đồ (images/)")
        self.chk_images.setChecked(True)

        self.chk_ast = QCheckBox("🧩 Cấu trúc Document AST JSON (.json)")
        self.chk_ast.setChecked(False)

        fmt_layout.addWidget(self.chk_md)
        fmt_layout.addWidget(self.chk_tex)
        fmt_layout.addWidget(self.chk_pdf)
        fmt_layout.addWidget(self.chk_images)
        fmt_layout.addWidget(self.chk_ast)
        layout.addWidget(fmt_group)

        # Directory Selector
        dir_group = QGroupBox("Vị Trí Lưu Tài Liệu (Export Location)")
        dir_layout = QVBoxLayout(dir_group)
        dir_layout.setSpacing(6)

        path_row = QHBoxLayout()
        self.txt_dir = QLineEdit(str(self.default_parent_dir))
        self.txt_dir.textChanged.connect(self._update_preview_label)
        self.btn_browse = QPushButton("📁 Chọn Vị Trí...")
        self.btn_browse.setObjectName("secondaryBtn")
        self.btn_browse.clicked.connect(self._browse)

        path_row.addWidget(self.txt_dir)
        path_row.addWidget(self.btn_browse)
        dir_layout.addLayout(path_row)

        self.lbl_hint = QLabel()
        self.lbl_hint.setStyleSheet("color: #38bdf8; font-size: 9pt;")
        dir_layout.addWidget(self.lbl_hint)
        self._update_preview_label()

        layout.addWidget(dir_group)

        # Action Buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch()
        self.btn_cancel = QPushButton("Hủy")
        self.btn_cancel.setObjectName("secondaryBtn")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_export = QPushButton("🚀 Xuất Vào Vị Trí Đã Chọn")
        self.btn_export.setObjectName("accentBtn")
        self.btn_export.clicked.connect(self.accept)

        btn_box.addWidget(self.btn_cancel)
        btn_box.addWidget(self.btn_export)
        layout.addLayout(btn_box)

    def _update_preview_label(self):
        curr_text = self.txt_dir.text().strip()
        if not curr_text:
            return
        curr = Path(curr_text)
        target_path = curr / self.base_name if curr.name != self.base_name else curr
        self.lbl_hint.setText(f"📁 Tất cả file sẽ được xuất vào: <b>{target_path}</b>")

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn Vị Trí Lưu Thư Mục Tài Liệu", self.txt_dir.text())
        if folder:
            self.txt_dir.setText(folder)
            self._update_preview_label()

    def get_selected_options(self):
        return {
            "export_dir": Path(self.txt_dir.text().strip()),
            "markdown": self.chk_md.isChecked(),
            "latex": self.chk_tex.isChecked(),
            "pdf": self.chk_pdf.isChecked(),
            "images": self.chk_images.isChecked(),
            "ast_json": self.chk_ast.isChecked(),
        }
