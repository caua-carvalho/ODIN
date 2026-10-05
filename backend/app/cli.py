import asyncio
import json
import sys
import uuid

import websockets

from app.config import settings


class OdinCLI:
    """Interactive terminal client for Odin."""

    def __init__(self) -> None:
        self.conversation_id = str(uuid.uuid4())
        self.websocket_url = (
            f"ws://{settings.odin_host}:"
            f"{settings.odin_port}/api/ws/{self.conversation_id}"
        )

    async def run(self) -> None:
        self._print_banner()

        try:
            async with websockets.connect(self.websocket_url) as websocket:
                await self._session(websocket)
        except ConnectionRefusedError:
            self._print_error(
                "Não foi possível conectar ao backend.\n"
                f"Verifique se o Odin está rodando em "
                f"{settings.odin_host}:{settings.odin_port}."
            )
            sys.exit(1)
        except KeyboardInterrupt:
            print()
        except Exception as exc:
            self._print_error(f"Erro de conexão: {exc}")
            sys.exit(1)

    async def _session(self, websocket) -> None:
        while True:
            try:
                message = await asyncio.to_thread(self._read_input)
            except EOFError:
                print()
                return

            if not message:
                continue

            if message in {"/exit", "/quit", "/q"}:
                return

            if message == "/help":
                self._print_help()
                continue

            await websocket.send(
                json.dumps(
                    {
                        "type": "message",
                        "content": message,
                    }
                )
            )

            await self._receive_response(websocket)

    async def _receive_response(self, websocket) -> None:
        text_started = False

        while True:
            raw_message = await websocket.recv()
            event = json.loads(raw_message)

            event_type = event.get("type")

            if event_type == "status":
                if not text_started:
                    self._print_status(event.get("message", ""))

            elif event_type == "text_chunk":
                if not text_started:
                    print("Odin > ", end="", flush=True)
                    text_started = True

                print(event.get("content", ""), end="", flush=True)

            elif event_type == "tool_start":
                if text_started:
                    print()

                tool = event.get("tool", "unknown")
                print(f"[tool] {tool}")

            elif event_type == "tool_end":
                tool = event.get("tool", "unknown")
                success = event.get("success", False)

                status = "ok" if success else "erro"
                print(f"[tool] {tool}: {status}")

            elif event_type == "permission_request":
                if text_started:
                    print()

                print("[permission] Aprovação necessária.")

            elif event_type == "error":
                if text_started:
                    print()

                self._print_error(event.get("message", "Erro desconhecido"))

            elif event_type == "done":
                if text_started:
                    print()

                print()
                return

    @staticmethod
    def _read_input() -> str:
        try:
            return input("You > ").strip()
        except KeyboardInterrupt:
            print()
            return "/exit"

    @staticmethod
    def _print_banner() -> None:
        print()
        print("╭──────────────────────────────────────╮")
        print("│                 ODIN                 │")
        print("│          Personal AI Assistant       │")
        print("╰──────────────────────────────────────╯")
        print()
        print("Digite /help para ver os comandos.")
        print()

    @staticmethod
    def _print_help() -> None:
        print()
        print("Comandos:")
        print("  /help   Mostra esta ajuda")
        print("  /exit   Encerra o Odin")
        print("  /quit   Encerra o Odin")
        print("  /q      Encerra o Odin")
        print()

    @staticmethod
    def _print_status(message: str) -> None:
        if message:
            print(f"[odin] {message}")

    @staticmethod
    def _print_error(message: str) -> None:
        print(f"[erro] {message}")


def main() -> None:
    cli = OdinCLI()
    asyncio.run(cli.run())


if __name__ == "__main__":
    main()