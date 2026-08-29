"""LaTeX Generator: converts Document AST into clean, 100% self-contained standard LaTeX source code."""

from typing import Optional
from app.core.document import Document
from app.core.blocks import (
    BaseBlock, BlockType, HeadingBlock, ParagraphBlock,
    FormulaBlock, TableBlock, FigureBlock, CaptionBlock,
    ListBlock, FootnoteBlock, ReferenceBlock, CodeBlock
)

# Comprehensive Universal LaTeX Master Template:
# Pre-loads all standard packages for mathematics, physics, multilingual fonts (Vietnamese/Unicode),
# complex tables, algorithms, graphics, and styling so any scientific document compiles without missing packages.
LATEX_DOCUMENT_TEMPLATE = r"""\documentclass[11pt,a4paper]{article}

% =========================================================================
% 1. Multilingual & Font Support (Unicode, Vietnamese & CJK Safe)
% =========================================================================
\usepackage{iftex}
\ifPDFTeX
  \usepackage[utf8]{inputenc}
  \usepackage[T1,T5]{fontenc}
  \usepackage[vietnamese,english]{babel}
\else
  \usepackage{fontspec}
\fi

% =========================================================================
% 2. Mathematics, Physics & Symbols Packages
% =========================================================================
\usepackage{amsmath,amssymb,amsfonts,amsthm,mathtools,bm,mathrsfs}
\usepackage{physics,siunitx}
\usepackage{cancel,cases,esint}

% =========================================================================
% 3. Tables, Arrays & Advanced Layout
% =========================================================================
\usepackage{booktabs,tabularx,longtable,multirow,multicol,array}
\usepackage{makecell,colortbl}

% =========================================================================
% 4. Graphics, Figures, Subfigures & Colors
% =========================================================================
\usepackage{graphicx}
\usepackage{xcolor}
\usepackage{float,wrapfig}
\usepackage{caption,subcaption}
\usepackage{tikz}

% =========================================================================
% 5. Code Listings & Algorithms
% =========================================================================
\usepackage{listings}
\usepackage{algorithm}
\usepackage{algorithmic}

% =========================================================================
% 6. Boxes, Lists, URLs & Hyperlinks
% =========================================================================
\usepackage{enumitem}
\usepackage{tcolorbox}
\usepackage{url}
\usepackage[hidelinks,colorlinks=true,linkcolor=blue,citecolor=blue,urlcolor=blue]{hyperref}

% Standard Page Dimensions & Paragraph Formatting
\setlength{\topmargin}{-0.5in}
\setlength{\textheight}{9.0in}
\setlength{\oddsidemargin}{0in}
\setlength{\evensidemargin}{0in}
\setlength{\textwidth}{6.5in}
\setlength{\parindent}{0pt}
\setlength{\parskip}{6pt}

\title{ {{- doc_title -}} }
\author{ {{- doc_author -}} }
\date{\today}

\begin{document}

\maketitle

{{ doc_body }}

\end{document}
"""

