"""VLM Client: Communicates with LM Studio Local Server (OpenAI Vision API spec) with Online VLM Fallback, disabled thinking, and 180s timeout."""

from __future__ import annotations
import re
import base64
import httpx
from pathlib import Path
from typing import Optional, Dict, Any

from config import (
    LM_STUDIO_API_URL, LM_STUDIO_API_KEY, VLM_MODEL_NAME,
    ONLINE_API_KEY, ONLINE_PROVIDER, ONLINE_MODEL, AI_MODE
)
from app.utils.logging import get_logger

logger = get_logger("VLMClient")

def encode_image(image_path: str | Path) -> str:
    """Reads an image file and returns base64 encoded string."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

def _clean_response(text: str) -> str:
    """Strips <think>...</think> tags and markdown fences if any."""
    clean = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    return clean

def _call_online_vlm(base64_img: str, prompt: str, system_prompt: str = "", timeout: float = 180.0) -> str:
    """Sends image + prompt to Online VLM (Google Gemini or OpenAI Vision)."""
    if not ONLINE_API_KEY:
        return ""
    try:
        if ONLINE_PROVIDER == "google":
            model = ONLINE_MODEL.replace("models/", "").strip() or "gemini-2.0-flash"
            endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={ONLINE_API_KEY}"
            payload = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {"text": f"{system_prompt}\n\n{prompt}" if system_prompt else prompt},
                            {
                                "inline_data": {
                                    "mime_type": "image/png",
                                    "data": base64_img
                                }
                            }
                        ]
                    }
                ],
                "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2048}
            }
            headers = {
                "x-goog-api-key": ONLINE_API_KEY,
                "Content-Type": "application/json"
            }
            with httpx.Client(timeout=timeout) as client:
                r = client.post(endpoint, json=payload, headers=headers)
                if r.status_code == 200:
                    cand = r.json().get("candidates", [])
                    if cand:
                        parts = cand[0].get("content", {}).get("parts", [])
                        if parts:
                            return _clean_response(parts[0].get("text", ""))
                elif r.status_code == 404 and model != "gemini-2.0-flash":
                    # Fallback to standard gemini-2.0-flash
                    fb_ep = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={ONLINE_API_KEY}"
                    r2 = client.post(fb_ep, json=payload, headers=headers)
                    if r2.status_code == 200:
                        cand2 = r2.json().get("candidates", [])
                        if cand2:
                            parts2 = cand2[0].get("content", {}).get("parts", [])
                            if parts2:
                                return _clean_response(parts2[0].get("text", ""))
        else:
            # OpenAI / Custom Vision API
            headers_oai = {
                "Authorization": f"Bearer {ONLINE_API_KEY}",
                "Content-Type": "application/json"
            }
            payload_oai = {
                "model": ONLINE_MODEL or "gpt-4o-mini",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_img}"}}
                        ]
                    }
                ],
                "max_tokens": 2048,
                "reasoning_effort": "low",
                "enable_thinking": False
            }
            with httpx.Client(timeout=timeout) as client:
                r = client.post("https://api.openai.com/v1/chat/completions", headers=headers_oai, json=payload_oai)
                if r.status_code == 200:
                    choices = r.json().get("choices", [])
                    if choices:
                        return _clean_response(choices[0].get("message", {}).get("content", ""))
    except Exception as err:
        logger.error(f"Online VLM error: {err}")
    return ""

def _call_local_vlm(base64_img: str, prompt: str, system_prompt: str = "", timeout: float = 180.0) -> str:
    """Sends image + prompt to Local LM Studio VLM with thinking disabled."""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LM_STUDIO_API_KEY}"
    }
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_img}"}}
        ]
    })
    payload = {
        "model": VLM_MODEL_NAME,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 2048,
        "enable_thinking": False,
        "chat_template_kwargs": {"enable_thinking": False},
        "reasoning_effort": "low"
    }
    try:
        url = f"{LM_STUDIO_API_URL.rstrip('/')}/chat/completions"
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices", [])
                if choices:
                    return _clean_response(choices[0].get("message", {}).get("content", ""))
    except Exception:
        pass
    return ""

def call_vlm(
    image_path: str | Path,
    prompt: str,
    system_prompt: str = "",
    model_name: Optional[str] = None,
    timeout: float = 180.0
) -> str:
    """
    Unified VLM caller that honors AI_MODE (online_only, auto, local_only).
    """
    path_obj = Path(image_path)
    if not path_obj.exists():
        logger.error(f"Image not found for VLM: {image_path}")
        return ""

    base64_img = encode_image(path_obj)

    # 1. Online Only Mode
    if AI_MODE == "online_only":
        res = _call_online_vlm(base64_img, prompt, system_prompt, timeout=timeout)
        if res:
            return res
        return _call_local_vlm(base64_img, prompt, system_prompt, timeout=timeout)

    # 2. Local Only Mode
    elif AI_MODE == "local_only":
        return _call_local_vlm(base64_img, prompt, system_prompt, timeout=timeout)

    # 3. Auto Mode (Local with Online Fallback)
    else:
        res = _call_local_vlm(base64_img, prompt, system_prompt, timeout=4.0)
        if res:
            return res
        return _call_online_vlm(base64_img, prompt, system_prompt, timeout=timeout)

def parse_table_image(image_path: str | Path) -> str:
    """Converts a cropped table image into clean Markdown table using VLM without thinking tokens."""
    prompt = (
        "Convert the table in this image into a clean GitHub-flavored Markdown table. "
        "Preserve column headers and all cell data accurately. "
        "Output directly without detailed chain-of-thought or reasoning tokens. "
        "Output only the markdown table (| col1 | col2 |) without extra explanation or tags."
    )
    res = call_vlm(image_path, prompt)
    clean = res.replace("```markdown", "").replace("```", "").strip()
    return clean

def parse_chart_image(image_path: str | Path) -> str:
    """Analyzes a cropped chart/figure image and generates a structured data summary without thinking tokens."""
    prompt = (
        "Analyze this scientific chart or visualization. Extract the title, axis labels, legends, "
        "and summarize the key data trends and numbers in concise Markdown bullet points. "
        "Output directly without detailed chain-of-thought or reasoning tokens."
    )
    return call_vlm(image_path, prompt)

def parse_math_image(image_path: str | Path) -> str:
    """Converts a difficult math formula crop into standard LaTeX code without thinking tokens."""
    prompt = (
        "Convert the mathematical formula in this image into precise standard LaTeX format. "
        "Output directly without detailed chain-of-thought or reasoning tokens. "
        "Output only the LaTeX expression (e.g. \\frac{a}{b}, \\sum_{i=1}^n x_i) inside $$...$$."
    )
    res = call_vlm(image_path, prompt)
    clean = res.replace("```latex", "").replace("```", "").strip()
    return clean

def refine_markdown(markdown_text: str) -> str:
    """Refines grammar, spacing, and cohesion of final assembled Markdown using LLM text model."""
    prompt = (
        "You are an expert academic paper editor. Refine and polish the following Markdown document. "
        "Ensure all LaTeX equations ($...$ and $$...$$), tables, and headings are properly formatted and coherent. "
        "Output directly without detailed chain-of-thought. "
        "Do NOT remove or alter mathematical formulas.\n\n"
        f"{markdown_text}"
    )
    if AI_MODE == "online_only" and ONLINE_API_KEY:
        try:
            from app.ai.online import OnlineProvider
            p = OnlineProvider(provider=ONLINE_PROVIDER, api_key=ONLINE_API_KEY, model_name=ONLINE_MODEL, timeout=180.0)
            return p.complete(prompt=markdown_text, system_prompt="Refine academic markdown directly without altering math equations.")
        except Exception:
            pass
    return markdown_text
