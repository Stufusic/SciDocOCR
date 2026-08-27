"""Pipeline Engine and Background Worker for Document Processing."""

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
    page_completed = Signal(int, object)  # page_num, PageData
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

            # 2. OCR & FORMULA EXTRACTION PAGE BY PAGE
            self.signals.state_changed.emit(PipelineState.OCR_RUNNING.value)
            render_dpi = self.render_dpi

            mineru_done = False
            if self.ocr_router.mode == "mineru":
                from app.services.mineru_service import MinerUService
                from app.ai.latex_annotator import LatexAnnotator
                from app.markdown.merger import MarkdownChunkMerger
                from app.markdown.parser import MarkdownParser

                self.mineru_svc = MinerUService(
                    cli_path=self.mineru_cli_path,
                    method=self.mineru_method
                )
                if self.mineru_svc.is_available():
                    self.signals.progress.emit(10, 100, "Phase 1 & 2: Splitting PDF into 4-page chunks & executing MinerU...")
                    
                    # 1. Split and execute MinerU chunk by chunk
                    chunk_results = self.mineru_svc.process_chunks(
                        pdf_path=Path(pdf_path),
                        output_dir=self.project.output_dir,
                        images_dir=self.project.images_dir,
                        chunk_size=4,
                        method=self.mineru_method,
                        progress_callback=lambda cur, tot, msg: self.signals.progress.emit(
                            10 + int((cur / tot) * 40), 100, msg
                        )
                    )

                    if self._is_cancelled:
                        self.signals.state_changed.emit(PipelineState.CANCELLED.value)
                        self.signals.progress.emit(0, 100, "Processing cancelled by user.")
                        return

                    if chunk_results:
                        # 2. Phase 3: Multi-Task LLM (Audit LaTeX + Annotate Math + Translate)
                        self.signals.progress.emit(55, 100, "Phase 3: LLM Auditing LaTeX & Generating Concept Annotations (💡)...")
                        annotator = LatexAnnotator(ai_router=self.ai_router)
                        
                        annotated_chunks = []
                        for c_idx, c in enumerate(chunk_results):
                            if self._is_cancelled:
                                self.signals.state_changed.emit(PipelineState.CANCELLED.value)
                                self.signals.progress.emit(0, 100, "Processing cancelled by user.")
                                return
                            
                            self.signals.progress.emit(
                                55 + int((c_idx / len(chunk_results)) * 20), 100,
                                f"Auditing LaTeX & Annotating Chunk {c.chunk_index}/{len(chunk_results)} (Pages {c.start_page}-{c.end_page})..."
                            )
                            c.markdown_text = annotator.process_chunk_markdown(
                                markdown_text=c.markdown_text,
                                translate=self.translate,
                                target_lang=self.target_lang
                            )
                            annotated_chunks.append(c)

                        # 3. Phase 4: Merge Chunks & Assemble Master Document
                        self.signals.progress.emit(75, 100, "Phase 4: Merging chunks & building AST structure...")
                        merger = MarkdownChunkMerger()
                        full_md = merger.merge_chunks(annotated_chunks, doc_title=doc.metadata.title)

                        # Parse blocks per chunk and distribute to corresponding pages
                        parser = MarkdownParser()
                        chunk_blocks_map = {}
                        for c in annotated_chunks:
                            c_blocks = parser.parse_page_blocks(c.markdown_text, page_number=c.start_page)
                            num_pages_in_chunk = max(1, c.end_page - c.start_page + 1)
                            if num_pages_in_chunk == 1:
                                chunk_blocks_map[c.start_page] = c_blocks
                            else:
                                blocks_per_page = max(1, len(c_blocks) // num_pages_in_chunk)
                                for sub_i, p_target in enumerate(range(c.start_page, c.end_page + 1)):
                                    if sub_i == num_pages_in_chunk - 1:
                                        chunk_blocks_map[p_target] = c_blocks[sub_i * blocks_per_page:]
                                    else:
                                        chunk_blocks_map[p_target] = c_blocks[sub_i * blocks_per_page:(sub_i + 1) * blocks_per_page]

                        # Build pages
                        for p_idx in range(total_pages):
                            p_num = p_idx + 1
                            info = page_infos[p_idx]
                            page_obj = PageData(page_number=p_num, width_pt=info.width, height_pt=info.height)
                            
                            # Render preview image
                            p_file = self.project.images_dir / f"page_{p_num}.png"
                            renderer.render_page_to_file(p_idx, str(p_file), dpi=render_dpi)
                            page_obj.preview_image_path = str(p_file)

                            p_blocks = chunk_blocks_map.get(p_num, [])
                            for b in p_blocks:
                                page_obj.add_block(b)

                            doc.add_page(page_obj)
                            self.signals.page_completed.emit(p_num, page_obj)

                        self.project.document = doc
                        self.project.save()

                        # Write final merged Markdown file
                        md_out = self.project.output_dir / f"{Path(pdf_path).stem}.md"
                        with open(md_out, "w", encoding="utf-8") as f:
                            f.write(full_md)

                        # Generate LaTeX with styled annotation quotes
                        self.signals.progress.emit(90, 100, "Generating LaTeX source with styled annotations...")
                        tex_content = self.latex_generator.generate_latex(doc)
                        tex_out = self.project.output_dir / f"{Path(pdf_path).stem}.tex"
                        with open(tex_out, "w", encoding="utf-8") as f:
                            f.write(tex_content)

                        # Compile PDF using XeLaTeX
                        if self.compile_pdf and not self._is_cancelled:
                            self.signals.progress.emit(95, 100, "Compiling PDF via XeLaTeX...")
                            success, out_pdf, log = self.latex_compiler.compile_tex(str(tex_out), str(self.project.output_dir))
                            if not success:
                                fallback_pdf = self.project.output_dir / f"{Path(pdf_path).stem}_output.pdf"
                                self.latex_compiler.compile_fallback_pdf(doc, str(fallback_pdf))

                        # Complete pipeline
                        self.project.update_state(PipelineState.COMPLETED.value, last_page=total_pages)
                        self.signals.state_changed.emit(PipelineState.COMPLETED.value)
                        self.signals.progress.emit(100, 100, "Pipeline completed successfully with 4-phase MinerU & LLM!")
                        self.signals.finished.emit(doc)
                        return

            # Standard or fallback per-page OCR processing loop
            for p_idx in range(total_pages):
                if self._is_cancelled:
                    self.signals.state_changed.emit(PipelineState.CANCELLED.value)
                    return

                page_num = p_idx + 1
                # If resuming and already processed
                if page_num <= last_done_page and doc.get_page(page_num):
                    continue

                pct = 10 + int((p_idx / total_pages) * 50)
                self.signals.progress.emit(pct, 100, f"Processing Page {page_num}/{total_pages} (OCR & Math at {render_dpi} DPI)...")

                info = page_infos[p_idx]
                page_data = PageData(
                    page_number=page_num,
                    width_pt=info.width,
                    height_pt=info.height,
                    is_scanned=info.is_scanned
                )

                # Render page image preview for GUI
                preview_file = self.project.images_dir / f"page_{page_num}.png"
                renderer.render_page_to_file(p_idx, str(preview_file), dpi=render_dpi)
                page_data.preview_image_path = str(preview_file)

                # Page hash for caching
                img_bytes = renderer.render_page_to_bytes(p_idx, dpi=render_dpi)
                page_sha = compute_bytes_sha256(img_bytes)
                page_data.sha256_hash = page_sha

                # Check Cache first (mode-aware so switching to Online AI reprocesses)
                cache_key = f"{page_sha}_{self.ocr_router.mode}"
                cached_blocks = self.cache_manager.get_cached_page_blocks(cache_key)
                if cached_blocks:
                    for b in cached_blocks:
                        page_data.add_block(b)
                else:
                    # Extract raw blocks and process through OCR router
                    raw_blocks = extractor.extract_page_blocks(p_idx)
                    processed_blocks = self.ocr_router.process_page(
                        blocks=raw_blocks,
                        page_index=p_idx,
                        page_width=info.width,
                        page_height=info.height,
                        image_bytes=img_bytes,
                        preview_image_path=str(preview_file),
                        image_dir=self.project.images_dir
                    )
                    for b in processed_blocks:
                        page_data.add_block(b)

                    # Store in cache
                    self.cache_manager.store_cached_page_blocks(cache_key, processed_blocks)

                doc.add_page(page_data)
                self.project.document = doc
                self.project.update_state(PipelineState.OCR_RUNNING.value, last_page=page_num)
                self.signals.page_completed.emit(page_num, page_data)

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
