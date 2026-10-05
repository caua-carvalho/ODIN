from __future__ import annotations

from pathlib import Path

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory
from prompt_toolkit.shortcuts import PromptSession
from prompt_toolkit.styles import Style


# ─────────────────────────────────────────────
# ODIN Theme
# ─────────────────────────────────────────────

ODIN_ORANGE = "#FF6A00"
ODIN_BLACK = "#0A0A0A"
ODIN_DARK = "#111111"
ODIN_GRAY = "#737373"
ODIN_WHITE = "#F5F5F5"


COMMANDS = {
    "/help": "Show available commands",
    "/clear": "Clear the terminal",
    "/status": "Show Odin connection status",
    "/model": "Show current LLM model",
    "/workspace": "Show current workspace",
    "/tools": "Show available tools",
    "/exit": "Exit Odin",
    "/quit": "Exit Odin",
}


class OdinCompleter(Completer):
    """Autocomplete Odin slash commands."""

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor

        if not text.startswith("/"):
            return

        for command, description in COMMANDS.items():
            if command.startswith(text):
                yield Completion(
                    command,
                    start_position=-len(text),
                    display=command,
                    display_meta=description,
                )


class OdinPrompt:
    """Interactive terminal input."""

    def __init__(self) -> None:
        style = Style.from_dict(
            {
                # Input
                "prompt": f"bold {ODIN_ORANGE}",

                # Bottom status bar
                "bottom-toolbar": (
                    f"bg:{ODIN_BLACK} {ODIN_GRAY}"
                ),

                # Autocomplete
                "completion-menu.completion": (
                    f"bg:{ODIN_DARK} {ODIN_WHITE}"
                ),
                "completion-menu.completion.current": (
                    f"bg:{ODIN_ORANGE} {ODIN_BLACK}"
                ),
                "completion-menu.meta.completion": (
                    f"bg:{ODIN_DARK} {ODIN_GRAY}"
                ),
                "completion-menu.meta.completion.current": (
                    f"bg:{ODIN_ORANGE} {ODIN_BLACK}"
                ),
            }
        )

        history_file = Path.home() / ".odin_history"
        history = FileHistory(str(history_file))

        self.session = PromptSession(
            history=history,
            completer=OdinCompleter(),
            complete_while_typing=True,
            style=style,
            bottom_toolbar=self._toolbar,
        )

    def _toolbar(self) -> str:
        return (
            " Enter enviar  •  "
            "↑↓ histórico  •  "
            "Tab autocomplete  •  "
            "/help comandos"
        )

    async def ask(self) -> str:
        return await self.session.prompt_async(
            [
                ("class:prompt", "❯ "),
            ],
        )
