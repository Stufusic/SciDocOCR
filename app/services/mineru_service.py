"""MinerU Service Integration: Subprocess execution wrapper for MinerU (mineru.cli.client / magic-pdf) with 4-page chunking."""

from __future__ import annotations
import sys
import os
import shutil
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple, List, Callable
from app.utils.logging import get_logger
from app.pdf.splitter import PDFSplitter, PDFChunkInfo

logger = get_logger("MinerUService")

@dataclass
class ChunkResult:
    """Represents the extraction result of a single PDF chunk."""
    chunk_index: int
    start_page: int
    end_page: int
    markdown_text: str
    images_saved: List[str]
    success: bool

class MinerUService:
    """Wrapper for executing MinerU via Local Server Port (http://127.0.0.1:8000) or isolated CLI subprocess."""

    def __init__(
        self,
        cli_path: str = "magic-pdf",
        server_url: str = "http://127.0.0.1:8000",
        method: str = "auto",
        backend: str = "pipeline"
    ):
        self.cli_path = cli_path
        self.server_url = server_url.rstrip("/")
        self.method = method  # "auto", "ocr", "txt"
        self.backend = backend  # "pipeline", "hybrid-engine", "vlm-engine"
        self._current_proc: Optional[subprocess.Popen] = None
        self._is_cancelled: bool = False

    def cancel(self):
        """Immediately terminates any running MinerU subprocess."""
        self._is_cancelled = True
        if self._current_proc and self._current_proc.poll() is None:
            try:
                logger.info("Terminating running MinerU subprocess...")
                self._current_proc.terminate()
                self._current_proc.kill()
            except Exception as e:
                logger.warning(f"Error terminating MinerU subprocess: {e}")

    def _has_cuda(self) -> bool:
        """Checks if CUDA is available in PyTorch."""
        try:
            import torch
            return bool(torch.cuda.is_available())
        except Exception:
            return False

    def check_server_port(self) -> Tuple[bool, str]:
        """Checks if MinerU Local Server is active on the configured port."""
        import httpx
        try:
            for endpoint in [f"{self.server_url}/docs", f"{self.server_url}/v1/models", f"{self.server_url}/"]:
                try:
                    resp = httpx.get(endpoint, timeout=1.5)
                    if resp.status_code < 500:
                        return (True, f"MinerU Local Server is online at {self.server_url}")
                except Exception:
                    continue
            return (False, f"No response from MinerU Local Server at {self.server_url}")
        except Exception as e:
            return (False, str(e))

    def is_available(self) -> bool:
        """Checks if MinerU is available either via local server port or as an executable/module."""
        # 1. Check local server port first
        ok, _ = self.check_server_port()
        if ok:
            return True

        # 2. Check direct custom path
        if self.cli_path and (Path(self.cli_path).exists() or shutil.which(self.cli_path)):
            return True

        # 3. Direct Python module check (MinerU 3.x)
        try:
            import mineru
            return True
        except ImportError:
            pass

        # 4. Direct magic-pdf / mineru in PATH
        if shutil.which("magic-pdf") or shutil.which("mineru"):
            return True

        # 5. Check virtualenv
        local_mineru = Path.cwd() / "mineru_env" / "Scripts" / "magic-pdf.exe"
        if local_mineru.exists():
            return True

        return False

    def get_executable(self) -> str:
        """Returns the best command or executable path for running MinerU CLI."""
        if self.cli_path and (Path(self.cli_path).exists() or shutil.which(self.cli_path)):
            return self.cli_path

        if shutil.which("magic-pdf"):
            return "magic-pdf"
        if shutil.which("mineru"):
            return "mineru"

        try:
            import mineru
            return f"{sys.executable} -m mineru.cli.client"
        except ImportError:
            pass

        local_mineru = Path.cwd() / "mineru_env" / "Scripts" / "magic-pdf.exe"
        if local_mineru.exists():
            return str(local_mineru)

        return self.cli_path or "magic-pdf"

    def run_single_pdf(
        self,
        pdf_path: Path,
        output_dir: Path,
        method: Optional[str] = None,
        timeout: float = 300.0
    ) -> Tuple[bool, Optional[str], Optional[Path]]:
        """
        Executes MinerU CLI command for a single PDF file:
        Handles magic-pdf (without -b) and mineru / mineru.cli.client (with -b) appropriately.
        
        Returns: (success, markdown_content, output_folder)
        """
        if self._is_cancelled:
            return (False, None, None)

        pdf_file = Path(pdf_path).resolve()
        out_base = Path(output_dir).resolve()
        out_base.mkdir(parents=True, exist_ok=True)

        if not pdf_file.exists():
            logger.error(f"Input PDF not found for MinerU: {pdf_file}")
            return (False, None, None)

        use_method = method or self.method or "auto"
        exe_cmd = self.get_executable()

        is_legacy_magic_pdf = "magic-pdf" in exe_cmd.lower()
        primary_backend = self.backend or ("hybrid-engine" if self._has_cuda() else "pipeline")

        backends_to_try = [primary_backend]
        if primary_backend != "pipeline" and not is_legacy_magic_pdf:
            backends_to_try.append("pipeline")

        proc_returncode = None
        for backend in backends_to_try:
            if self._is_cancelled:
                return (False, None, None)

            # Build command args
            if exe_cmd.startswith(sys.executable):
                cmd = [sys.executable, "-m", "mineru.cli.client", "-p", str(pdf_file), "-o", str(out_base), "-m", use_method, "-b", backend]
            elif is_legacy_magic_pdf:
                cmd = [exe_cmd, "-p", str(pdf_file), "-o", str(out_base), "-m", use_method]
            else:
                cmd = [exe_cmd, "-p", str(pdf_file), "-o", str(out_base), "-m", use_method, "-b", backend]

            logger.info(f"Running MinerU CLI: {' '.join(cmd)}")

            try:
                self._current_proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace"
                )

                stdout, stderr = self._current_proc.communicate(timeout=timeout)
                proc_returncode = self._current_proc.returncode
                self._current_proc = None

                if self._is_cancelled:
                    return (False, None, None)

                if proc_returncode == 0:
                    logger.info("MinerU execution completed successfully.")
                    break
                else:
                    logger.warning(f"MinerU exited with code {proc_returncode}. Output:\n{(stderr or stdout or '')[:1000]}")
            except subprocess.TimeoutExpired:
                if self._current_proc:
                    self._current_proc.kill()
                    self._current_proc = None
                logger.error(f"MinerU CLI execution timed out after {timeout} seconds.")
            except Exception as e:
                logger.error(f"MinerU execution failed: {e}")

        if proc_returncode != 0:
            return (False, None, None)

        # Search for output folder: <output_dir>/<pdf_stem>/auto/ or <output_dir>/<pdf_stem>/
        stem = pdf_file.stem
        possible_dirs = [
            out_base / stem / "auto",
            out_base / stem / "ocr",
            out_base / stem / "txt",
            out_base / stem,
            out_base
        ]

        target_folder: Optional[Path] = None
        md_file: Optional[Path] = None

        for d in possible_dirs:
            if d.exists() and d.is_dir():
                target_folder = d
                matches = list(d.glob("*.md"))
                if matches:
                    md_file = matches[0]
                    break

        if not md_file or not md_file.exists():
            logger.warning(f"MinerU output folder found but no .md file detected in: {target_folder}")
            return (False, None, target_folder)

        markdown_content = md_file.read_text(encoding="utf-8", errors="replace")
        logger.info(f"Loaded {len(markdown_content)} characters of Markdown from MinerU ({md_file.name})")

        return (True, markdown_content, target_folder)

    def process_chunks(
        self,
        pdf_path: Path,
        output_dir: Path,
        images_dir: Path,
        chunk_size: int = 4,
        method: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        timeout_per_chunk: float = 600.0
    ) -> List[ChunkResult]:
        """
        Splits PDF into 4-page chunks, executes MinerU on each chunk,
        collects all cropped images/figures into images_dir, and returns chunk results.
        """
        input_pdf = Path(pdf_path).resolve()
        out_base = Path(output_dir).resolve()
        img_dest = Path(images_dir).resolve()
        img_dest.mkdir(parents=True, exist_ok=True)

        temp_chunks_dir = out_base / "temp_chunks"
        splitter = PDFSplitter(chunk_size=chunk_size)
        chunks = splitter.split_pdf(input_pdf, temp_chunks_dir)

        if not chunks:
            logger.warning(f"No pages/chunks extracted from PDF: {input_pdf}")
            return []

        total_chunks = len(chunks)
        results: List[ChunkResult] = []

        for idx, chunk in enumerate(chunks):
            if self._is_cancelled:
                logger.info("Process chunks cancelled by user.")
                break

            if progress_callback:
                pct = int((idx / total_chunks) * 100)
                progress_callback(
                    pct, 100,
                    f"MinerU Processing Chunk {chunk.chunk_index}/{total_chunks} (Pages {chunk.start_page}-{chunk.end_page})..."
                )

            chunk_out = temp_chunks_dir / f"out_chunk_{chunk.chunk_index}"
            chunk_out.mkdir(parents=True, exist_ok=True)

            logger.info(f"Processing chunk {chunk.chunk_index}/{total_chunks} (Pages {chunk.start_page}-{chunk.end_page})")
            ok, md_content, out_folder = self.run_single_pdf(
                chunk.file_path,
                chunk_out,
                method=method,
                timeout=timeout_per_chunk
            )
            if self._is_cancelled:
                logger.info("Process chunks cancelled after single PDF run.")
                break

            saved_images: List[str] = []
            final_md = md_content or ""

            # Collect and copy all images generated in this chunk
            if out_folder and out_folder.exists():
                images_subdirs = [out_folder / "images", out_folder]
                for sdir in images_subdirs:
                    if sdir.exists() and sdir.is_dir():
                        for img_file in sdir.glob("*.*"):
                            if img_file.suffix.lower() in [".png", ".jpg", ".jpeg", ".webp"]:
                                # Prefix filename to avoid collision across chunks: chunk_{idx}_{filename}
                                new_img_name = f"chunk_{chunk.chunk_index}_{img_file.name}"
                                target_img_path = img_dest / new_img_name
                                shutil.copy2(img_file, target_img_path)
                                saved_images.append(new_img_name)

                                # Update image reference in this chunk's markdown
                                old_ref = f"images/{img_file.name}"
                                old_ref_rel = img_file.name
                                final_md = final_md.replace(old_ref, f"images/{new_img_name}")
                                final_md = final_md.replace(f"]({old_ref_rel})", f"](images/{new_img_name})")

            results.append(ChunkResult(
                chunk_index=chunk.chunk_index,
                start_page=chunk.start_page,
                end_page=chunk.end_page,
                markdown_text=final_md,
                images_saved=saved_images,
                success=ok
            ))

        # Cleanup temporary PDF chunk files
        PDFSplitter.cleanup_chunks(chunks)
        try:
            shutil.rmtree(temp_chunks_dir, ignore_errors=True)
        except Exception:
            pass

        return results

    # Alias for backward compatibility
    run_mineru = run_single_pdf
