"""Formula Validator: validates LaTeX syntax, balanced brackets, and flags OCR anomalies."""

import re
from typing import Tuple, List, Dict
from app.core.blocks import FormulaBlock

class FormulaValidator:
    """Validates mathematical LaTeX strings for structural correctness."""

    def __init__(self):
        # Known common OCR confusions in math
        self.confusion_patterns = [
            (r"\bdelta\b", r"\partial", "Potential confusion: 'delta' might be partial derivative '\\partial'"),
            (r"\\sqrt\s*([a-zA-Z0-9])", r"\\sqrt{\1}", "Missing curly braces in '\\sqrt'"),
            (r"\\frac\s*([a-zA-Z0-9])\s*([a-zA-Z0-9])", r"\\frac{\1}{\2}", "Missing curly braces in '\\frac'"),
        ]

    def check_bracket_balance(self, latex: str) -> Tuple[bool, List[str]]:
        """Checks if curly braces, parentheses, and square brackets are balanced."""
        stack = []
        pairs = {')': '(', '}': '{', ']': '['}
        issues = []

        for i, char in enumerate(latex):
            if char in "({[":
                stack.append((char, i))
            elif char in ")}]":
                if not stack:
                    issues.append(f"Unmatched closing bracket '{char}' at position {i}")
                else:
                    top_char, _ = stack.pop()
                    if pairs[char] != top_char:
                        issues.append(f"Mismatched bracket '{top_char}' with '{char}' at position {i}")

        while stack:
            unmatched_char, pos = stack.pop()
            issues.append(f"Unclosed opening bracket '{unmatched_char}' at position {pos}")

        return (len(issues) == 0, issues)

    def check_environments(self, latex: str) -> Tuple[bool, List[str]]:
        """Checks if \\begin{env} has matching \\end{env}."""
        begins = re.findall(r"\\begin\{([a-zA-Z0-9\*]+)\}", latex)
        ends = re.findall(r"\\end\{([a-zA-Z0-9\*]+)\}", latex)
        issues = []

        if len(begins) != len(ends):
            issues.append(f"Mismatched LaTeX environments: {len(begins)} \\begin vs {len(ends)} \\end")
        else:
            for b, e in zip(begins, ends):
                if b != e:
                    issues.append(f"Mismatched environment name: \\begin{{{b}}} closed by \\end{{{e}}}")

        return (len(issues) == 0, issues)

    def validate_formula_block(self, block: FormulaBlock) -> FormulaBlock:
        """Validates and updates FormulaBlock issues and confidence score."""
        latex = block.latex.strip()
        issues: List[str] = []

        # 1. Bracket checks
        balanced, b_issues = self.check_bracket_balance(latex)
        issues.extend(b_issues)

        # 2. Environment checks
        envs_ok, env_issues = self.check_environments(latex)
        issues.extend(env_issues)

        # 3. Check for obvious syntax breakages
        if latex.endswith("\\") and not latex.endswith("\\\\"):
            issues.append("Trailing unescaped backslash")

        # 4. Check for OCR confusion suggestions
        for pat, _, msg in self.confusion_patterns:
            if re.search(pat, latex):
                issues.append(msg)

        block.issues = issues
        block.is_valid = (len(issues) == 0)

        # Adjust confidence if invalid
        if not block.is_valid:
            penalty = len(issues) * 0.15
            block.confidence = max(0.40, round(block.confidence - penalty, 2))

        return block
