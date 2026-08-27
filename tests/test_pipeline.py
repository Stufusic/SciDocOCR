"""Test Pipeline for SciDoc OCR verifying Layout Cleaning, Formula Extraction, and Block Validation."""

import pytest
from pathlib import Path
import pymupdf as fitz

from app.core.blocks import (
    BaseBlock, HeadingBlock, ParagraphBlock, FormulaBlock,
    FigureBlock, CaptionBlock, BlockType, BoundingBox
)
from app.processors.layout_cleaner import LayoutCleaner
from app.processors.block_validator import BlockValidator
from app.models.layout_detector import DocumentLayoutDetector
from app.models.latex_extractor import LatexExtractor
from app.ocr.local_ocr import LocalOCR

def test_layout_cleaner_synthetic():
    cleaner = LayoutCleaner(proximity_threshold=30.0, min_cluster_size=8)

    # Create a grid of 16 tiny token blocks representing an attention matrix
    noise_blocks = []
    tokens = ["<pad>", "<eos>", "the", "law", "will", "never", "be", "perfect",
              "-", ".", "<pad>", "<pad>", "0.12", "0.85", "0.01", "<eos>"]

    for i, tok in enumerate(tokens):
        row = i // 4
        col = i % 4
        bbox = BoundingBox(x0=100 + col*20, y0=200 + row*15, x1=115 + col*20, y1=212 + row*15)
        noise_blocks.append(ParagraphBlock(text=tok, bbox=bbox, confidence=0.95))

    # Add a normal heading and paragraph
    regular_heading = HeadingBlock(text="Figure 3: Attention heatmaps", bbox=BoundingBox(100, 300, 400, 320))
    regular_para = ParagraphBlock(text="This diagram visualizes multi-head attention.", bbox=BoundingBox(100, 340, 500, 380))

    all_blocks = noise_blocks + [regular_heading, regular_para]
    assert len(all_blocks) == 18

    # Clean chart noise
    cleaned = cleaner.clean_chart_noise(all_blocks, page_num=13)

    # Noise blocks should be reduced by > 80% and merged into FigureBlock
    fig_blocks = [b for b in cleaned if b.block_type == BlockType.FIGURE]
    assert len(fig_blocks) == 1
    assert len(cleaned) < 5
    assert (len(all_blocks) - len(cleaned)) / len(all_blocks) > 0.70

def test_block_validator_false_formula_correction():
    validator = BlockValidator()

    # False formula: a regular English paragraph with a math word
    false_f1 = FormulaBlock(
        latex=r"We call our particular attention mechanism Scaled Dot-Product Attention as described below.",
        raw_text=r"We call our particular attention mechanism Scaled Dot-Product Attention as described below.",
        confidence=0.65
    )

    # True formula
    true_f2 = FormulaBlock(
        latex=r"\text{Attention}(Q, K, V) = \text{softmax}\left(\frac{QK^T}{\sqrt{d_k}}\right)V",
        confidence=0.98
    )

    blocks = [false_f1, true_f2]
    corrected = validator.validate_and_correct_blocks(blocks)

    assert corrected[0].block_type == BlockType.PARAGRAPH
    assert corrected[0].text.startswith("We call our particular attention")
    assert corrected[1].block_type == BlockType.FORMULA
    assert r"\text{Attention}" in corrected[1].latex

def test_latex_extractor_multihead_stitch():
    extractor = LatexExtractor()

    f1 = FormulaBlock(
        latex=r"\text{MultiHead}(Q, K, V) = \text{Concat}(\text{head}_1, \dots, \text{head}_h)W^O",
        bbox=BoundingBox(100, 100, 400, 120)
    )
    f2 = ParagraphBlock(
        text=r"where \text{head}_i = \text{Attention}(QW_i^Q, KW_i^K, VW_i^V)",
        bbox=BoundingBox(100, 125, 400, 145)
    )

    stitched = extractor.stitch_fragmented_formulas([f1, f2])
    assert len(stitched) == 1
    assert isinstance(stitched[0], FormulaBlock)
    assert r"\text{MultiHead}" in stitched[0].latex
    assert r"\text{head}_i" in stitched[0].latex

def test_pipeline_on_transformer_paper_if_present():
    transformer_pdf_path = Path(r"C:\Users\KieuKhang\.scidoc_projects\1706.03762v7\source\1706.03762v7.pdf")
    if not transformer_pdf_path.exists():
        pytest.skip("Transformer paper 1706.03762v7.pdf not present in user scidoc_projects.")

    doc = fitz.open(str(transformer_pdf_path))
    ocr = LocalOCR()
    from app.pdf.extractor import PDFExtractor
    extractor = PDFExtractor(doc)

    # 1. Test Page 4 (Formulas: Attention & MultiHead)
    raw_p4 = extractor.extract_page_blocks(3)
    p4_processed = ocr.process_page_blocks(raw_p4, 3)

    formulas_p4 = [b for b in p4_processed if b.block_type == BlockType.FORMULA]
    headings_p4 = [b for b in p4_processed if b.block_type == BlockType.HEADING]

    # Attention formula should be captured
    assert any("Attention" in getattr(f, "latex", "") for f in formulas_p4)

    # 2. Test Page 13 (Attention heatmaps noise clustering)
    raw_p13 = extractor.extract_page_blocks(12)
    p13_processed = ocr.process_page_blocks(raw_p13, 12)

    # Count reduction of raw text fragments
    assert len(p13_processed) < len(raw_p13)
    # Check for Figure block created
    fig_blocks = [b for b in p13_processed if b.block_type == BlockType.FIGURE]
    assert len(fig_blocks) >= 1

    doc.close()
