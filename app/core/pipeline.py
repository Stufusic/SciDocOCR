"""Pipeline Engine and Background Worker for Document Processing."""

import gc
import traceback
from enum import Enum
from pathlib import Path
from typing import Optional, Callable
from PySide6.QtCore import QThread, Signal, QObject

from app.core.document import Document, PageData, DocumentMetadata
from app.core.project import SciDocProject
from app.pdf.analyzer import PDFAnalyzer
from app.pdf.extractor import PDFExtractor
from app.pdf.renderer import PDFRenderer
from app.models.layout_detector import DocumentLayoutDetector
from app.ocr.router import OCRRouter
from app.validation.document import DocumentValidator
from app.markdown.renderer import MarkdownRenderer
from app.latex.generator import LaTeXGenerator
from app.latex.compiler import LaTeXCompiler
from app.translation.translator import DocumentTranslator
from app.ai.router import AIRouter
from app.storage.cache import CacheManager
from app.utils.hashing import compute_bytes_sha256
from app.utils.logging import get_logger

logger = get_logger("JobPipeline")

class PipelineState(str, Enum):
    CREATED = "CREATED"
    ANALYZING = "ANALYZING"
    OCR_RUNNING = "OCR_RUNNING"
    RECONSTRUCTING = "RECONSTRUCTING"
    FORMULA_PROCESSING = "FORMULA_PROCESSING"
    VALIDATING = "VALIDATING"
    MARKDOWN_READY = "MARKDOWN_READY"
    TRANSLATING = "TRANSLATING"
    LATEX_GENERATING = "LATEX_GENERATING"
    COMPILING = "COMPILING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class PipelineSignals(QObject):
    progress = Signal(int, int, str)  # current_step, total_steps, message
    state_changed = Signal(str)       # state_name
    layout_detected = Signal(int, object)  # page_num, PageData (immediate YOLO layout bboxes preview)
    page_completed = Signal(int, object)   # page_num, PageData (final OCR structured text)
    finished = Signal(object)         # Document
    error = Signal(str)               # error_message


