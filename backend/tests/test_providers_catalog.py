"""Provider catalog + runtime selection tests.

Covers the metadata/availability rules, model discovery parsing/merging and the
active-selection holder that powers /api/providers and the /model CLI command.
"""
import sys
from pathlib import Path

import pytest

# Make sure we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agent.providers import catalog
from app.config import Settings


@pytest.fixture(autouse=True)
def _reset_active():
    """Keep the process-wide active selection from leaking between tests."""
    previous = catalog.get_active()
    yield
    if previous is not None:
        catalog.set_active(previous.provider, previous.model)


class TestOllamaTags:
    def test_parse_names(self):
        data = {
            "models": [
                {"name": "qwen3:0.6b"},
                {"model": "llama3:8b"},
                {"name": "qwen2.5-coder:7b"},
            ]
        }
        assert catalog.parse_ollama_tags(data) == [
            "qwen3:0.6b",
            "llama3:8b",
            "qwen2.5-coder:7b",
        ]

    def test_ignores_malformed_entries(self):
        assert catalog.parse_ollama_tags({"models": [None, {}, {"name": ""}]}) == []

    def test_missing_models_key(self):
        assert catalog.parse_ollama_tags({}) == []


class TestAvailability:
    def test_gemini_requires_api_key(self):
        meta = catalog.PROVIDERS["gemini"]
        assert catalog.is_configured(meta, Settings(gemini_api_key="", _env_file=None)) is False
        assert catalog.is_configured(meta, Settings(gemini_api_key="k", _env_file=None)) is True

    def test_ollama_needs_no_key(self):
        meta = catalog.PROVIDERS["ollama"]
        assert catalog.is_configured(meta, Settings(_env_file=None)) is True


class TestActiveSelection:
    def test_roundtrip_and_normalization(self):
        active = catalog.set_active("  GEMINI ", "gemini-2.5-flash")
        assert active.provider == "gemini"
        assert active.model == "gemini-2.5-flash"
        assert catalog.get_active() is active

    def test_as_dict(self):
        assert catalog.set_active("ollama", "qwen3:0.6b").as_dict() == {
            "provider": "ollama",
            "model": "qwen3:0.6b",
        }


class TestListModels:
    async def test_unknown_provider_is_empty(self):
        assert await catalog.list_models("does-not-exist") == []

    async def test_gemini_without_key_falls_back(self, monkeypatch):
        async def _no_discovery(_config):
            return []

        monkeypatch.setattr(catalog, "_discover_gemini_models", _no_discovery)
        config = Settings(
            odin_model_provider="gemini",
            odin_model="gemini-2.5-flash",
            gemini_api_key="",
            _env_file=None,
        )
        models = await catalog.list_models("gemini", config)
        assert "gemini-2.5-flash" in models
        assert "gemini-2.5-pro" in models

    async def test_merges_discovered_active_and_config(self, monkeypatch):
        async def _discovery(_config):
            return ["model-a", "model-b"]

        monkeypatch.setattr(catalog, "_discover_gemini_models", _discovery)
        catalog.set_active("gemini", "active-model")
        config = Settings(
            odin_model_provider="gemini",
            odin_model="config-model",
            gemini_api_key="k",
            _env_file=None,
        )
        models = await catalog.list_models("gemini", config)
        # Discovered first, then the pinned active/config models, then fallbacks.
        assert models[:4] == ["model-a", "model-b", "active-model", "config-model"]

    async def test_deduplicates(self, monkeypatch):
        async def _discovery(_config):
            return ["dup", "dup"]

        monkeypatch.setattr(catalog, "_discover_ollama_models", _discovery)
        config = Settings(
            odin_model_provider="ollama",
            odin_model="dup",
            _env_file=None,
        )
        models = await catalog.list_models("ollama", config)
        assert models.count("dup") == 1
