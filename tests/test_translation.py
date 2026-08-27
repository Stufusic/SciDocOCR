"""Tests for translation masking, formula protection, and validation."""

import pytest
from app.translation.parser import ProtectedBlockParser
from app.translation.validator import TranslationValidator

def test_protected_block_masking_and_unmasking():
    parser = ProtectedBlockParser()
    validator = TranslationValidator()

    sample_text = (
        "According to Einstein, the energy is given by $$E = mc^2$$ where $m$ is mass. "
        "See equation \\ref{eq1} and reference \\cite{einstein1905} for details. "
        "Here is sample code:\n```python\nprint('hello')\n```\nDone."
    )

    masked_text, placeholder_map = parser.mask_protected_elements(sample_text)

    # Asserts
    assert "$$E = mc^2$$" not in masked_text
    assert "$m$" not in masked_text
    assert "\\ref{eq1}" not in masked_text
    assert "\\cite{einstein1905}" not in masked_text
    assert "print('hello')" not in masked_text
    assert len(placeholder_map) == 5

    # Simulate translation of surrounding words into Vietnamese
    simulated_translation = (
        f"Theo Einstein, năng lượng được cho bởi {list(placeholder_map.keys())[1]} với {list(placeholder_map.keys())[3]} là khối lượng. "
        f"Xem phương trình {list(placeholder_map.keys())[4]} và tài liệu tham khảo {list(placeholder_map.keys())[4]} để biết thêm chi tiết. "
        f"Dưới đây là mã nguồn mẫu:\n{list(placeholder_map.keys())[0]}\nHoàn thành."
    )

    # Unmask
    restored = parser.unmask_protected_elements(masked_text, placeholder_map)
    assert "$$E = mc^2$$" in restored
    assert "$m$" in restored
    assert "\\cite{einstein1905}" in restored
    assert "print('hello')" in restored

def test_google_translate_service_integration():
    from app.translation.google_translate import GoogleTranslateService
    gt = GoogleTranslateService()
    p = ProtectedBlockParser()

    text = "The energy is given by $$E=mc^2$$ where $m$ is mass."
    masked, pmap = p.mask_protected_elements(text)
    trans = gt.translate_text(masked, source_lang="en", target_lang="vi")
    restored = p.unmask_protected_elements(trans, pmap)

    assert "$$E=mc^2$$" in restored
    assert "$m$" in restored

def test_strip_thought_content():
    from app.utils.thought_cleaner import strip_thought_content

    # 1. Closed XML think tags
    t1 = "<think>Let me analyze the math formula.</think>Result: $$E=mc^2$$"
    assert strip_thought_content(t1) == "Result: $$E=mc^2$$"

    # 2. Closed thought tags
    t2 = "<thought>\nStep 1: Translate\n</thought>\nĐây là bản dịch tiếng Việt."
    assert strip_thought_content(t2) == "Đây là bản dịch tiếng Việt."

    # 3. Fenced thought blocks
    t3 = "```thought\nAnalyzing reasoning steps\n```\nFinal answer is 42."
    assert strip_thought_content(t3) == "Final answer is 42."

    # 4. Leading Thinking Process block
    t4 = "Thinking Process:\n1. Check LaTeX\n2. Format\n\nNội dung chính xác."
    assert strip_thought_content(t4) == "Nội dung chính xác."
