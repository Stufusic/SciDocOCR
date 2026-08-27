"""Markdown, LaTeX, and Document AST Viewer/Editor Widget."""

import json
from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPlainTextEdit, QTextBrowser, QPushButton, QLabel, QSplitter
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt, Signal
from app.core.document import Document

class MarkdownViewer(QWidget):
    """Multi-tab Editor and Viewer for Markdown, LaTeX, and AST JSON."""

    content_saved = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.tabs = QTabWidget()

        # Tab 1: Markdown (Split View: Raw Editor | Formatted View)
        md_tab = QWidget()
        md_layout = QVBoxLayout(md_tab)
        md_layout.setContentsMargins(4, 4, 4, 4)

        md_splitter = QSplitter(Qt.Horizontal)

        # Editor
        self.md_editor = QPlainTextEdit()
        self.md_editor.setFont(QFont("Consolas", 11))
        self.md_editor.setPlaceholderText("Markdown content will appear here...")
        self.md_editor.textChanged.connect(self._on_md_text_changed)

        # Formatted Preview
        self.md_preview = QTextBrowser()
        self.md_preview.setFont(QFont("Segoe UI", 11))
        self.md_preview.setStyleSheet("background-color: #1e293b; color: #f8fafc; padding: 10px;")

        md_splitter.addWidget(self.md_editor)
        md_splitter.addWidget(self.md_preview)
        md_splitter.setSizes([300, 300])

        md_layout.addWidget(md_splitter)
        self.tabs.addTab(md_tab, "📝 Markdown")

        # Tab 2: LaTeX .tex
        tex_tab = QWidget()
        tex_layout = QVBoxLayout(tex_tab)
        tex_layout.setContentsMargins(4, 4, 4, 4)
        self.tex_editor = QPlainTextEdit()
        self.tex_editor.setFont(QFont("Consolas", 11))
        self.tex_editor.setPlaceholderText("LaTeX source will appear here...")
        tex_layout.addWidget(self.tex_editor)
        self.tabs.addTab(tex_tab, "📐 LaTeX (.tex)")

        # Tab 3: AST JSON
        ast_tab = QWidget()
        ast_layout = QVBoxLayout(ast_tab)
        ast_layout.setContentsMargins(4, 4, 4, 4)
        self.ast_viewer = QPlainTextEdit()
        self.ast_viewer.setFont(QFont("Consolas", 10))
        self.ast_viewer.setReadOnly(True)
        ast_layout.addWidget(self.ast_viewer)
        self.tabs.addTab(ast_tab, "🌳 Document AST")

        # Tab 4: AI Chat Assistant
        from app.gui.chat_panel import AIChatPanel
        from app.ai.router import AIRouter
        self.chat_panel = AIChatPanel(ai_router=AIRouter())
        self.tabs.addTab(self.chat_panel, "💬 AI Assistant")

        layout.addWidget(self.tabs)

    def set_ai_router(self, ai_router):
        self.chat_panel.ai_router = ai_router
        self.chat_panel._sync_with_settings()

    def set_markdown(self, text: str):
        self.md_editor.setPlainText(text)
        self._update_preview(text)

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
        self._update_preview(text)

    def _update_preview(self, text: str):
        # Basic markdown to HTML preview with math block styling
        html = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        # Convert # headings
        import re
        html = re.sub(r"^### (.*)$", r"<h3 style='color:#60a5fa;'>\1</h3>", html, flags=re.MULTILINE)
        html = re.sub(r"^## (.*)$", r"<h2 style='color:#38bdf8;'>\1</h2>", html, flags=re.MULTILINE)
        html = re.sub(r"^# (.*)$", r"<h1 style='color:#93c5fd;'>\1</h1>", html, flags=re.MULTILINE)

        # Convert bold / italic
        html = re.sub(r"\*\*([^\*]+)\*\*", r"<b>\1</b>", html)
        html = re.sub(r"\*([^\*]+)\*", r"<i>\1</i>", html)

        # Convert math display block $$...$$
        html = re.sub(
            r"\$\$([\s\S]*?)\$\$",
            r"<div style='background:#0f172a; border-left:3px solid #a855f7; padding:8px; margin:8px 0; font-family:Consolas;'>\1</div>",
            html
        )

        # Convert paragraphs
        paragraphs = html.split("\n\n")
        formatted = "".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paragraphs if p.strip())
        self.md_preview.setHtml(f"<div style='color:#f8fafc; font-size:14px; line-height:1.6;'>{formatted}</div>")

    def get_markdown(self) -> str:
        return self.md_editor.toPlainText()

    def get_latex(self) -> str:
        return self.tex_editor.toPlainText()
