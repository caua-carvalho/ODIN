# Odin Personal AI Assistant — AGENTS.md

This file contains high-signal, repo-specific guidance for future OpenCode sessions.
Every line below answers: "Would an agent likely miss this without help?"
Lines that are generic or obvious are omitted.

## Commands

| Command | What it does |
|---|---|
| `odin start` | Start the backend (FastAPI/uvicorn) via scripts/server.sh |
| `odin stop` | Stop the running backend |
| `odin restart` | Restart the backend |
| `odin status` | Show backend status, PID, URL |
| `odin logs` / `odin logs --follow` | Show (or tail) the backend log at `~/.local/state/odin/server.log` |
| `odin help` | Print the command list |
| `odin` (no args) | Launch interactive CLI chat (runs `app.cli.main`) |
| `./scripts/setup.sh` | Full setup: create venv, install deps, npm install, create .env |
| `./scripts/install-autostart.sh` | Install autostart: systemd `--user` unit (starts at boot) + desktop entry (opens the panel on login) |
| `./scripts/open-panel.sh` | Wait for the backend, then open the web panel in the browser (used by the desktop autostart entry) |
| `./scripts/dev.sh` *(not yet created but referenced)* | Development workflow — see note below |

> **Note**: The `setup.sh` script references `./scripts/dev.sh` at the end, but that file does not exist in this repo. If you need a dev server, run `uvicorn app.main:app --host 127.0.0.1 --port 8000` from the backend dir, and separately `npm run dev` from the frontend dir.

> **CLI internals**: The `start|stop|restart|status|logs|help` subcommands are implemented in `scripts/odin.sh` (a shell wrapper), **not** in `app/cli/main.py`. The interactive chat (no args) is `app/cli/main.py` and supports in-session slash commands `/help`, `/clear`, `/model`, `/models` (via `app/cli/commands.py`).

## Developer workflow

