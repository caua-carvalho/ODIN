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
| `./scripts/build.sh` | Install backend deps + build the frontend (`frontend/dist`) in one shot |
| `./scripts/install-service.sh` | Install the **system** systemd unit (`deploy/odin.service`, `Restart=always`); needs sudo — for hosting |
| `./scripts/cloudflared-quick-tunnel.sh` | Fastest public URL: launches a Cloudflare quick tunnel to `127.0.0.1:8000` |
| `./scripts/tailscale-funnel-setup.sh` | Permanent public URL **without a domain**: Tailscale Funnel (`*.ts.net`), userspace, no sudo |
| `./scripts/backup.sh [dest]` | Back up `odin.db` + workspace (default `~/.local/state/odin/backups`) |

> **Note**: `setup.sh` no longer references a non-existent `scripts/dev.sh`; it now points at `./scripts/build.sh` and `./scripts/odin.sh start`. For a dev server, run `uvicorn app.main:app --host 127.0.0.1 --port 8000` from the backend dir, and separately `npm run dev` from the frontend dir.

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

## Hosting / deploy

The intended hosting topology is **backend on `127.0.0.1:8000` + Cloudflare
Tunnel** (`cloudflared`, outbound-only — no inbound port, automatic TLS). Full
walkthrough in **`README.deploy.md`**. Pieces:

- `deploy/odin.service` — system systemd unit template (rendered by
  `scripts/install-service.sh`); this is the *hosting* unit, distinct from the
  desktop `--user` unit installed by `install-autostart.sh`.
- `.env.production.example` — production env template (loopback bind, token,
  public `ODIN_CORS_ORIGINS`).
- `scripts/cloudflared-quick-tunnel.sh` — immediate `*.trycloudflare.com` URL
  (rotating, no Access); named tunnel + domain + Cloudflare Access is documented
  in the README.
- `scripts/tailscale-funnel-setup.sh` — **zero-domain** permanent option:
  runs `tailscaled` in userspace mode as a `systemd --user` service (no sudo)
  and exposes `127.0.0.1:<port>` at `https://<host>.<tailnet>.ts.net` via
  Tailscale Funnel. Interactive browser steps: device login + enable Funnel.
  `Linger=yes` keeps it alive across logout/reboot. This is what this machine
  uses in practice (tailnet `tail5426dc.ts.net`, host `odin`).

## LLM providers

Every provider is served by **one** LiteLLM-backed adapter, `LiteLLMProvider`
(`backend/app/agent/providers/litellm_provider.py`), built by `create_llm_provider`
in `backend/app/agent/providers/factory.py` (`PROVIDER_BUILDERS` is derived from
the catalog). Providers and their availability rules live in
`backend/app/agent/providers/catalog.py` (`PROVIDERS`):

- **gemini**: Requires `GEMINI_API_KEY` in `.env`.
- **groq**: Requires `GROQ_API_KEY` in `.env`; OpenAI-compatible API (`GROQ_BASE_URL`).
- **ollama**: Requires `OLLAMA_BASE_URL` (default `http://localhost:11434`) in `.env`. No API key.
- **openai**: Requires `OPENAI_API_KEY` in `.env`.
- **anthropic**: Requires `ANTHROPIC_API_KEY` in `.env`.

`ODIN_MODEL` is the vendor model id; the LiteLLM vendor prefix is added
automatically (`gemini-2.5-flash` → `gemini/gemini-2.5-flash`; groq ids already
contain a slash, so `openai/gpt-oss-120b` → `groq/openai/gpt-oss-120b`). A model
that is already prefixed is left untouched.

> **Adding a provider**: add one `ProviderMeta` to `catalog.PROVIDERS` — no new
> adapter class is needed. The catalog's `litellm_prefix` (defaults to the id)
> and `api_key_setting` drive both the factory and `/api/providers`.

> **LiteLLM is imported lazily** (the adapter imports it on first use) because
> `import litellm` costs ~15s. `main.py` starts a daemon thread (`warm()`) at
> startup so the first user message does not pay that cost. The legacy adapters
> (`gemini.py`, `groq.py`, `ollama.py`) were **removed** once LiteLLM was
> validated end-to-end; `litellm_provider.py` is now the only adapter.

> **Tool-call ids are preserved verbatim** by `LiteLLMProvider`. LiteLLM encodes
> the Gemini thought signature inside the tool-call id (separator `__thought__`)
> and reconstructs it on the next request, so never regenerate that id. Provider
> extras also round-trip through `LLMToolCall.metadata["provider_specific_fields"]`.

