"""Tests for layout detection, columns, and reading order reconstruction."""

import pytest
from app.core.blocks import ParagraphBlock, HeadingBlock, BoundingBox
from app.layout.columns import ColumnDetector
from app.layout.ordering import ReadingOrderReconstructor

def test_single_column_ordering():
    page_w, page_h = 595.0, 842.0
    reconstructor = ReadingOrderReconstructor(page_w, page_h)

    b1 = ParagraphBlock(text="Line 1", bbox=BoundingBox(50, 100, 500, 120))
    b2 = ParagraphBlock(text="Line 2", bbox=BoundingBox(50, 150, 500, 170))
    b3 = ParagraphBlock(text="Line 3", bbox=BoundingBox(50, 200, 500, 220))

    # Pass in shuffled order
    ordered = reconstructor.reconstruct_order([b3, b1, b2])
    assert [b.text for b in ordered] == ["Line 1", "Line 2", "Line 3"]

def test_two_column_ordering():
    page_w, page_h = 600.0, 800.0
    reconstructor = ReadingOrderReconstructor(page_w, page_h)

    # Title spanning across top
    title = HeadingBlock(text="Paper Title", bbox=BoundingBox(50, 50, 550, 80))

    # Left column blocks (x from 50 to 280)
    col1_1 = ParagraphBlock(text="Left 1", bbox=BoundingBox(50, 120, 280, 180))
    col1_2 = ParagraphBlock(text="Left 2", bbox=BoundingBox(50, 200, 280, 260))
    col1_3 = ParagraphBlock(text="Left 3", bbox=BoundingBox(50, 280, 280, 340))

    # Right column blocks (x from 320 to 550)
    col2_1 = ParagraphBlock(text="Right 1", bbox=BoundingBox(320, 120, 550, 180))
    col2_2 = ParagraphBlock(text="Right 2", bbox=BoundingBox(320, 200, 550, 260))
    col2_3 = ParagraphBlock(text="Right 3", bbox=BoundingBox(320, 280, 550, 340))

    blocks = [col2_1, col1_2, title, col2_2, col1_1, col2_3, col1_3]
    ordered = reconstructor.reconstruct_order(blocks)

    ordered_texts = [b.text for b in ordered]
    assert ordered_texts[0] == "Paper Title"
    # Left column should be read before right column
    assert ordered_texts[1:4] == ["Left 1", "Left 2", "Left 3"]
    assert ordered_texts[4:7] == ["Right 1", "Right 2", "Right 3"]

def test_heading_level_classification():
    from app.models.layout_detector import DocumentLayoutDetector
    detector = DocumentLayoutDetector()

    blocks = [
        ParagraphBlock(text="1. Introduction", bbox=BoundingBox(0,0,100,20)),
        ParagraphBlock(text="1 Introduction", bbox=BoundingBox(0,25,100,45)),
        ParagraphBlock(text="1.2 Related Work", bbox=BoundingBox(0,50,100,70)),
        ParagraphBlock(text="2.3.1 Attention Mechanism", bbox=BoundingBox(0,75,100,95)),
        ParagraphBlock(text="This is a standard body text paragraph.", bbox=BoundingBox(0,100,100,120))
    ]

    routed = detector.classify_and_route_blocks(blocks)
    assert len(routed) == 5
    assert isinstance(routed[0], HeadingBlock) and routed[0].level == 1
    assert isinstance(routed[1], HeadingBlock) and routed[1].level == 1
    assert isinstance(routed[2], HeadingBlock) and routed[2].level == 2
    assert isinstance(routed[3], HeadingBlock) and routed[3].level == 3
    assert isinstance(routed[4], ParagraphBlock)