1. **Backend**: `cd backend && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000`
2. **Frontend**: `cd frontend && npm run dev` (Vite dev server at http://localhost:3000)
3. The frontend proxies `/api` → `http://127.0.0.1:8000` (vite.config.ts) and WebSocket upgrades are also proxied.

## Autostart (boot + web panel)

Odin can be configured to start on boot and open its web panel on login. This is
installed by `./scripts/install-autostart.sh`, which writes three things:

- `~/.config/systemd/user/odin.service` — a `Type=oneshot` `--user` unit whose
  `ExecStart` runs `scripts/server.sh start` (and `ExecStop` runs `... stop`).
  Enabled into `default.target` and started at boot thanks to
  `loginctl enable-linger "$USER"`.
- `~/.config/autostart/odin-panel.desktop` — XDG autostart entry for desktops
  that honor it (GNOME/KDE/XFCE).
- `~/.config/hypr/custom/execs.lua` — **this machine runs Hyprland**, which does
  *not* read `~/.config/autostart`, so the panel is opened from the compositor
  config instead via `hl.on("hyprland.start", ...)` → `scripts/open-panel.sh`.

`scripts/open-panel.sh` waits for `/api/health` and then opens the panel in
Firefox (override with `ODIN_BROWSER`). Re-running the installer is idempotent
and rewrites its managed block in the Hyprland file. Manage the backend with
`systemctl --user {status,start,stop,restart} odin.service`.

**The web panel is served by the backend**, not a separate dev server: `main.py`
mounts `frontend/dist` at `/` (with an SPA fallback to `index.html`) so the
console lives at `http://127.0.0.1:8000` on the same origin as the API. After
changing frontend code you must rebuild it (`cd frontend && npm run build`) for
the served panel to reflect the change. If `frontend/dist` is missing, the
backend logs a warning and serves only the API.

## LLM providers

The backend supports **three** LLM providers, registered in `backend/app/agent/providers/factory.py` under `PROVIDER_BUILDERS` and described in `backend/app/agent/providers/catalog.py` (`PROVIDERS`):

- **gemini**: Requires `GEMINI_API_KEY` in `.env`.
- **groq**: Requires `GROQ_API_KEY` in `.env`. OpenAI-compatible API.
- **ollama**: Requires `OLLAMA_BASE_URL` (default `http://localhost:11434`) in `.env`. No API key.

> **Note**: The local, git-ignored `.env` banner lists `openai` and `anthropic` as options, but `PROVIDER_BUILDERS` only implements `gemini`, `groq`, `ollama` (the committed `.env.example` matches). Selecting an unimplemented provider raises `Unsupported LLM provider: ...`. Add new providers by: (1) creating an adapter in `backend/app/agent/providers/` implementing `LLMProvider`, (2) registering it in `PROVIDER_BUILDERS` **and** adding its `ProviderMeta` to `catalog.PROVIDERS`.

> **Runtime selection**: The active provider/model can be switched at runtime (global, process-wide) via `POST /api/providers/select`, used by the frontend TopBar selector (`ModelSelector.tsx`) and the CLI `/model` command. The switch is **in-memory only** — restarting the backend falls back to `.env`. Provider metadata, availability and dynamic model discovery live in `backend/app/agent/providers/catalog.py`; `/api/health` reports the active selection (not raw `settings`).

> **Critical**: The `.env` file **must** exist and contain at minimum `ODIN_MODEL_PROVIDER` and `ODIN_MODEL`. The `setup.sh` script copies `.env.example` → `.env` and warns to add `GEMINI_API_KEY`. Without a valid API key, the app will fail to start.

## Environment

- `.env` is at the repo root. It is **git-ignored** (but `.env.example` is committed so others can see the schema).
- `ODIN_WORKSPACE` defaults to `/home/caua/odin-workspace` (configure in `.env` or `Settings.odin_workspace`).
- `DATABASE_URL` defaults to `sqlite+aiosqlite:///./odin.db` (a local SQLite file kept in the repo root).
- The `.env.example` lists all available env vars: model provider, model name, API keys, database URL, host/port, debug flag.

## Security & path boundaries

All filesystem and shell operations go through a **security gate**. This is **not** optional — the agent will refuse commands that escape the workspace.

Key concepts:

- **PathGuard** (`backend/app/security/path_guard.py`): Resolves paths canonically via `Path(path).resolve()`. Never use string comparison to check paths.
- **SecurityPolicy** (`backend/app/security/policy.py`): Classifies operations (READ/WRITE/DELETE/MOVE/EXECUTE) and returns `AccessLevel` (`ALLOW` / `REQUIRE_APPROVAL` / `DENY`).
- **Workspace boundary**: Operations *inside* `ODIN_WORKSPACE` are always allowed. Outside → READ is denied; WRITE/DELETE/MOVE/EXECUTE require approval.
- **Privileged commands**: `sudo`, `apt`, `systemctl`, `fdisk`, `mkfs`, etc. always require approval.
- **Safe dev executables**: `git`, `python`, `node`, `npm`, `pytest`, etc. are allowed without approval when inside the workspace.
- **Permission system**: WRITE/DELETE/MOVE/EXECUTE outside the workspace trigger a permission request (stored in DB, bridged via WebSocket). The agent will yield `permission_request` events that the UI must approve before the operation proceeds.

> **Important**: If an agent seems to "ignore" a tool call, it may have been denied by the security policy. Check the logs for `Access denied` or `REQUIRE_APPROVAL` messages.

## Tool registry

The agent maintains a registry of all available tools, registered during startup in `backend/app/main.py` lifespan:

- **Filesystem tools**: `read_file`, `list_directory`, `search_files`, `write_file`, `delete_file`, `move_file`, `create_directory`
- **Shell tool**: `execute_command`

Tools are converted to provider-agnostic LLM tool definitions via `ToolRegistry.to_llm_tools()` (in `backend/app/tools/registry.py`). The registry is a global singleton — if you add a new tool, you must register it in the lifespan section of `main.py`.

> **Signal**: The health endpoint (`/api/health`) reports `"tools_count": <n>`. If this is 0, no tools were registered, and the agent cannot perform any actions.

## Testing

- Tests live in `backend/tests/`. Run with: `cd backend && .venv/bin/pytest tests/ -v`
- Test modules: `test_security.py` (PathGuard + policy + command policy), `test_providers.py` (provider contracts, tool-call history, factory, env config), `test_providers_catalog.py` (catalog, availability, model discovery, active selection), `test_cli_config.py`. The full suite is ~73 tests and runs in a couple of seconds without any network access.
- Smoke tests (manual verification the app boots and talks to the LLM):
  - `python smoke_bootstrap.py` — FastAPI bootstrap with Ollama
  - `python smoke_agent.py` — Full OdinAgent loop with persistence
  - `python smoke_gemini.py` — Gemini provider round-trip
  - `python smoke_ollama.py` — Ollama provider round-trip
- All smoke scripts set env vars inline (override `.env`) so they don't need a running server.
- Tests use `asyncio_mode = "auto"` (from pyproject.toml).
- **End-to-end** is not covered by the suite: exercise the running server via `POST /api/conversations` + the `WS /api/ws/{id}` socket (send `{"type":"message","content":"..."}`), or invoke the tool classes directly in-process to test the security gate without an LLM.

## API basics (for reference)

| Endpoint | Description |
|---|---|
| `GET /api/health` | Returns status, model_provider, model, workspace, tools_count, agent_ready |
| `GET /api/ws/{conv_id}` | WebSocket chat endpoint (stream events: text_chunk, tool_start, tool_end, done, error) |
| `GET /api/conversations` | List conversations |
| `POST /api/conversations` | Create a new conversation (⚠️ **no trailing slash** — `POST /api/conversations/` returns 405) |
| `GET /api/conversations/{id}` | Get a conversation |
| `DELETE /api/conversations/{id}` | Delete a conversation |
| `GET /api/conversations/{id}/messages` | Get messages for a conversation |
| `GET /api/system` | System info (psutil: cpu, memory, disk, uptime) — **requires psutil** |
| `GET /api/tools` | List registered tools |
| `GET /api/skills` | List skill groupings (Filesystem, Development, System, ...) over registered tools |
| `GET /api/providers` | List LLM providers (availability + models) and the active selection |
| `POST /api/providers/select` | Switch the active provider/model at runtime (body: `{"provider": "...", "model": "..."}`) |
| `GET /api/mcp` | Mocked MCP servers (not implemented in MVP) |
| `GET /api/permissions` | List all permission requests |
| `GET /api/permissions/pending` | List pending permission requests |
| `POST /api/permissions/{id}/approve` | Approve a permission request |
| `POST /api/permissions/{id}/deny` | Deny a permission request |

> **Beware the SPA fallback**: `main.py` registers a catch-all `GET /{full_path:path}` that returns `index.html` with **HTTP 200** for any unmatched path. A typo'd API route (e.g. the old `GET /api/system/info`) therefore returns HTML — not a 404 — so always verify the endpoint exists in `/openapi.json` (the catch-all is excluded from the schema).

## Database

- SQLite async (SQLAlchemy) — file is `odin.db` at the repo root.
- On every startup, `init_db()` creates tables if they don't exist (`backend/app/database/session.py`).
- Tables: `conversations`, `messages`, `permission_requests`.
- Use `get_db_session()` (context manager) or `get_db()` (FastAPI dependency) for DB access.
- Permission requests are the mechanism that blocks/unblocks filesystem/shell operations outside the workspace.

## Architecture notes (what changes real behavior)

1. **Lifespan in `main.py`** is the single entry point for startup init: DB init → security init → tool registration → LLM provider init → agent init. If you add a tool, you must register it here (in `create_filesystem_tools` or manually).

2. **Provider factory** (`factory.py`) is the only place that maps `ODIN_MODEL_PROVIDER` → concrete provider. Adding a new provider requires editing this file.

3. **Security policy** (`policy.py`) determines what the agent is allowed to do. The agent will not execute a tool if the policy denies it. If you need to change what's "safe", edit `SAFE_DEV_EXECUTABLES`, `PRIVILEGED_EXECUTABLES`, etc.

4. **Permission flow**: When the agent tries a WRITE/DELETE/MOVE/EXECUTE outside the workspace, it yields a `permission_request` event. The UI must call `/api/permissions/{id}/approve` or `/api/permissions/{id}/deny` to unblock the agent.

5. **WebSocket chat** (`api/routes/chat.py`) is the real-time streaming endpoint. Clients send `{"type": "message", "content": "..."}` and receive events including `tool_start`/`tool_end`. The agent's `chat()` method yields these events.