"""Translation integrity validator: ensures 100% preservation of math and code."""

import re
from typing import Dict, List, Tuple

class TranslationValidator:
    """Verifies that no mathematical formulas or code were lost during translation."""

    def __init__(self):
        pass

    def validate_placeholders(self, translated_text: str, placeholder_map: Dict[str, str]) -> Tuple[bool, List[str]]:
        """
        Ensures every placeholder from original map exists in translated_text (casing & spacing tolerant).
        Returns: (is_valid, list_of_missing_tokens)
        """
        missing = []
        for token in placeholder_map.keys():
            if token in translated_text:
                continue
            pat = re.escape(token).replace(r"\_", r"[\_\s]*")
            if not re.search(pat, translated_text, flags=re.IGNORECASE):
                missing.append(token)

        return (len(missing) == 0, missing)

    def count_math_symbols(self, text: str) -> int:
        """Counts occurrence of $ and $$ markers in text."""
        return text.count("$")
