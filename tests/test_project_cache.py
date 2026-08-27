import pytest
import pymupdf as fitz
from pathlib import Path
from app.core.project import SciDocProject
from app.storage.cache import CacheManager
from app.core.blocks import ParagraphBlock, FormulaBlock

@pytest.fixture
def sample_pdf(tmp_path):
    pdf_path = tmp_path / "test_doc.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Test Document for Project", fontsize=14)
    doc.save(str(pdf_path))
    doc.close()
    return str(pdf_path)

def test_project_create_and_load(tmp_path, sample_pdf):
    proj_dir = tmp_path / "MySciDocProject"
    project = SciDocProject.create_new(proj_dir, sample_pdf, project_name="Quantum Paper")

    assert project.project_file.exists()
    assert (proj_dir / "source" / "test_doc.pdf").exists()

    # Load back
    loaded = SciDocProject.load(proj_dir)
    assert loaded.metadata["name"] == "Quantum Paper"
    assert loaded.metadata["pipeline_state"] == "CREATED"

def test_cache_manager(tmp_path):
    cache = CacheManager(tmp_path / "cache")
    sha = "abcdef1234567890"

    blocks = [
        ParagraphBlock(text="Cached paragraph", confidence=0.99),
        FormulaBlock(latex="E=mc^2", confidence=0.95)
    ]

    cache.store_cached_page_blocks(sha, blocks)
    retrieved = cache.get_cached_page_blocks(sha)

    assert retrieved is not None
    assert len(retrieved) == 2
    assert retrieved[0].text == "Cached paragraph"
    assert retrieved[1].latex == "E=mc^2"
