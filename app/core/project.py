"""Project Management system: workspace structure, project.json, and checkpoints."""

from __future__ import annotations
import json
import shutil
from pathlib import Path
from typing import Optional, Dict, Any
from app.core.document import Document
from app.core.exceptions import ProjectError
from app.utils.hashing import compute_file_sha256
from app.utils.logging import get_logger

logger = get_logger("ProjectManager")

class SciDocProject:
    """Represents a discrete SciDoc project directory and workspace."""

    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir).resolve()
        self.source_dir = self.project_dir / "source"
        self.output_dir = self.project_dir / "output"
        self.images_dir = self.project_dir / "images"
        self.cache_dir = self.project_dir / "cache"
        self.project_file = self.project_dir / "project.json"

        self.document: Optional[Document] = None
        self.metadata: Dict[str, Any] = {}
        self.settings: Optional[Any] = None

    @classmethod
    def create_new(cls, project_dir: Path, source_pdf_path: str, project_name: str = "SciDoc Project") -> SciDocProject:
        """Initializes a new project workspace directory."""
        project = cls(project_dir)
        project.project_dir.mkdir(parents=True, exist_ok=True)
        project.source_dir.mkdir(exist_ok=True)
        project.output_dir.mkdir(exist_ok=True)
        project.images_dir.mkdir(exist_ok=True)
        project.cache_dir.mkdir(exist_ok=True)

        # Copy source PDF to project/source/
        src_pdf = Path(source_pdf_path)
        dest_pdf = project.source_dir / src_pdf.name
        if str(src_pdf.resolve()) != str(dest_pdf.resolve()):
            shutil.copy2(src_pdf, dest_pdf)

        pdf_hash = compute_file_sha256(str(dest_pdf))

        project.metadata = {
            "name": project_name,
            "version": "1.0.0",
            "source_pdf": str(dest_pdf),
            "source_pdf_hash": pdf_hash,
            "pipeline_state": "CREATED",
            "last_processed_page": 0,
        }
        project.save()
        return project

    @classmethod
    def load(cls, project_dir: Path) -> SciDocProject:
        """Loads an existing project workspace from directory."""
        project = cls(project_dir)
        if not project.project_file.exists():
            raise ProjectError(f"project.json not found in {project_dir}")

        try:
            with open(project.project_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                project.metadata = data.get("project_metadata", {})
                doc_data = data.get("document", None)
                if doc_data:
                    project.document = Document.from_dict(doc_data)
            return project
        except Exception as e:
            raise ProjectError(f"Failed to load project: {e}")

    def save(self) -> None:
        """Saves project metadata and Document AST state to project.json."""
        self.project_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "project_metadata": self.metadata,
            "document": self.document.to_dict() if self.document else None
        }
        with open(self.project_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.debug(f"Project saved to {self.project_file}")

    def update_state(self, state: str, last_page: int = 0) -> None:
        self.metadata["pipeline_state"] = state
        if last_page > 0:
            self.metadata["last_processed_page"] = last_page
        self.save()
