"""PDF Splitter: Splits large PDF documents into small 4-page temporary chunks for isolated MinerU processing."""

from __future__ import annotations
import pymupdf as fitz
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional
from app.utils.logging import get_logger
from app.core.exceptions import PDFProcessingError

logger = get_logger("PDFSplitter")

@dataclass
class PDFChunkInfo:
    """Metadata describing a split chunk of a PDF document."""
    chunk_index: int
    file_path: Path
    start_page: int  # 1-indexed inclusive
    end_page: int    # 1-indexed inclusive
    page_count: int

class PDFSplitter:
    """Splits PDF documents into smaller chunks (e.g. 4 pages) to prevent high RAM/VRAM usage."""

    def __init__(self, chunk_size: int = 4):
        self.chunk_size = max(1, chunk_size)

    def split_pdf(self, input_pdf: Path, temp_dir: Path) -> List[PDFChunkInfo]:
        """
        Splits input_pdf into multiple PDF files of up to chunk_size pages.
        Returns list of PDFChunkInfo objects.
        """
        input_path = Path(input_pdf).resolve()
        out_temp = Path(temp_dir).resolve()
        out_temp.mkdir(parents=True, exist_ok=True)

        if not input_path.exists():
            raise PDFProcessingError(f"PDF file not found: {input_path}")

        try:
            doc = fitz.open(str(input_path))
            total_pages = len(doc)
            if total_pages == 0:
                doc.close()
                return []

            chunks: List[PDFChunkInfo] = []
            stem = input_path.stem

            for chunk_idx, start_idx in enumerate(range(0, total_pages, self.chunk_size)):
                end_idx = min(start_idx + self.chunk_size, total_pages)
                chunk_page_count = end_idx - start_idx
                
                chunk_file = out_temp / f"{stem}_chunk_{chunk_idx + 1}_p{start_idx + 1}_p{end_idx}.pdf"
                
                # Extract page subrange into new PDF document
                chunk_doc = fitz.open()
                chunk_doc.insert_pdf(doc, from_page=start_idx, to_page=end_idx - 1)
                chunk_doc.save(str(chunk_file))
                chunk_doc.close()

                info = PDFChunkInfo(
                    chunk_index=chunk_idx + 1,
                    file_path=chunk_file,
                    start_page=start_idx + 1,
                    end_page=end_idx,
                    page_count=chunk_page_count
                )
                chunks.append(info)
                logger.info(f"Created chunk {info.chunk_index}: Pages {info.start_page}-{info.end_page} -> {chunk_file.name}")

            doc.close()
            return chunks

        except Exception as e:
            logger.error(f"Failed to split PDF {input_path}: {e}")
            raise PDFProcessingError(f"Error splitting PDF: {e}")

    @staticmethod
    def cleanup_chunks(chunks: List[PDFChunkInfo]):
        """Safely removes temporary chunk PDF files to free disk space."""
        for c in chunks:
            try:
                if c.file_path.exists():
                    c.file_path.unlink()
            except Exception as e:
                logger.warning(f"Could not delete temp chunk {c.file_path}: {e}")
