web application/stitch/projects/15391610934161767904/screens/ebfb06d5449340ee9fb07ce77849fecd
# Documento de Requisitos de Produto (PRD) & Design Brief
**Projeto:** ODIN — Personal AI Operating Assistant & Local Console  
**Versão:** 1.0.0 (MVP)  
**Status:** Aprovado para Desenvolvimento Frontend  
**Autor:** Design & Product Architecture  

---

## 1. Visão Geral do Produto

### 1.1 Declaração de Missão
O **ODIN** é um assistente operacional de inteligência artificial local concebido para atuar como o cérebro supervisor de tarefas de engenharia de software, automação de ambiente, governança de ferramentas e inspeção de código em máquina local. Inspirado filosoficamente no conceito de computação assistiva omnipresente (como o JARVIS), o ODIN substitui a interface tradicional de "chat de perguntas e respostas" por um **console operacional unificado**, onde execução de ferramentas, monitoramento de recursos de hardware e governança de permissões ocorrem em um mesmo plano de comando.

### 1.2 Objetivos do MVP
- **Interface Tática e Funcional:** Proporcionar uma visão em tempo real do estado do agente supervisor, da telemetria da máquina e da timeline de atividades.
- **Transparência de Execução de Ferramentas:** Renderizar chamadas de sub-processos (ex.: `read_file`, `analyze_ast`, scripts bash, MCPs) com clareza técnica imediata (status de saída, tempo de execução, diff de código).
- **Segurança Zero-Trust Local:** Permitir que o operador humano audite e autorize ações críticas de modificação no disco (`write_file`, comandos destrutivos) com um único clique ou rejeição explícita.
- **Separação Rígida Frontend-Backend:** Desenvolver um frontend moderno, decoupled e orientado a contratos de API REST/WebSockets, viabilizando integração rápida com daemons locais desenvolvidos em Python, Go, Rust ou Node.js.

---

## 2. Personas e Casos de Uso

### 2.1 Persona Principal: Engenheiro de Software / Power User Local ("Cauã")
- **Contexto:** Desenvolve em múltiplas linguagens (TypeScript/Next.js, Python), utiliza modelos locais (Ollama, vLLM) e APIs remotas de alta capacidade (Claude 3.7 Sonnet).
- **Necessidades:**
  - Diagnosticar bugs complexos analisando árvores de arquivos locais sem precisar sair do fluxo.
  - Saber exatamente quais arquivos o agente está lendo ou modificando.
  - Manter controle de uso de hardware (CPU, VRAM da GPU, temperatura e memória).
  - Executar comandos com atalhos de teclado rápidos (HUD/Terminal pattern).

### 2.2 Principais Casos de Uso
1. **Diagnóstico & Reparo Autônomo de Código:** O operador aponta um repositório (`/home/caua/FnCash`) e um problema; o Odin lê a árvore de arquivos, identifica a falha e sugere/aplica patches com revisão de diff.
2. **Auditoria de Permissões Críticas:** Ações que modificam o filesystem fora da sandbox disparam alertas que exigem autorização explícita do operador antes da execução.
3. **Telemetria e Inspeção de Saúde:** Monitoramento em background do heartbeat do agente supervisor, latência de inferência e capacidade de tokens da janela de contexto.

---

## 3. Arquitetura de Informação & Mapa de Navegação

A navegação persistente do sistema é ancorada em uma barra lateral fixa (desktop) e cabeçalho de status em tempo real:

```
[ODIN v0.9.4 Kernel] ────────────────────────── [Status: Online | 18:42:32 UTC]
│
├── /dashboard       -> Painel do Sistema (Visão Geral, Recursos, Timeline)
├── /chat            -> Console Conversacional Tático & Execução de Tools
├── /tools           -> Catálogo de Ferramentas Registradas e RPCs Ativos
├── /skills          -> Módulos Especialistas de Conhecimento Habilitados
├── /mcp             -> Conexões e Servidores Model Context Protocol
├── /permissions     -> Fila de Autorizações e Políticas de Segurança Local
└── /settings        -> Configurações de Modelos, Chaves de API e Workspaces
```

---

## 4. Especificação Funcional das Telas Principais

### 4.1 Dashboard Operacional (`/dashboard`)
* **Header de Contexto:** Identificador do nó ativo (`NODE_01`), status do supervisor autônomo, seletor de workspace (`/home/caua/odin-workspace`) e botão de interrupção geral (*Kill-switch*).
* **Card de Alerta de Permissão Crítica:**
  - Destaque em âmbar para ações pendentes de autorização.
  - Exibição de comando, path afetado, delta de linhas e botões diretos: `Autorizar Ambas`, `Permitir`, `Recusar`.
* **Grid de Status de Agente & Inferência (6 Módulos):**
  1. *Núcleo Autônomo:* Status do ciclo de heartbeat (100ms ± 2ms).
  2. *Motor de Inferência:* Modelo principal (Claude 3.7 Sonnet) com fallback configurado (Ollama local / qwen2.5:14b) e janela de contexto utilizada (12.4k / 200k).
  3. *Estado Operacional:* Status das threads de trabalho alocadas em pool.
  4. *Espaço Raiz:* Contagem de artefatos rastreados no Git e política de isolamento.
  5. *Toolchain:* Total de ferramentas RPC ativas (`fs.*`, `bash`, `git`, `code_search`, `lsp`).
  6. *Governança Zero-Trust:* Total de ações validadas na sessão e módulos de guarda ativos.
