"""Tests for Multi-Provider Online AI, Model Fetcher, and .env synchronization."""

import pytest
from pathlib import Path
from app.ai.model_fetcher import fetch_available_models, FALLBACK_MODELS, DEFAULT_URLS
from app.ai.online import OnlineProvider
from app.storage.settings import AppSettings, SettingsManager, write_env_file, load_env_file

def test_model_fetcher_fallbacks():
    # When no key is provided, should return curated list
    openai_models = fetch_available_models("openai", "")
    assert "gpt-4o-mini" in openai_models
    assert "gpt-4o" in openai_models

    google_models = fetch_available_models("google", "")
    assert "gemini-3.1-flash-lite" in google_models
    assert "gemini-flash-latest" in google_models

    anthropic_models = fetch_available_models("anthropic", "")
    assert any("claude-3-7-sonnet" in m or "claude-3-5-sonnet" in m for m in anthropic_models)

    opencode_models = fetch_available_models("opencode", "")
    assert any("deepseek" in m for m in opencode_models)

def test_settings_multi_provider_persistence(tmp_path):
    config_file = tmp_path / "settings.json"
    env_file = tmp_path / ".env"
    manager = SettingsManager(str(config_file), env_path=str(env_file))

    s = manager.settings
    s.online_provider = "google"
    s.provider_keys["google"] = "AIzaSyTestKey123"
    s.provider_models["google"] = "gemini-2.0-flash"
    s.provider_keys["anthropic"] = "sk-ant-test-key-456"
    s.provider_models["anthropic"] = "claude-3-7-sonnet-20250219"

    manager.save_settings(s)

    # Reload
    loaded_manager = SettingsManager(str(config_file), env_path=str(env_file))
    loaded = loaded_manager.settings

    assert loaded.online_provider == "google"
    assert loaded.provider_keys["google"] == "AIzaSyTestKey123"
    assert loaded.provider_keys["anthropic"] == "sk-ant-test-key-456"
    assert loaded.provider_models["anthropic"] == "claude-3-7-sonnet-20250219"

def test_env_file_sync(tmp_path):
    env_file = tmp_path / ".env"
    settings = AppSettings(
        online_provider="google",
        online_model="gemini-2.0-flash",
        online_api_key="AIzaSyTestKey_ENV",
        provider_keys={"google": "AIzaSyTestKey_ENV", "openai": "sk-test-openai"}
    )
    write_env_file(env_file, settings)

    assert env_file.exists()
    loaded_vars = load_env_file(env_file)
    assert loaded_vars.get("GOOGLE_API_KEY") == "AIzaSyTestKey_ENV"
    assert loaded_vars.get("OPENAI_API_KEY") == "sk-test-openai"
    assert loaded_vars.get("ONLINE_PROVIDER") == "google"
    assert loaded_vars.get("ONLINE_MODEL") == "gemini-2.0-flash"

def test_online_provider_init():
    provider = OnlineProvider(
        provider="anthropic",
        api_key="test-key",
        base_url="https://api.anthropic.com/v1",
        model_name="claude-3-7-sonnet-20250219"
    )
    assert provider.provider == "anthropic"
    assert provider.model_name == "claude-3-7-sonnet-20250219"