> **Runtime selection**: The active provider/model can be switched at runtime (global, process-wide) via `POST /api/providers/select`, used by the frontend TopBar selector (`ModelSelector.tsx`) and the CLI `/model` command. The switch is **in-memory only** — restarting the backend falls back to `.env`. Provider metadata, availability and dynamic model discovery live in `backend/app/agent/providers/catalog.py`; `/api/health` reports the active selection (not raw `settings`).

> **Critical**: The `.env` file **must** exist and contain at minimum `ODIN_MODEL_PROVIDER` and `ODIN_MODEL`. The `setup.sh` script copies `.env.example` → `.env` and warns to add `GEMINI_API_KEY`. Without a valid API key, the app will fail to start.

## Environment

- `.env` is at the repo root. It is **git-ignored** (but `.env.example` is committed so others can see the schema).
- `ODIN_WORKSPACE` defaults to `/home/caua/odin-workspace` (configure in `.env` or `Settings.odin_workspace`).
- `ODIN_WEATHER_CITY` (default `São José dos Campos`) plus `ODIN_WEATHER_LAT` / `ODIN_WEATHER_LON` drive the Open-Meteo weather lookup used by the briefing's `weather` section.
- `ODIN_BRIEFING_REPOS` is a comma-separated list of repo paths reported in the briefing's `git` array (paths that are not git repos come back as `null`).
- `DATABASE_URL` defaults to `sqlite+aiosqlite:///./odin.db` (a local SQLite file kept in the repo root).
- The `.env.example` lists all available env vars: model provider, model name, API keys, database URL, host/port, debug flag, and the daily-briefing weather/repo settings.

## Security & path boundaries

All filesystem and shell operations go through a **security gate**. This is **not** optional — the agent will refuse commands that escape the workspace.

Key concepts:

- **PathGuard** (`backend/app/security/path_guard.py`): Resolves paths canonically via `Path(path).resolve()`. Never use string comparison to check paths.
- **SecurityPolicy** (`backend/app/security/policy.py`): Classifies operations (READ/WRITE/DELETE/MOVE/EXECUTE) and returns `AccessLevel` (`ALLOW` / `REQUIRE_APPROVAL` / `DENY`).
- **Workspace boundary**: Operations *inside* `ODIN_WORKSPACE` are always allowed. Outside → READ is denied; WRITE/DELETE/MOVE/EXECUTE require approval.
- **Privileged commands**: `sudo`, `apt`, `systemctl`, `fdisk`, `mkfs`, etc. always require approval.
- **Destructive / remote / network commands always require approval** (regardless of workspace): `rm`, `rmdir`, `chmod`, `chown`, `chgrp`, `truncate` (`DESTRUCTIVE_EXECUTABLES`), `ssh`, `scp`, `sftp`, `rsync`, `nc`, `ncat`, `telnet` (`REMOTE_EXECUTABLES`) and `curl`, `wget` (`NETWORK_EXECUTABLES`). This was tightened for hosting; to restore the old permissive behavior, move them back into `SAFE_DEV_EXECUTABLES`.
- **Safe dev executables**: `git`, `python`, `node`, `npm`, `pytest`, `cp`, `mv`, `mkdir`, etc. are allowed without approval when inside the workspace.
- **Permission system**: WRITE/DELETE/MOVE/EXECUTE outside the workspace trigger a permission request (stored in DB, bridged via WebSocket). The agent will yield `permission_request` events that the UI must approve before the operation proceeds.
- **Exposure guard** (`_enforce_exposure_guard` in `main.py` lifespan): the backend **refuses to start** if `ODIN_HOST` is not loopback and `ODIN_API_TOKEN` is empty. A public bind without a token is treated as RCE-by-design.
- **Auth rate limit** (`_FailureLimiter` in `security/auth.py`): wrong tokens are counted per client (`CF-Connecting-IP` / `X-Forwarded-For`, else socket peer) and answer `429` after `ODIN_AUTH_MAX_FAILURES` within `ODIN_AUTH_WINDOW_SECONDS`; a correct token resets the counter.

> **Important**: If an agent seems to "ignore" a tool call, it may have been denied by the security policy. Check the logs for `Access denied` or `REQUIRE_APPROVAL` messages.

## Tool registry

The agent maintains a registry of all available tools, registered during startup in `backend/app/main.py` lifespan:

