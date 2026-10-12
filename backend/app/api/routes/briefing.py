"""Daily briefing API.

Aggregates a one-glance snapshot of the machine, the workspace and the Odin
runtime for the panel's boot-once briefing modal.

Every section is collected resiliently: an ``asyncio.gather`` fans out the
independent collectors and a failing section degrades to ``null`` / an empty
list instead of breaking the whole request.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import psutil
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.providers import catalog
from app.agent.providers.base import LLMMessage
from app.config import settings
from app.database.models import AppState, Conversation, PermissionRequest
from app.database.session import get_db

logger = logging.getLogger("odin.api.briefing")

router = APIRouter()

VERSION = "0.1.0"

# app_state key that remembers the boot_time for which the briefing was shown.
STATE_LAST_BRIEFING_BOOT = "last_briefing_boot"

# --- weather ---------------------------------------------------------------
_WEATHER_TTL_SECONDS = 10 * 60
_WEATHER_TIMEOUT = 8.0
# Process-wide cache: {"at": monotonic seconds, "data": WeatherInfo | None}.
_weather_cache: dict = {"at": 0.0, "data": None}

# --- workspace scan --------------------------------------------------------
_SKIP_DIRS = {
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "dist",
    "build",
    "__pycache__",
    ".next",
}
_TODO_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".sh"}
_TODO_RE = re.compile(r"\b(?:TODO|FIXME|XXX)\b")
_MAX_TODO_FILE_BYTES = 256 * 1024
_MAX_TODO_FILES = 800
_RECENT_WINDOW_SECONDS = 7 * 24 * 3600
_RECENT_LIMIT = 5

# --- git -------------------------------------------------------------------
_GIT_TIMEOUT = 10


# ---------------------------------------------------------------------------
# Response models (frozen contract — see frontend/src/types/briefing.ts)
# ---------------------------------------------------------------------------
class BriefingWeather(BaseModel):
    city: str
    temperature: float
    apparent: float
    code: int
    description: str
    temp_max: float
    temp_min: float
    precipitation_probability: int


class BriefingGitRepo(BaseModel):
    name: str
    path: str
    branch: str
    changes: int
    last_commit: str
    ahead: int
    behind: int


class BriefingRecentFile(BaseModel):
    path: str
    age_seconds: int


class BriefingFiles(BaseModel):
    recent: list[BriefingRecentFile]
    todo_count: int


class BriefingSystem(BaseModel):
    cpu_percent: float
    memory_percent: float
    memory_used: int
    memory_total: int
    disk_percent: float
    disk_used: int
    disk_total: int
    load_avg: list[float]
    uptime_seconds: float


class BriefingRuntime(BaseModel):
    status: str
    version: str
    provider: str
    model: str
    tools_count: int
    agent_ready: bool


class BriefingPermissions(BaseModel):
    pending: int
    high_risk: int


class BriefingConversation(BaseModel):
    id: str
    title: str
    updated_at: str


class BriefingResponse(BaseModel):
    should_show: bool
    boot_time: float
    generated_at: str
    weather: BriefingWeather | None
    git: list[BriefingGitRepo | None]
    files: BriefingFiles
    system: BriefingSystem
    runtime: BriefingRuntime
    permissions: BriefingPermissions
    conversations: list[BriefingConversation]


class BriefingSummaryResponse(BaseModel):
    summary: str | None


class BriefingAckResponse(BaseModel):
    acknowledged: bool
    boot_time: float


# ---------------------------------------------------------------------------
# Weather (Open-Meteo)
# ---------------------------------------------------------------------------
# WMO weather interpretation codes -> Portuguese description.
_WMO_DESCRIPTIONS = {
    0: "Céu limpo",
    1: "Predominantemente limpo",
    2: "Parcialmente nublado",
    3: "Encoberto",
    45: "Nevoeiro",
    48: "Nevoeiro com geada",
    51: "Garoa leve",
    53: "Garoa moderada",
    55: "Garoa intensa",
    56: "Garoa congelante leve",
    57: "Garoa congelante intensa",
    61: "Chuva leve",
    63: "Chuva moderada",
    65: "Chuva forte",
    66: "Chuva congelante leve",
    67: "Chuva congelante forte",
    71: "Neve leve",
    73: "Neve moderada",
    75: "Neve forte",
    77: "Grãos de neve",
    80: "Pancadas de chuva leves",
    81: "Pancadas de chuva moderadas",
    82: "Pancadas de chuva fortes",
    85: "Pancadas de neve leves",
    86: "Pancadas de neve fortes",
    95: "Trovoada",
    96: "Trovoada com granizo leve",
    99: "Trovoada com granizo forte",
}


def describe_weather_code(code: int) -> str:
    """Map a WMO weather interpretation code to a Portuguese description."""
    return _WMO_DESCRIPTIONS.get(code, "Condições desconhecidas")


def _weather_url() -> str:
    return (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={settings.odin_weather_lat}&longitude={settings.odin_weather_lon}"
        "&current=temperature_2m,apparent_temperature,weather_code"
        "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
        "&timezone=auto"
    )


def parse_weather_payload(payload: dict, city: str) -> BriefingWeather | None:
    """Parse an Open-Meteo response into the briefing weather model."""
    current = payload.get("current") or {}
    daily = payload.get("daily") or {}

    code = current.get("weather_code")
    if code is None:
        return None

    def _first(key: str, default: float = 0.0) -> float:
        values = daily.get(key) or []
        value = values[0] if values else default
        return default if value is None else value

    try:
        code_int = int(code)
        return BriefingWeather(
            city=city,
            temperature=float(current.get("temperature_2m") or 0.0),
            apparent=float(current.get("apparent_temperature") or 0.0),
            code=code_int,
            description=describe_weather_code(code_int),
            temp_max=float(_first("temperature_2m_max")),
            temp_min=float(_first("temperature_2m_min")),
            precipitation_probability=int(_first("precipitation_probability_max") or 0),
        )
    except (TypeError, ValueError):
        return None


def _reset_weather_cache() -> None:
    """Drop the in-memory weather cache (used by tests)."""
    _weather_cache["at"] = 0.0
    _weather_cache["data"] = None


async def _fetch_weather() -> BriefingWeather | None:
    """Fetch current + today's weather from Open-Meteo, cached for ~10 min."""
    cached = _weather_cache.get("data")
    if cached is not None and time.monotonic() - _weather_cache.get("at", 0.0) < _WEATHER_TTL_SECONDS:
        return cached

    async with httpx.AsyncClient(timeout=_WEATHER_TIMEOUT) as client:
        response = await client.get(_weather_url())
        response.raise_for_status()
        payload = response.json()

    weather = parse_weather_payload(payload, settings.odin_weather_city)
    if weather is not None:
        _weather_cache["data"] = weather
        _weather_cache["at"] = time.monotonic()
    return weather


