"""Main Pipeline Coordinator: Batch & Modular Document OCR with VLM."""

import sys
import argparse
from pathlib import Path
from tqdm import tqdm

from config import INPUT_DIR, OUTPUT_DIR, USE_VLM_FOR_TABLES, USE_VLM_FOR_CHARTS
from src.layout_parser import LayoutParser
from src.math_engine import MathEngine
from src.vlm_client import parse_table_image, parse_chart_image
from src.assembler import DocumentAssembler
from app.utils.logging import setup_logger

logger = setup_logger("DocumentOCRPipeline")

def process_document(pdf_path: str | Path, refine: bool = False) -> str:
    """Executes the complete 4-phase VLM + OCR document processing pipeline."""
    pdf_file = Path(pdf_path).resolve()
    if not pdf_file.exists():
        raise FileNotFoundError(f"Input document not found: {pdf_file}")

    print("=" * 65)
    print(f"🚀 Starting Document OCR Pipeline on: {pdf_file.name}")
    print("=" * 65)

    # -------------------------------------------------------------
    # PHASE 1: Layout Analysis & Cropping -> Draft Skeleton
    # -------------------------------------------------------------
    print("\n[Phase 1/4] Analyzing Layout & Cropping Visual Regions...")
    layout_parser = LayoutParser()
    parse_result = layout_parser.parse_document(pdf_file)
    skeleton = parse_result["draft_skeleton"]
    crops_meta = parse_result["crops_metadata"]

    math_items = {k: v for k, v in crops_meta.items() if v["type"] == "math"}
    table_items = {k: v for k, v in crops_meta.items() if v["type"] == "table"}
    chart_items = {k: v for k, v in crops_meta.items() if v["type"] == "chart"}

    print(f"  ✓ Found {len(math_items)} formulas, {len(table_items)} tables, {len(chart_items)} charts/figures.")

    replacements = {}
    math_engine = MathEngine()

    # -------------------------------------------------------------
    # PHASE 2 & 3A: Fast Math OCR with VLM Fallback
    # -------------------------------------------------------------
    if math_items:
        print("\n[Phase 2/4] Processing Mathematical Formulas (Fast OCR + VLM Fallback)...")
        for placeholder, item in tqdm(math_items.items(), desc="Math Formulas"):
            latex_code, conf, method = math_engine.process_math_crop(
                item["crop_path"],
                raw_text_hint=item.get("text_hint", ""),
                is_inline=False
            )
            replacements[placeholder] = latex_code

    # -------------------------------------------------------------
    # PHASE 3B: Deep Visual Parsing for Tables
    # -------------------------------------------------------------
    if table_items and USE_VLM_FOR_TABLES:
        print("\n[Phase 3/4] Processing Tables with VLM Table Parser...")
        for placeholder, item in tqdm(table_items.items(), desc="Tables to Markdown"):
            md_table = parse_table_image(item["crop_path"])
            if md_table:
                replacements[placeholder] = f"\n{md_table}\n"
            else:
                replacements[placeholder] = f"\n[Table: {item.get('text_hint', '')}]\n"

    # -------------------------------------------------------------
    # PHASE 3C: Deep Visual Parsing for Charts / Figures
    # -------------------------------------------------------------
    if chart_items and USE_VLM_FOR_CHARTS:
        print("\n[Phase 3/4] Processing Charts & Visualizations with VLM Chart Parser...")
        for placeholder, item in tqdm(chart_items.items(), desc="Charts to Data"):
            chart_summary = parse_chart_image(item["crop_path"])
            caption = item.get("text_hint", "Figure")
            img_rel = Path(item["crop_path"]).as_posix()
            if chart_summary:
                replacements[placeholder] = f"\n![{caption}]({img_rel})\n\n> **Chart Insights:**\n{chart_summary}\n"
            else:
                replacements[placeholder] = f"\n![{caption}]({img_rel})\n"

    # -------------------------------------------------------------
    # PHASE 4: Synthesis & Final Assembly
    # -------------------------------------------------------------
    print("\n[Phase 4/4] Assembling Final Structured Markdown Document...")
    assembler = DocumentAssembler()
    final_output = assembler.assemble(skeleton, replacements, refine_with_llm=refine)

    out_file = OUTPUT_DIR / "final_output.md"
    print("\n" + "=" * 65)
    print(f"🎉 Pipeline Complete! Final Markdown generated at:\n👉 {out_file.resolve()}")
    print("=" * 65)

    return final_output

def main():
    parser = argparse.ArgumentParser(description="Modular & Batch-Oriented Document OCR Pipeline with VLM")
    parser.add_argument("pdf_path", nargs="?", help="Path to input PDF file")
    parser.add_argument("--refine", action="store_true", help="Refine final document with LLM text model")
    args = parser.parse_args()

    input_pdf = args.pdf_path
    if not input_pdf:
        # Search for first PDF in input/ directory
        candidates = list(INPUT_DIR.glob("*.pdf"))
        if candidates:
            input_pdf = candidates[0]
        else:
            # Fallback to sample in scidoc projects
            sample = Path.home() / ".scidoc_projects" / "1706.03762v7" / "source" / "1706.03762v7.pdf"
            if sample.exists():
                input_pdf = sample
            else:
                print(f"No PDF provided and none found in {INPUT_DIR}. Usage: python main.py <file.pdf>")
                sys.exit(1)

    process_document(input_pdf, refine=args.refine)

if __name__ == "__main__":
    main()
