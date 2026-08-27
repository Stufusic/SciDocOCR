import pytest
import pymupdf as fitz
from pathlib import Path
from app.core.project import SciDocProject
from app.pdf.analyzer import PDFAnalyzer
from app.pdf.extractor import PDFExtractor
from app.pdf.renderer import PDFRenderer
from app.ocr.router import OCRRouter
from app.core.document import Document, PageData, DocumentMetadata
from app.validation.document import DocumentValidator
from app.markdown.renderer import MarkdownRenderer
from app.latex.generator import LaTeXGenerator
from app.latex.compiler import LaTeXCompiler
from app.translation.translator import DocumentTranslator
from app.ai.router import AIRouter

@pytest.fixture
def complex_scientific_pdf(tmp_path):
    pdf_path = tmp_path / "complex_science_paper.pdf"
    doc = fitz.open()

    # Page 1: Quantum Field Theory
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((50, 60), "Quantum Field Theory & Thermodynamics", fontsize=18, fontname="helv")
    p1.insert_text((50, 90), "Author: Prof. SciDoc", fontsize=11, fontname="helv")
    p1.insert_text((50, 130), "1. Introduction to Quantum States", fontsize=14, fontname="helv")
    p1.insert_text((50, 160), "In theoretical physics, relativistic energy-momentum relation is given by:", fontsize=11, fontname="helv")
    p1.insert_text((80, 200), "E^2 = (pc)^2 + (m_0 c^2)^2", fontsize=12, fontname="helv")
    p1.insert_text((50, 250), "Furthermore, the Gaussian integral in quantum mechanics states:", fontsize=11, fontname="helv")
    p1.insert_text((80, 290), "\\int_{-\\infty}^{\\infty} e^{-a x^2} dx = \\sqrt{\\frac{\\pi}{a}}", fontsize=12, fontname="helv")
    p1.insert_text((50, 340), "2. Thermodynamic Measurements", fontsize=14, fontname="helv")
    p1.insert_text((50, 370), "State\tTemperature (K)\tPressure (atm)\tEntropy (J/K)", fontsize=10, fontname="helv")
    p1.insert_text((50, 390), "State A\t298.15\t1.00\t150.2", fontsize=10, fontname="helv")
    p1.insert_text((50, 410), "State B\t350.00\t2.50\t185.7", fontsize=10, fontname="helv")

    doc.save(str(pdf_path))
    doc.close()
    return str(pdf_path)

def test_full_pipeline_e2e(complex_scientific_pdf, tmp_path):
    proj_dir = tmp_path / "SciDoc_E2E_Project"
    project = SciDocProject.create_new(proj_dir, complex_scientific_pdf, "E2E Quantum Paper")

    analyzer = PDFAnalyzer(complex_scientific_pdf)
    meta = analyzer.get_metadata()
    doc_metadata = DocumentMetadata(
        title=meta.get("title", "Quantum Paper"),
        author=meta.get("author", ""),
        source_pdf_path=complex_scientific_pdf
    )
    doc = Document(metadata=doc_metadata)

    extractor = PDFExtractor(analyzer.doc)
    renderer = PDFRenderer(analyzer.doc)
    ocr_router = OCRRouter(mode="local_only")

    # Process page 0
    p0_info = analyzer.analyze_page(0)
    page_data = PageData(page_number=1, width_pt=p0_info.width, height_pt=p0_info.height)
    raw_blocks = extractor.extract_page_blocks(0)
    processed_blocks = ocr_router.process_page(
        raw_blocks, 0, p0_info.width, p0_info.height
    )
    for b in processed_blocks:
        page_data.add_block(b)
    doc.add_page(page_data)

    # Validate
    validator = DocumentValidator()
    val_stats = validator.validate_document(doc)
    assert val_stats["total_blocks"] >= 5
    assert val_stats["formula_count"] >= 1

    # Render Markdown
    md_renderer = MarkdownRenderer()
    md_text = md_renderer.render_document(doc)
    assert "# Quantum Field Theory" in md_text
    assert "$$" in md_text
    assert "| State | Temperature (K) |" in md_text or "State A" in md_text

    # Render LaTeX
    latex_gen = LaTeXGenerator()
    tex_text = latex_gen.generate_latex(doc)
    assert "\\begin{document}" in tex_text
    assert "\\begin{equation}" in tex_text or "$" in tex_text

    # Save outputs
    md_file = project.output_dir / "output.md"
    tex_file = project.output_dir / "output.tex"
    with open(md_file, "w", encoding="utf-8") as f:
        f.write(md_text)
    with open(tex_file, "w", encoding="utf-8") as f:
        f.write(tex_text)

    # Compile fallback PDF
    compiler = LaTeXCompiler()
    out_pdf = project.output_dir / "output.pdf"
    pdf_res = compiler.compile_fallback_pdf(doc, str(out_pdf))
    assert Path(pdf_res).exists()
    assert Path(pdf_res).stat().st_size > 1000

    analyzer.close()
