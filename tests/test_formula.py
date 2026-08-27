"""Tests for Formula OCR, normalizer, and validator."""

import pytest
from app.ocr.formula_ocr import FormulaOCR
from app.validation.formula import FormulaValidator
from app.core.blocks import FormulaBlock

def test_formula_normalizer():
    ocr = FormulaOCR()
    raw = "E = mc^2 + α * ∫ f(x) dx"
    norm = ocr.normalize_latex(raw)
    assert r"\alpha" in norm
    assert r"\int" in norm

def test_formula_detection():
    ocr = FormulaOCR()
    is_f, conf = ocr.is_standalone_formula(r"f(x) = \frac{1}{\sqrt{2\pi}} e^{-\frac{x^2}{2}} (1.1)")
    assert is_f is True
    assert conf >= 0.70

    is_f2, _ = ocr.is_standalone_formula("This is a simple narrative sentence explaining the experimental setup.")
    assert is_f2 is False

def test_formula_validator_brackets():
    val = FormulaValidator()

    # Valid formula
    ok, issues = val.check_bracket_balance(r"\frac{a + b}{c + d} = \sqrt{x^2 + y^2}")
    assert ok is True
    assert len(issues) == 0

    # Invalid unbalanced bracket
    ok_bad, issues_bad = val.check_bracket_balance(r"\frac{a + b{c + d}")
    assert ok_bad is False
    assert len(issues_bad) > 0

def test_formula_validator_block():
    val = FormulaValidator()
    block = FormulaBlock(latex=r"\int_0^1 x dx = \frac{1}{2}", confidence=0.95)
    validated = val.validate_formula_block(block)
    assert validated.is_valid is True
    assert validated.confidence == 0.95
