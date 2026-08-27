"""Path management utilities."""

import os
from pathlib import Path

def get_app_dir() -> Path:
    """Returns the base application directory."""
    return Path(__file__).resolve().parent.parent.parent

def get_cache_dir() -> Path:
    """Returns the cache directory under user app data or local folder."""
    cache = get_app_dir() / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    return cache

def get_logs_dir() -> Path:
    """Returns logs directory."""
    logs = get_app_dir() / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    return logs

def get_assets_dir() -> Path:
    """Returns assets directory."""
    assets = get_app_dir() / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    return assets