- **Filesystem tools**: `read_file`, `list_directory`, `search_files`, `write_file`, `delete_file`, `move_file`, `create_directory`
- **Shell tool**: `execute_command`
- **Project tools**: `list_projects`, `get_project`, `create_project`, `update_project`, `delete_project`, `list_tasks`, `create_task`, `update_task`, `move_task`, `delete_task`, `list_project_files`, `read_project_file`, `write_project_file`, `create_project_directory`, `delete_project_file` (see the Projects section)

Tools are converted to provider-agnostic LLM tool definitions via `ToolRegistry.to_llm_tools()` (in `backend/app/tools/registry.py`). The registry is a global singleton — if you add a new tool, you must register it in the lifespan section of `main.py`.

> **Signal**: The health endpoint (`/api/health`) reports `"tools_count": <n>`. If this is 0, no tools were registered, and the agent cannot perform any actions.

## MCP servers

External [MCP](https://modelcontextprotocol.io) servers can be plugged in to add
tools without hand-coding them. The SDK (`mcp==2.3.0`) is **optional and lazily
imported**; with no servers configured (or the package absent) Odin boots exactly
as before, and `MCPManager.start()` is a no-op.

- Config: `ODIN_MCP_SERVERS` in `.env` — a JSON array of server objects
  (`name`, `transport` = `stdio`|`sse`|`http`, plus `command`/`args`/`env` for
  stdio or `url`/`headers` for remote, and `trusted`). Parsing is tolerant:
  invalid entries are logged and skipped so a config typo can never stop boot.
  See `.env.example` for examples.
- Code: `backend/app/agent/mcp/` — `config.py` (parse/validate),
  `manager.py` (connections + discovery + lifecycle), `tool.py`
  (`McpToolInfo`, `McpToolAdapter`, `create_mcp_tools`). It is registered in the
  `main.py` lifespan *after* the native tools (`await mcp_manager.start()` then
  `tool_registry.register(...)` for each discovered tool); `mcp_manager.stop()`
  runs on shutdown. `/api/mcp` reports the live status.
- Each server runs in a **dedicated asyncio task** that owns its transport and
  `ClientSession` for the whole process (tool calls are funnelled through a
  queue). Entering/closing the anyio context managers in a *single* task is
  required — doing so across tasks raises "Attempted to exit cancel scope in a
  different task". Startup waits up to `ODIN_MCP_STARTUP_TIMEOUT` (default 8s)
  per server, then continues.

> **SECURITY INVARIANT — do not weaken**: MCP tools execute in an **external
> process that `PathGuard` cannot inspect**, so every MCP tool call requires
> explicit user approval by default (the same `permission_requests` row +
> `permission_request` WebSocket event + `permission_manager.request_approval`
> flow as `execute_command`). Only servers marked `"trusted": true` in
> `ODIN_MCP_SERVERS` skip that blanket approval — and even then, any declared
> path-like argument is still classified by the shared `SecurityPolicy`, so the
> workspace boundary holds. `McpToolAdapter` assumes `OperationType.EXECUTE`
> unless the MCP tool advertises `readOnlyHint`. Tool names are namespaced
> `mcp__<server>__<tool>` so they cannot collide with native tools. Guarded by
> `backend/tests/test_mcp.py`.

## Testing

- Tests live in `backend/tests/`. Run with: `cd backend && .venv/bin/pytest tests/ -v`
- Test modules: `test_security.py` (PathGuard + policy + command policy), `test_providers.py` (provider contract, tool registry bridge, tool-call history, factory, env config), `test_litellm_provider.py` (the LiteLLM adapter: message/tool conversion, streamed tool-call accumulation, provider-extra round-trip, fake backend), `test_providers_catalog.py` (catalog, availability, model discovery, active selection), `test_auth_session.py` (session signer + login route + middleware), `test_cli_config.py`, `test_briefing.py`, `test_projects.py` (project/task CRUD + workspace path-traversal guards). The full suite runs in a couple of seconds without any network access.
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
| `GET /api/health` | Returns status, model_provider, model, workspace, tools_count, agent_ready, auth_required (public) |
| `POST /api/auth/login` | Log in with `{"token": "<ODIN_API_TOKEN>", "remember": true}`; returns a signed session token (public) |
| `GET /api/auth/session` | Describe the presented credential (`method`, `expires_at`); requires auth |
| `GET /api/ws/{conv_id}` | WebSocket chat endpoint (stream events: text_chunk, tool_start, tool_end, done, error) |
| `GET /api/conversations` | List conversations |
| `POST /api/conversations` | Create a new conversation (⚠️ **no trailing slash** — `POST /api/conversations/` returns 405) |
| `GET /api/conversations/{id}` | Get a conversation |
| `DELETE /api/conversations/{id}` | Delete a conversation |
| `GET /api/conversations/{id}/messages` | Get messages for a conversation |
| `GET /api/system` | System info (psutil: cpu, memory, disk, uptime) — **requires psutil** |
| `GET /api/briefing` | Aggregated daily briefing (weather, git, recent files, system, runtime, permissions, recent conversations) plus `should_show` for the boot-once modal |
| `POST /api/briefing/summary` | Generate a short LLM narrative of the briefing (`{"summary": null}` when no provider/agent is available) |
| `POST /api/briefing/ack` | Mark this boot's briefing as shown so it does not reappear (persists the current `boot_time` in `app_state`) |
| `GET /api/tools` | List registered tools |
| `GET /api/skills` | List skill groupings (Filesystem, Development, System, ...) over registered tools |
| `GET /api/providers` | List LLM providers (availability + models) and the active selection |
| `POST /api/providers/select` | Switch the active provider/model at runtime (body: `{"provider": "...", "model": "..."}`) |
| `GET /api/mcp` | Live status of configured MCP servers (connected/error + `tool_count`, `transport`, `trusted`) |
| `GET /api/permissions` | List all permission requests |
| `GET /api/permissions/pending` | List pending permission requests |
| `POST /api/permissions/{id}/approve` | Approve a permission request |
| `POST /api/permissions/{id}/deny` | Deny a permission request |
| `GET/POST /api/projects` | List / create projects |
| `GET/PATCH/DELETE /api/projects/{id}` | Read / update / delete a project (delete also removes its workspace directory) |
| `GET/POST /api/projects/{id}/tasks` | List / create tasks (the same rows power the TODO list and the Kanban) |
| `PATCH/DELETE /api/tasks/{task_id}` | Update (title, status, priority, position) / delete a task |
| `POST /api/projects/{id}/tasks/reorder` | Bulk-persist Kanban column/order after a drag-and-drop |
| `GET/POST /api/projects/{id}/files` | List / upload workspace files (multipart `file` + form field `path`) |
| `GET /api/projects/{id}/files/download` | Download a workspace file (`?path=`) |
| `POST /api/projects/{id}/files/mkdir` | Create a workspace directory |
| `DELETE /api/projects/{id}/files` | Delete a workspace file or directory (`?path=`) |

> **Beware the SPA fallback**: `main.py` registers a catch-all `GET /{full_path:path}` that returns `index.html` with **HTTP 200** for any unmatched path. A typo'd API route (e.g. the old `GET /api/system/info`) therefore returns HTML — not a 404 — so always verify the endpoint exists in `/openapi.json` (the catch-all is excluded from the schema).

> **Daily briefing (boot-once)**: The briefing is meant to appear **once per boot**. `GET /api/briefing` compares the current `psutil.boot_time()` against the value stored in the `app_state` table (key `last_briefing_boot`) and returns `should_show`; the panel acknowledges it via `POST /api/briefing/ack`, which writes the current boot_time so subsequent loads return `should_show: false` for the same boot. On the frontend the modal lives in `AppLayout.tsx` (not a page), auto-opens on first load over the default Dashboard route, and is also re-openable from the command palette ("Show daily briefing"). The briefing contract is frozen in `frontend/src/types/briefing.ts` and must mirror `backend/app/api/routes/briefing.py`.

## Projects (TODO / Kanban / workspace)

The **Projects** tab lets the user organise projects. Each project has three views that share one data model:

- **TODO list** and **Kanban board** are two renderings of the same `tasks` rows: `status` (`todo` | `doing` | `done`) is the Kanban column and `position` orders cards within a column. Editing a task in one view is reflected in the other.
- **Workspace** is an on-disk folder for arbitrary files (drag-and-drop upload, folder creation, download, delete).

Key facts:

- Project files live at `<ODIN_WORKSPACE>/projects/<slug>/`. Because they are inside the security boundary, the agent's filesystem tools can also read/write them (the daily briefing's "recent files" scan will surface them too).
- The project root directory is created on project creation and removed (with its contents) when the project is deleted.
- All file paths are resolved canonically and validated by `resolve_path` in `backend/app/projects/service.py`: absolute paths and `..` traversal are rejected, and nothing may escape the project root. The `slug` is generated from the name (lowercased, non-alphanumerics → `-`, `-2`/`-3` suffix on collision) by `slugify`.
- **All project domain logic lives in `backend/app/projects/service.py`**, which is the single source of truth for both the REST routes (`app/api/routes/projects.py` is a thin wrapper) and the agent tools (`app/tools/projects/tools.py`). Service functions raise `fastapi.HTTPException` for expected failures (400/404/409); the tools catch them and return `ToolResult(success=False, error=...)`.
- The 15 project tools are created by `create_project_tools(security_policy)` and registered in the lifespan. They reference a project by **id, slug or (unambiguous) name** (`service.get_project_by_reference`) and a task by **id or (unambiguous) title**; ambiguous references return an error listing the candidates. They all operate inside `ODIN_WORKSPACE`, so the security policy returns ALLOW and no approval is requested.
- Uploads require **`python-multipart`** (added to `backend/requirements.txt`); re-run `pip install -r requirements.txt` after pulling if it is missing.
- The routers are registered in `main.py` as `app.include_router(projects.router, prefix="/api", tags=["projects"])` — note the `/api` prefix plus full paths inside the module (`/projects`, `/tasks/{task_id}`), unlike the other routers which pass a resource-specific prefix.
- Frontend: pages `ProjectsPage.tsx` (grid) and `ProjectDetailPage.tsx` (tabs), components under `frontend/src/components/projects/`, types in `types/project.ts`, API client in `api/projects.ts`. The API client gained `patch` and a multipart `upload` helper. The Kanban uses **native HTML5 drag & drop** (no DnD library). The sidebar item is `Projetos` and the page jump shortcut is now `1–7`.

