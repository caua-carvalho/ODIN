"""Tests for the interactive permission approval flow in the CLI.

Covers:
- permission answer parsing (never defaults to approval);
- the renderer showing all data from a permission_request event;
- the client sending decisions to the existing backend endpoints;
- the main event handler orchestration.
"""
import sys
from io import StringIO
from pathlib import Path

import httpx
import pytest
from rich.console import Console

# Make sure we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.cli.client import OdinClient
from app.cli.main import OdinCLI
from app.cli.prompt import parse_approval_answer
from app.cli.renderer import OdinRenderer


PERMISSION_EVENT = {
    "type": "permission_request",
    "id": "req-123",
    "tool": "execute_command",
    "operation": "EXECUTE",
    "target": "sudo systemctl restart nginx",
    "reason": "This operation requires user authorization.",
    "risk_level": "high",
    "arguments": {"command": "sudo systemctl restart nginx"},
}


class TestApprovalAnswerParsing:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("y", True),
            ("Y", True),
            ("yes", True),
            ("YES", True),
            ("  YeS  ", True),
            ("n", False),
            ("N", False),
            ("no", False),
            ("No", False),
            ("", None),
            ("   ", None),
            ("maybe", None),
            ("1", None),
            ("true", None),
            ("ye", None),
            ("nope", None),
            ("(y)", None),
        ],
    )
    def test_parse(self, raw, expected):
        assert parse_approval_answer(raw) is expected

    def test_ambiguous_input_never_approves(self):
        """Anything invalid must be None (re-prompt), never True."""
        for raw in ["", "huh", "yep", "sure", "1", "ok"]:
            result = parse_approval_answer(raw)
            assert result is not True


class TestRendererPermissionRequest:
    def _render(self, event: dict) -> str:
        out = StringIO()
        console = Console(file=out, width=110, force_terminal=False)
        OdinRenderer(console=console).permission_request(event)
        return out.getvalue()

    def test_renders_all_event_data(self):
        output = self._render(PERMISSION_EVENT)
        assert "execute_command" in output
        assert "EXECUTE" in output
        assert "HIGH" in output
        assert "sudo systemctl restart nginx" in output
        assert "This operation requires user authorization." in output
        assert "Approve" in output
        assert "Deny" in output

    def test_renders_filesystem_target(self):
        output = self._render(
            {
                "type": "permission_request",
                "id": "req-2",
                "tool": "write_file",
                "operation": "WRITE",
                "target": "/etc/hosts",
                "reason": "Outside workspace",
                "risk_level": "medium",
                "arguments": {"path": "/etc/hosts", "content": "..."},
            }
        )
        assert "write_file" in output
        assert "/etc/hosts" in output
        assert "Target:" in output

    def test_handles_missing_optional_fields(self):
        output = self._render({"type": "permission_request", "id": "req-3"})
        assert "unknown" in output
        assert "Approve" in output


