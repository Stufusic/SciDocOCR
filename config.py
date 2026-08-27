"""Pipeline configuration for Modular & Batch-Oriented Document OCR with VLM."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env if present
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "input"
TEMP_DIR = BASE_DIR / "temp"
OUTPUT_DIR = BASE_DIR / "output"

PAGES_DIR = TEMP_DIR / "pages"
CROPS_MATH_DIR = TEMP_DIR / "crops" / "math"
CROPS_TABLES_DIR = TEMP_DIR / "crops" / "tables"
CROPS_CHARTS_DIR = TEMP_DIR / "crops" / "charts"

# Ensure all pipeline directories exist
for p in [INPUT_DIR, TEMP_DIR, OUTPUT_DIR, PAGES_DIR, CROPS_MATH_DIR, CROPS_TABLES_DIR, CROPS_CHARTS_DIR]:
    p.mkdir(parents=True, exist_ok=True)

# LM Studio Local VLM Configuration (OpenAI Compatible)
LM_STUDIO_API_URL = os.getenv("LMSTUDIO_URL", "http://localhost:1234/v1")
LM_STUDIO_API_KEY = os.getenv("LMSTUDIO_KEY", "lm-studio")
VLM_MODEL_NAME = os.getenv("LMSTUDIO_MODEL", "qwen/qwen3.5-9b")

# Online VLM Configuration (Google Gemini / OpenAI Vision Fallback)
ONLINE_API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY", "")
ONLINE_PROVIDER = os.getenv("ONLINE_PROVIDER", "google")
ONLINE_MODEL = os.getenv("ONLINE_MODEL", "gemini-3.5-flash")

# Processing Mode
AI_MODE = os.getenv("AI_MODE", "local_only")
RENDER_DPI = int(os.getenv("OCR_DPI", "400"))
MATH_CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.85"))
USE_VLM_FOR_TABLES = True
USE_VLM_FOR_CHARTS = True
USE_VLM_MATH_FALLBACK = True
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "180.0"))