class LaTeXGenerator:
    """Generates compilable LaTeX documents from Document AST."""

    def __init__(self):
        pass

    def escape_latex(self, text: str) -> str:
        """Escapes special LaTeX characters in regular prose while preserving inline math $...$ and display math $$...$$."""
        if not text:
            return ""

        import re
        # Find all math expressions ($...$ or $$...$$) and replace with unique placeholders
        placeholders = []
        def _mask_math(m):
            placeholders.append(m.group(0))
            return f"__LATEX_MATH_PH_{len(placeholders)-1}__"

        # Mask $$...$$ first, then $...$
        masked = re.sub(r"\$\$.*?\$\$", _mask_math, text, flags=re.DOTALL)
        masked = re.sub(r"\$[^\$\n]+?\$", _mask_math, masked)

        replacements = [
            ("\\", r"\textbackslash{}"),
            ("&", r"\&"), ("%", r"\%"), ("#", r"\#"),
            ("^", r"\^{}"), ("~", r"\~{}"),
            ("{", r"\{"), ("}", r"\}"), ("_", r"\_")
        ]
        for char, rep in replacements:
            masked = masked.replace(char, rep)

        # Restore math expressions untouched
        for idx, math_str in enumerate(placeholders):
            masked = masked.replace(f"__LATEX_MATH_PH_{idx}__", math_str)

        return masked

    def render_block(self, block: BaseBlock) -> str:
        btype = block.block_type

        if btype == BlockType.HEADING and isinstance(block, HeadingBlock):
            escaped = self.escape_latex(block.text)
            if block.level == 1:
                return f"\\section{{{escaped}}}\n"
            elif block.level == 2:
                return f"\\subsection{{{escaped}}}\n"
            elif block.level == 3:
                return f"\\subsubsection{{{escaped}}}\n"
            else:
                return f"\\paragraph{{{escaped}}}\n"

        elif btype == BlockType.PARAGRAPH and isinstance(block, ParagraphBlock):
            text = block.text or ""
            # Handle formula / concept annotation callouts
            if "💡" in text or text.strip().startswith(">"):
                clean_note = text.replace(">", "").strip()
                escaped_note = self.escape_latex(clean_note)
                return f"\n\\begin{{quote}}\n\\small\\textbf{{Annotation:}} \\textit{{{escaped_note}}}\n\\end{{quote}}\n\n"
            return f"{self.escape_latex(text)}\n\n"

        elif btype == BlockType.CAPTION and isinstance(block, CaptionBlock):
            escaped = self.escape_latex(block.text or "")
            return f"\\textit{{{escaped}}}\n\n"

        elif btype == BlockType.FORMULA and isinstance(block, FormulaBlock):
            latex = block.latex or ""
            if block.is_inline:
                return f"${latex}$"
            return f"\n\\begin{{equation}}\n{latex}\n\\end{{equation}}\n\n"

        elif btype == BlockType.TABLE and isinstance(block, TableBlock):
            if not block.rows:
                if getattr(block, "image_crop_path", None):
                    img_p = str(block.image_crop_path).replace("\\", "/")
                    lines = ["\\begin{table}[htbp]", "\\centering"]
                    lines.append(f"\\includegraphics[width=0.9\\linewidth]{{{img_p}}}")
                    if block.caption:
                        lines.append(f"\\caption{{{self.escape_latex(block.caption)}}}")
                    lines.append("\\end{table}\n")
                    return "\n".join(lines)
                return ""
            num_cols = len(block.rows[0])
            col_spec = "|" + "|".join(["c"] * num_cols) + "|"
            lines = [
                "\\begin{table}[htbp]",
                "\\centering",
                f"\\begin{{tabular}}{{{col_spec}}}",
                "\\hline"
            ]
            # Header
            header_cells = [self.escape_latex(str(c)) for c in block.rows[0]]
            lines.append(" & ".join(header_cells) + r" \\")
            lines.append("\\hline")

            # Body rows
            for row in block.rows[1:]:
                padded = list(row) + [""] * (num_cols - len(row))
                cells = [self.escape_latex(str(c)) for c in padded[:num_cols]]
                lines.append(" & ".join(cells) + r" \\")
                lines.append("\\hline")

            lines.append("\\end{tabular}")
            if block.caption:
                lines.append(f"\\caption{{{self.escape_latex(block.caption)}}}")
            lines.append("\\end{table}\n")
            return "\n".join(lines)

        elif btype == BlockType.FIGURE and isinstance(block, FigureBlock):
            lines = ["\\begin{figure}[htbp]", "\\centering"]
            if block.image_path:
                # Use forward slashes for TeX graphics compatibility
                img_p = str(block.image_path).replace("\\", "/")
                lines.append(f"\\includegraphics[width=0.85\\linewidth]{{{img_p}}}")
            if block.caption:
                lines.append(f"\\caption{{{self.escape_latex(block.caption)}}}")
            lines.append("\\end{figure}\n")
            return "\n".join(lines)

        elif btype == BlockType.LIST and isinstance(block, ListBlock):
            env = "enumerate" if block.is_ordered else "itemize"
            lines = [f"\\begin{{{env}}}"]
            for item in block.items:
                lines.append(f"  \\item {self.escape_latex(item)}")
            lines.append(f"\\end{{{env}}}\n")
            return "\n".join(lines)

        elif btype == BlockType.CODE and isinstance(block, CodeBlock):
            return f"\\begin{{verbatim}}\n{block.code}\n\\end{{verbatim}}\n\n"

        elif btype == BlockType.FOOTNOTE and isinstance(block, FootnoteBlock):
            return f"\\footnote{{{self.escape_latex(block.text)}}}\n"

        return ""

    def generate_latex(self, doc: Document) -> str:
        """Generates full standalone LaTeX source string."""
        body_parts = []
        for page in doc.pages:
            for block in page.blocks:
                rendered = self.render_block(block)
                if rendered:
                    body_parts.append(rendered)

        doc_body = "\n".join(body_parts)
        doc_title = self.escape_latex(doc.metadata.title or "Scientific Document")
        doc_author = self.escape_latex(doc.metadata.author or "")

        tex = LATEX_DOCUMENT_TEMPLATE
        tex = tex.replace("{{- doc_title -}}", doc_title)
        tex = tex.replace("{{- doc_author -}}", doc_author)
        tex = tex.replace("{{ doc_body }}", doc_body)
        return tex