class TestClientResolvePermission:
    def _client(self, handler) -> OdinClient:
        return OdinClient()

    async def test_approve_calls_approve_endpoint(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["method"] = request.method
            seen["url"] = str(request.url)
            return httpx.Response(200, json={"id": "req-1", "status": "approved"})

        client = self._client(handler)
        result = await client.resolve_permission(
            request_id="req-1",
            approved=True,
            transport=httpx.MockTransport(handler),
        )

        assert result is True
        assert seen["method"] == "POST"
        assert seen["url"].endswith("/api/permissions/req-1/approve")

    async def test_deny_calls_deny_endpoint(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            return httpx.Response(200, json={"id": "req-1", "status": "denied"})

        client = self._client(handler)
        result = await client.resolve_permission(
            request_id="req-1",
            approved=False,
            transport=httpx.MockTransport(handler),
        )

        assert result is False
        assert seen["url"].endswith("/api/permissions/req-1/deny")

    async def test_http_error_returns_none(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"detail": "Permission request not found"})

        result = await OdinClient().resolve_permission(
            request_id="missing",
            approved=True,
            transport=httpx.MockTransport(handler),
        )
        assert result is None

    async def test_expired_request_returns_none(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(410, json={"detail": "Permission request has expired"})

        result = await OdinClient().resolve_permission(
            request_id="old",
            approved=True,
            transport=httpx.MockTransport(handler),
        )
        assert result is None

    async def test_unexpected_body_returns_none(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"status": "pending"})

        result = await OdinClient().resolve_permission(
            request_id="req-1",
            approved=True,
            transport=httpx.MockTransport(handler),
        )
        assert result is None

    async def test_connection_error_returns_none(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom", request=request)

        result = await OdinClient().resolve_permission(
            request_id="req-1",
            approved=True,
            transport=httpx.MockTransport(handler),
        )
        assert result is None


class FakeRenderer:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def permission_request(self, event: dict) -> None:
        self.calls.append(("request", event))

    def permission_approved(self) -> None:
        self.calls.append(("approved",))

    def permission_denied(self) -> None:
        self.calls.append(("denied",))

    def permission_failed(self, detail: str | None = None) -> None:
        self.calls.append(("failed", detail))


class FakePrompt:
    def __init__(self, answer: bool) -> None:
        self.answer = answer
        self.asked = False

    async def ask_approval(self) -> bool:
        self.asked = True
        return self.answer


class FakeClient:
    def __init__(self, result) -> None:
        self.result = result
        self.calls: list[tuple] = []

    async def resolve_permission(self, request_id: str, approved: bool):
        self.calls.append((request_id, approved))
        return self.result


def _cli(renderer, prompt, client) -> OdinCLI:
    cli = OdinCLI.__new__(OdinCLI)
    cli.renderer = renderer
    cli.prompt = prompt
    cli.client = client
    return cli


class TestPermissionEventHandling:
    async def test_approved_flow_sends_decision_and_confirms(self):
        renderer, prompt, client = FakeRenderer(), FakePrompt(True), FakeClient(True)
        cli = _cli(renderer, prompt, client)

        await cli._handle_permission_request(PERMISSION_EVENT)

        assert prompt.asked is True
        # The original request_id and the user decision are preserved.
        assert client.calls == [("req-123", True)]
        assert renderer.calls[0] == ("request", PERMISSION_EVENT)
        assert ("approved",) in renderer.calls
        assert not any(c[0] == "failed" for c in renderer.calls)

    async def test_denied_flow(self):
        renderer, prompt, client = FakeRenderer(), FakePrompt(False), FakeClient(False)
        cli = _cli(renderer, prompt, client)

        await cli._handle_permission_request(PERMISSION_EVENT)

        assert client.calls == [("req-123", False)]
        assert ("denied",) in renderer.calls
        assert not any(c[0] == "approved" for c in renderer.calls)

    async def test_backend_failure_is_not_approved(self):
        renderer, prompt, client = FakeRenderer(), FakePrompt(True), FakeClient(None)
        cli = _cli(renderer, prompt, client)

        await cli._handle_permission_request(PERMISSION_EVENT)

        assert client.calls == [("req-123", True)]
        assert ("failed", None) in renderer.calls
        assert not any(c[0] == "approved" for c in renderer.calls)

    async def test_missing_request_id_fails_without_calling_backend(self):
        renderer, prompt, client = FakeRenderer(), FakePrompt(True), FakeClient(True)
        cli = _cli(renderer, prompt, client)

        await cli._handle_permission_request({"type": "permission_request"})

        assert client.calls == []
        assert any(c[0] == "failed" for c in renderer.calls)

    async def test_prompt_error_denies(self):
        class BrokenPrompt:
            async def ask_approval(self) -> bool:
                raise RuntimeError("tty broke")

        renderer, client = FakeRenderer(), FakeClient(False)
        cli = _cli(renderer, BrokenPrompt(), client)

        await cli._handle_permission_request(PERMISSION_EVENT)

        assert client.calls == [("req-123", False)]
        assert ("denied",) in renderer.calls
