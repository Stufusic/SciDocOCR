"""Settings manager for SciDoc OCR with automatic .env synchronization."""

from __future__ import annotations
import os
import json
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Dict, Any, Optional
from app.utils.paths import get_app_dir

def find_env_file() -> Path:
    """Finds or defines the primary .env file path for the project."""
    # 1. Project root (parent of app directory)
    project_root = Path(__file__).resolve().parent.parent.parent
    env_in_root = project_root / ".env"
    if env_in_root.parent.exists():
        return env_in_root

    # 2. Fallback to current working directory or app directory
    cwd_env = Path.cwd() / ".env"
    return cwd_env

def load_env_file(env_path: Path) -> Dict[str, str]:
    """Reads key-value pairs from a .env file."""
    env_vars: Dict[str, str] = {}
    if not env_path.exists():
        return env_vars

    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k and v:
                    env_vars[k] = v
                    os.environ[k] = v
    except Exception:
        pass

    return env_vars

def write_env_file(env_path: Path, settings: AppSettings) -> None:
    """Writes / updates the .env file with all provider API keys and active configuration."""
    try:
        env_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# ========================================================",
            "# SciDoc OCR Environment Configuration & API Keys",
            "# ========================================================",
            f"OPENAI_API_KEY={settings.provider_keys.get('openai', '')}",
            f"GOOGLE_API_KEY={settings.provider_keys.get('google', '')}",
            f"GEMINI_API_KEY={settings.provider_keys.get('google', '')}",
            f"ANTHROPIC_API_KEY={settings.provider_keys.get('anthropic', '')}",
            f"OPENROUTER_API_KEY={settings.provider_keys.get('opencode', '')}",
            "",
            "# Active Online Provider & Model",
            f"ONLINE_PROVIDER={settings.online_provider}",
            f"ONLINE_MODEL={settings.online_model}",
            f"ONLINE_API_URL={settings.online_api_url}",
            f"ONLINE_API_KEY={settings.online_api_key}",
            "",
            "# LM Studio Offline Engine",
            f"LMSTUDIO_URL={settings.lmstudio_url}",
            f"LMSTUDIO_MODEL={settings.lmstudio_model}",
            f"AI_MODE={settings.ai_mode}",
            "# MinerU Engine",
            f"MINERU_METHOD={getattr(settings, 'mineru_method', 'auto')}",
            f"MINERU_CLI_PATH={getattr(settings, 'mineru_cli_path', 'magic-pdf')}",
            "",
            "# Languages & Document Settings",
            f"SOURCE_LANGUAGE={settings.source_language}",
            f"TARGET_LANGUAGE={settings.target_language}",
            f"LATEX_COMPILER={settings.latex_compiler}",
            f"OCR_DPI={settings.ocr_dpi}",
            f"CONFIDENCE_THRESHOLD={settings.confidence_threshold}",
            ""
        ]
        with open(env_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception:
        pass

@dataclass
class AppSettings:
    theme: str = "dark"  # dark / light
    ai_mode: str = "auto"  # auto, local_only, mineru, online_only
    lmstudio_url: str = "http://127.0.0.1:1234/v1"
    lmstudio_model: str = "local-model"

    # MinerU Configuration
    mineru_server_url: str = "http://127.0.0.1:8000"
    mineru_method: str = "auto"  # "auto", "ocr", "txt"
    mineru_cli_path: str = "magic-pdf"

    # Active Online Provider: "openai", "google", "anthropic", "opencode", "custom"
    online_provider: str = "openai"
    online_api_url: str = "https://api.openai.com/v1"
    online_api_key: str = ""
    online_model: str = "gpt-4o-mini"

    # Per-provider keys, URLs, and models to preserve settings when switching
    provider_keys: Dict[str, str] = field(default_factory=lambda: {
        "openai": "",
        "google": "",
        "anthropic": "",
        "opencode": "",
        "custom": ""
    })
    provider_urls: Dict[str, str] = field(default_factory=lambda: {
        "openai": "https://api.openai.com/v1",
        "google": "https://generativelanguage.googleapis.com/v1beta/openai",
        "anthropic": "https://api.anthropic.com/v1",
        "opencode": "https://openrouter.ai/api/v1",
        "custom": "https://api.openai.com/v1"
    })
    provider_models: Dict[str, str] = field(default_factory=lambda: {
        "openai": "gpt-4o-mini",
        "google": "gemini-3.5-flash",
        "anthropic": "claude-3-7-sonnet-20250219",
        "opencode": "deepseek/deepseek-chat",
        "custom": "gpt-4o-mini"
    })

    source_language: str = "en"
    target_language: str = "vi"
    translation_engine: str = "google_translate"  # "google_translate" or "ai_llm"
    ocr_dpi: int = 400
    confidence_threshold: float = 0.85
    latex_compiler: str = "xelatex"
    auto_save_interval_sec: int = 30

class SettingsManager:
    """Manages application settings persistence with automatic .env and settings.json synchronization."""

    def __init__(self, config_path: Optional[str] = None, env_path: Optional[str] = None):
        self.path = Path(config_path) if config_path else get_app_dir() / "settings.json"
        self.global_path = Path.home() / ".scidoc" / "settings.json"
        self.env_path = Path(env_path) if env_path else find_env_file()
        self.settings = self.load_settings()

    def load_settings(self) -> AppSettings:
        # 1. Load from local settings.json or global home settings.json
        data: Dict[str, Any] = {}
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        elif self.global_path.exists():
            try:
                with open(self.global_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}

        defaults = AppSettings()
        if "provider_keys" not in data:
            data["provider_keys"] = {
                "openai": data.get("online_api_key", ""),
                "google": "",
                "anthropic": "",
                "opencode": "",
                "custom": ""
            }
        else:
            for p in defaults.provider_keys.keys():
                if p not in data["provider_keys"]:
                    data["provider_keys"][p] = ""
        if "provider_urls" not in data:
            data["provider_urls"] = dict(defaults.provider_urls)
        else:
            for p, def_url in defaults.provider_urls.items():
                if not data["provider_urls"].get(p):
                    data["provider_urls"][p] = def_url

        if "provider_models" not in data:
            data["provider_models"] = dict(defaults.provider_models)
        else:
            for p, def_m in defaults.provider_models.items():
                if not data["provider_models"].get(p):
                    data["provider_models"][p] = def_m

        if "online_provider" not in data:
            data["online_provider"] = "openai"

        # Check global path if local had empty keys
        if self.global_path.exists():
            try:
                with open(self.global_path, "r", encoding="utf-8") as f:
                    g_data = json.load(f)
                    g_keys = g_data.get("provider_keys", {})
                    for p, k in g_keys.items():
                        if k and not data["provider_keys"].get(p):
                            data["provider_keys"][p] = k
            except Exception:
                pass

        # 2. Read from .env and environment variables
        env_vars = load_env_file(self.env_path)

        # Merge environment variables (only if non-empty)
        openai_k = env_vars.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if openai_k and not data["provider_keys"].get("openai"):
            data["provider_keys"]["openai"] = openai_k

        google_k = env_vars.get("GOOGLE_API_KEY") or env_vars.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if google_k and not data["provider_keys"].get("google"):
            data["provider_keys"]["google"] = google_k

        anthropic_k = env_vars.get("ANTHROPIC_API_KEY") or env_vars.get("CLAUDE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY")
        if anthropic_k and not data["provider_keys"].get("anthropic"):
            data["provider_keys"]["anthropic"] = anthropic_k

        opencode_k = env_vars.get("OPENROUTER_API_KEY") or env_vars.get("OPENCODE_API_KEY") or os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENCODE_API_KEY")
        if opencode_k and not data["provider_keys"].get("opencode"):
            data["provider_keys"]["opencode"] = opencode_k

        if "ONLINE_PROVIDER" in env_vars and env_vars["ONLINE_PROVIDER"]:
            data["online_provider"] = env_vars["ONLINE_PROVIDER"]
        if "ONLINE_MODEL" in env_vars and env_vars["ONLINE_MODEL"]:
            data["online_model"] = env_vars["ONLINE_MODEL"]
        if "ONLINE_API_URL" in env_vars and env_vars["ONLINE_API_URL"]:
            data["online_api_url"] = env_vars["ONLINE_API_URL"]
        if "ONLINE_API_KEY" in env_vars and env_vars["ONLINE_API_KEY"]:
            data["online_api_key"] = env_vars["ONLINE_API_KEY"]
            if data["online_provider"] in data.get("provider_keys", {}):
                data["provider_keys"][data["online_provider"]] = env_vars["ONLINE_API_KEY"]
        if "LMSTUDIO_URL" in env_vars and env_vars["LMSTUDIO_URL"]:
            data["lmstudio_url"] = env_vars["LMSTUDIO_URL"]
        if "LMSTUDIO_MODEL" in env_vars and env_vars["LMSTUDIO_MODEL"]:
            data["lmstudio_model"] = env_vars["LMSTUDIO_MODEL"]
        if "AI_MODE" in env_vars and env_vars["AI_MODE"]:
            data["ai_mode"] = env_vars["AI_MODE"]

        active_prov = data.get("online_provider", "openai")
        active_key = data["provider_keys"].get(active_prov, "") or data.get("online_api_key", "")
        if active_key:
            data["online_api_key"] = active_key
            if active_prov in data.get("provider_models", {}):
                data["online_model"] = data["provider_models"][active_prov]

        valid_fields = set(AppSettings.__dataclass_fields__.keys())
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        settings = AppSettings(**filtered_data)

        # Update environment variables in memory
        for prov, k in settings.provider_keys.items():
            if k:
                if prov == "openai": os.environ["OPENAI_API_KEY"] = k
                elif prov == "google":
                    os.environ["GOOGLE_API_KEY"] = k
                    os.environ["GEMINI_API_KEY"] = k
                elif prov == "anthropic": os.environ["ANTHROPIC_API_KEY"] = k
                elif prov == "opencode": os.environ["OPENROUTER_API_KEY"] = k

        return settings

    def save_settings(self, settings: Optional[AppSettings] = None) -> None:
        if settings is not None:
            self.settings = settings

        # Sync active provider key
        active_prov = self.settings.online_provider or "openai"
        if active_prov in self.settings.provider_keys:
            self.settings.online_api_key = self.settings.provider_keys[active_prov]

        # 1. Save to local settings.json
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(asdict(self.settings), f, indent=2, ensure_ascii=False)

        # 2. Save to global user-home settings.json (~/.scidoc/settings.json)
        try:
            self.global_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.global_path, "w", encoding="utf-8") as f:
                json.dump(asdict(self.settings), f, indent=2, ensure_ascii=False)
        except Exception:
            pass

        # 3. Save to .env file
        write_env_file(self.env_path, self.settings)

        # 4. Sync to active process environment
        for prov, k in self.settings.provider_keys.items():
            if k:
                if prov == "openai": os.environ["OPENAI_API_KEY"] = k
                elif prov == "google":
                    os.environ["GOOGLE_API_KEY"] = k
                    os.environ["GEMINI_API_KEY"] = k
                elif prov == "anthropic": os.environ["ANTHROPIC_API_KEY"] = k
                elif prov == "opencode": os.environ["OPENROUTER_API_KEY"] = k

    def get_settings(self) -> AppSettings:
        """Returns the current active AppSettings instance."""
        return self.settings
