"""Tests for Document AST and Blocks."""

import pytest
from app.core.blocks import (
    BlockType, HeadingBlock, ParagraphBlock, FormulaBlock,
    TableBlock, BoundingBox, block_from_dict
)
from app.core.document import Document, PageData, DocumentMetadata

def test_block_creation_and_dict():
    bbox = BoundingBox(10.0, 20.0, 100.0, 50.0)
    h_block = HeadingBlock(level=1, text="Introduction", bbox=bbox, confidence=0.98)
    assert h_block.block_type == BlockType.HEADING
    assert h_block.bbox.width == 90.0
    assert h_block.bbox.height == 30.0

    d = h_block.to_dict()
    assert d["block_type"] == "heading"
    assert d["level"] == 1

    restored = block_from_dict(d)
    assert isinstance(restored, HeadingBlock)
    assert restored.text == "Introduction"
    assert restored.confidence == 0.98
    assert restored.bbox.to_tuple() == (10.0, 20.0, 100.0, 50.0)

def test_formula_block():
    f_block = FormulaBlock(latex=r"\int_0^\infty e^{-x^2} dx", is_inline=False, confidence=0.95)
    assert f_block.block_type == BlockType.FORMULA
    d = f_block.to_dict()
    restored = block_from_dict(d)
    assert isinstance(restored, FormulaBlock)
    assert restored.latex == r"\int_0^\infty e^{-x^2} dx"

def test_document_and_page():
    doc = Document(metadata=DocumentMetadata(title="Quantum Physics", author="A. Einstein"))
    page1 = PageData(page_number=1, width_pt=595.0, height_pt=842.0)

    page1.add_block(HeadingBlock(level=1, text="Quantum Mechanics"))
    page1.add_block(ParagraphBlock(text="Energy is quantized."))
    page1.add_block(FormulaBlock(latex="E = h\\nu", confidence=0.99))

    doc.add_page(page1)

    assert len(doc.pages) == 1
    stats = doc.get_stats()
    assert stats["total_blocks"] == 3
    assert stats["formula_count"] == 1
    assert stats["heading_count"] == 1

    # Test full doc serialization
    doc_dict = doc.to_dict()
    doc_restored = Document.from_dict(doc_dict)
    assert doc_restored.metadata.title == "Quantum Physics"
    assert len(doc_restored.pages) == 1
    assert len(doc_restored.pages[0].blocks) == 3
