"""Markdown, LaTeX, and Document AST Viewer/Editor Widget with Code & View Mode Switching."""

import re
import json
from pathlib import Path
from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPlainTextEdit, QTextBrowser, QPushButton, QLabel, QSplitter,
    QApplication, QMenu
)
from PySide6.QtGui import QFont, QAction
from PySide6.QtCore import Qt, Signal
from app.core.document import Document
from app.utils import image_file_to_base64_data_uri

class MarkdownViewer(QWidget):
    """Multi-tab Editor and Viewer with a compact dropdown button next to the Markdown tab."""

    content_saved = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.current_mode = "split"  # "split", "code", "view"
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.tabs = QTabWidget()

        # =====================================================================
        # Tab Bar Corner Widget: Small compact mode button right beside Markdown tab
        # =====================================================================
        self.corner_widget = QWidget()
        corner_layout = QHBoxLayout(self.corner_widget)
        corner_layout.setContentsMargins(0, 2, 6, 2)
        corner_layout.setSpacing(6)

        # Small compact Dropdown Menu button
        self.btn_mode_menu = QPushButton("🔀 Split ▾")
        self.btn_mode_menu.setObjectName("secondaryBtn")
        self.btn_mode_menu.setStyleSheet("padding: 3px 9px; font-size: 11px; font-weight: bold; min-height: 20px; border-radius: 4px;")
        self.btn_mode_menu.setToolTip("Nhấn để chuyển đổi chế độ xem Markdown: Song song, Chỉ mã nguồn, hoặc Chỉ xem trước")

        self.mode_menu = QMenu(self)
        self.act_split = self.mode_menu.addAction("🔀 Song Song (Split View)")
        self.act_code = self.mode_menu.addAction("💻 Mã Nguồn (Code Only)")
        self.act_view = self.mode_menu.addAction("👁️ Xem Trước (Preview Only)")

        self.act_split.triggered.connect(lambda: self.set_view_mode("split"))
        self.act_code.triggered.connect(lambda: self.set_view_mode("code"))
        self.act_view.triggered.connect(lambda: self.set_view_mode("view"))

        self.btn_mode_menu.setMenu(self.mode_menu)
        corner_layout.addWidget(self.btn_mode_menu)

        self.btn_copy_md = QPushButton("📋 Sao Chép")
        self.btn_copy_md.setObjectName("secondaryBtn")
        self.btn_copy_md.setStyleSheet("padding: 3px 8px; font-size: 11px; min-height: 20px; border-radius: 4px;")
        self.btn_copy_md.clicked.connect(self._copy_markdown_to_clipboard)
        corner_layout.addWidget(self.btn_copy_md)

        self.lbl_md_stats = QLabel("")
        self.lbl_md_stats.setStyleSheet("color: #64748b; font-size: 11px; padding-right: 4px;")
        corner_layout.addWidget(self.lbl_md_stats)

        self.tabs.setCornerWidget(self.corner_widget, Qt.TopRightCorner)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # =====================================================================
        # Tab 1: Markdown (Full Height Splitter)
        # =====================================================================
        md_tab = QWidget()
        md_layout = QVBoxLayout(md_tab)
        md_layout.setContentsMargins(4, 4, 4, 4)
        md_layout.setSpacing(0)

        # Markdown Splitter: Raw Editor & Formatted HTML Browser
        self.md_splitter = QSplitter(Qt.Horizontal)

        # Raw Editor
        self.md_editor = QPlainTextEdit()
        self.md_editor.setFont(QFont("Consolas", 11))
        self.md_editor.setPlaceholderText("Nội dung Markdown sẽ xuất hiện tại đây...")
        self.md_editor.setStyleSheet("background-color: #0f172a; color: #f8fafc; border: 1px solid #334155; border-radius: 6px; padding: 8px;")
        self.md_editor.textChanged.connect(self._on_md_text_changed)

        # Formatted Rich View
        self.md_preview = QTextBrowser()
        self.md_preview.setFont(QFont("Segoe UI", 11))
        self.md_preview.setOpenExternalLinks(True)
        self.md_preview.setStyleSheet("background-color: #1e293b; color: #f8fafc; border: 1px solid #334155; border-radius: 6px; padding: 12px;")

        self.md_splitter.addWidget(self.md_editor)
        self.md_splitter.addWidget(self.md_preview)
        self.md_splitter.setSizes([350, 350])

        md_layout.addWidget(self.md_splitter)
        self.tabs.addTab(md_tab, "📝 Markdown")

        # =====================================================================
        # Tab 2: LaTeX .tex
        # =====================================================================
        tex_tab = QWidget()
        tex_layout = QVBoxLayout(tex_tab)
        tex_layout.setContentsMargins(4, 4, 4, 4)
        tex_layout.setSpacing(4)

        tex_toolbar = QHBoxLayout()
        btn_copy_tex = QPushButton("📋 Sao Chép LaTeX (.tex)")
        btn_copy_tex.setObjectName("secondaryBtn")
        btn_copy_tex.clicked.connect(self._copy_latex_to_clipboard)
        tex_toolbar.addWidget(btn_copy_tex)
        tex_toolbar.addStretch()
        tex_layout.addLayout(tex_toolbar)

        self.tex_editor = QPlainTextEdit()
        self.tex_editor.setFont(QFont("Consolas", 11))
        self.tex_editor.setPlaceholderText("Mã nguồn LaTeX sẽ xuất hiện tại đây...")
        self.tex_editor.setStyleSheet("background-color: #0f172a; color: #f8fafc; border: 1px solid #334155; border-radius: 6px; padding: 8px;")
        tex_layout.addWidget(self.tex_editor)
        self.tabs.addTab(tex_tab, "📐 LaTeX (.tex)")

        # =====================================================================
        # Tab 3: AST JSON
        # =====================================================================
        ast_tab = QWidget()
        ast_layout = QVBoxLayout(ast_tab)
        ast_layout.setContentsMargins(4, 4, 4, 4)
        self.ast_viewer = QPlainTextEdit()
        self.ast_viewer.setFont(QFont("Consolas", 10))
        self.ast_viewer.setReadOnly(True)
        self.ast_viewer.setStyleSheet("background-color: #0f172a; color: #f8fafc; border: 1px solid #334155; border-radius: 6px; padding: 8px;")
        ast_layout.addWidget(self.ast_viewer)
        self.tabs.addTab(ast_tab, "🌳 Document AST")

        # =====================================================================
        # Tab 4: AI Chat Assistant
        # =====================================================================
        from app.gui.chat_panel import AIChatPanel
        from app.ai.router import AIRouter
        self.chat_panel = AIChatPanel(ai_router=AIRouter())
        self.tabs.addTab(self.chat_panel, "💬 AI Assistant")

        layout.addWidget(self.tabs)

    # ------------------ Mode & Tab Switching ------------------

    def _on_tab_changed(self, index: int):
        """Shows Markdown mode & copy controls only on Tab 0 (Markdown), hides on other tabs."""
        if hasattr(self, "corner_widget") and self.corner_widget:
            self.corner_widget.setVisible(index == 0)

    def set_view_mode(self, mode: str):
        """Switches Markdown display mode: 'code', 'view', or 'split'."""
        self.current_mode = mode
        if mode == "code":
            self.btn_mode_menu.setText("💻 Code ▾")
            self.md_editor.show()
            self.md_preview.hide()
        elif mode == "view":
            self.btn_mode_menu.setText("👁️ Preview ▾")
            self.md_editor.hide()
            self.md_preview.show()
            self._update_preview(self.md_editor.toPlainText())
        else:  # split
            self.btn_mode_menu.setText("🔀 Split ▾")
            self.md_editor.show()
            self.md_preview.show()
            self.md_splitter.setSizes([350, 350])
            self._update_preview(self.md_editor.toPlainText())

    def _copy_markdown_to_clipboard(self):
        text = self.md_editor.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self.btn_copy_md.setText("✓ Đã chép!")
            from PySide6.QtCore import QTimer
            QTimer.singleShot(1500, lambda: self.btn_copy_md.setText("📋 Sao Chép"))

    def _copy_latex_to_clipboard(self):
        text = self.tex_editor.toPlainText()
        if text:
            QApplication.clipboard().setText(text)

    # ------------------ Content Setters ------------------

    def set_project(self, project):
        if project:
            self.project_dir = getattr(project, "project_dir", None)
            self.images_dir = getattr(project, "images_dir", None)

    def set_ai_router(self, ai_router):
        self.chat_panel.ai_router = ai_router
        self.chat_panel._sync_with_settings()

    def set_markdown(self, text: str, images_dir: Optional[Path] = None):
        if images_dir:
            self.images_dir = images_dir
        self.md_editor.setPlainText(text)
        self._update_preview(text)
        self._update_stats(text)

    def set_latex(self, text: str):
        self.tex_editor.setPlainText(text)

    def set_document_ast(self, doc: Document):
        try:
            formatted_json = json.dumps(doc.to_dict(), indent=2, ensure_ascii=False)
            self.ast_viewer.setPlainText(formatted_json)
            self.chat_panel.set_document(doc)
        except Exception:
            pass

    def _on_md_text_changed(self):
        text = self.md_editor.toPlainText()
        self._update_stats(text)
        if self.current_mode in ("view", "split"):
            self._update_preview(text)

    def _update_stats(self, text: str):
        if not text:
            self.lbl_md_stats.setText("0 từ | 0 ký tự")
            return
        words = len(text.split())
        chars = len(text)
        self.lbl_md_stats.setText(f"{words:,} từ | {chars:,} ký tự")

    # ------------------ Rich HTML Markdown Rendering ------------------

    def _update_preview(self, text: str):
        if not text:
            self.md_preview.setHtml("<div style='color:#64748b; font-style:italic; padding:20px;'>Tài liệu trống...</div>")
            return

        html = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        # 1. Code blocks (```...```)
        def _render_code_block(m):
            code_text = m.group(1).strip()
            return f"<pre style='background:#0f172a; color:#38bdf8; border:1px solid #334155; border-radius:6px; padding:10px; font-family:Consolas;'>{code_text}</pre>"
        html = re.sub(r"```[\w]*\n([\s\S]*?)```", _render_code_block, html)

        # 2. Math Display Blocks ($$...$$)
        def _render_math_block(m):
            math_expr = m.group(1).strip()
            return f"<div style='background:#0f172a; border-left:4px solid #a855f7; padding:10px 14px; margin:12px 0; border-radius:0 6px 6px 0; color:#e9d5ff; font-family:Consolas, monospace; font-size:14px;'>📐 <b>Công thức:</b><br><span style='color:#c084fc;'>{math_expr}</span></div>"
        html = re.sub(r"\$\$([\s\S]*?)\$\$", _render_math_block, html)

        # 3. Inline math ($...$)
        html = re.sub(r"\$([^\$\n]+?)\$", r"<code style='background:#3b0764; color:#d8b4fe; padding:2px 6px; border-radius:4px; font-family:Consolas;'>\1</code>", html)

        # 4. Headings
        html = re.sub(r"^#### (.*)$", r"<h4 style='color:#38bdf8; margin-top:14px; margin-bottom:6px;'>\1</h4>", html, flags=re.MULTILINE)
        html = re.sub(r"^### (.*)$", r"<h3 style='color:#60a5fa; margin-top:16px; margin-bottom:8px;'>\1</h3>", html, flags=re.MULTILINE)
        html = re.sub(r"^## (.*)$", r"<h2 style='color:#93c5fd; margin-top:20px; margin-bottom:10px; border-bottom:1px solid #334155; padding-bottom:4px;'>\1</h2>", html, flags=re.MULTILINE)
        html = re.sub(r"^# (.*)$", r"<h1 style='color:#bfdbfe; margin-top:24px; margin-bottom:12px; border-bottom:2px solid #3b82f6; padding-bottom:6px;'>\1</h1>", html, flags=re.MULTILINE)

        # 5. Bold & Italic
        html = re.sub(r"\*\*([^\*]+)\*\*", r"<b style='color:#ffffff;'>\1</b>", html)
        html = re.sub(r"\*([^\*]+)\*", r"<i>\1</i>", html)

        # 6. Blockquotes
        html = re.sub(r"^> (.*)$", r"<blockquote style='border-left:3px solid #64748b; margin:8px 0; padding-left:10px; color:#cbd5e1;'>\1</blockquote>", html, flags=re.MULTILINE)

        # 7. Images / Figures (Render real image directly via Base64 Data URI)
        def _render_image(m):
            caption = m.group(1).strip()
            img_rel_path = m.group(2).strip()

            candidates = []
            if Path(img_rel_path).is_absolute():
                candidates.append(Path(img_rel_path))

            img_name = Path(img_rel_path).name
            if hasattr(self, "images_dir") and self.images_dir:
                candidates.append(self.images_dir / img_name)
                candidates.append(self.images_dir / img_rel_path)
            if hasattr(self, "project_dir") and self.project_dir:
                candidates.append(self.project_dir / img_rel_path)
                candidates.append(self.project_dir / "images" / img_name)

            candidates.append(Path.cwd() / img_rel_path)

            resolved_file = None
            for c in candidates:
                if c and c.exists() and c.is_file():
                    resolved_file = c
                    break

            if resolved_file:
                data_uri = image_file_to_base64_data_uri(resolved_file)
                if data_uri:
                    cap_html = f"<div style='color:#94a3b8; font-size:12px; margin-top:6px;'><b>Hình:</b> <i>{caption}</i></div>" if caption else ""
                    return f"<div style='margin:16px 0; text-align:center;'><img src='{data_uri}' style='max-width:94%; max-height:480px; border:1px solid #475569; border-radius:6px; background-color:#ffffff; padding:4px;' /><br>{cap_html}</div>"

            cap_text = f": {caption}" if caption else ""
            return f"<div style='margin:12px 0; text-align:center;'><span style='background:#1e293b; border:1px solid #475569; padding:6px 12px; border-radius:4px; color:#94a3b8; font-size:12px;'>🖼️ Hình ảnh{cap_text} (<i>{img_rel_path}</i>)</span></div>"

        html = re.sub(r"!\[(.*?)\]\((.*?)\)", _render_image, html)

        # 8. Tables (| ... | ... |)
        def _render_table(m):
            table_lines = m.group(0).strip().split("\n")
            table_html = ["<table style='border-collapse:collapse; width:100%; margin:12px 0; border:1px solid #334155; font-size:13px;'>"]
            for idx, line in enumerate(table_lines):
                if re.match(r"^\|?\s*[-:]+[-| :]*\|?$", line):
                    continue
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if idx == 0:
                    row_html = "".join(f"<th style='border:1px solid #334155; padding:8px; background:#0f172a; color:#93c5fd; text-align:left;'>{c}</th>" for c in cells)
                else:
                    bg = "#1e293b" if idx % 2 == 0 else "#0f172a"
                    row_html = "".join(f"<td style='border:1px solid #334155; padding:7px 8px; background:{bg}; color:#f8fafc;'>{c}</td>" for c in cells)
                table_html.append(f"<tr>{row_html}</tr>")
            table_html.append("</table>")
            return "".join(table_html)

        html = re.sub(r"((?:^\|.+?\|\r?\n?)+)", _render_table, html, flags=re.MULTILINE)

        # 9. Paragraphs
        paragraphs = html.split("\n\n")
        formatted = "".join(f"<p style='margin:8px 0; line-height:1.65;'>{p.replace(chr(10), '<br>')}</p>" for p in paragraphs if p.strip())
        self.md_preview.setHtml(f"<div style='color:#f8fafc; font-family:Segoe UI, sans-serif; font-size:14px; line-height:1.65;'>{formatted}</div>")

    def get_markdown(self) -> str:
        return self.md_editor.toPlainText()

    def get_latex(self) -> str:
        return self.tex_editor.toPlainText()

