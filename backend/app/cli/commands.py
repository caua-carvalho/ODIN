from __future__ import annotations

import sys

from rich.console import Console
from rich.table import Table

from app.cli.client import OdinConfigClient, OdinConfigError
from app.config import settings


# ODIN theme
ODIN_ORANGE = "#FF6A00"
ODIN_BLACK = "#0A0A0A"
ODIN_DARK = "#111111"
ODIN_GRAY = "#737373"
ODIN_WHITE = "#F5F5F5"


class CommandHandler:
    """Handles local CLI commands."""

    def __init__(
        self,
        console: Console,
        config_client: OdinConfigClient | None = None,
    ) -> None:
        self.console = console
        self.config = config_client or OdinConfigClient()

    async def execute(self, command: str) -> str | None:
        command = command.strip()
        lowered = command.lower()

        if lowered == "/help":
            self.help()
            return "continue"

        if lowered == "/clear":
            self.console.clear()
            return "continue"

        if lowered == "/status":
            await self.status()
            return "continue"

        if lowered.startswith("/model") or lowered.startswith("/models"):
            await self.model_command(command)
            return "continue"

        if lowered == "/workspace":
            self.workspace()
            return "continue"

        if lowered == "/tools":
            self.tools()
            return "continue"

        if lowered in {"/exit", "/quit", "/q"}:
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
            ("/model", "Show or change the active model"),
            ("/models", "List available models"),
            ("/workspace", "Show current workspace"),
            ("/tools", "Show available tools"),
            ("/exit", "Exit Odin"),
        ]

        for command, description in commands:
            table.add_row(command, description)

        self.console.print()
        self.console.print(table)
        self.console.print()

    async def status(self) -> None:
        self.console.print()

        try:
            health = await self.config.get_health()
        except OdinConfigError as exc:
            self.console.print(f"[red]●[/red] {exc}")
            self.console.print()
            return

        online = health.get("status") == "online"
        ready = bool(health.get("agent_ready"))

        if online and ready:
            self.console.print("[green]●[/green] Backend online")
        elif online:
            self.console.print("[yellow]●[/yellow] Backend online (agent not ready)")
        else:
            self.console.print("[red]●[/red] Backend offline")

        self.console.print(
            f"  [{ODIN_GRAY}]Host:[/{ODIN_GRAY}] "
            f"{settings.odin_host}:{settings.odin_port}"
        )
        self.console.print(
            f"  [{ODIN_GRAY}]Provider:[/{ODIN_GRAY}] "
            f"{health.get('model_provider')}"
        )
        self.console.print(
            f"  [{ODIN_GRAY}]Model:[/{ODIN_GRAY}] {health.get('model')}"
        )
        self.console.print(
            f"  [{ODIN_GRAY}]Tools:[/{ODIN_GRAY}] {health.get('tools_count')}"
        )

        self.console.print()

    async def model_command(self, raw: str) -> None:
        parts = raw.split()
        subcommand = parts[0].lower()

        try:
            data = await self.config.list_providers()
        except OdinConfigError as exc:
            self.console.print()
            self.console.print(f"[red]{exc}[/red]")
            self.console.print()
            return

        if subcommand == "/models":
            self._list_models(data, parts[1] if len(parts) > 1 else None)
            return

        # /model with no arguments → interactive selector (tty) or table.
        if len(parts) == 1:
            if sys.stdin.isatty():
                try:
                    picked = await self._pick_in_console(data)
                except Exception:
                    picked = None
                if picked is not None:
                    await self._apply(picked[0], picked[1])
                    return
            self._show_catalog(data)
            return

        if len(parts) == 3:
            await self._apply(parts[1].lower(), parts[2])
            return

        self.console.print()
        self.console.print("[red]Uso:[/red] /model [provider modelo]")
        self.console.print("[dim]  /model            abre o seletor[/dim]")
        self.console.print("[dim]  /model gemini gemini-2.5-flash[/dim]")
        self.console.print()

    def _list_models(self, data: dict, provider_id: str | None) -> None:
        self.console.print()

        if provider_id is None:
            for provider in data.get("providers", []):
                self._print_provider_models(provider, data.get("active") or {})
            self.console.print(
                f"[{ODIN_GRAY}]Use /models <provider> para listar um só "
                f"provider.[/{ODIN_GRAY}]"
            )
        else:
            provider = next(
                (p for p in data.get("providers", []) if p["id"] == provider_id),
                None,
            )
            if provider is None:
                self.console.print(
                    f"[red]Provider desconhecido: {provider_id}[/red]"
                )
            else:
                self._print_provider_models(provider, data.get("active") or {})

        self.console.print()

    def _print_provider_models(
        self,
        provider: dict,
        active: dict,
    ) -> None:
        configured = bool(provider.get("configured", True))
        label = f"[bold {ODIN_ORANGE}]{provider.get('label')}[/bold {ODIN_ORANGE}]"
        if not configured:
            label += "  [red](API key ausente — não configurado)[/red]"
        self.console.print(label)

        models = provider.get("models") or []
        if not models:
            self.console.print(f"  [{ODIN_GRAY}]sem modelos disponíveis[/{ODIN_GRAY}]")
            return

        for model in models:
            is_active = (
                provider["id"] == active.get("provider") and model == active.get("model")
            )
            if is_active:
                self.console.print(
                    f"  [green]●[/green] [{ODIN_WHITE}]{model}[/{ODIN_WHITE}] [dim](ativo)[/dim]"
                )
            else:
                self.console.print(f"  [dim]○[/dim] {model}")

    def _show_catalog(self, data: dict) -> None:
        self.console.print()
        for provider in data.get("providers", []):
            self._print_provider_models(provider, data.get("active") or {})
            self.console.print()
        self.console.print(
            f"[{ODIN_GRAY}]Troque com:[/{ODIN_GRAY}] "
            f"/model <provider> <modelo>"
        )
        self.console.print()

    async def _pick_in_console(self, data: dict) -> tuple[str, str] | None:
        """Interactive provider → model picker (prompt_toolkit)."""
        from prompt_toolkit.shortcuts import radiolist_dialog

        active = data.get("active") or {}
        providers = [
            p
            for p in data.get("providers", [])
            if p.get("configured", True) and p.get("models")
        ]

        if not providers:
            self.console.print()
            self.console.print(
                "[red]Nenhum provider configurado com modelos disponíveis.[/red]"
            )
            self.console.print()
            return None

        provider_id = await radiolist_dialog(
            title="ODIN · Provider",
            text=f"Seleção atual: {active.get('provider')} / {active.get('model')}",
            values=[(p["id"], p["label"]) for p in providers],
        ).run_async()

        if not provider_id:
            return None

        provider = next((p for p in providers if p["id"] == provider_id), None)
        if provider is None:
            return None

        model = await radiolist_dialog(
            title="ODIN · Modelo",
            text=f"Selecione o modelo ({provider['label']}):",
            values=[(m, m) for m in provider["models"]],
        ).run_async()

        if not model:
            return None

        return provider_id, model

    async def _apply(self, provider: str, model: str) -> None:
        try:
            result = await self.config.select(provider, model)
        except OdinConfigError as exc:
            self.console.print()
            self.console.print(f"[red]{exc}[/red]")
            self.console.print()
            return

        self.console.print()
        self.console.print(
            f"[green]✓[/green] Provider: [{ODIN_ORANGE}]{result.get('provider')}"
            f"[/{ODIN_ORANGE}]  Modelo: [{ODIN_ORANGE}]{result.get('model')}"
            f"[/{ODIN_ORANGE}]"
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