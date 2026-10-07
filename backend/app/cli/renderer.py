from __future__ import annotations

import json

from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text


ODIN_ORANGE = "#FF6A00"
ODIN_BLACK = "#0A0A0A"
ODIN_DARK = "#111111"
ODIN_GRAY = "#737373"
ODIN_WHITE = "#F5F5F5"

# Border/emphasis color per risk level (unknown risk → orange).
RISK_STYLES = {
    "high": "red",
    "medium": "yellow",
    "low": "green",
}


class OdinRenderer:
    """Terminal renderer for Odin."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()
        self.response_buffer: list[str] = []

    def banner(self) -> None:
        self.console.print()

        title = Text()
        title.append("◉ ", style=f"bold {ODIN_ORANGE}")
        title.append("ODIN", style=f"bold {ODIN_WHITE}")
        title.append("  ", style="dim")
        title.append("v0.1.0", style=f"dim {ODIN_GRAY}")

        subtitle = Text(
            "Personal AI Agent",
            style=f"dim {ODIN_GRAY}",
        )

        self.console.print(
            Panel(
                Group(title, subtitle),
                border_style=ODIN_ORANGE,
                padding=(0, 2),
            )
        )

        self.console.print(
            f"Digite [{ODIN_ORANGE}]/help[/{ODIN_ORANGE}] para comandos.",
            style=f"dim {ODIN_GRAY}",
        )
        self.console.print()

    def thinking(self, message: str = "Thinking...") -> None:
        self.console.print(
            f"[{ODIN_ORANGE}]●[/{ODIN_ORANGE}] {message}",
            style=f"dim {ODIN_GRAY}",
        )

    def tool_start(self, tool: str) -> None:
        self.console.print(
            f"  [{ODIN_ORANGE}]├─[/{ODIN_ORANGE}] "
            f"[bold {ODIN_WHITE}]{tool}[/bold {ODIN_WHITE}]",
            style=f"dim {ODIN_GRAY}",
        )

    def tool_end(self, tool: str, success: bool) -> None:
        if success:
            self.console.print(
                f"  [green]✓[/green] {tool}",
                style=f"dim {ODIN_GRAY}",
            )
        else:
            self.console.print(
                f"  [red]✗[/red] {tool}",
                style=f"dim {ODIN_GRAY}",
            )

    def permission_request(self, event: dict) -> None:
        """Render a full permission request received from the backend."""
        self.console.print()

        tool = str(event.get("tool") or "unknown")
        operation = str(event.get("operation") or "-")
        risk = str(event.get("risk_level") or "-")
        reason = str(event.get("reason") or "").strip()
        target = str(event.get("target") or "").strip()
        arguments = event.get("arguments")

        if not target and isinstance(arguments, dict) and arguments:
            target = json.dumps(arguments, ensure_ascii=False)

        risk_style = RISK_STYLES.get(risk.lower(), ODIN_ORANGE)

        body = Text()
        body.append("Tool:       ", style=f"dim {ODIN_GRAY}")
        body.append(tool, style=f"bold {ODIN_WHITE}")
        body.append("\n")
        body.append("Operation:  ", style=f"dim {ODIN_GRAY}")
        body.append(operation, style=f"bold {ODIN_WHITE}")
        body.append("\n")
        body.append("Risk:       ", style=f"dim {ODIN_GRAY}")
        body.append(risk.upper(), style=f"bold {risk_style}")

        if target:
            target_label = (
                "Command:"
                if isinstance(arguments, dict) and "command" in arguments
                else "Target:"
            )
            body.append("\n\n")
            body.append(f"{target_label}\n", style=f"dim {ODIN_GRAY}")
            body.append(target, style=ODIN_WHITE)

        if reason:
            body.append("\n\n")
            body.append("Reason:\n", style=f"dim {ODIN_GRAY}")
            body.append(reason, style=ODIN_WHITE)

        body.append("\n\n")
        body.append("[Y] ", style="bold green")
        body.append("Approve", style="green")
        body.append("    ", style=ODIN_GRAY)
        body.append("[N] ", style="bold red")
        body.append("Deny", style="red")

        self.console.print(
            Panel(
                body,
                title="Permission Required",
                title_align="left",
                border_style=risk_style,
                padding=(0, 2),
            )
        )

    def permission_approved(self) -> None:
        """Render a backend-confirmed approval."""
        self.console.print(
            f"  [green]✓[/green] Permission approved "
            f"[dim](confirmed by backend)[/dim]",
            style=f"dim {ODIN_GRAY}",
        )
        self.console.print()

    def permission_denied(self) -> None:
        """Render a backend-confirmed denial."""
        self.console.print(
            "  [red]✗[/red] Permission denied",
            style=f"dim {ODIN_GRAY}",
        )
        self.console.print()

    def permission_failed(self, detail: str | None = None) -> None:
        """Render a decision that the backend did NOT confirm.

        The operation must be treated as not approved.
        """
        message = (
            "The backend did not confirm the decision. "
            "The operation was NOT approved."
        )
        if detail:
            message = f"{message}\n\n{detail}"

        self.console.print()
        self.console.print(
            Panel(
                Text(message, style="red"),
                title="Permission Error",
                title_align="left",
                border_style="red",
                padding=(0, 2),
            )
        )
        self.console.print()

    def append_text(self, content: str) -> None:
        self.response_buffer.append(content)

    def render_response(self) -> None:
        if not self.response_buffer:
            return

        content = "".join(self.response_buffer).strip()
        self.response_buffer.clear()

        if not content:
            return

        self.console.print()

        self.console.print(
            Panel(
                Markdown(content),
                border_style=ODIN_DARK,
                padding=(0, 2),
            )
        )

        self.console.print()

    def error(self, message: str) -> None:
        self.response_buffer.clear()

        self.console.print()

        self.console.print(
            Panel(
                Text(
                    message,
                    style="red",
                ),
                title="Error",
                border_style="red",
                padding=(0, 2),
            )
        )

        self.console.print()

    def status(self, message: str) -> None:
        self.console.print(
            f"[{ODIN_ORANGE}]●[/{ODIN_ORANGE}] {message}",
            style=f"dim {ODIN_GRAY}",
        )

    def done(self) -> None:
        self.render_response()

    def goodbye(self) -> None:
        self.console.print()

        self.console.print(
            "Até mais.",
            style=f"dim {ODIN_GRAY}",
        )

        self.console.print()
