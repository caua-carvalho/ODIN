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
            self.renderer.permission_request()

        elif event_type == "error":
            self.renderer.error(
                event.get("message", "Unknown error")
            )

        elif event_type == "done":
            self.renderer.done()


def main() -> None:
    asyncio.run(OdinCLI().run())


if __name__ == "__main__":
    main()