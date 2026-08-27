"""LaTeX Validator and Compiler Log Error Parser."""

import re
from typing import List, Dict, Any, Tuple

class LaTeXValidator:
    """Parses LaTeX compilation logs and detects syntax errors."""

    def __init__(self):
        pass

    def parse_compiler_log(self, log_text: str) -> List[Dict[str, Any]]:
        """
        Parses LaTeX log output and extracts errors, line numbers, and context.
        """
        errors = []
        # Pattern for standard LaTeX error lines: "! LaTeX Error: ..." or "! Undefined control sequence."
        error_blocks = re.split(r"\n(?=!\s+)", log_text)

        for blk in error_blocks:
            if not blk.startswith("!"):
                continue

            lines = blk.strip().split("\n")
            first_line = lines[0][1:].strip()  # Strip leading "!"

            line_num = -1
            context = ""
            for line in lines[1:]:
                line_match = re.search(r"^l\.(\d+)\s*(.*)$", line)
                if line_match:
                    line_num = int(line_match.group(1))
                    context = line_match.group(2)
                    break

            errors.append({
                "message": first_line,
                "line": line_num,
                "context": context,
                "raw_block": blk.strip()
            })

        return errors

    def suggest_repairs(self, errors: List[Dict[str, Any]]) -> List[str]:
        """Provides automated suggestions based on parsed errors."""
        suggestions = []
        for err in errors:
            msg = err["message"]
            if "Undefined control sequence" in msg:
                suggestions.append(f"Line {err['line']}: Missing package or typo in command '{err['context']}'")
            elif "Missing $ inserted" in msg:
                suggestions.append(f"Line {err['line']}: Mathematical symbol outside math environment ($...$)")
            elif "File `" in msg and "not found" in msg:
                suggestions.append(f"Missing referenced image or style file in line {err['line']}")
            else:
                suggestions.append(f"Line {err['line']}: {msg}")
        return suggestions
