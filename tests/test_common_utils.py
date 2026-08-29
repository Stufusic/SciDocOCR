"""Unit tests for central common utilities in app.utils.common."""

import os
import io
import json
import pytest
from pathlib import Path
from PIL import Image

from app.utils.common import (
    get_app_dir,
    get_cache_dir,
    get_logs_dir,
    get_assets_dir,
    get_projects_dir,
    ensure_dir,
    sanitize_filename,
    purge_directory,
    safe_read_text,
    safe_write_text,
    safe_read_json,
    safe_write_json,
    optimize_image_for_ai,
    image_bytes_to_base64,
    image_file_to_base64_data_uri,
    strip_thought_content,
    clean_latex_math,
    compute_file_sha256,
    compute_bytes_sha256,
    compute_text_sha256,
    get_logger,
)

def test_paths_and_directories(tmp_path):
    assert get_app_dir().exists()
    assert get_cache_dir().exists()
    assert get_logs_dir().exists()
    assert get_assets_dir().exists()
    assert get_projects_dir().exists()

    sub = tmp_path / "a" / "b" / "c"
    created = ensure_dir(sub)
    assert created.exists()
    assert created.is_dir()

def test_sanitize_filename():
    assert sanitize_filename("my:file*name?test.pdf") == "my_file_name_test.pdf"
    assert sanitize_filename("1706.03762v7/output\\math") == "1706.03762v7_output_math"
    assert sanitize_filename("") == "document"
    assert sanitize_filename("   ") == "document"

def test_purge_directory(tmp_path):
    target = tmp_path / "purge_me"
    target.mkdir()
    (target / "file1.txt").write_text("hello", encoding="utf-8")
    (target / "subdir").mkdir()
    (target / "subdir" / "file2.txt").write_text("world", encoding="utf-8")

    purge_directory(target, keep_root=True)
    assert target.exists()
    assert len(list(target.iterdir())) == 0

def test_safe_file_io(tmp_path):
    test_txt = tmp_path / "test.txt"
    assert safe_read_text(test_txt, default="empty") == "empty"
    
    assert safe_write_text(test_txt, "Scientific OCR Text")
    assert safe_read_text(test_txt) == "Scientific OCR Text"

    test_json = tmp_path / "test.json"
    data = {"name": "SciDoc", "version": 1.0, "nested": [1, 2, 3]}
    assert safe_write_json(test_json, data)
    read_data = safe_read_json(test_json)
    assert read_data == data

def test_image_helpers(tmp_path):
    # Create test image
    img = Image.new("RGB", (2400, 1600), color=(73, 109, 137))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    raw_bytes = buf.getvalue()

    # 1. Optimize image
    opt_bytes, mime = optimize_image_for_ai(raw_bytes, max_dim=1800, quality=85)
    assert mime == "image/jpeg"
    assert len(opt_bytes) < len(raw_bytes)
    assert len(opt_bytes) > 0

    # 2. Base64
    b64 = image_bytes_to_base64(opt_bytes)
    assert isinstance(b64, str)
    assert len(b64) > 0

    # 3. File data URI
    img_file = tmp_path / "sample.png"
    img_file.write_bytes(raw_bytes)
    uri = image_file_to_base64_data_uri(img_file)
    assert uri.startswith("data:image/png;base64,")

def test_strip_thought_content():
    raw = "<think>\nLet me solve this formula step by step...\n</think>\nHere is the answer: $E=mc^2$"
    assert strip_thought_content(raw) == "Here is the answer: $E=mc^2$"

    raw2 = "```thought\nAnalyzing document structure\n```\n# Introduction"
    assert strip_thought_content(raw2) == "# Introduction"

def test_hashing(tmp_path):
    sample_text = "Transformer Architecture"
    assert len(compute_text_sha256(sample_text)) == 64
    assert len(compute_bytes_sha256(sample_text.encode("utf-8"))) == 64

    sample_f = tmp_path / "hash_me.txt"
    sample_f.write_text(sample_text, encoding="utf-8")
    assert compute_file_sha256(sample_f) == compute_text_sha256(sample_text)

def test_logger():
    logger = get_logger("TestLogger")
    assert logger.name == "TestLogger"
