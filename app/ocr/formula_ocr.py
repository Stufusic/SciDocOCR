"""Formula Detection and LaTeX Converter for Scientific Documents."""

import re
from typing import List, Tuple, Optional
from app.core.blocks import BaseBlock, FormulaBlock, ParagraphBlock, BlockType, BoundingBox

# Mapping of common unicode scientific symbols to LaTeX commands
UNICODE_TO_LATEX = {
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta", "ε": r"\epsilon",
    "θ": r"\theta", "λ": r"\lambda", "μ": r"\mu", "π": r"\pi", "σ": r"\sigma",
    "ω": r"\omega", "Δ": r"\Delta", "Σ": r"\Sigma", "Ω": r"\Omega", "Φ": r"\Phi",
    "∫": r"\int", "∬": r"\iint", "∭": r"\iiint", "∮": r"\oint",
    "∑": r"\sum", "∏": r"\prod", "∂": r"\partial", "∇": r"\nabla",
    "√": r"\sqrt", "∞": r"\infty", "≈": r"\approx", "≠": r"\neq",
    "≤": r"\le", "≥": r"\ge", "±": r"\pm", "∓": r"\mp", "×": r"\times",
    "÷": r"\div", "∈": r"\in", "∉": r"\notin", "⊂": r"\subset", "⊆": r"\subseteq",
    "→": r"\to", "⇒": r"\Rightarrow", "⇔": r"\Leftrightarrow", "↔": r"\leftrightarrow",
    "·": r"\cdot", "…": r"\dots", "∀": r"\forall", "∃": r"\exists"
}

# Regex to detect display math characteristics
MATH_INDICATORS = [
    r"=", r"\+", r"-", r"\\times", r"\\int", r"\\sum", r"\\frac", r"\^", r"_",
    r"\\partial", r"\\sqrt", r"\\alpha", r"\\beta", r"\\pi", r"\\theta",
    r"\d+\s*[\+\-\*\/=]\s*\d+"
]

class FormulaOCR:
    """Detects, normalizes, and extracts formulas into LaTeX AST blocks."""

    def __init__(self):
        pass

    def normalize_latex(self, raw_expr: str) -> str:
        """Converts unicode math characters and standard symbols to valid LaTeX."""
        text = raw_expr.strip()
        # Replace unicode math symbols
        for uni_char, latex_sym in UNICODE_TO_LATEX.items():
            text = text.replace(uni_char, f" {latex_sym} ")

        # Clean multiple spaces
        text = re.sub(r"\s+", " ", text).strip()

        # Clean fraction notation if written like a/b in standalone equations
        # E.g. (a + b)/(c + d) -> \frac{a + b}{c + d}
        frac_pattern = r"\(([^\(\)]+)\)\s*\/\s*\(([^\(\)]+)\)"
        text = re.sub(frac_pattern, r"\\frac{\1}{\2}", text)

        # Clean square root notation: sqrt(x) -> \sqrt{x}
        text = re.sub(r"sqrt\(([^\)]+)\)", r"\\sqrt{\1}", text)
        text = re.sub(r"\\sqrt\s*\(([^\)]+)\)", r"\\sqrt{\1}", text)

        return text

    def is_standalone_formula(self, text: str) -> Tuple[bool, float]:
        """
        Determines if a given block of text is primarily a standalone math equation.
        Returns: (is_formula, confidence_score)
        """
        clean = text.strip()
        if not clean:
            return (False, 0.0)

        # Check if text contains high density of math symbols or equation syntax
        math_score = 0.0
        words = re.findall(r"\b[a-zA-Z]{3,}\b", clean)
        word_count = len(words)
        
        # Check math markers
        has_equals = "=" in clean
        has_integral = any(k in clean for k in ["\\int", "∫", "\\sum", "∑", "\\prod", "∏", "\\partial", "∂", "\\nabla", "∇"])
        has_fractions_or_roots = any(k in clean for k in ["\\frac", "\\sqrt", "√", "^", "_"])
        has_math_fn = bool(re.search(r"\b(Attention|MultiHead|Concat|softmax|Softmax|FFN|LayerNorm|sin|cos|tan|log|exp|max|min)\s*\(", clean))
        
        if has_integral or has_fractions_or_roots or has_math_fn:
            math_score += 0.5
        if has_equals:
            math_score += 0.4
        if any(sym in clean for sym in UNICODE_TO_LATEX.keys()):
            math_score += 0.4

        # Equation numbering like (1), (2.1)
        if re.search(r"\(\d+(\.\d+)?[a-z]?\)\s*$", clean):
            math_score += 0.3

        # Short expressions with math symbols and few normal English prose words
        if word_count <= 2 and (has_equals or has_integral or has_fractions_or_roots):
            math_score += 0.5
        elif word_count > 6:
            math_score -= 0.4

        is_formula = math_score >= 0.5
        confidence = min(1.0, max(0.60, math_score)) if is_formula else 0.95
        return (is_formula, round(confidence, 2))

    def detect_and_convert_blocks(self, blocks: List[BaseBlock]) -> List[BaseBlock]:
        """Processes a list of blocks, converting standalone equation paragraphs into FormulaBlocks."""
        result_blocks: List[BaseBlock] = []

        for b in blocks:
            if b.block_type == BlockType.PARAGRAPH and isinstance(b, ParagraphBlock):
                is_formula, conf = self.is_standalone_formula(b.text)
                if is_formula:
                    latex_expr = self.normalize_latex(b.text)
                    result_blocks.append(FormulaBlock(
                        id=b.id,
                        bbox=b.bbox,
                        source_page=b.source_page,
                        order_index=b.order_index,
                        column_index=b.column_index,
                        confidence=conf,
                        latex=latex_expr,
                        raw_text=b.text,
                        is_inline=False,
                        is_valid=True
                    ))
                else:
                    # Replace unicode math in regular paragraph to inline math format
                    normalized_para = self.normalize_inline_math(b.text)
                    b.text = normalized_para
                    result_blocks.append(b)
            else:
                result_blocks.append(b)

        return result_blocks

    def normalize_inline_math(self, text: str) -> str:
        """Finds small inline equations and wraps them in $...$ if not already wrapped."""
        normalized = text
        for char, latex_sym in UNICODE_TO_LATEX.items():
            if char in normalized:
                # Wrap in $...$ if not already inside math delimiters
                normalized = normalized.replace(char, f"${latex_sym}$")
        # Clean double dollar signs if accidentally nested
        normalized = normalized.replace("$$", "$").replace("$$", "$")
        return normalized
