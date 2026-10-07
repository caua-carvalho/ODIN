from __future__ import annotations

import asyncio

from rich.console import Console

from app.cli.client import OdinClient
from app.cli.commands import CommandHandler
from app.cli.prompt import OdinPrompt
from app.cli.renderer import OdinRenderer


class OdinCLI:
    """Interactive Odin terminal application."""

    def __init__(self) -> None:
        self.renderer = OdinRenderer()
        self.prompt = OdinPrompt()
        self.console = Console()
        self.commands = CommandHandler(self.console)
        self.client = OdinClient()

    async def run(self) -> None:
        self.renderer.banner()

        try:
            async with await self.client.connect() as websocket:
                await self._session(websocket)

        except ConnectionRefusedError:
            self.renderer.error(
                "Não foi possível conectar ao backend.\n\n"
                "Verifique se o Odin está rodando em "
                "127.0.0.1:8000."
            )

        except KeyboardInterrupt:
            self.renderer.goodbye()

        except Exception as exc:
            self.renderer.error(str(exc))

    async def _session(self, websocket) -> None:
        while True:
            try:
                message = await self.prompt.ask()

            except (EOFError, KeyboardInterrupt):
                self.renderer.goodbye()
                return

            message = message.strip()

            if not message:
                continue

            command_result = self.commands.execute(message)

            if command_result == "exit":
                self.renderer.goodbye()
                return

            if command_result == "continue":
                continue

            await self._send_message(websocket, message)

    async def _send_message(self, websocket, message: str) -> None:
        async for event in self.client.send_message(
            websocket,
            message,
        ):
            await self._handle_event(event)

    async def _handle_event(self, event: dict) -> None:
        event_type = event.get("type")

        if event_type == "status":
            self.renderer.status(
                event.get("message", "Thinking...")
            )

        elif event_type == "text_chunk":
            self.renderer.append_text(
                event.get("content", "")
            )

        elif event_type == "tool_start":
            self.renderer.tool_start(
                event.get("tool", "unknown")
            )

        elif event_type == "tool_end":
            self.renderer.tool_end(
                event.get("tool", "unknown"),
                event.get("success", False),
            )

        elif event_type == "permission_request":
            await self._handle_permission_request(event)

        elif event_type == "permission_resolved":
            # Broadcast by the backend whenever any client (this CLI, the
            # web frontend, or a timeout) resolves a request. Our own
            # decision is already rendered after the HTTP call confirms
            # it, so there is nothing extra to display here.
            pass

        elif event_type == "error":
            self.renderer.error(
                event.get("message", "Unknown error")
            )

        elif event_type == "done":
            self.renderer.done()

    async def _handle_permission_request(self, event: dict) -> None:
        """Interactive approval flow for a permission_request event.

        Renders the operation, asks the user for a decision and forwards
        it to the backend, which resolves the agent's pending future.
        The flow blocks only while waiting for input (async prompt), so
        the event loop and the WebSocket stay alive.
        """
        request_id = event.get("id")

        if not request_id:
            # Without the original id the decision cannot reach the
            # backend: treat the operation as NOT approved.
            self.renderer.permission_request(event)
            self.renderer.permission_failed(
                "Event has no request id."
            )
            return

        self.renderer.permission_request(event)

        # Capture the decision (invalid input re-prompts, interrupt
        # denies - this can never approve by accident).
        try:
            approved = await self.prompt.ask_approval()
        except Exception:  # defensive: input failure must deny, not approve
            approved = False

        # Send the decision to the backend. `confirmed` is True only
        # when the backend acknowledged the approval; None means the
        # communication failed and the operation is not approved.
        try:
            confirmed = await self.client.resolve_permission(
                request_id=request_id,
                approved=approved,
            )
        except Exception as exc:  # defensive: never ignore failures
            self.renderer.permission_failed(str(exc))
            return

        if confirmed is None:
            self.renderer.permission_failed()
        elif confirmed:
            self.renderer.permission_approved()
        else:
            self.renderer.permission_denied()


def main() -> None:
    asyncio.run(OdinCLI().run())


if __name__ == "__main__":
    main()