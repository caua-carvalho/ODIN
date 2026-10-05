from __future__ import annotations

from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text


ODIN_ORANGE = "#FF6A00"
ODIN_BLACK = "#0A0A0A"
ODIN_DARK = "#111111"
ODIN_GRAY = "#737373"
ODIN_WHITE = "#F5F5F5"


class OdinRenderer:
    """Terminal renderer for Odin."""

    def __init__(self) -> None:
        self.console = Console()
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

    def permission_request(self) -> None:
        self.console.print()

        self.console.print(
            Panel(
                "[yellow]Permission required[/yellow]\n\n"
                "Odin requested an operation that requires approval.",
                border_style="yellow",
                padding=(1, 2),
            )
        )

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
