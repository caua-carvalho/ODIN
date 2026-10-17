# Odin — Assistente pessoal de IA

Odin é um assistente pessoal de IA que roda **na sua máquina** e, diferente de um
chat comum, **age**: ele lê e escreve arquivos, executa comandos e organiza
projetos por meio de ferramentas. Tudo passa por um portão de segurança que
limita o que o agente pode fazer fora do *workspace* configurado.

Principais recursos:

- **Chat com ferramentas** (function calling) através de um backend FastAPI e um
  WebSocket de streaming.
- **Briefing diário** — clima, estado dos repositórios git, arquivos recentes,
  sistema, permissões pendentes e conversas recentes, mostrado uma vez por boot
  no painel.
- **Painel web** (React/Vite) servido pelo próprio backend, em
  `http://127.0.0.1:8000`.
- **App mobile** (Expo/React Native) espelhando o painel.
- **Projetos** com lista TODO, quadro Kanban e um *workspace* em disco para cada
  projeto.
- **Múltiplos provedores de LLM** via [LiteLLM](https://github.com/BerriAI/litellm)
  (gemini, groq, ollama, openai, anthropic), com troca em tempo de execução.
- **Servidores MCP** opcionais e **memória de longo prazo** opt-in (Mem0).

> Segurança em primeiro lugar: o backend sobe em **loopback** e, para acesso
> externo, é exposto por um túnel de saída (Cloudflare/Tailscale) — nunca
> abrindo portas de entrada. Veja [`README.deploy.md`](README.deploy.md).

## Índice

- [O que é o Odin](#o-que-é-o-odin)
- [Quickstart](#quickstart)
- [Arquitetura resumida](#arquitetura-resumida)
- [Providers LLM](#providers-llm)
- [Segurança](#segurança)
- [Testes](#testes)
- [Memória de longo prazo (opt-in)](#memória-de-longo-prazo-opt-in)
- [Contribuindo](#contribuindo)

## O que é o Odin

O Odin é composto por um agente que conversa com um modelo de linguagem e decide
quando chamar ferramentas. As ferramentas nativas cobrem o sistema de arquivos
(`read_file`, `write_file`, `list_directory`, `search_files`, `move_file`, …), a
execução de comandos (`execute_command`) e o gerenciamento de projetos/tarefas.
Ferramentas de servidores MCP externos podem ser plugadas sem alterar o código.

O usuário interage por três clientes:

- **Painel web** em `http://127.0.0.1:8000` (a interface principal).
- **App mobile** (Expo) para uso pelo celular.
- **CLI** no terminal (`odin`, sem argumentos), com os comandos `/help`,
  `/clear`, `/model` e `/models` dentro da sessão.

## Quickstart

Pré-requisitos:

- **Python 3.10+** (o setup cria a venv com `python3 -m venv`)
- **Node.js + npm** (para o painel web)
- **git**
- Uma **chave de API** de pelo menos um provedor de LLM (ou um
  [Ollama](https://ollama.com) local, que não exige chave)

Passo a passo, a partir da raiz do repositório:

```bash
# 1. Dependências do backend, do frontend e cria o .env / o workspace
./scripts/setup.sh

# 2. Edite o .env e informe a chave do provedor escolhido
#    (mínimo obrigatório: ODIN_MODEL_PROVIDER, ODIN_MODEL e a chave / OLLAMA_BASE_URL)
$EDITOR .env

# 3. Instala dependências e builda o painel para frontend/dist
./scripts/build.sh

# 4. Sobe o backend
odin start            # ou: ./scripts/odin.sh start
```

Depois acesse o painel em **http://127.0.0.1:8000**.

O `.env` é **obrigatório** e é git-ignorado. O `setup.sh` copia
[`.env.example`](.env.example) → `.env`; edite-o antes de subir o backend. Sem
uma chave/URL de provedor válida a aplicação não inicia. Para começar rápido com
o Gemini (o padrão do `.env.example`):

```ini
ODIN_MODEL_PROVIDER=gemini
ODIN_MODEL=gemini-2.5-flash
GEMINI_API_KEY=<sua-chave>
```

Comandos úteis (implementados em [`scripts/odin.sh`](scripts/odin.sh)):

| Comando | O que faz |
|---|---|
| `odin start` / `odin stop` / `odin restart` | Sobe / para / reinicia o backend |
| `odin status` | Mostra status, PID e URL do backend |
| `odin logs` / `odin logs --follow` | Mostra (ou acompanha) o log em `~/.local/state/odin/server.log` |
| `odin` (sem argumentos) | Abre o chat interativo no terminal |

> O comando `odin` é um lançador fino para `scripts/odin.sh`. Se ele não estiver
> no `PATH`, use `./scripts/odin.sh start` (e equivalentes) diretamente.

**Desenvolvimento** (recarregamento automático):

```bash
# backend
cd backend && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
# painel (Vite em http://localhost:3000, com proxy /api -> 127.0.0.1:8000)
cd frontend && npm run dev
```

O backend serve o painel a partir de `frontend/dist`; depois de mudar o frontend,
rode novamente `./scripts/build.sh` (ou `npm run build` em `frontend/`) para que a
versão servida reflita a mudança.

## Arquitetura resumida

```
odin/
├── backend/     API FastAPI + agente + banco SQLite
├── frontend/    Painel web (React + Vite + Tailwind)
├── mobile/      App mobile (Expo / React Native)
├── deploy/      Unit systemd de hospedagem + exemplos de túnel
└── scripts/     setup, build, start/stop, backup, túneis, autostart
```

**Backend** ([`backend/`](backend/)) — FastAPI/uvicorn. O *lifespan* em
[`backend/app/main.py`](backend/app/main.py) é o ponto único de inicialização:
banco → segurança → registro de ferramentas → provider de LLM → agente.

- [`backend/app/agent/`](backend/app/agent/) — o loop do agente e os provedores
  ([`providers/`](backend/app/agent/providers/)), servidores MCP
  ([`mcp/`](backend/app/agent/mcp/)) e memória de longo prazo
  ([`memory/`](backend/app/agent/memory/)).
- [`backend/app/tools/`](backend/app/tools/) — ferramentas nativas (filesystem,
  shell, projetos) expostas ao modelo.
- [`backend/app/security/`](backend/app/security/) — [`path_guard.py`](backend/app/security/path_guard.py),
  [`policy.py`](backend/app/security/policy.py), [`auth.py`](backend/app/security/auth.py)
  e [`session.py`](backend/app/security/session.py).
- [`backend/app/api/routes/`](backend/app/api/routes/) — rotas REST e o WebSocket
  de chat (`/api/ws/{id}`).
- [`backend/app/database/`](backend/app/database/) — SQLAlchemy assíncrono sobre
  SQLite (`odin.db` na raiz do repositório).
- [`backend/app/cli/`](backend/app/cli/) — o chat de terminal.

**Frontend** ([`frontend/`](frontend/)) — React 19 + Vite + Tailwind. O build
gera `frontend/dist`, que o backend monta em `/` (com *fallback* SPA para
`index.html`), de modo que o painel vive na mesma origem da API.

**Mobile** ([`mobile/`](mobile/)) — Expo (SDK 57) + React Native + Expo Router,
com telas equivalentes ao painel (Dashboard, Chat, Projetos, Permissões,
Ferramentas, Skills, Sistema e Configurações). Tem toolchain própria; veja
[`mobile/README.md`](mobile/README.md) e [`mobile/AGENTS.md`](mobile/AGENTS.md).

## Providers LLM

Todos os provedores são atendidos por **um único** adaptador baseado em LiteLLM
([`backend/app/agent/providers/litellm_provider.py`](backend/app/agent/providers/litellm_provider.py)).
O catálogo de provedores — disponibilidade e modelos — fica em
[`backend/app/agent/providers/catalog.py`](backend/app/agent/providers/catalog.py).

| Provedor | `ODIN_MODEL_PROVIDER` | Credencial / URL | Modelo padrão |
|---|---|---|---|
| Google Gemini | `gemini` | `GEMINI_API_KEY` | `gemini-2.5-flash` |
| Groq | `groq` | `GROQ_API_KEY` (+ `GROQ_BASE_URL`) | `openai/gpt-oss-120b` |
| Ollama (local) | `ollama` | `OLLAMA_BASE_URL` (padrão `http://localhost:11434`), sem chave | `qwen3:0.6b` |
| OpenAI | `openai` | `OPENAI_API_KEY` | `gpt-4o-mini` |
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY` | `claude-3-5-haiku-latest` |

Configuração no `.env`:

```ini
ODIN_MODEL_PROVIDER=groq
ODIN_MODEL=openai/gpt-oss-120b
GROQ_API_KEY=<sua-chave>
```

`ODIN_MODEL` é o id do modelo no fornecedor; o prefixo do LiteLLM é adicionado
automaticamente (`gemini-2.5-flash` → `gemini/gemini-2.5-flash`; ids da Groq já
contêm `/`, então `openai/gpt-oss-120b` → `groq/openai/gpt-oss-120b`). Um modelo
já prefixado é mantido como está. Adicionar um provedor novo é só acrescentar um
`ProviderMeta` ao catálogo — não há classe de adaptador nova.

**Troca em tempo de execução:** o provedor/modelo ativo pode ser mudado sem
reiniciar, pelo seletor da barra superior do painel ou pelo comando `/model` da
CLI (`POST /api/providers/select`). A troca é **somente em memória** — reiniciar
o backend volta ao que está no `.env`.

## Segurança

Todo acesso a arquivos e shell passa por um **portão de segurança** (o agente
recusa operações que escapam do *workspace*).

- **Workspace** (`ODIN_WORKSPACE`, padrão `/home/caua/odin-workspace`): operações
  **dentro** dele são liberadas. Fora, leitura é negada e escrita/exclusão/
  movimentação/execução **exigem aprovação**.
- **Política de aprovações** — [`backend/app/security/policy.py`](backend/app/security/policy.py)
  classifica cada operação como `ALLOW`, `REQUIRE_APPROVAL` ou `DENY`. Comandos
  privilegiados (`sudo`, `apt`, `systemctl`, …) e comandos destrutivos / de rede
  (`rm`, `chmod`, `ssh`, `rsync`, `curl`, `wget`, …) **sempre** pedem aprovação.
  Uma execução fora do workspace gera um *permission request* no banco, enviado
  ao painel/app por um evento WebSocket; a operação só prossegue após
  approve/deny (`/api/permissions/{id}/approve` e `/api/permissions/{id}/deny`).
- **MCP** — ferramentas de servidores MCP rodam em processo externo que o
  `PathGuard` não enxerga, então **toda** chamada MCP pede aprovação por padrão.
  Só servidores marcados `"trusted": true` em `ODIN_MCP_SERVERS` pulam essa etapa.
- **Token e sessões** — `ODIN_API_TOKEN` (vazio por padrão = desabilitado) ativa
  um portão de token na `/api/*`. O painel troca o token por um **token de sessão**
  assinado (HMAC-SHA256), com TTL configurável, via `POST /api/auth/login`, para
  não guardar o token cru. O segredo de assinatura é `ODIN_SESSION_SECRET` ou,
  se vazio, derivado do `ODIN_API_TOKEN`.
- **Guarda de exposição** — o backend **se recusa a iniciar** se `ODIN_HOST` não
  for loopback e `ODIN_API_TOKEN` estiver vazio. Para bind de LAN
  (`ODIN_HOST=0.0.0.0`) ou host público, defina o token.
- **Rate limit** — tentativas de token erradas por cliente respondem `429` após
  `ODIN_AUTH_MAX_FAILURES` dentro de `ODIN_AUTH_WINDOW_SECONDS`.

Nunca versione valores reais de `ODIN_API_TOKEN` ou `ODIN_SESSION_SECRET`; use
`openssl rand -hex 32`. Os arquivos [`.env.example`](.env.example) e
[`.env.production.example`](.env.production.example) trazem **apenas
placeholders**.

Para hospedar (Cloudflare Tunnel, Tailscale Funnel, serviço systemd endurecido,
backup e checklist de verificação), siga o **[`README.deploy.md`](README.deploy.md)**.

## Testes

A suíte é rápida e não usa rede:

```bash
cd backend && .venv/bin/pytest tests/ -v
```

Smoke tests (verificação manual de que a aplicação sobe e conversa com o LLM —
não precisam de servidor rodando) ficam em [`backend/`](backend/):

```bash
cd backend
.venv/bin/python smoke_bootstrap.py   # bootstrap FastAPI com Ollama
.venv/bin/python smoke_agent.py       # loop completo do agente, com persistência
.venv/bin/python smoke_gemini.py      # round-trip do provedor Gemini
.venv/bin/python smoke_ollama.py      # round-trip do provedor Ollama
```

## Memória de longo prazo (opt-in)

O Odin pode lembrar de fatos entre conversas usando [Mem0](https://github.com/mem0ai/mem0),
**local-first**: tanto o LLM de extração quanto o *embedder* apontam para o seu
Ollama, e o *vector store* (Chroma) fica em disco — sem servidor e sem chave de
API. O código vive em [`backend/app/agent/memory/`](backend/app/agent/memory/).

É totalmente **opt-in e preguiçoso**: com `ODIN_MEMORY_ENABLED` desligado (o
padrão) o Mem0 nunca é importado e o agente se comporta como antes. Para ativar:

```bash
# dependências opcionais (não estão no requirements.txt base)
backend/.venv/bin/pip install -r backend/requirements-memory.txt
# modelos locais de exemplo
ollama pull qwen3:0.6b && ollama pull nomic-embed-text
```

```ini
ODIN_MEMORY_ENABLED=true
```

Em máquinas sem GPU, a extração local é pesada; use `ODIN_MEMORY_INFER=false`
para guardar os turnos crus e recordar por similaridade de embedding, ou aponte o
LLM de extração para um provedor hospedado com `ODIN_MEMORY_LLM_PROVIDER`. As
demais variáveis estão documentadas em [`.env.example`](.env.example) e em
[`backend/requirements-memory.txt`](backend/requirements-memory.txt).

## Contribuindo

Para trabalhar no código, leia o **[`AGENTS.md`](AGENTS.md)**: ele é o guia
detalhado do repositório (comandos, topologia de deploy, invariantes de segurança,
fluxo de permissões, artefatos de ferramentas e convenções de teste) e responde às
perguntas que não são óbvias só de olhar a árvore.

Resumo do fluxo:

1. Crie a venv e instale as dependências com `./scripts/setup.sh`.
2. Faça suas mudanças mantendo os testes verdes: `cd backend && .venv/bin/pytest tests/ -v`.
3. Se mexer no frontend, rebuilde com `./scripts/build.sh` para o painel servido
   refletir a mudança.
4. Siga as convenções existentes (a *fonte da verdade* de cada domínio está
   indicada no `AGENTS.md`).

Hospedagem e operação contínua são documentadas separadamente em
[`README.deploy.md`](README.deploy.md).
