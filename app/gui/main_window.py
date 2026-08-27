"""Main Application Window for SciDoc OCR Studio."""

import os
import shutil
from pathlib import Path
from typing import Optional
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QFileDialog, QMessageBox, QToolBar
)
from PySide6.QtGui import QAction, QIcon
from PySide6.QtCore import Qt, QTimer

from app.gui.styles import DARK_THEME_QSS
from app.gui.pdf_viewer import PDFViewer
from app.gui.markdown_viewer import MarkdownViewer
from app.gui.project_panel import ProjectPanel
from app.gui.progress_panel import ProgressPanel
from app.gui.review_panel import ReviewDialog
from app.gui.settings_dialog import SettingsDialog
from app.gui.export_dialog import ExportDialog

from app.core.project import SciDocProject
from app.core.pipeline import JobPipelineWorker, PipelineState
from app.core.blocks import FormulaBlock, BlockType
from app.storage.settings import SettingsManager
from app.ai.router import AIRouter
from app.ocr.router import OCRRouter
from app.markdown.renderer import MarkdownRenderer
from app.latex.generator import LaTeXGenerator
from app.utils.logging import get_logger

logger = get_logger("MainWindow")

class MainWindow(QMainWindow):
    """SciDoc OCR Main Window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("SciDoc OCR - Scientific Document Studio v1.0")
        self.resize(1280, 800)
        self.setMinimumSize(850, 550)

        # Settings & Core engines
        self.settings_manager = SettingsManager()
        self.ai_router = self._build_ai_router()
        self.ocr_router = OCRRouter(mode=self.settings_manager.settings.ai_mode, ai_router=self.ai_router)
        self.markdown_renderer = MarkdownRenderer()
        self.latex_generator = LaTeXGenerator()

        self.current_project: Optional[SciDocProject] = None
        self.pipeline_worker: Optional[JobPipelineWorker] = None

        self._init_ui()
        self._apply_theme()

        # Check initial AI health once on startup without background polling loop
        self._check_ai_health()

    def _build_ai_router(self) -> AIRouter:
        s = self.settings_manager.settings
        return AIRouter(
            mode=s.ai_mode,
            lmstudio_url=s.lmstudio_url,
            lmstudio_model=s.lmstudio_model,
            online_provider=s.online_provider,
            online_key=s.online_api_key,
            online_url=s.online_api_url,
            online_model=s.online_model,
            translation_engine=getattr(s, "translation_engine", "google_translate")
        )

    def _init_ui(self):
        # 1. Menubar & Toolbar
        self._create_toolbars()

        # 2. Main Triple-Pane Layout
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        self.splitter = QSplitter(Qt.Horizontal)

        # Left: Project Sidebar
        self.project_panel = ProjectPanel()
        self.project_panel.page_selected.connect(self._on_page_selected)
        self.splitter.addWidget(self.project_panel)

        # Center: PDF Viewer
        self.pdf_viewer = PDFViewer()
        self.pdf_viewer.page_changed.connect(self._on_page_selected)
        self.splitter.addWidget(self.pdf_viewer)

        # Right: Markdown & LaTeX Viewer
        self.markdown_viewer = MarkdownViewer()
        self.splitter.addWidget(self.markdown_viewer)

        # Set initial splitter proportions: 220px | 500px | 500px
        self.splitter.setSizes([220, 520, 520])
        main_layout.addWidget(self.splitter, stretch=1)

        # Bottom: Progress Panel
        self.progress_panel = ProgressPanel()
        self.progress_panel.cancel_requested.connect(self._cancel_pipeline)
        self.progress_panel.review_requested.connect(self._open_review_mode)
        main_layout.addWidget(self.progress_panel)

        self.setCentralWidget(central_widget)

    def _create_toolbars(self):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # Open PDF
        act_open_pdf = QAction("📂 Open PDF", self)
        act_open_pdf.triggered.connect(self._action_open_pdf)
        toolbar.addAction(act_open_pdf)

        # Open Project
        act_open_proj = QAction("📁 Open Project", self)
        act_open_proj.triggered.connect(self._action_open_project)
        toolbar.addAction(act_open_proj)

        # Save Project
        act_save_proj = QAction("💾 Save", self)
        act_save_proj.triggered.connect(self._action_save_project)
        toolbar.addAction(act_save_proj)

        # Save Project As (Backup to custom folder)
        act_save_proj_as = QAction("📁 Save As...", self)
        act_save_proj_as.triggered.connect(self._action_save_project_as)
        toolbar.addAction(act_save_proj_as)

        toolbar.addSeparator()

        # Run OCR Pipeline
        self.act_run_pipeline = QAction("⚡ Process All", self)
        self.act_run_pipeline.triggered.connect(self._action_run_pipeline)
        toolbar.addAction(self.act_run_pipeline)

        # Translate Document
        self.act_translate = QAction("🌐 Translate", self)
        self.act_translate.triggered.connect(self._action_translate)
        toolbar.addAction(self.act_translate)

        # AI Chat Assistant
        act_chat = QAction("💬 AI Assistant", self)
        act_chat.triggered.connect(self._action_open_chat)
        toolbar.addAction(act_chat)

        # Export Dialog
        act_export = QAction("📤 Export...", self)
        act_export.triggered.connect(self._action_export)
        toolbar.addAction(act_export)

        toolbar.addSeparator()

        # Settings
        act_settings = QAction("⚙ Settings", self)
        act_settings.triggered.connect(self._action_settings)
        toolbar.addAction(act_settings)

    def _apply_theme(self):
        self.setStyleSheet(DARK_THEME_QSS)

    def _check_ai_health(self):
        status = self.ai_router.get_status()
        self.progress_panel.set_ai_status(
            online_ok=status["online_ai"],
            lmstudio_ok=status["lmstudio"]
        )
        self.markdown_viewer.set_ai_router(self.ai_router)

    # ------------------ Actions ------------------

    def _action_open_pdf(self):
        if self.pipeline_worker and self.pipeline_worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Pipeline Đang Chạy",
                "Tiến trình bóc tách tài liệu đang chạy. Bạn có muốn hủy tiến trình hiện tại và mở PDF mới?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
            self._cancel_pipeline()

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Scientific PDF Document", "", "PDF Files (*.pdf);;All Files (*)"
        )
        if not file_path:
            return

        pdf_name = Path(file_path).stem
        proj_dir = Path.home() / ".scidoc_projects" / pdf_name
        self.current_project = SciDocProject.create_new(
            project_dir=proj_dir,
            source_pdf_path=file_path,
            project_name=pdf_name
        )

        self._action_run_pipeline()

    def _action_open_project(self):
        if self.pipeline_worker and self.pipeline_worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Pipeline Đang Chạy",
                "Tiến trình đang chạy. Bạn có muốn hủy tiến trình hiện tại và mở dự án khác?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
            self._cancel_pipeline()

        folder = QFileDialog.getExistingDirectory(self, "Open SciDoc Project Directory")
        if not folder:
            return
        try:
            self.current_project = SciDocProject.load(Path(folder))
            if self.current_project.document:
                self._load_document_into_ui(self.current_project.document)
                QMessageBox.information(self, "Project Loaded", f"Loaded project with {len(self.current_project.document.pages)} pages.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load project: {e}")

    def _action_save_project(self):
        if self.current_project:
            self.current_project.save()
            QMessageBox.information(self, "Saved", f"Project saved successfully in:\n{self.current_project.project_dir}")

    def _action_save_project_as(self):
        if not self.current_project:
            QMessageBox.warning(self, "Save Project", "No active project to save.")
            return

        folder = QFileDialog.getExistingDirectory(self, "Select Destination Folder for Project Backup")
        if not folder:
            return

        target_dir = Path(folder)
        try:
            # Save current state first
            self.current_project.save()

            # Copy all project files to the target backup folder
            for item in self.current_project.project_dir.iterdir():
                dest_item = target_dir / item.name
                if item.is_dir():
                    if dest_item.exists():
                        shutil.rmtree(dest_item)
                    shutil.copytree(item, dest_item)
                else:
                    shutil.copy2(item, dest_item)

            QMessageBox.information(
                self,
                "Backup Saved",
                f"✓ Complete project successfully backed up to:\n{target_dir}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save project to {target_dir}:\n{e}")

    def _action_run_pipeline(self, translate: bool = False):
        if not self.current_project:
            QMessageBox.warning(self, "No Project", "Please open a PDF file first.")
            return

        s = self.settings_manager.settings
        self.ai_router = self._build_ai_router()
        self.ocr_router = OCRRouter(mode=s.ai_mode, ai_router=self.ai_router)

        self.pipeline_worker = JobPipelineWorker(
            project=self.current_project,
            ai_router=self.ai_router,
            ocr_router=self.ocr_router,
            translate=translate,
            source_lang=s.source_language,
            target_lang=s.target_language,
            compile_pdf=True,
            render_dpi=s.ocr_dpi or 400,
            mineru_method=getattr(s, "mineru_method", "auto"),
            mineru_cli_path=getattr(s, "mineru_cli_path", "magic-pdf")
        )

        self.pipeline_worker.signals.progress.connect(self.progress_panel.set_progress)
        self.pipeline_worker.signals.page_completed.connect(self._on_page_completed)
        self.pipeline_worker.signals.finished.connect(self._on_pipeline_finished)
        self.pipeline_worker.signals.error.connect(self._on_pipeline_error)

        self.progress_panel.btn_cancel.setEnabled(True)
        self.act_run_pipeline.setEnabled(False)
        self.act_translate.setEnabled(False)
        self.pipeline_worker.start()

    def _action_translate(self):
        self._action_run_pipeline(translate=True)

    def _action_open_chat(self):
        """Switches to the AI Assistant tab."""
        self.markdown_viewer.tabs.setCurrentIndex(3)

    def _action_settings(self):
        dlg = SettingsDialog(self.settings_manager, self)
        if dlg.exec() == SettingsDialog.Accepted:
            self.ai_router = self._build_ai_router()
            self._check_ai_health()

    def _action_export(self):
        if not self.current_project or not self.current_project.document:
            QMessageBox.warning(self, "Export", "No processed document to export.")
            return

        doc = self.current_project.document
        dlg = ExportDialog(self.current_project.output_dir, doc.metadata.title, self)
        if dlg.exec() == ExportDialog.Accepted:
            opts = dlg.get_selected_options()
            out_dir = opts["export_dir"]
            out_dir.mkdir(parents=True, exist_ok=True)
            stem = Path(doc.metadata.source_pdf_path).stem or "scidoc_export"

            # Copy images folder so exported Markdown and LaTeX can render images
            if self.current_project.images_dir.exists():
                export_img_dir = out_dir / "images"
                export_img_dir.mkdir(parents=True, exist_ok=True)
                for img_f in self.current_project.images_dir.glob("*.*"):
                    shutil.copy2(img_f, export_img_dir / img_f.name)

            if opts["markdown"]:
                md = self.markdown_renderer.render_document(doc)
                with open(out_dir / f"{stem}.md", "w", encoding="utf-8") as f:
                    f.write(md)

            if opts["latex"]:
                tex = self.latex_generator.generate_latex(doc)
                with open(out_dir / f"{stem}.tex", "w", encoding="utf-8") as f:
                    f.write(tex)

            if opts["pdf"]:
                # Copy compiled PDF if available
                compiled_pdf = self.current_project.output_dir / f"{stem}.pdf"
                if compiled_pdf.exists():
                    shutil.copy2(compiled_pdf, out_dir / f"{stem}.pdf")
                else:
                    from app.latex.compiler import LaTeXCompiler
                    LaTeXCompiler().compile_fallback_pdf(doc, str(out_dir / f"{stem}.pdf"))

            QMessageBox.information(self, "Export Completed", f"Files successfully exported to:\n{out_dir}")

    # ------------------ Pipeline Callbacks ------------------

    def _on_page_completed(self, page_num: int, page_data):
        self.project_panel.update_page_item(page_num, page_data)
        if page_num == 1 or self.pdf_viewer.current_page == page_num:
            if page_data.preview_image_path:
                self.pdf_viewer.load_page_image(
                    page_data.preview_image_path,
                    page_data,
                    page_num,
                    len(self.current_project.document.pages) if self.current_project.document else 1
                )

    def _on_pipeline_finished(self, doc):
        self.act_run_pipeline.setEnabled(True)
        self.act_translate.setEnabled(True)
        self.progress_panel.btn_cancel.setEnabled(False)
        self._load_document_into_ui(doc)

    def _on_pipeline_error(self, error_msg: str):
        self.act_run_pipeline.setEnabled(True)
        self.act_translate.setEnabled(True)
        self.progress_panel.btn_cancel.setEnabled(False)
        QMessageBox.critical(self, "Pipeline Error", f"Error during execution:\n{error_msg}")

    def _cancel_pipeline(self):
        if self.pipeline_worker:
            self.pipeline_worker.cancel()
            self.act_run_pipeline.setEnabled(True)
            self.act_translate.setEnabled(True)
            self.progress_panel.btn_cancel.setEnabled(False)
            self.progress_panel.set_progress(0, 100, "Processing cancelled by user.")

    def _load_document_into_ui(self, doc):
        self.project_panel.update_document(doc)

        # Markdown & LaTeX tabs
        md_text = self.markdown_renderer.render_document(doc)
        self.markdown_viewer.set_markdown(md_text)

        tex_text = self.latex_generator.generate_latex(doc)
        self.markdown_viewer.set_latex(tex_text)
        self.markdown_viewer.set_document_ast(doc)

        # Load first page in viewer
        if doc.pages:
            p1 = doc.pages[0]
            if p1.preview_image_path:
                self.pdf_viewer.load_page_image(p1.preview_image_path, p1, 1, len(doc.pages))

        # Check for review items
        stats = doc.get_stats()
        self.progress_panel.set_review_count(stats["low_confidence_count"])

    def _on_page_selected(self, page_num: int):
        if not self.current_project or not self.current_project.document:
            return
        doc = self.current_project.document
        page = doc.get_page(page_num)
        if page and page.preview_image_path:
            self.pdf_viewer.load_page_image(page.preview_image_path, page, page_num, len(doc.pages))

    def _open_review_mode(self):
        if not self.current_project or not self.current_project.document:
            return

        doc = self.current_project.document
        review_blocks = [b for b in doc.get_all_blocks() if b.confidence < 0.85 or (b.block_type == BlockType.FORMULA and not getattr(b, 'is_valid', True))]

        if not review_blocks:
            QMessageBox.information(self, "Review Mode", "All blocks have high confidence! No items need review.")
            return

        dlg = ReviewDialog(review_blocks, self.ai_router, self, project=self.current_project)
        dlg.block_updated.connect(self._on_reviewed_block_updated)
        dlg.exec()

    def _on_reviewed_block_updated(self, block):
        if self.current_project and self.current_project.document:
            self.current_project.save()
            self._load_document_into_ui(self.current_project.document)

    def closeEvent(self, event):
        """Safely stops background pipeline and chat threads when exiting."""
        if self.pipeline_worker and self.pipeline_worker.isRunning():
            self.pipeline_worker.cancel()
            self.pipeline_worker.wait(1500)
        if hasattr(self, 'markdown_viewer') and hasattr(self.markdown_viewer, 'chat_panel'):
            cp = getattr(self.markdown_viewer, 'chat_panel', None)
            if cp and hasattr(cp, 'current_worker') and cp.current_worker and cp.current_worker.isRunning():
                try:
                    cp.current_worker.cancel()
                    cp.current_worker.wait(1000)
                except Exception:
                    pass
        event.accept()
