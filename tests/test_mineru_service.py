"""Tests for MinerU Service integration."""

import pytest
from pathlib import Path
from app.services.mineru_service import MinerUService

def test_mineru_service_init():
    svc = MinerUService(cli_path="magic-pdf", method="auto")
    assert svc.cli_path == "magic-pdf"
    assert svc.method == "auto"
    assert isinstance(svc.is_available(), bool)
    assert isinstance(svc.get_executable(), str)

def test_mineru_service_nonexistent_pdf(tmp_path):
    svc = MinerUService(cli_path="magic-pdf", method="auto")
    dummy_pdf = tmp_path / "non_existent.pdf"
    ok, md, folder = svc.run_mineru(dummy_pdf, tmp_path / "output")
    assert ok is False
    assert md is None
