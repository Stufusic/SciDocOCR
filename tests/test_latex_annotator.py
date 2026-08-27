"""Unit tests for LatexAnnotator."""

import pytest
from typing import List
from app.ai.latex_annotator import LatexAnnotator
from app.ai.base import AIProvider
from app.ai.router import AIRouter

class DummyProvider(AIProvider):
    def is_available(self) -> bool:
        return True

    def complete(self, prompt: str, system_prompt: str = "", temperature: float = 0.2, max_tokens: int = 2048) -> str:
        return "# Test\n$$\\frac{a}{b}$$\n> 💡 **Phân số cơ bản** — Tỉ số giữa a và b."

    def correct_text(self, text: str) -> str:
        return text

    def repair_formula(self, latex: str, issues: List[str]) -> str:
        return latex

    def translate_text(self, text: str, source_lang: str = "en", target_lang: str = "vi") -> str:
        return text

    def document_to_markdown(self, page_content: str) -> str:
        return page_content

def test_latex_annotator_passthrough_when_no_router():
    annotator = LatexAnnotator(ai_router=None)
    md = "# Test\n$$\\frac{a}{b}$$"
    res = annotator.process_chunk_markdown(md)
    assert res == md

def test_latex_annotator_mock_provider():
    router = AIRouter(mode="local_only")
    router.lmstudio_provider = DummyProvider()

    annotator = LatexAnnotator(ai_router=router)
    md = "# Test\n$$\\frac{a}{b}$$"
    res = annotator.process_chunk_markdown(md, translate=False)
    assert "💡" in res
    assert "Phân số cơ bản" in res
