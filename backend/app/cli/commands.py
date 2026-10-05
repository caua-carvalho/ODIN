from __future__ import annotations

from rich.console import Console
from rich.table import Table

from app.config import settings


# ODIN theme
ODIN_ORANGE = "#FF6A00"
ODIN_BLACK = "#0A0A0A"
ODIN_DARK = "#111111"
ODIN_GRAY = "#737373"
ODIN_WHITE = "#F5F5F5"


class CommandHandler:
    """Handles local CLI commands."""

    def __init__(self, console: Console) -> None:
        self.console = console

    def execute(self, command: str) -> str | None:
        command = command.strip().lower()

        if command == "/help":
            self.help()
            return "continue"

        if command == "/clear":
            self.console.clear()
            return "continue"

        if command == "/status":
            self.status()
            return "continue"

        if command == "/model":
            self.model()
            return "continue"

        if command == "/workspace":
            self.workspace()
            return "continue"

        if command == "/tools":
            self.tools()
            return "continue"

        if command in {"/exit", "/quit", "/q"}:
            return "exit"

        return None

    def help(self) -> None:
        table = Table(
            title="ODIN Commands",
            show_header=True,
            header_style=f"bold {ODIN_ORANGE}",
            border_style=ODIN_DARK,
        )

        table.add_column(
            "Command",
            style=f"bold {ODIN_ORANGE}",
        )

        table.add_column(
            "Description",
            style=ODIN_WHITE,
        )

        commands = [
            ("/help", "Show available commands"),
            ("/clear", "Clear terminal"),
            ("/status", "Show backend status"),
            ("/model", "Show current model"),
            ("/workspace", "Show current workspace"),
            ("/tools", "Show available tools"),
            ("/exit", "Exit Odin"),
        ]

        for command, description in commands:
            table.add_row(command, description)

        self.console.print()
        self.console.print(table)
        self.console.print()

    def status(self) -> None:
        self.console.print()

        self.console.print(
            f"[green]●[/green] Backend configured"
        )

        self.console.print(
            f"  [{ODIN_GRAY}]Host:[/{ODIN_GRAY}] "
            f"{settings.odin_host}:{settings.odin_port}"
        )

        self.console.print()

    def model(self) -> None:
        self.console.print()

        self.console.print(
            f"[{ODIN_ORANGE}]Model:[/{ODIN_ORANGE}] "
            f"{settings.odin_model}"
        )

        self.console.print(
            f"[{ODIN_ORANGE}]Provider:[/{ODIN_ORANGE}] "
            f"{settings.odin_model_provider}"
        )

        self.console.print()

    def workspace(self) -> None:
        self.console.print()

        self.console.print(
            f"[{ODIN_ORANGE}]Workspace:[/{ODIN_ORANGE}] "
            f"{settings.workspace_path}"
        )

        self.console.print()

    def tools(self) -> None:
        self.console.print()

        self.console.print(
            f"[{ODIN_GRAY}]Tool registry is managed by the "
            f"Odin backend.[/{ODIN_GRAY}]"
        )

        self.console.print()
