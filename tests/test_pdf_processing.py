import pytest
import pymupdf as fitz
from pathlib import Path
from app.pdf.analyzer import PDFAnalyzer
from app.pdf.extractor import PDFExtractor
from app.pdf.renderer import PDFRenderer
from app.ocr.local_ocr import LocalOCR

@pytest.fixture
def sample_pdf(tmp_path):
    pdf_path = tmp_path / "sample_scientific.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    # Insert text and formulas
    page.insert_text((50, 60), "Quantum Field Theory in Curved Spacetime", fontsize=18, fontname="helv")
    page.insert_text((50, 100), "Abstract", fontsize=14, fontname="helv")
    page.insert_text((50, 130), "We study the Hawking radiation and black hole thermodynamics in details.", fontsize=11, fontname="helv")
    page.insert_text((50, 180), "E = mc^2", fontsize=12, fontname="helv")
    page.insert_text((50, 220), "T_H = \\frac{\\hbar c^3}{8\\pi G M k_B}", fontsize=12, fontname="helv")

    doc.save(str(pdf_path))
    doc.close()
    return str(pdf_path)

def test_pdf_analyzer_and_extractor(sample_pdf):
    analyzer = PDFAnalyzer(sample_pdf)
    assert analyzer.page_count == 1

    info = analyzer.analyze_page(0)
    assert info.page_number == 1
    assert info.is_scanned is False
    assert info.text_length > 50

    extractor = PDFExtractor(analyzer.doc)
    blocks = extractor.extract_page_blocks(0)
    assert len(blocks) >= 3

    ocr = LocalOCR(info.width, info.height)
    final_blocks = ocr.process_page_blocks(blocks, 0)
    assert len(final_blocks) >= 3

    analyzer.close()

def test_pdf_renderer(sample_pdf, tmp_path):
    doc = fitz.open(sample_pdf)
    renderer = PDFRenderer(doc)
    img_bytes = renderer.render_page_to_bytes(0, dpi=100)
    assert len(img_bytes) > 0

    out_file = tmp_path / "rendered.png"
    rendered_path = renderer.render_page_to_file(0, str(out_file), dpi=100)
    assert Path(rendered_path).exists()
    doc.close()
