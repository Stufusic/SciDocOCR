"""Tests for Markdown and LaTeX generators."""

import pytest
from app.core.document import Document, PageData, DocumentMetadata
from app.core.blocks import HeadingBlock, ParagraphBlock, FormulaBlock, TableBlock
from app.markdown.renderer import MarkdownRenderer
from app.markdown.parser import MarkdownParser
from app.latex.generator import LaTeXGenerator

def test_markdown_render_and_parse():
    doc = Document(metadata=DocumentMetadata(title="Test Document", author="Tester"))
    page = PageData(page_number=1)

    page.add_block(HeadingBlock(level=1, text="Introduction"))
    page.add_block(ParagraphBlock(text="This is a paragraph with math."))
    page.add_block(FormulaBlock(latex="x^2 + y^2 = z^2", is_inline=False))
    page.add_block(TableBlock(rows=[["Header 1", "Header 2"], ["Data A", "Data B"]]))

    doc.add_page(page)

    renderer = MarkdownRenderer()
    md_output = renderer.render_document(doc)

    assert "# Test Document" in md_output
    assert "## Introduction" in md_output or "# Introduction" in md_output
    assert "$$\nx^2 + y^2 = z^2\n$$" in md_output
    assert "| Header 1 | Header 2 |" in md_output

    # Test parser
    parser = MarkdownParser()
    parsed_doc = parser.parse_text(md_output)
    assert len(parsed_doc.pages) == 1
    assert len(parsed_doc.pages[0].blocks) >= 3

def test_latex_generation():
    doc = Document(metadata=DocumentMetadata(title="Physics Paper", author="Physicist"))
    page = PageData(page_number=1)
    page.add_block(HeadingBlock(level=1, text="Quantum Mechanics"))
    page.add_block(FormulaBlock(latex=r"\hat{H}\Psi = E\Psi"))
    doc.add_page(page)

    gen = LaTeXGenerator()
    tex = gen.generate_latex(doc)

    assert r"\documentclass" in tex
    assert r"\usepackage{amsmath" in tex
    assert r"\section{Quantum Mechanics}" in tex
    assert r"\begin{equation}" in tex
    assert r"\hat{H}\Psi = E\Psi" in tex
