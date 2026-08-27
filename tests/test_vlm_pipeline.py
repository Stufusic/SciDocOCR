"""Tests for Modular & Batch-Oriented Document OCR Pipeline with VLM."""

import pytest
from pathlib import Path
from src.layout_parser import LayoutParser
from src.math_engine import MathEngine
from src.assembler import DocumentAssembler

def test_math_engine_syntax_validation():
    engine = MathEngine()
    assert engine.is_syntax_valid(r"\frac{a}{b}") is True
    assert engine.is_syntax_valid(r"\sqrt{x^2 + y^2}") is True
    assert engine.is_syntax_valid(r"\frac{a}{b") is False  # Missing closing brace
    assert engine.is_syntax_valid(r"(x + y") is False       # Missing closing paren

def test_assembler_placeholder_replacement(tmp_path):
    assembler = DocumentAssembler()
    skeleton = (
        "# Introduction\n\n"
        "Here is the attention formula:\n"
        "{{MATH_PAGE_1_ID_0}}\n\n"
        "And the results table:\n"
        "{{TABLE_PAGE_1_ID_1}}\n\n"
        "And the model architecture:\n"
        "{{CHART_PAGE_1_ID_2}}\n"
    )
    replacements = {
        "{{MATH_PAGE_1_ID_0}}": "$$\\text{Attention}(Q,K,V) = \\text{softmax}\\left(\\frac{QK^T}{\\sqrt{d_k}}\\right)V$$",
        "{{TABLE_PAGE_1_ID_1}}": "| Model | BLEU |\n| --- | --- |\n| Transformer | 28.4 |",
        "{{CHART_PAGE_1_ID_2}}": "![Model Architecture](crops/chart.png)"
    }
    out_file = tmp_path / "final_output.md"
    result = assembler.assemble(skeleton, replacements, refine_with_llm=False, output_path=out_file)

    assert "\\text{Attention}" in result
    assert "| Transformer | 28.4 |" in result
    assert "crops/chart.png" in result
    assert "{{" not in result  # All placeholders replaced
    assert out_file.exists()

def test_layout_parser_math_detection():
    parser = LayoutParser()
    assert parser.is_math_block(r"\text{Attention}(Q, K, V) = \text{softmax}\left(\frac{QK^T}{\sqrt{d_k}}\right)V") is True
    assert parser.is_math_block("This is a simple text paragraph without equations.") is False
    assert parser.is_table_block("Table 1: Performance metrics\nCol1\tCol2\nVal1\tVal2\nVal3\tVal4") is True
    assert parser.is_chart_or_figure("Figure 1: The Transformer model architecture.") is True
