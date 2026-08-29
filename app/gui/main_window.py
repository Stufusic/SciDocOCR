"""Main Application Window for SciDoc OCR Studio."""

import os
import re
import json
import shutil
from pathlib import Path
from typing import Optional
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QFileDialog, QMessageBox, QToolBar
)
from PySide6.QtGui import QAction, QIcon
from PySide6.QtCore import Qt, QTimer, QThread, Signal

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
from app.translation.translator import DocumentTranslator
from app.utils import get_logger, sanitize_filename, purge_directory, get_projects_dir, safe_write_text

logger = get_logger("MainWindow")

class MarkdownTranslationWorker(QThread):
    """Worker thread that translates Markdown sequentially in ~1500-char chunks and streams results live."""
    chunk_ready = Signal(str, int, int)
    progress = Signal(int, int, str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, markdown_text: str, translator: DocumentTranslator, source_lang: str, target_lang: str):
        super().__init__()
        self.markdown_text = markdown_text
        self.translator = translator
        self.source_lang = source_lang
        self.target_lang = target_lang
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            def on_chunk(accumulated, current, total):
                if self._is_cancelled:
                    return
                pct = int((current / total) * 100) if total > 0 else 0
                self.progress.emit(pct, 100, f"Đang dịch phần {current}/{total} (1500 ký tự/lần)...")
                self.chunk_ready.emit(accumulated, current, total)

            result = self.translator.translate_markdown_stream(
                self.markdown_text,
                source_lang=self.source_lang,
                target_lang=self.target_lang,
                chunk_size=1500,
                chunk_callback=on_chunk,
                cancel_check=lambda: self._is_cancelled
            )
            if not self._is_cancelled:
                self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))

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
        self.trans_worker: Optional[MarkdownTranslationWorker] = None
        self.queued_pdf_path: Optional[str] = None

        # Batch Project Processing State
        self.project_dir: Optional[Path] = None
        self.project_pdf_files: List[Path] = []
        self.batch_queue: List[Path] = []
        self.batch_export_dir: Optional[Path] = None
        self.batch_current_index: int = 0
        self.batch_total_count: int = 0
        self.is_batch_processing: bool = False

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
        self.project_panel.file_selected.connect(self._on_project_file_selected)
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

        # Run OCR Pipeline / Process All (Only shown when a Project is opened)
        self.act_run_pipeline = QAction("⚡ Process All", self)
        self.act_run_pipeline.triggered.connect(self._action_run_pipeline)
        self.act_run_pipeline.setVisible(False)
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

    # ------------------ Actions & Queue ------------------

    def _load_and_run_pdf(self, file_path: str, translate: bool = False, auto_run: bool = True):
        """Initializes workspace, displays initial PDF preview, and optionally starts pipeline."""
        pdf_name = Path(file_path).stem
        self.setWindowTitle(f"SciDoc OCR Studio - {pdf_name}.pdf")

        # Clear UI components from previous document
        if hasattr(self, 'markdown_viewer'):
            self.markdown_viewer.set_markdown("")
            self.markdown_viewer.set_latex("")
        if hasattr(self, 'project_panel') and hasattr(self.project_panel, 'page_list'):
            self.project_panel.page_list.clear()

        # Clean up / Purge all previous internal cache directories so storage stays 100% clean
        projects_root = get_projects_dir()
        purge_directory(projects_root, keep_root=True)

        proj_dir = projects_root / pdf_name
        self.current_project = SciDocProject.create_new(
            project_dir=proj_dir,
            source_pdf_path=file_path,
            project_name=pdf_name
        )

        # 1. Instantly display PDF Page 1 & populate page list in app
        try:
            from app.pdf.analyzer import PDFAnalyzer
            from app.pdf.renderer import PDFRenderer
            with PDFAnalyzer(file_path) as analyzer:
                renderer = PDFRenderer(analyzer.doc)
                preview_file = self.current_project.images_dir / "page_1.png"
                img_bytes = renderer.render_page_to_bytes(0, dpi=150)
                with open(preview_file, "wb") as f:
                    f.write(img_bytes)
                total_p = analyzer.page_count
                self.pdf_viewer.load_page_image(str(preview_file), None, 1, total_p)
                for p_i in range(1, total_p + 1):
                    self.project_panel.page_list.addItem(f"Trang {p_i} (Đang chờ...)")
        except Exception as e:
            logger.warning(f"Could not render instant initial preview: {e}")

        # 2. Execute pipeline if auto_run requested
        if auto_run:
            self._action_run_pipeline(translate=translate)

    def _action_open_pdf(self):
        # If a pipeline is currently running, support queuing exactly 1 subsequent file
        if self.pipeline_worker and self.pipeline_worker.isRunning():
            if self.queued_pdf_path is not None:
                QMessageBox.warning(
                    self,
                    "Hàng Đợi Đã Đầy",
                    f"Hàng đợi hiện đã có 1 file đang chờ: '{Path(self.queued_pdf_path).name}'.\n"
                    "Hệ thống chỉ cho phép tối đa 1 file trong hàng đợi. Vui lòng chờ tiến trình hoàn tất!"
                )
                return

            file_path, _ = QFileDialog.getOpenFileName(
                self, "Chọn File PDF Đưa Vào Hàng Đợi (Queue)", "", "PDF Files (*.pdf);;All Files (*)"
            )
            if not file_path:
                return

            self.queued_pdf_path = file_path
            pdf_name = Path(file_path).name
            QMessageBox.information(
                self,
                "Đã Thêm Vào Hàng Đợi",
                f"✓ File '{pdf_name}' đã được thêm vào hàng đợi.\n"
                "Tiến trình sẽ tự động xử lý file này ngay sau khi file hiện tại hoàn thành."
            )
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Scientific PDF Document", "", "PDF Files (*.pdf);;All Files (*)"
        )
        if not file_path:
            return

        # Single document mode
        self.is_batch_processing = False
        self.project_pdf_files = []
        self.project_panel.docs_group.setVisible(False)
        self.act_run_pipeline.setVisible(False)

        self._load_and_run_pdf(file_path, auto_run=True)

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

        folder = QFileDialog.getExistingDirectory(self, "Chọn Thư Mục Dự Án (Chứa các file PDF)")
        if not folder:
            return

        proj_path = Path(folder)
        pdf_files: List[Path] = []
        for root, _, files in os.walk(folder):
            for f in sorted(files):
                f_lower = f.lower()
                r_lower = root.lower()
                if f_lower.endswith(".pdf") and not f_lower.endswith("_output.pdf") and "images" not in r_lower and ".scidoc" not in r_lower:
                    full_p = Path(root) / f
                    if full_p not in pdf_files:
                        pdf_files.append(full_p)

        if not pdf_files:
            QMessageBox.warning(self, "Mở Dự Án", f"Không tìm thấy tệp PDF nào trong thư mục:\n{folder}")
            return

        self.project_dir = proj_path
        self.project_pdf_files = pdf_files
        self.project_panel.populate_project_files(pdf_files)

        # Show and update Process All action button
        self.act_run_pipeline.setVisible(True)
        self.act_run_pipeline.setEnabled(True)
        self.act_run_pipeline.setText(f"⚡ Process All ({len(pdf_files)})")

        # Load preview of first PDF without running pipeline yet
        self._load_and_run_pdf(str(pdf_files[0]), auto_run=False)

        QMessageBox.information(
            self,
            "Đã Nạp Dự Án",
            f"✓ Đã tìm thấy {len(pdf_files)} tài liệu PDF trong dự án: '{proj_path.name}'.\n\n"
            f"Nhấn nút '⚡ Process All ({len(pdf_files)})' trên thanh công cụ để tự động xử lý và xuất toàn bộ dự án."
        )

    def _on_project_file_selected(self, file_path: str):
        """When user clicks a file in the project document list."""
        if self.pipeline_worker and self.pipeline_worker.isRunning():
            return
        self._load_and_run_pdf(file_path, auto_run=False)

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
            self.current_project.save()
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
        # 1. Batch Project Processing Mode
        if self.project_pdf_files and len(self.project_pdf_files) > 0 and not self.is_batch_processing:
            default_export_dir = self.project_dir if self.project_dir else (Path.home() / "Documents")
            msg = QMessageBox(self)
            msg.setWindowTitle("Xác Nhận Xử Lý Dự Án (Process All)")
            msg.setIcon(QMessageBox.Question)
            msg.setText(
                f"Bắt đầu tự động xử lý toàn bộ <b>{len(self.project_pdf_files)} tài liệu</b> theo thứ tự từ trên xuống?<br><br>"
                f"📁 Vị trí xuất kết quả mặc định:<br><b>{default_export_dir}</b><br><br>"
                f"<i>(Mỗi tài liệu sẽ tự động được nạp, xử lý và xuất ra một thư mục mang tên tài liệu đó)</i>"
            )
            btn_start = msg.addButton("🚀 Bắt Đầu Xử Lý Tất Cả", QMessageBox.AcceptRole)
            btn_choose_dir = msg.addButton("📁 Đổi Vị Trí Xuất...", QMessageBox.ActionRole)
            btn_cancel = msg.addButton("Hủy", QMessageBox.RejectRole)

            msg.exec()
            clicked = msg.clickedButton()
            if clicked == btn_cancel:
                return
            elif clicked == btn_choose_dir:
                custom_dir = QFileDialog.getExistingDirectory(self, "Chọn Thư Mục Xuất Toàn Bộ Dự Án", str(default_export_dir))
                if not custom_dir:
                    return
                chosen_export_dir = Path(custom_dir)
            else:
                chosen_export_dir = default_export_dir

            # Initialize Batch Processing Queue
            self.is_batch_processing = True
            self.batch_queue = list(self.project_pdf_files)
            self.batch_total_count = len(self.project_pdf_files)
            self.batch_current_index = 0
            self.batch_export_dir = chosen_export_dir

            self._run_next_batch_item()
            return

        # 2. Single Document Processing Mode
        if not self.current_project:
            QMessageBox.warning(self, "Không Có Tài Liệu", "Vui lòng mở một file PDF hoặc chọn Open Project trước.")
            return

        if self.pipeline_worker and self.pipeline_worker.isRunning():
            self.pipeline_worker.cancel()
            self.pipeline_worker.wait(3000)

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
        self.pipeline_worker.signals.layout_detected.connect(self._on_layout_detected)
        self.pipeline_worker.signals.page_completed.connect(self._on_page_completed)
        self.pipeline_worker.signals.finished.connect(self._on_pipeline_finished)
        self.pipeline_worker.signals.error.connect(self._on_pipeline_error)

        self.progress_panel.btn_cancel.setEnabled(True)
        self.act_run_pipeline.setEnabled(False)
        self.act_translate.setEnabled(False)
        self.pipeline_worker.start()

    def _run_next_batch_item(self):
        """Processes the next PDF document in the batch queue."""
        if not self.batch_queue:
            # Batch completely finished!
            self.is_batch_processing = False
            self.act_run_pipeline.setEnabled(True)
            self.act_translate.setEnabled(True)
            self.progress_panel.btn_cancel.setEnabled(False)
            self.progress_panel.set_progress(100, 100, f"✓ Đã hoàn tất xử lý toàn bộ {self.batch_total_count} tài liệu!")

            msg = QMessageBox(self)
            msg.setWindowTitle("Hoàn Tất Xử Lý Dự Án")
            msg.setIcon(QMessageBox.Information)
            msg.setText(
                f"✓ Đã hoàn tất xử lý và xuất toàn bộ <b>{self.batch_total_count} tài liệu</b> trong dự án!<br><br>"
                f"📁 Thư mục lưu trữ: <b>{self.batch_export_dir}</b>"
            )
            btn_open = msg.addButton("📂 Mở Thư Mục Dự Án", QMessageBox.ActionRole)
            msg.addButton("Đóng", QMessageBox.RejectRole)
            msg.exec()
            if msg.clickedButton() == btn_open:
                try:
                    import os
                    os.startfile(str(self.batch_export_dir))
                except Exception:
                    pass
            return

        next_pdf = self.batch_queue.pop(0)
        self.batch_current_index += 1
        self.project_panel.update_project_file_status(self.batch_current_index - 1, "running")
        self.progress_panel.set_progress(
            0, 100,
            f"Đang xử lý [{self.batch_current_index}/{self.batch_total_count}]: {next_pdf.name}..."
        )
        self._load_and_run_pdf(str(next_pdf), auto_run=True)

    def _action_translate(self):
        # 1. If Markdown text already exists in editor/viewer, translate it in ~1500-char streaming chunks!
        current_md = self.markdown_viewer.get_markdown().strip()
        if current_md:
            s = self.settings_manager.get_settings()
            self.act_run_pipeline.setEnabled(False)
            self.act_translate.setEnabled(False)
            self.progress_panel.btn_cancel.setEnabled(True)
            self.progress_panel.set_progress(0, 100, "Bắt đầu dịch Markdown (1500 ký tự/lần)...")

            translator = DocumentTranslator(self.ai_router)
            self.trans_worker = MarkdownTranslationWorker(
                markdown_text=current_md,
                translator=translator,
                source_lang=s.source_language,
                target_lang=s.target_language
            )
            self.trans_worker.chunk_ready.connect(self._on_translation_chunk_ready)
            self.trans_worker.progress.connect(self.progress_panel.set_progress)
            self.trans_worker.finished.connect(self._on_markdown_translation_finished)
            self.trans_worker.error.connect(self._on_markdown_translation_error)
            self.trans_worker.start()
            return

        # 2. Otherwise run full pipeline with translate=True
        self._action_run_pipeline(translate=True)

    def _on_translation_chunk_ready(self, accumulated_md: str, current: int, total: int):
        """Pushes translated Markdown live to editor & rich preview as each chunk arrives."""
        self.markdown_viewer.set_markdown(
            accumulated_md,
            images_dir=self.current_project.images_dir if self.current_project else None
        )

    def _on_markdown_translation_finished(self, final_md: str):
        self.act_run_pipeline.setEnabled(True)
        self.act_translate.setEnabled(True)
        self.progress_panel.btn_cancel.setEnabled(False)
        self.progress_panel.set_progress(100, 100, "✓ Dịch Markdown hoàn tất!")

        self.markdown_viewer.set_markdown(
            final_md,
            images_dir=self.current_project.images_dir if self.current_project else None
        )

        # Update Project cache file if project is loaded
        if self.current_project:
            try:
                md_path = self.current_project.project_dir / "output.md"
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(final_md)
            except Exception as e:
                logger.warning(f"Could not save output.md: {e}")

    def _on_markdown_translation_error(self, err_msg: str):
        self.act_run_pipeline.setEnabled(True)
        self.act_translate.setEnabled(True)
        self.progress_panel.btn_cancel.setEnabled(False)
        QMessageBox.critical(self, "Lỗi Dịch Thuật", f"Đã xảy ra lỗi khi dịch:\n{err_msg}")

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
            QMessageBox.warning(self, "Xuất Tài Liệu", "Không có tài liệu đã xử lý để xuất.")
            return

        doc = self.current_project.document
        raw_name = Path(doc.metadata.source_pdf_path).stem if doc.metadata.source_pdf_path else (self.current_project.project_name or "scidoc_export")
        safe_stem = sanitize_filename(raw_name, fallback="scidoc_export")

        # Open Export Dialog with clean default location (e.g. Documents)
        doc_dir = Path.home() / "Documents"
        default_parent_dir = doc_dir if doc_dir.exists() else Path.home()
        dlg = ExportDialog(default_parent_dir, safe_stem, self)
        if dlg.exec() == ExportDialog.Accepted:
            opts = dlg.get_selected_options()
            selected_dir = opts["export_dir"]

            # Ensure all exported files and images are grouped into a dedicated folder named after the document
            if selected_dir.name != safe_stem:
                out_dir = selected_dir / safe_stem
            else:
                out_dir = selected_dir

            out_dir.mkdir(parents=True, exist_ok=True)

            # 1. Copy images folder so exported Markdown and LaTeX can render images seamlessly
            if opts.get("images", True) and self.current_project.images_dir.exists():
                export_img_dir = out_dir / "images"
                export_img_dir.mkdir(parents=True, exist_ok=True)
                for img_f in self.current_project.images_dir.glob("*.*"):
                    try:
                        shutil.copy2(img_f, export_img_dir / img_f.name)
                    except Exception as e:
                        logger.warning(f"Could not copy image {img_f}: {e}")

            # 2. Export Markdown (.md) - prioritizing latest edited/translated content in viewer
            if opts["markdown"]:
                md_text = self.markdown_viewer.get_markdown().strip() or self.markdown_renderer.render_document(doc)
                with open(out_dir / f"{safe_stem}.md", "w", encoding="utf-8") as f:
                    f.write(md_text)

            # 3. Export LaTeX (.tex) - prioritizing latest LaTeX code in viewer
            if opts["latex"]:
                tex_text = self.markdown_viewer.get_latex().strip() or self.latex_generator.generate_latex(doc)
                with open(out_dir / f"{safe_stem}.tex", "w", encoding="utf-8") as f:
                    f.write(tex_text)

            # 4. Export Compiled PDF Document (.pdf)
            if opts["pdf"]:
                compiled_candidates = [
                    self.current_project.output_dir / f"{safe_stem}.pdf",
                    self.current_project.output_dir / f"{raw_name}.pdf",
                    self.current_project.output_dir / f"{raw_name}_output.pdf",
                    self.current_project.output_dir / "output.pdf"
                ]
                existing_pdf = next((p for p in compiled_candidates if p.exists()), None)
                target_pdf = out_dir / f"{safe_stem}.pdf"
                if existing_pdf:
                    try:
                        shutil.copy2(existing_pdf, target_pdf)
                    except Exception:
                        pass
                else:
                    from app.latex.compiler import LaTeXCompiler
                    LaTeXCompiler().compile_fallback_pdf(doc, str(target_pdf))

            # 5. Export AST JSON structure (.json)
            if opts.get("ast_json", False):
                import json
                with open(out_dir / f"{safe_stem}_ast.json", "w", encoding="utf-8") as f:
                    json.dump(doc.to_dict(), f, indent=2, ensure_ascii=False)

            # Show Success notification with 1-click "Open Folder" button
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Xuất Tài Liệu Thành Công")
            msg_box.setIcon(QMessageBox.Information)
            msg_box.setText(f"✓ Đã gom toàn bộ tệp chuyển đổi và thư mục ảnh vào:\n\n📁 {out_dir}")
            btn_open = msg_box.addButton("📂 Mở Thư Mục", QMessageBox.ActionRole)
            msg_box.addButton("Đóng", QMessageBox.RejectRole)
            msg_box.exec()
            if msg_box.clickedButton() == btn_open:
                import os
                try:
                    os.startfile(str(out_dir))
                except Exception:
                    pass

    # ------------------ Pipeline Callbacks ------------------

    def _on_layout_detected(self, page_num: int, page_data):
        """Immediately renders YOLOv10 layout bounding boxes onto PDF Viewer before LLM transcription."""
        if page_num == 1 or self.pdf_viewer.current_page == page_num:
            if page_data.preview_image_path:
                total_p = len(self.current_project.document.pages) if (self.current_project and self.current_project.document and len(self.current_project.document.pages) > 0) else self.pdf_viewer.total_pages
                self.pdf_viewer.load_page_image(
                    page_data.preview_image_path,
                    page_data,
                    page_num,
                    max(1, total_p)
                )

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

        # Batch Processing Mode: Auto-export to doc-named folder and advance to next document
        if self.is_batch_processing and self.batch_export_dir:
            raw_name = Path(doc.metadata.source_pdf_path).stem if doc.metadata.source_pdf_path else (self.current_project.project_name if self.current_project else "document")
            safe_stem = sanitize_filename(raw_name, fallback="document")
            doc_out_dir = self.batch_export_dir / safe_stem
            doc_out_dir.mkdir(parents=True, exist_ok=True)

            # 1. Copy images
            if self.current_project and self.current_project.images_dir.exists():
                img_out = doc_out_dir / "images"
                img_out.mkdir(parents=True, exist_ok=True)
                for img_f in self.current_project.images_dir.glob("*.*"):
                    try:
                        shutil.copy2(img_f, img_out / img_f.name)
                    except Exception:
                        pass

            # 2. Export Markdown (.md)
            md_text = self.markdown_viewer.get_markdown().strip() or self.markdown_renderer.render_document(doc)
            safe_write_text(doc_out_dir / f"{safe_stem}.md", md_text)

            # 3. Export LaTeX (.tex)
            tex_text = self.markdown_viewer.get_latex().strip() or self.latex_generator.generate_latex(doc)
            safe_write_text(doc_out_dir / f"{safe_stem}.tex", tex_text)

            # 4. Export PDF (.pdf)
            compiled_candidates = [
                self.current_project.output_dir / f"{safe_stem}.pdf",
                self.current_project.output_dir / f"{raw_name}.pdf",
                self.current_project.output_dir / f"{raw_name}_output.pdf",
            ] if self.current_project else []
            existing_pdf = next((p for p in compiled_candidates if p.exists()), None)
            if existing_pdf:
                try:
                    shutil.copy2(existing_pdf, doc_out_dir / f"{safe_stem}.pdf")
                except Exception:
                    pass

            # Update project list status to done
            self.project_panel.update_project_file_status(self.batch_current_index - 1, "done")

            # Advance to next batch document
            QTimer.singleShot(600, self._run_next_batch_item)
            return

        # Single file mode queue trigger if any
        if self.queued_pdf_path:
            next_file = self.queued_pdf_path
            self.queued_pdf_path = None
            logger.info(f"Triggering queued PDF from queue: {next_file}")
            QTimer.singleShot(600, lambda: self._load_and_run_pdf(next_file, auto_run=True))

    def _on_pipeline_error(self, error_msg: str):
        self.act_run_pipeline.setEnabled(True)
        self.act_translate.setEnabled(True)
        self.progress_panel.btn_cancel.setEnabled(False)
        QMessageBox.critical(self, "Lỗi Tiến Trình", f"Đã xảy ra lỗi khi xử lý tài liệu:\n{error_msg}")

        # In Batch Mode: Mark error and ask to continue with remaining files
        if self.is_batch_processing:
            self.project_panel.update_project_file_status(self.batch_current_index - 1, "error")
            if self.batch_queue:
                reply = QMessageBox.question(
                    self,
                    "Tiếp Tục Xử Lý Dự Án?",
                    f"Tài liệu hiện tại gặp lỗi. Bạn có muốn bỏ qua và tiếp tục xử lý các tài liệu còn lại ({len(self.batch_queue)} file)?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                if reply == QMessageBox.Yes:
                    QTimer.singleShot(600, self._run_next_batch_item)
                    return
                else:
                    self.is_batch_processing = False
                    self.batch_queue.clear()
            return

        if self.queued_pdf_path:
            next_file = self.queued_pdf_path
            self.queued_pdf_path = None
            reply = QMessageBox.question(
                self,
                "Hàng Đợi Có File Đang Chờ",
                f"File hiện tại gặp sự cố. Bạn có muốn tiếp tục xử lý file trong hàng đợi ({Path(next_file).name})?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if reply == QMessageBox.Yes:
                QTimer.singleShot(600, lambda: self._load_and_run_pdf(next_file, auto_run=True))

    def _cancel_pipeline(self):
        if self.pipeline_worker:
            self.pipeline_worker.cancel()
            self.pipeline_worker.wait(3000)
        if self.trans_worker and self.trans_worker.isRunning():
            self.trans_worker.cancel()
            self.trans_worker.wait(1500)
        self.act_run_pipeline.setEnabled(True)
        self.act_translate.setEnabled(True)
        self.progress_panel.btn_cancel.setEnabled(False)
        self.progress_panel.set_progress(0, 100, "Processing cancelled by user.")
        self.queued_pdf_path = None

    def _load_document_into_ui(self, doc):
        self.project_panel.update_document(doc)

        # Markdown & LaTeX tabs
        self.markdown_viewer.set_project(self.current_project)
        md_text = self.markdown_renderer.render_document(doc)
        self.markdown_viewer.set_markdown(
            md_text,
            images_dir=self.current_project.images_dir if self.current_project else None
        )

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
        """Safely stops background pipeline, translation, and chat threads when exiting."""
        if self.pipeline_worker and self.pipeline_worker.isRunning():
            self.pipeline_worker.cancel()
            self.pipeline_worker.wait(1500)
        if hasattr(self, 'trans_worker') and self.trans_worker and self.trans_worker.isRunning():
            self.trans_worker.cancel()
            self.trans_worker.wait(1000)
        if hasattr(self, 'markdown_viewer') and hasattr(self.markdown_viewer, 'chat_panel'):
            cp = getattr(self.markdown_viewer, 'chat_panel', None)
            if cp and hasattr(cp, 'current_worker') and cp.current_worker and cp.current_worker.isRunning():
                try:
                    cp.current_worker.cancel()
                    cp.current_worker.wait(1000)
                except Exception:
                    pass
        event.accept()