* **Telemetria de Hardware & Host (Monitor Lateral/Inferior):**
  - Gráficos sparkline para uso de CPU (AMD Ryzen 9 7950X, temperatura e frequência de clock).
  - Medidor de memória RAM & VRAM (NVIDIA RTX 4090 alocada).
  - Armazenamento NVMe e taxa de I/O em tempo real.
* **Linha do Tempo de Atividades Recentes:**
  - Stream de logs em tempo real categorizados por tipo (`TOOL_EXEC`, `THREAD_SYNC`, `PERMISSAO`, `HABILIDADE`, `DAEMON`, `AUDITORIA`).
  - Identificação de timestamp preciso e links para histórico completo.

### 4.2 Console de Chat Operacional (`/chat`)
* **Barra de Metadados da Sessão:** Thread ativa (`#049`), título da tarefa de diagnóstico, botões `+ Nova Conversa` e `Exportar Logs`.
* **Métricas da Thread:** Indicadores rápidos de arquivos indexados no contexto, latência de inferência do motor, velocidade de geração de tokens (tok/s) e modo de proteção do filesystem (`Read / Guarded`).
* **Área de Diálogo & Mensagens:**
  - *Mensagem do Operador:* Alinhada à direita, cartão discreto em tom carvão sem ruído gráfico.
  - *Mensagem do Odin:* Alinhada à esquerda, com metadados de inferência e tokens gastos.
  - *Card de Execução de Ferramentas:* Bloco especializado exibindo ferramenta acionada (`read_file`, `analyze_ast`), tempo de execução, caminho do arquivo e snippet de código com marcação e destaque semântico.
  - *Ações do Agente:* Botões contextuais de aprovação de execução (`Aplicar patch via write_file`, `Ver diff`, `Executar testes`).
* **Input de Comando (Terminal HUD / Floating Capsule):**
  - Campo de entrada com atalhos de autocompletar (`/inspect`, `/run-tests`, `/clear`).
  - Contagem de contexto consumido em tempo real.
  - Indicador de modelo ativo e botão de disparo com tecla de atalho (`Shift + Enter` para nova linha, `Enter` para envio).

---

## 5. Diretrizes de Design & Identidade Visual

O ODIN suporta duas linhagens estéticas refinadas criadas no projeto:
1. **Linhagem A — Tactical HUD Operating System:** Linhas técnicas precisas, divisores finos, acentos em laranja âmbar tático (`#FF7A00`), tipografia monoespaçada visível e estilo de console de inteligência militar.
2. **Linhagem B — Obsidian Serenity (Minimal Orgânico):** Cantos arredondados contínuos (`rounded-2xl` e pílulas), curvas suaves, fundo obsidian escuro profundo (`#131316`), acentos aveludados e sensação de calm tech sofisticada.

### 5.1 Tokens de Cor Fundamentais
* **Backgrounds Primários:** `#050505`, `#0A0A0A`, `#0E0E11`
* **Superfícies & Cartões:** `#131316`, `#1B1B1E`, `#222226`
* **Acento Primário (Identidade Odin):** `#FF7A00` / `#FF8A3D` (Laranja Âmbar — reservado para status ativos, ações principais, cursores e indicadores luminosos)
* **Texto Primário:** `#F5F5F5` (Alto contraste e legibilidade)
* **Texto Secundário / Labels:** `#8E8E93` e `#52525B`
* **Bordas Estruturais:** `rgba(255, 255, 255, 0.08)` a `rgba(255, 255, 255, 0.12)`

### 5.2 Tipografia
* **Interface Geral:** Inter / Geist Sans (11px a 18px, pesos Regular e Medium).
* **Dados Técnicos, Código e Logs:** JetBrains Mono / Fira Code (11px a 13px com tracking reduzido).

---

## 6. Contrato de Integração do Frontend (API Mocking & Real-Time)

Para conectar o frontend ao backend local, as seguintes interfaces de dados e eventos foram preparadas:

### 6.1 Endpoints REST Esperados
- `GET /api/v1/system/status` — Retorna uso de CPU, RAM, VRAM, disco, temperatura e uptime.
- `GET /api/v1/agent/state` — Retorna heartbeat, modelo ativo, fallback e permissões pendentes.
- `GET /api/v1/activity/timeline` — Lista os últimos eventos de execução do agente.
- `POST /api/v1/permissions/authorize` — Payload `{ actionId: string, decision: 'allow' | 'deny' }`.
- `POST /api/v1/chat/threads` — Inicia nova thread de execução.

### 6.2 Canais WebSocket / SSE
- `ws://127.0.0.1:8080/events`
  - Evento `tool_call_start`: Dispara o skeleton card no chat.
  - Evento `tool_call_completed`: Atualiza o snippet com resultado e status.
  - Evento `token_stream`: Renderiza texto em tempo real sem travamentos de DOM.
  - Evento `hardware_tick`: Atualiza sparklines a cada 1 segundo.

---

## 7. Roadmap de Versões Futuras

* **Fase 1 (Atual - MVP Frontend):** Estrutura completa de Dashboard e Chat Console com variações tática HUD e orgânica minimalista.
* **Fase 2 (Conectividade Local):** Integração com daemon local em WebSocket/gRPC e mock de servidor Ollama/Claude.
* **Fase 3 (Telas Secundárias):** Visualizador interativo de servidores MCP, gerenciador de habilidades dinâmicas e painel avançado de configurações de chaves.
* **Fase 4 (Mobile/Companion App):** Visualização compacta e drawer responsivo para monitoramento remoto de tarefas longas do agente.
