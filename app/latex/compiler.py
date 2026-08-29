"""LaTeX and PDF Compiler Engine with Standalone Python Fallback."""

import subprocess
import shutil
import os
import re
from pathlib import Path
from typing import Tuple, List, Optional
from app.core.exceptions import LaTeXCompilationError
from app.latex.validator import LaTeXValidator
from app.core.document import Document
from app.utils.logging import get_logger

logger = get_logger("LaTeXCompiler")

class LaTeXCompiler:
    """Compiles LaTeX .tex to .pdf using system TeX engine or ReportLab fallback."""

    def __init__(self, preferred_engine: Optional[str] = None):
        self.preferred_engine = preferred_engine
        self.validator = LaTeXValidator()

    def discover_engines(self) -> List[str]:
        """Detects available LaTeX compilers in system PATH."""
        candidates = ["xelatex", "pdflatex", "lualatex", "tectonic"]
        found = []
        for eng in candidates:
            if shutil.which(eng):
                found.append(eng)
        return found

    def sanitize_tex_source(self, tex_content: str, missing_packages: List[str]) -> str:
        """Removes uninstalled packages from the TeX preamble to ensure successful compilation."""
        lines = tex_content.splitlines()
        clean_lines = []
        for line in lines:
            is_bad = False
            for pkg in missing_packages:
                pkg_name = pkg.replace(".sty", "")
                if re.search(rf"\\usepackage(\[[^\]]*\])?\{{{pkg_name}\}}", line):
                    is_bad = True
                    break
            if not is_bad:
                clean_lines.append(line)
        return "\n".join(clean_lines)

    def compile_tex(self, tex_file_path: str, output_dir: Optional[str] = None) -> Tuple[bool, str, str]:
        """
        Compiles a .tex file to PDF using discovered LaTeX engine.
        Returns: (success, output_pdf_path, log_output)
        """
        tex_path = Path(tex_file_path).resolve()
        if not tex_path.exists():
            raise LaTeXCompilationError(f"TeX file {tex_file_path} does not exist.")

        work_dir = tex_path.parent if output_dir is None else Path(output_dir).resolve()
        work_dir.mkdir(parents=True, exist_ok=True)

        engines = self.discover_engines()
        if not engines:
            return (False, "", "No LaTeX compiler (xelatex, pdflatex, tectonic) found on system PATH.")

        target_engines = []
        if self.preferred_engine and self.preferred_engine in engines:
            target_engines.append(self.preferred_engine)
        for eng in engines:
            if eng not in target_engines:
                target_engines.append(eng)

        expected_pdf = work_dir / f"{tex_path.stem}.pdf"

        # Record modification time before compile
        pre_mtime = expected_pdf.stat().st_mtime if expected_pdf.exists() else 0
        res = None
        log_output = ""

        for engine in target_engines:
            logger.info(f"Compiling {tex_path.name} with engine: {engine}")
            cmd = [
                engine,
                "-interaction=nonstopmode",
                f"-output-directory={str(work_dir)}",
                str(tex_path)
            ]

            try:
                res = subprocess.run(
                    cmd,
                    cwd=str(work_dir),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=90
                )
                log_output = res.stdout or ""

                # If PDF was created or updated and has substantial size
                if expected_pdf.exists() and expected_pdf.stat().st_size > 1000:
                    post_mtime = expected_pdf.stat().st_mtime
                    if post_mtime >= pre_mtime:
                        logger.info(f"Successfully compiled PDF using {engine}: {expected_pdf} ({expected_pdf.stat().st_size} bytes)")
                        return (True, str(expected_pdf), log_output)

                # Check for missing packages (e.g. kvsetkeys, booktabs, geometry)
                missing = re.findall(r"File `([^']+\.sty)' not found", log_output)
                if missing:
                    logger.warning(f"Engine {engine} failed due to missing packages: {missing}. Sanitizing TeX preamble...")
                    with open(tex_path, "r", encoding="utf-8") as f:
                        raw_tex = f.read()

                    sanitized = self.sanitize_tex_source(raw_tex, missing)
                    with open(tex_path, "w", encoding="utf-8") as f:
                        f.write(sanitized)

                    # Retry compilation immediately
                    res2 = subprocess.run(
                        cmd,
                        cwd=str(work_dir),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=90
                    )
                    if expected_pdf.exists() and expected_pdf.stat().st_size > 1000:
                        logger.info(f"Successfully compiled PDF after sanitizing preamble: {expected_pdf}")
                        return (True, str(expected_pdf), res2.stdout or "")

            except Exception as e:
                logger.error(f"Error running {engine}: {e}")

        # Final check if expected_pdf exists
        if expected_pdf.exists() and expected_pdf.stat().st_size > 1000:
            return (True, str(expected_pdf), log_output)

        errors = self.validator.parse_compiler_log(log_output)
        return_code = res.returncode if res is not None else -1
        error_msg = f"LaTeX compilation exited with code {return_code}. Found {len(errors)} errors."
        logger.error(error_msg)
        return (False, "", log_output)

    def compile_fallback_pdf(self, doc: Document, output_pdf_path: str) -> str:
        """
        Builds a styled PDF directly from Document AST using ReportLab
        when no system TeX installation is available.
        """
        import html
        from reportlab.lib.pagesizes import letter, A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors

        out_path = Path(output_pdf_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        doc_pdf = SimpleDocTemplate(str(out_path), pagesize=A4)
        styles = getSampleStyleSheet()

        # Custom styles
        title_style = ParagraphStyle("TitleStyle", parent=styles["Heading1"], fontSize=18, leading=22, spaceAfter=12)
        h2_style = ParagraphStyle("H2Style", parent=styles["Heading2"], fontSize=14, leading=18, spaceBefore=10, spaceAfter=6)
        body_style = ParagraphStyle("BodyStyle", parent=styles["Normal"], fontSize=10, leading=14, spaceAfter=8)
        math_style = ParagraphStyle("MathStyle", parent=styles["Code"], fontSize=10, leading=14, backColor=colors.whitesmoke, spaceAfter=8)

        story = []

        if doc.metadata.title:
            story.append(Paragraph(html.escape(doc.metadata.title), title_style))
            if doc.metadata.author:
                story.append(Paragraph(f"Author: {html.escape(doc.metadata.author)}", body_style))
            story.append(Spacer(1, 10))

        from app.core.blocks import BlockType, HeadingBlock, ParagraphBlock, FormulaBlock, TableBlock

        for page in doc.pages:
            for block in page.blocks:
                if block.block_type == BlockType.HEADING and isinstance(block, HeadingBlock):
                    story.append(Paragraph(html.escape(block.text or ""), h2_style))
                elif block.block_type == BlockType.PARAGRAPH and isinstance(block, ParagraphBlock):
                    story.append(Paragraph(html.escape(block.text or ""), body_style))
                elif block.block_type == BlockType.FORMULA and isinstance(block, FormulaBlock):
                    story.append(Paragraph(f"[Equation] {html.escape(block.latex or '')}", math_style))
                elif block.block_type == BlockType.TABLE and isinstance(block, TableBlock):
                    if block.rows:
                        # Clean cell text for table
                        escaped_rows = [[html.escape(str(c)) for c in row] for row in block.rows]
                        t = Table(escaped_rows)
                        t.setStyle(TableStyle([
                            ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
                            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                            ('FONTSIZE', (0,0), (-1,-1), 9),
                        ]))
                        story.append(t)
                        story.append(Spacer(1, 8))

        doc_pdf.build(story)
        logger.info(f"Fallback PDF generated at: {out_path}")
        return str(out_path)
