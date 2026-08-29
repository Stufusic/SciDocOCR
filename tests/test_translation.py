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

def test_google_translate_chunking():
    from app.translation.google_translate import GoogleTranslateService
    gt = GoogleTranslateService()

    long_text = "This is a long scientific sentence. " * 50  # ~1800 chars
    chunks = gt._split_text_chunks(long_text, max_chars=500)
    assert len(chunks) >= 3
    for c in chunks:
        assert len(c) <= 600

def test_document_translator_page_by_page():
    from app.translation.translator import DocumentTranslator
    from app.core.document import Document, PageData
    from app.core.blocks import ParagraphBlock, HeadingBlock, BoundingBox
    from app.ai.router import AIRouter

    class MockAIRouter(AIRouter):
        def translate_text(self, text, source_lang="en", target_lang="vi"):
            return f"[VI] {text}"

    translator = DocumentTranslator(ai_router=MockAIRouter())
    page = PageData(page_number=1, width_pt=600, height_pt=800)
    page.add_block(HeadingBlock(text="Introduction", bbox=BoundingBox(0,0,100,20)))
    page.add_block(ParagraphBlock(text="Attention is all you need.", bbox=BoundingBox(0,30,100,50)))

    translated_page = translator.translate_page(page, source_lang="en", target_lang="vi")
    assert translated_page.status == "translated"
    assert translated_page.blocks[0].text == "[VI] Introduction"
    assert translated_page.blocks[1].text == "[VI] Attention is all you need."

def test_markdown_1500_char_chunking_and_streaming():
    from app.translation.translator import DocumentTranslator
    from app.ai.router import AIRouter

    class MockAIRouter(AIRouter):
        def translate_text(self, text, source_lang="en", target_lang="vi"):
            return f"[VI] {text}"

    translator = DocumentTranslator(ai_router=MockAIRouter())

    # Build a long markdown document (> 3500 chars) with math, images, headings
    para1 = ("# Title of the Paper\n\nThis is paragraph one with inline math $E=mc^2$ and more details. \n\n") * 12
    para2 = "## Section Two\n\nHere is display math:\n$$F = m \\cdot a$$\n\nAnd an image: ![Diagram](images/fig_p1_1.png)\n\n"
    para3 = ("This is paragraph three explaining scientific results in deep detail. \n\n") * 15
    sample_md = para1 + para2 + para3

    # Check 1500-char chunking
    chunks = translator.split_markdown_into_chunks(sample_md, max_chars=1500)
    assert len(chunks) >= 2
    for c in chunks:
        assert len(c) <= 2200  # reasonably bounded around 1500 without breaking blocks

    # Test streaming translation callback
    accumulated_results = []
    def callback(acc, current, total):
        accumulated_results.append((acc, current, total))

    result = translator.translate_markdown_stream(
        sample_md,
        source_lang="en",
        target_lang="vi",
        chunk_size=1500,
        chunk_callback=callback
    )

    assert len(accumulated_results) == len(chunks)
    assert "$E=mc^2$" in result
    assert "$$F = m \\cdot a$$" in result
    assert "![Diagram](images/fig_p1_1.png)" in result
    assert "[VI]" in result