# ---------------------------------------------------------------------------
# Git
# ---------------------------------------------------------------------------
def _git(path: str, *args: str) -> str:
    """Run a git command in ``path``; raises RuntimeError on failure."""
    result = subprocess.run(
        ["git", "-C", path, *args],
        capture_output=True,
        text=True,
        timeout=_GIT_TIMEOUT,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def _git_ahead_behind(path: str) -> tuple[int, int]:
    """Return (ahead, behind) relative to the upstream, or (0, 0) if none."""
    try:
        output = _git(path, "rev-list", "--left-right", "--count", "@{upstream}...HEAD")
    except (RuntimeError, subprocess.SubprocessError):
        return 0, 0
    parts = output.split()
    if len(parts) != 2:
        return 0, 0
    try:
        # Left = commits only on the upstream (behind), right = only on HEAD (ahead).
        behind, ahead = int(parts[0]), int(parts[1])
    except ValueError:
        return 0, 0
    return ahead, behind


def collect_git_repo(path: str) -> BriefingGitRepo | None:
    """Describe a git repository, or None when ``path`` is not a repo."""
    expanded = Path(path).expanduser()
    if not expanded.is_dir():
        return None

    try:
        branch = _git(str(expanded), "rev-parse", "--abbrev-ref", "HEAD")
    except (RuntimeError, subprocess.SubprocessError):
        return None  # not a git repository

    try:
        status = _git(str(expanded), "status", "--porcelain")
        changes = len([line for line in status.splitlines() if line.strip()])
    except (RuntimeError, subprocess.SubprocessError):
        changes = 0

    try:
        last_commit = _git(str(expanded), "log", "-1", "--format=%h · %s · %cr")
    except (RuntimeError, subprocess.SubprocessError):
        last_commit = ""

    ahead, behind = _git_ahead_behind(str(expanded))

    return BriefingGitRepo(
        name=expanded.name,
        path=path,
        branch=branch,
        changes=changes,
        last_commit=last_commit,
        ahead=ahead,
        behind=behind,
    )


async def _collect_git() -> list[BriefingGitRepo | None]:
    paths = [p.strip() for p in settings.odin_briefing_repos.split(",") if p.strip()]

    async def _one(repo_path: str) -> BriefingGitRepo | None:
        try:
            return await asyncio.to_thread(collect_git_repo, repo_path)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(f"briefing: git section failed for {repo_path}: {exc}")
            return None

    return list(await asyncio.gather(*(_one(p) for p in paths)))


# ---------------------------------------------------------------------------
# Workspace files
# ---------------------------------------------------------------------------
def scan_workspace(workspace: str) -> BriefingFiles:
    """Return recently modified files and a TODO/FIXME/XXX count."""
    root = Path(workspace).expanduser()
    if not root.is_dir():
        return BriefingFiles(recent=[], todo_count=0)

    now = time.time()
    recent: list[tuple[float, str]] = []
    todo_count = 0
    todo_files = 0

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune hidden and noisy directories in-place so os.walk skips them.
        dirnames[:] = [
            d for d in dirnames if not d.startswith(".") and d not in _SKIP_DIRS
        ]

        for filename in filenames:
            file_path = Path(dirpath) / filename
            try:
                stat = file_path.stat()
            except OSError:
                continue

            age = now - stat.st_mtime
            if 0 <= age <= _RECENT_WINDOW_SECONDS:
                try:
                    rel = file_path.relative_to(root).as_posix()
                except ValueError:
                    continue
                recent.append((stat.st_mtime, rel))

            if (
                todo_files < _MAX_TODO_FILES
                and file_path.suffix.lower() in _TODO_EXTENSIONS
                and stat.st_size <= _MAX_TODO_FILE_BYTES
            ):
                todo_files += 1
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                todo_count += len(_TODO_RE.findall(content))

    recent.sort(key=lambda item: item[0], reverse=True)
    top = recent[:_RECENT_LIMIT]

    return BriefingFiles(
        recent=[
            BriefingRecentFile(path=rel, age_seconds=int(now - mtime))
            for mtime, rel in top
        ],
        todo_count=todo_count,
    )


# ---------------------------------------------------------------------------
# System / runtime
# ---------------------------------------------------------------------------
def collect_system() -> BriefingSystem:
    cpu = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    load = list(psutil.getloadavg())

    return BriefingSystem(
        cpu_percent=cpu,
        memory_percent=mem.percent,
        memory_used=mem.used,
        memory_total=mem.total,
        disk_percent=disk.percent,
        disk_used=disk.used,
        disk_total=disk.total,
        load_avg=load,
        uptime_seconds=time.time() - psutil.boot_time(),
    )


def collect_runtime() -> BriefingRuntime:
    # Imported lazily: the singletons live in main, which imports this module.
    from app.main import odin_agent, tool_registry

    active = catalog.get_active()
    return BriefingRuntime(
        status="online",
        version=VERSION,
        provider=active.provider if active else settings.odin_model_provider,
        model=active.model if active else settings.odin_model,
        tools_count=len(tool_registry),
        agent_ready=odin_agent is not None and odin_agent.provider is not None,
    )


# ---------------------------------------------------------------------------
# DB-backed sections
# ---------------------------------------------------------------------------
async def collect_permissions(db: AsyncSession) -> BriefingPermissions:
    result = await db.execute(
        select(PermissionRequest).where(PermissionRequest.status == "pending")
    )
    rows = result.scalars().all()
    high_risk = sum(1 for row in rows if row.risk_level in ("high", "critical"))
    return BriefingPermissions(pending=len(rows), high_risk=high_risk)


async def collect_conversations(db: AsyncSession) -> list[BriefingConversation]:
    result = await db.execute(
        select(Conversation).order_by(Conversation.updated_at.desc()).limit(5)
    )
    return [
        BriefingConversation(
            id=row.id,
            title=row.title,
            updated_at=row.updated_at.isoformat() if row.updated_at else "",
        )
        for row in result.scalars().all()
    ]


async def get_state(db: AsyncSession, key: str) -> str | None:
    result = await db.execute(select(AppState).where(AppState.key == key))
    row = result.scalar_one_or_none()
    return row.value if row else None


async def set_state(db: AsyncSession, key: str, value: str) -> None:
    result = await db.execute(select(AppState).where(AppState.key == key))
    row = result.scalar_one_or_none()
    if row is None:
        db.add(AppState(key=key, value=value))
    else:
        row.value = value
    await db.commit()


def should_show_briefing(last_boot: str | None, boot_time: float) -> bool:
    """Show the briefing only once per boot."""
    if not last_boot:
        return True
    try:
        return float(last_boot) != boot_time
    except (TypeError, ValueError):
        return True


# ---------------------------------------------------------------------------
# Collection orchestration
# ---------------------------------------------------------------------------
async def _safe(coro, default):
    """Run a coroutine, returning ``default`` if it raises."""
    try:
        return await coro
    except Exception as exc:
        logger.warning(f"briefing: section failed: {exc}")
        return default


async def _collect(db: AsyncSession) -> BriefingResponse:
    boot_time = psutil.boot_time()
    last_boot = await get_state(db, STATE_LAST_BRIEFING_BOOT)
    should_show = should_show_briefing(last_boot, boot_time)

    weather, git, files, system, runtime = await asyncio.gather(
        _safe(_fetch_weather(), None),
        _safe(_collect_git(), []),
        _safe(asyncio.to_thread(scan_workspace, settings.odin_workspace), BriefingFiles(recent=[], todo_count=0)),
        _safe(asyncio.to_thread(collect_system), _empty_system()),
        _safe(asyncio.to_thread(collect_runtime), _empty_runtime()),
    )

    # The DB sections share one AsyncSession, so they must run sequentially.
    permissions = await _safe(collect_permissions(db), BriefingPermissions(pending=0, high_risk=0))
    conversations = await _safe(collect_conversations(db), [])

    return BriefingResponse(
        should_show=should_show,
        boot_time=boot_time,
        generated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        weather=weather,
        git=git,
        files=files,
        system=system,
        runtime=runtime,
        permissions=permissions,
        conversations=conversations,
    )


def _empty_system() -> BriefingSystem:
    return BriefingSystem(
        cpu_percent=0.0,
        memory_percent=0.0,
        memory_used=0,
        memory_total=0,
        disk_percent=0.0,
        disk_used=0,
        disk_total=0,
        load_avg=[0.0, 0.0, 0.0],
        uptime_seconds=0.0,
    )


def _empty_runtime() -> BriefingRuntime:
    active = catalog.get_active()
    return BriefingRuntime(
        status="online",
        version=VERSION,
        provider=active.provider if active else settings.odin_model_provider,
        model=active.model if active else settings.odin_model,
        tools_count=0,
        agent_ready=False,
    )


# ---------------------------------------------------------------------------
# Summary (LLM)
# ---------------------------------------------------------------------------
def _build_summary_prompt(briefing: BriefingResponse) -> str:
    lines = ["Resuma o briefing diário do Odin em 2-3 frases, em português do Brasil."]
    lines.append(f"Data: {briefing.generated_at}")
    if briefing.weather:
        w = briefing.weather
        lines.append(
            f"Clima em {w.city}: {w.temperature}°C (sensação {w.apparent}°C), "
            f"{w.description}, máx {w.temp_max}°C / mín {w.temp_min}°C, "
            f"chance de chuva {w.precipitation_probability}%."
        )
    if briefing.git:
        repos = [g for g in briefing.git if g is not None]
        if repos:
            parts = [
                f"{r.name} ({r.branch}): {r.changes} alterações, {r.ahead} à frente, "
                f"{r.behind} atrás"
                for r in repos
            ]
            lines.append("Repositórios: " + "; ".join(parts) + ".")
    lines.append(f"Arquivos recentes: {len(briefing.files.recent)}; pendências TODO: {briefing.files.todo_count}.")
    s = briefing.system
    lines.append(
        f"Sistema: CPU {s.cpu_percent}%, memória {s.memory_percent}%, "
        f"disco {s.disk_percent}%."
    )
    lines.append(
        f"Permissões pendentes: {briefing.permissions.pending} "
        f"(alto risco: {briefing.permissions.high_risk})."
    )
    lines.append(f"Runtime: {briefing.runtime.provider}/{briefing.runtime.model}.")
    return "\n".join(lines)


async def _generate_summary(briefing: BriefingResponse) -> str | None:
    try:
        from app.main import odin_agent
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"briefing: could not import agent: {exc}")
        return None

    if odin_agent is None or odin_agent.provider is None:
        return None

    system = (
        "Você é o Odin, o assistente pessoal do usuário. "
        "Responda em português do Brasil, em no máximo 2-3 frases, de forma direta e amigável."
    )
    messages = [LLMMessage(role="user", content=_build_summary_prompt(briefing))]

    try:
        parts: list[str] = []
        async for chunk in odin_agent.provider.generate(messages, [], system):
            if chunk.type == "text" and chunk.content:
                parts.append(chunk.content)
            elif chunk.type == "error":
                return None
        summary = "".join(parts).strip()
        return summary or None
    except Exception as exc:
        logger.warning(f"briefing: summary generation failed: {exc}")
        return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("", response_model=BriefingResponse)
async def get_briefing(db: AsyncSession = Depends(get_db)) -> BriefingResponse:
    """Return the aggregated daily briefing payload."""
    return await _collect(db)


@router.post("/summary", response_model=BriefingSummaryResponse)
async def briefing_summary(db: AsyncSession = Depends(get_db)) -> BriefingSummaryResponse:
    """Generate a short natural-language summary of the briefing."""
    briefing = await _collect(db)
    return BriefingSummaryResponse(summary=await _generate_summary(briefing))


@router.post("/ack", response_model=BriefingAckResponse)
async def acknowledge_briefing(db: AsyncSession = Depends(get_db)) -> BriefingAckResponse:
    """Mark the current boot's briefing as shown so it does not reappear."""
    boot_time = psutil.boot_time()
    await set_state(db, STATE_LAST_BRIEFING_BOOT, str(boot_time))
    return BriefingAckResponse(acknowledged=True, boot_time=boot_time)
