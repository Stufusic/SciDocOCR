"""Protected Block Parser for Scientific Translation."""

import re
from typing import Tuple, Dict, List

class ProtectedBlockParser:
    """
    Extracts and replaces formulas, code blocks, citations, and references
    with immutable tokens before sending to LLM.
    """

    def __init__(self):
        pass

    def mask_protected_elements(self, text: str) -> Tuple[str, Dict[str, str]]:
        """
        Masks all math ($$, $), code (```, `), and citations (\\cite, \\ref).
        Returns: (masked_text, placeholder_map)
        """
        placeholders: Dict[str, str] = {}
        masked = text

        # 1. Mask fenced code blocks ```...```
        def mask_code_block(match):
            token = f"__SCIDOC_CODE_BLOCK_{len(placeholders):03d}__"
            placeholders[token] = match.group(0)
            return token

        masked = re.sub(r"```[\s\S]*?```", mask_code_block, masked)

        # 2. Mask display math $$...$$ or \[...\]
        def mask_display_math(match):
            token = f"__SCIDOC_MATH_DISP_{len(placeholders):03d}__"
            placeholders[token] = match.group(0)
            return token

        masked = re.sub(r"\$\$[\s\S]*?\$\$", mask_display_math, masked)
        masked = re.sub(r"\\\[[\s\S]*?\\\]", mask_display_math, masked)

        # 3. Mask inline code `...`
        def mask_inline_code(match):
            token = f"__SCIDOC_INLINE_CODE_{len(placeholders):03d}__"
            placeholders[token] = match.group(0)
            return token

        masked = re.sub(r"`[^`\n]+`", mask_inline_code, masked)

        # 4. Mask inline math $...$ or \(...\)
        def mask_inline_math(match):
            token = f"__SCIDOC_MATH_INLN_{len(placeholders):03d}__"
            placeholders[token] = match.group(0)
            return token

        masked = re.sub(r"(?<!\\)\$([^\$\n]+?)(?<!\\)\$", mask_inline_math, masked)
        masked = re.sub(r"\\\([^\n]+?\\\)", mask_inline_math, masked)

        # 5. Mask LaTeX citations & references \cite{...}, \ref{...}, \eqref{...}
        def mask_citations(match):
            token = f"__SCIDOC_CITE_REF_{len(placeholders):03d}__"
            placeholders[token] = match.group(0)
            return token

        masked = re.sub(r"\\(cite|ref|eqref|label)\{[^\}]+\}", mask_citations, masked)

        return (masked, placeholders)

    def unmask_protected_elements(self, text: str, placeholder_map: Dict[str, str]) -> str:
        """Restores original protected elements from placeholders (case & whitespace tolerant)."""
        result = text
        for token, original in placeholder_map.items():
            # Exact replacement first
            if token in result:
                result = result.replace(token, original)
            else:
                # Regex fallback for altered casing or spacing from translators
                pat = re.escape(token).replace(r"\_", r"[\_\s]*")
                result = re.sub(pat, lambda m, orig=original: orig, result, flags=re.IGNORECASE)
        return result