## Database

- SQLite async (SQLAlchemy) — file is `odin.db` at the repo root.
- On every startup, `init_db()` creates tables if they don't exist (`backend/app/database/session.py`).
- Tables: `conversations`, `messages`, `permission_requests`, `app_state` (generic key/value store; holds `last_briefing_boot` for the boot-once briefing), `projects`, `tasks`.
- Use `get_db_session()` (context manager) or `get_db()` (FastAPI dependency) for DB access.
- Permission requests are the mechanism that blocks/unblocks filesystem/shell operations outside the workspace.

## Architecture notes (what changes real behavior)

1. **Lifespan in `main.py`** is the single entry point for startup init: DB init → security init → tool registration → LLM provider init → agent init. If you add a tool, you must register it here (in `create_filesystem_tools` or manually).

2. **Provider factory** (`factory.py`) is the only place that maps `ODIN_MODEL_PROVIDER` → concrete provider. Since the LiteLLM migration it builds one `LiteLLMProvider` for every vendor; adding a provider means adding a `ProviderMeta` to `catalog.py`, not editing the factory.

3. **Security policy** (`policy.py`) determines what the agent is allowed to do. The agent will not execute a tool if the policy denies it. If you need to change what's "safe", edit `SAFE_DEV_EXECUTABLES`, `PRIVILEGED_EXECUTABLES`, etc.

