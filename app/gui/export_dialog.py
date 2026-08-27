"""Export Dialog for saving Markdown, LaTeX, and compiled PDF artifacts."""

from pathlib import Path
from typing import Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QLineEdit, QPushButton, QFileDialog, QMessageBox, QGroupBox
)

class ExportDialog(QDialog):
    """Export dialog for choosing target file formats and export directory."""

    def __init__(self, default_out_dir: Path, base_name: str, parent: Optional[QDialog] = None):
        super().__init__(parent)
        self.setWindowTitle("SciDoc OCR - Export Document")
        self.resize(480, 320)
        self.default_out_dir = default_out_dir
        self.base_name = base_name

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Formats Group
        fmt_group = QGroupBox("Select Export Formats")
        fmt_layout = QVBoxLayout(fmt_group)

        self.chk_md = QCheckBox("Markdown (.md) with MathJax LaTeX math")
        self.chk_md.setChecked(True)

        self.chk_tex = QCheckBox("LaTeX Source (.tex) with standard packages")
        self.chk_tex.setChecked(True)

        self.chk_pdf = QCheckBox("Compiled PDF Document (.pdf)")
        self.chk_pdf.setChecked(True)

        self.chk_ast = QCheckBox("Document AST JSON (.json)")
        self.chk_ast.setChecked(False)

        fmt_layout.addWidget(self.chk_md)
        fmt_layout.addWidget(self.chk_tex)
        fmt_layout.addWidget(self.chk_pdf)
        fmt_layout.addWidget(self.chk_ast)
        layout.addWidget(fmt_group)

        # Directory Selector
        dir_group = QGroupBox("Export Destination")
        dir_layout = QHBoxLayout(dir_group)

        self.txt_dir = QLineEdit(str(self.default_out_dir))
        self.btn_browse = QPushButton("Browse...")
        self.btn_browse.setObjectName("secondaryBtn")
        self.btn_browse.clicked.connect(self._browse)

        dir_layout.addWidget(self.txt_dir)
        dir_layout.addWidget(self.btn_browse)
        layout.addWidget(dir_group)

        # Action Buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("secondaryBtn")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_export = QPushButton("Export Now")
        self.btn_export.setObjectName("accentBtn")
        self.btn_export.clicked.connect(self.accept)

        btn_box.addWidget(self.btn_cancel)
        btn_box.addWidget(self.btn_export)
        layout.addLayout(btn_box)

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Export Directory", self.txt_dir.text())
        if folder:
            self.txt_dir.setText(folder)

    def get_selected_options(self):
        return {
            "export_dir": Path(self.txt_dir.text()),
            "markdown": self.chk_md.isChecked(),
            "latex": self.chk_tex.isChecked(),
            "pdf": self.chk_pdf.isChecked(),
            "ast_json": self.chk_ast.isChecked(),
        }
