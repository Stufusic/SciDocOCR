"""Unit tests for PDFSplitter."""

import pytest
import pymupdf as fitz
from pathlib import Path
from app.pdf.splitter import PDFSplitter

def test_pdf_splitter(tmp_path):
    # Create a dummy 9-page PDF
    pdf_path = tmp_path / "sample_9pages.pdf"
    doc = fitz.open()
    for i in range(9):
        page = doc.new_page(width=595, height=842)
        page.insert_text((50, 50), f"Page {i + 1} Content")
    doc.save(str(pdf_path))
    doc.close()

    splitter = PDFSplitter(chunk_size=4)
    chunks = splitter.split_pdf(pdf_path, tmp_path / "chunks")

    # 9 pages with chunk_size=4 should yield 3 chunks (4, 4, 1)
    assert len(chunks) == 3
    assert chunks[0].start_page == 1
    assert chunks[0].end_page == 4
    assert chunks[0].page_count == 4
    assert chunks[0].file_path.exists()

    assert chunks[1].start_page == 5
    assert chunks[1].end_page == 8
    assert chunks[1].page_count == 4

    assert chunks[2].start_page == 9
    assert chunks[2].end_page == 9
    assert chunks[2].page_count == 1

    # Cleanup
    PDFSplitter.cleanup_chunks(chunks)
    assert not chunks[0].file_path.exists()