4. **Permission flow**: When the agent tries a WRITE/DELETE/MOVE/EXECUTE outside the workspace, it yields a `permission_request` event. The UI must call `/api/permissions/{id}/approve` or `/api/permissions/{id}/deny` to unblock the agent.

   > **The approval UI only appears if the agent actually calls the tool.** The tools create the DB row and broadcast `permission_request` from *inside* `_request_permission`. If the LLM instead asks the user for permission in prose ("I need your authorization — shall I proceed?"), no request exists, so the web/mobile Approve/Deny buttons never render. This is why the system prompt (`agent/prompts/system.py`) and the tool descriptions spell out that the model must **invoke the tool directly and never ask for confirmation in chat** — do not reword them back to "state the reason when requesting approval". Guarded by `tests/test_prompts.py::test_system_prompt_keeps_hitl_contract`.

5. **WebSocket chat** (`api/routes/chat.py`) is the real-time streaming endpoint. Clients send `{"type": "message", "content": "..."}` and receive events including `tool_start`/`tool_end`. The agent's `chat()` method yields these events.

## Authentication (optional, for LAN / mobile)

- `ODIN_API_TOKEN` (empty by default = **disabled**) adds a bearer-token gate to the API. When set, every `/api/*` request must send `Authorization: Bearer <token>`; `/api/health` and `POST /api/auth/login` are exempt. WebSocket clients that cannot set headers pass `?token=<token>` on `/api/ws/{id}` instead.
- **Web panel login**: the panel exchanges `ODIN_API_TOKEN` for a signed, expiring **session token** via `POST /api/auth/login` (`{"token": "...", "remember": true}`), so the raw token never lives in `localStorage`. Session tokens are HMAC-SHA256 signed (`backend/app/security/session.py`, stdlib only — no PyJWT, no server-side store) and are accepted anywhere the raw token is. TTL: `ODIN_SESSION_TTL_DAYS` (7) with "remember me", else `ODIN_SESSION_TTL_HOURS` (12). Signing secret = `ODIN_SESSION_SECRET` or, if empty, `ODIN_API_TOKEN` (rotating it invalidates all sessions). `GET /api/auth/session` reports the presented credential; `/api/health` exposes `auth_required` so the frontend knows whether to show the login screen.
- Frontend: gate lives in `frontend/src/App.tsx` (`AuthGate`), state in `frontend/src/auth/AuthContext.tsx`, UI in `frontend/src/pages/LoginPage.tsx`, storage in `frontend/src/api/session.ts`. A `401` (or WebSocket close `1008`) dispatches `odin:unauthorized` and drops the panel back to the login screen. The legacy `localStorage['odin_api_token']` still works as a fallback credential.
- **The exposure guard makes the token effectively mandatory for any non-loopback bind**: `main.py` refuses to start if `ODIN_HOST` is not loopback and the token is empty. So for a LAN bind (`ODIN_HOST=0.0.0.0`) or a public host you *must* set `ODIN_API_TOKEN`. For the recommended hosting setup the backend stays on `127.0.0.1` and the token is still set as defense in depth (see `README.deploy.md`).
- Implemented in `backend/app/security/auth.py` (`TokenAuthMiddleware`, `PUBLIC_PATHS`, constant-time compare, plus a `_FailureLimiter` that returns `429` after repeated wrong tokens — the login route runs its own limiter since it is public). It is registered **before** `CORSMiddleware` in `main.py` on purpose: Starlette makes the **last**-added middleware the outermost, so CORS stays outside the gate and answers preflight `OPTIONS` without an `Authorization` header (adding auth *after* CORS is the bug — the preflight would 401).
- Clients: the mobile app stores the raw token in its Connect/Settings screen; the web panel stores the session token (`odin_session` in `localStorage`) and only sends the raw token once, at login.
- Reaching the backend from a phone on the LAN requires `ODIN_HOST=0.0.0.0` — pair it with a token (or, preferably, use a Cloudflare tunnel and keep it loopback).
- `scripts/server.sh` (used by `odin start/restart`) reads `ODIN_HOST`/`ODIN_PORT` **from the repo `.env`** (falling back to an exported shell var, then `127.0.0.1:8000`). So setting `ODIN_HOST=0.0.0.0` in `.env` and running `odin restart` is enough — no manual `export` needed.
- **CORS is only a browser concern** (Vite web panel, Expo **web**). Native Expo Go does not enforce it; its failure mode is `java.net.ConnectException ... 127.0.0.1:8000`, which means the app is still pointing at `127.0.0.1` instead of the machine's LAN IP (`hostname -I`). Set the app's server URL to `http://<lan-ip>:8000`. The allowed origins/regex live in `settings.odin_cors_origins` / `odin_cors_origin_regex` (`main.py`); the defaults include `:3000` (Vite) and `:8081` (Expo web) plus any private-LAN origin.

## Mobile app (`mobile/`)

Expo (SDK 57) + React Native + Expo Router + NativeWind client mirroring the web panel (Dashboard, Chat, Projects TODO/Kanban/Workspace, Permissions, Tools, Skills, System, Settings). It has its own toolchain and `mobile/AGENTS.md`; run its commands from `mobile/` (`npx expo start`, `npx tsc --noEmit`, `npx expo lint`, `npx expo-doctor`). It is **not** part of the Vite build and is not served by the backend.

- First launch shows a `connect` screen (server URL + optional token), persisted via AsyncStorage (`src/lib/config.ts`); the root `Stack.Protected` guard in `src/app/_layout.tsx` reveals the `(tabs)` navigator once configured.
- Kanban uses real cross-column drag & drop via `react-native-reanimated-dnd` (Draggable cards + Droppable columns); precise ordering lives in the TODO view.
- Binaries are built with EAS (`mobile/eas.json`): `npx eas-cli@latest build --profile preview` (Android APK) / `production` (AAB + iOS). `ios/` and `android/` are CNG-generated — never edit them by hand.