class JobPipelineWorker(QThread):
    """Background worker executing the complete scientific document pipeline."""

    def __init__(
        self,
        project: SciDocProject,
        ai_router: AIRouter,
        ocr_router: OCRRouter,
        translate: bool = False,
        source_lang: str = "en",
        target_lang: str = "vi",
        compile_pdf: bool = True,
        render_dpi: int = 400,
        mineru_method: str = "auto",
        mineru_cli_path: str = "magic-pdf",
        parent: Optional[QObject] = None
    ):
        super().__init__(parent)
        self.project = project
        self.ai_router = ai_router
        self.ocr_router = ocr_router
        self.translate = translate
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.compile_pdf = compile_pdf
        self.render_dpi = render_dpi or 400
        self.mineru_method = mineru_method or "auto"
        self.mineru_cli_path = mineru_cli_path or "magic-pdf"

        self.signals = PipelineSignals()
        self._is_cancelled = False
        self.mineru_svc = None
        self.layout_detector = getattr(ocr_router, "layout_detector", None) or DocumentLayoutDetector()
        self.cache_manager = CacheManager(project.cache_dir)
        self.markdown_renderer = MarkdownRenderer()
        self.latex_generator = LaTeXGenerator()
        self.latex_compiler = LaTeXCompiler()
        self.doc_validator = DocumentValidator()

    def cancel(self):
        self._is_cancelled = True
        if self.mineru_svc:
            self.mineru_svc.cancel()

    def run(self):
        analyzer = None
        try:
            pdf_path = self.project.metadata.get("source_pdf", "")
            if not pdf_path or not Path(pdf_path).exists():
                raise ValueError(f"Source PDF file not found: {pdf_path}")

            # 1. ANALYZING PDF
            self.signals.state_changed.emit(PipelineState.ANALYZING.value)
            self.signals.progress.emit(5, 100, "Analyzing PDF structure...")

            analyzer = PDFAnalyzer(pdf_path)
            meta = analyzer.get_metadata()
            doc_metadata = DocumentMetadata(
                title=meta.get("title", Path(pdf_path).stem),
                author=meta.get("author", ""),
                source_pdf_path=pdf_path,
                file_hash=meta.get("file_hash", ""),
                source_language=self.source_lang,
                target_language=self.target_lang
            )

            # Check if project already has a document to resume from
            if self.project.document:
                doc = self.project.document
            else:
                doc = Document(metadata=doc_metadata)

            extractor = PDFExtractor(analyzer.doc)
            renderer = PDFRenderer(analyzer.doc)
            page_infos = analyzer.analyze_all_pages() or []
            total_pages = len(page_infos)
            if total_pages == 0:
                raise ValueError("PDF document has 0 pages or could not be analyzed.")

            last_done_page = self.project.metadata.get("last_processed_page", 0)

            # 2. OCR & FORMULA EXTRACTION BY CHUNKS (Streaming Queue)
            self.signals.state_changed.emit(PipelineState.OCR_RUNNING.value)
            render_dpi = max(300, getattr(self, "render_dpi", 400))

            # Build 4-page chunk ranges from intact original PDF
            chunk_size = 4
            chunk_ranges = []
            for start_p in range(1, total_pages + 1, chunk_size):
                end_p = min(start_p + chunk_size - 1, total_pages)
                chunk_ranges.append((start_p, end_p))
            total_chunks = len(chunk_ranges)

            for c_idx, (start_page, end_page) in enumerate(chunk_ranges):
                if self._is_cancelled:
                    self.signals.state_changed.emit(PipelineState.CANCELLED.value)
                    self.signals.progress.emit(0, 100, "Processing cancelled by user.")
                    return

                chunk_index = c_idx + 1
                pct = 10 + int((c_idx / total_chunks) * 55)
                self.signals.progress.emit(
                    pct, 100,
                    f"Đang xử lý Chunk {chunk_index}/{total_chunks} (Trang {start_page}-{end_page}) với YOLOv10m & VLM Vision OCR..."
                )
                logger.info(f"Processing Chunk {chunk_index}/{total_chunks} (Pages {start_page}-{end_page}) with mode: {self.ocr_router.mode} at {render_dpi} DPI")

                # Process all pages inside this chunk
                for page_num in range(start_page, end_page + 1):
                    if self._is_cancelled:
                        self.signals.state_changed.emit(PipelineState.CANCELLED.value)
                        return

                    p_idx = page_num - 1
                    info = page_infos[p_idx]
                    page_data = PageData(
                        page_number=page_num,
                        width_pt=info.width,
                        height_pt=info.height,
                        is_scanned=info.is_scanned
                    )

                    # 1. Render Page Image directly to bytes and save file in 1 step
                    preview_file = self.project.images_dir / f"page_{page_num}.png"
                    img_bytes = renderer.render_page_to_bytes(p_idx, dpi=render_dpi)
                    with open(preview_file, "wb") as f:
                        f.write(img_bytes)
                    page_data.preview_image_path = str(preview_file)

                    # 2. Page hash for caching
                    page_sha = compute_bytes_sha256(img_bytes)
                    page_data.sha256_hash = page_sha

                    active_model = ""
                    if self.ai_router and hasattr(self.ai_router, "online_provider"):
                        active_model = getattr(self.ai_router.online_provider, "model_name", "")
                    cache_key = f"{page_sha}_{self.ocr_router.mode}_{active_model}"
                    cached_blocks = self.cache_manager.get_cached_page_blocks(cache_key)
                    if cached_blocks:
                        for b in cached_blocks:
                            page_data.add_block(b)
                    else:
                        # 3. YOLOv10m ONNX Layout & Section Bounding Box Detection
                        raw_blocks = extractor.extract_page_blocks(p_idx)
                        layout_routed_blocks = self.layout_detector.classify_and_route_blocks(raw_blocks, page_num=page_num, preview_image_path=str(preview_file))
                        figure_blocks = self.layout_detector.extract_figures_from_page(str(preview_file), page_num=page_num, image_dir=self.project.images_dir)

                        # Emit immediate layout detection preview for UI display BEFORE sending to LLM
                        layout_preview_page = PageData(
                            page_number=page_num,
                            width_pt=info.width,
                            height_pt=info.height,
                            is_scanned=info.is_scanned,
                            preview_image_path=str(preview_file)
                        )
                        for b in (layout_routed_blocks + figure_blocks):
                            layout_preview_page.add_block(b)

                        self.signals.layout_detected.emit(page_num, layout_preview_page)
                        logger.info(f"Page {page_num}: YOLOv10 detected {len(layout_preview_page.blocks)} layout regions. Sent layout preview to UI before pushing to LLM.")

                        # 4. Push High-Res Image to Vision AI (Online VLM / Local Model) to OCR Section contents & LaTeX formulas
                        processed_blocks = self.ocr_router.process_page(
                            blocks=layout_routed_blocks,
                            page_index=p_idx,
                            page_width=info.width,
                            page_height=info.height,
                            image_bytes=img_bytes,
                            preview_image_path=str(preview_file),
                            image_dir=self.project.images_dir,
                            figure_blocks=figure_blocks
                        )
                        for b in processed_blocks:
                            page_data.add_block(b)

                        self.cache_manager.store_cached_page_blocks(cache_key, processed_blocks)

                    doc.add_page(page_data)
                    self.signals.page_completed.emit(page_num, page_data)

                # Save project checkpoint after chunk completion
                self.project.document = doc
                self.project.update_state(PipelineState.OCR_RUNNING.value, last_page=end_page)
                self.project.save()

                # Eager memory cleanup
                gc.collect()

            # 3. VALIDATING DOCUMENT
            self.signals.state_changed.emit(PipelineState.VALIDATING.value)
            self.signals.progress.emit(65, 100, "Validating formulas & confidence...")
            self.doc_validator.validate_document(doc)

            # 4. MARKDOWN GENERATION
            self.signals.state_changed.emit(PipelineState.MARKDOWN_READY.value)
            self.signals.progress.emit(70, 100, "Generating Markdown...")
            md_content = self.markdown_renderer.render_document(doc)
            md_out = self.project.output_dir / f"{Path(pdf_path).stem}.md"
            with open(md_out, "w", encoding="utf-8") as f:
                f.write(md_content)

            # 5. TRANSLATION (OPTIONAL)
            if self.translate and not self._is_cancelled:
                self.signals.state_changed.emit(PipelineState.TRANSLATING.value)
                self.signals.progress.emit(75, 100, f"Translating to {self.target_lang} (protecting formulas)...")
                translator = DocumentTranslator(self.ai_router)
                translator.translate_document(
                    doc,
                    source_lang=self.source_lang,
                    target_lang=self.target_lang,
                    progress_callback=lambda cur, tot, msg: self.signals.progress.emit(
                        75 + int((cur / tot) * 15), 100, msg
                    )
                )
                # Re-render translated markdown
                trans_md = self.markdown_renderer.render_document(doc)
                trans_md_out = self.project.output_dir / f"{Path(pdf_path).stem}_{self.target_lang}.md"
                with open(trans_md_out, "w", encoding="utf-8") as f:
                    f.write(trans_md)

            # 6. LATEX GENERATION
            self.signals.state_changed.emit(PipelineState.LATEX_GENERATING.value)
            self.signals.progress.emit(90, 100, "Generating LaTeX document...")
            latex_content = self.latex_generator.generate_latex(doc)
            tex_out = self.project.output_dir / f"{Path(pdf_path).stem}.tex"
            with open(tex_out, "w", encoding="utf-8") as f:
                f.write(latex_content)

            # 7. PDF COMPILATION
            if self.compile_pdf and not self._is_cancelled:
                self.signals.state_changed.emit(PipelineState.COMPILING.value)
                self.signals.progress.emit(95, 100, "Compiling PDF output...")
                success, out_pdf, log = self.latex_compiler.compile_tex(str(tex_out), str(self.project.output_dir))
                if not success:
                    logger.info("System TeX not available or returned error; building styled fallback PDF.")
                    fallback_pdf = self.project.output_dir / f"{Path(pdf_path).stem}_output.pdf"
                    self.latex_compiler.compile_fallback_pdf(doc, str(fallback_pdf))

            # 8. COMPLETED
            self.project.document = doc
            self.project.update_state(PipelineState.COMPLETED.value, last_page=total_pages)
            self.signals.state_changed.emit(PipelineState.COMPLETED.value)
            self.signals.progress.emit(100, 100, "Pipeline completed successfully!")
            self.signals.finished.emit(doc)

        except Exception as e:
            logger.error(f"Pipeline error: {e}\n{traceback.format_exc()}")
            self.signals.state_changed.emit(PipelineState.FAILED.value)
            self.signals.error.emit(str(e))
        finally:
            if analyzer:
                try:
                    analyzer.close()
                except Exception:
                    pass
