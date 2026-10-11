"""CLI config client tests.

Verifies the REST provider/model client used by the `/model` command:
response parsing, backend error-detail propagation and connection failures.
"""
import sys
from pathlib import Path

import httpx
import pytest

# Make sure we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.cli.client import OdinConfigClient, OdinConfigError


def _client(handler) -> OdinConfigClient:
    return OdinConfigClient(
        base_url="http://odin.test",
        transport=httpx.MockTransport(handler),
    )


class TestListProviders:
    async def test_returns_payload(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "GET"
            assert request.url.path == "/api/providers"
            return httpx.Response(
                200,
                json={
                    "providers": [
                        {
                            "id": "ollama",
                            "label": "Ollama (local)",
                            "description": "local",
                            "configured": True,
                            "models": ["qwen3:0.6b"],
                        }
                    ],
                    "active": {"provider": "ollama", "model": "qwen3:0.6b"},
                },
            )

        data = await _client(handler).list_providers()
        assert data["active"]["provider"] == "ollama"
        assert data["providers"][0]["models"] == ["qwen3:0.6b"]


class TestSelect:
    async def test_posts_selection(self):
        seen: dict = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            seen["method"] = request.method
            seen["path"] = request.url.path
            seen["body"] = request.content
            return httpx.Response(
                200, json={"provider": "ollama", "model": "llama3:8b"}
            )

        result = await _client(handler).select("ollama", "llama3:8b")

        assert seen["method"] == "POST"
        assert seen["path"] == "/api/providers/select"
        assert b"llama3:8b" in seen["body"]
        assert result == {"provider": "ollama", "model": "llama3:8b"}

    async def test_surfaces_backend_detail(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                400, json={"detail": "Provider 'gemini' is not configured"}
            )

        with pytest.raises(OdinConfigError, match="not configured"):
            await _client(handler).select("gemini", "gemini-2.5-flash")


class TestConnectionErrors:
    async def test_request_error_is_wrapped(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        with pytest.raises(OdinConfigError, match="alcançar o backend"):
            await _client(handler).get_health()
