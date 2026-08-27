import pymupdf as fitz
from typing import List, Dict, Any, Optional
from app.pdf.page import PDFPageInfo
from app.core.exceptions import PDFProcessingError
from app.utils.hashing import compute_file_sha256


class PDFAnalyzer:
    """Analyzes PDF files for layout, text availability, and scan characteristics."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.file_hash = compute_file_sha256(file_path)
        try:
            self.doc = fitz.open(file_path)
        except Exception as e:
            raise PDFProcessingError(f"Cannot open PDF file {file_path}: {e}")

    @property
    def page_count(self) -> int:
        return len(self.doc)

    def get_metadata(self) -> Dict[str, Any]:
        meta = self.doc.metadata or {}
        return {
            "title": meta.get("title") or "Untitled Scientific Document",
            "author": meta.get("author") or "",
            "creation_date": meta.get("creationDate") or "",
            "page_count": self.page_count,
            "file_hash": self.file_hash,
            "source_pdf_path": self.file_path,
        }

    def analyze_page(self, page_index: int) -> PDFPageInfo:
        if page_index < 0 or page_index >= self.page_count:
            raise PDFProcessingError(f"Invalid page index {page_index}. Document has {self.page_count} pages.")

        page = self.doc[page_index]
        rect = page.rect
        text = page.get_text("text").strip()
        text_length = len(text)
        image_list = page.get_images()
        image_count = len(image_list)

        # Scanned page detection heuristic:
        # If very low text length (< 50 chars) and has at least one large image covering most of the page
        is_scanned = False
        if text_length < 50 and image_count > 0:
            is_scanned = True
        elif text_length == 0:
            is_scanned = True

        has_fonts = bool(page.get_fonts())

        return PDFPageInfo(
            page_number=page_index + 1,
            width=rect.width,
            height=rect.height,
            is_scanned=is_scanned,
            text_length=text_length,
            image_count=image_count,
            has_fonts=has_fonts
        )

    def analyze_all_pages(self) -> List[PDFPageInfo]:
        return [self.analyze_page(i) for i in range(self.page_count)]

    def close(self):
        if hasattr(self, "doc") and self.doc:
            self.doc.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
