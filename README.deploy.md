# Hospedando o Odin (Cloudflare Tunnel + domínio)

Odin executa comandos e mexe em arquivos, então a regra de ouro é: **ele nunca
escuta na internet**. O backend sobe em `127.0.0.1:8000` e é exposto por um
**Cloudflare Tunnel** (`cloudflared`), que abre uma conexão *de dentro para
fora*. Nenhuma porta de entrada é aberta e o TLS é automático.

```
Celular / navegador ──HTTPS──► Cloudflare (TLS + Access) ──túnel──► 127.0.0.1:8000
```

---

## Caminho mais rápido (5 minutos, sem domínio)

Dá acesso imediato pelo celular e pelo painel web, com URL temporária.

1. **Defina o token** (protege a `/api/*`). Sem ele, a API ficaria aberta:
   ```bash
   cp .env.production.example .env     # se ainda não tiver .env hospedável
   openssl rand -hex 32                # cole em ODIN_API_TOKEN no .env
   ./scripts/build.sh                  # instala deps + builda o painel
   odin start                          # ou: systemctl start odin.service
   ```
2. **Suba o túnel rápido:**
   ```bash
   ./scripts/cloudflared-quick-tunnel.sh
   ```
   Ele instala o `cloudflared` se necessário (em `~/.local/bin`, sem sudo) e
   imprime algo como `https://algo-aleatorio.trycloudflare.com`.
3. **Conecte os clientes:**
   - **Painel web:** abra a URL e, no console do navegador:
     ```js
     localStorage.setItem('odin_api_token', '<seu-token>')
     ```
   - **App mobile:** tela de Connect/Settings → Server URL = a URL do túnel +
     o mesmo token.

> A URL **muda** a cada reinício do `cloudflared` e não tem login do Cloudflare
> na frente — só o token. Bom para testar hoje; para uso contínuo, vá para o
> túnel nomeado abaixo.

---

## Acesso permanente SEM domínio (Tailscale Funnel)

Se você não tem domínio, o **Tailscale Funnel** dá uma URL pública **fixa e
grátis** (`https://<hostname>.<tailnet>.ts.net`), com HTTPS automático, sem
abrir porta nenhuma. Roda em modo *userspace* (não precisa de sudo/TUN) como
serviço `systemd --user` e, com `Linger=yes`, sobrevive a logout/reboot.

```bash
./scripts/tailscale-funnel-setup.sh          # ou: ./scripts/tailscale-funnel-setup.sh 8000
```

O script instala os binários do Tailscale em `~/.local/opt/tailscale`, cria o
unit `~/.config/systemd/user/tailscaled.service`, habilita-o e sobe o Funnel
para `127.0.0.1:<porta>`. Duas aprovações no navegador são pedidas na primeira
vez:

1. **Login do dispositivo** — o `tailscale up` imprime uma URL
   (`https://login.tailscale.com/a/...`); autorize a máquina na sua tailnet.
2. **Habilitar Funnel** — `https://login.tailscale.com/f/funnel?node=...`
   (beta, desabilitado por padrão; o fluxo também provisiona os certificados
   HTTPS e o MagicDNS).

Resultado: `https://odin.<sua-tailnet>.ts.net` → `http://127.0.0.1:<porta>`.
Use o mesmo `ODIN_API_TOKEN` como segunda camada de proteção.

```bash
~/.local/bin/tailscale serve status            # ver o Funnel ativo
~/.local/bin/tailscale funnel --https=443 off  # desligar
```

> O `README` principal de deploy usa o **Cloudflare Tunnel**; o Tailscale é a
> alternativa sem domínio. Ambos mantêm o backend em loopback.

---

## Túnel nomeado + domínio + Cloudflare Access (URL fixa e com login)

Pré-requisitos: domínio com os nameservers no Cloudflare (plano Free) e conta
Cloudflare Zero Trust (Access grátis até 50 usuários).

1. **Instale o cloudflared** (com sudo, agora que é permanente):
   ```bash
   curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | \
     sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
   echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" | \
     sudo tee /etc/apt/sources.list.d/cloudflared.list
   sudo apt update && sudo apt install -y cloudflared
   ```
2. **Autentique e crie o túnel:**
   ```bash
   cloudflared tunnel login
   cloudflared tunnel create odin
   cloudflared tunnel route dns odin odin.seudominio.com
   ```
3. **Configure o hostname** em `~/.cloudflared/config.yml` (use o UUID e o
   credentials.json impressos no passo anterior — veja
   `deploy/cloudflared-config.yml.example`):
   ```yaml
   tunnel: <UUID>
   credentials-file: /home/<user>/.cloudflared/<UUID>.json
   ingress:
     - hostname: odin.seudominio.com
       service: http://127.0.0.1:8000
     - service: http_status:404
   ```
4. **Rode como serviço:**
   ```bash
   sudo cloudflared service install
   sudo systemctl enable --now cloudflared
   ```
5. **Some `ODIN_CORS_ORIGINS`** no `.env` para a origem pública e reinicie o
   backend:
   ```
   ODIN_CORS_ORIGINS=https://odin.seudominio.com
   ```
6. **Ligue o login (Cloudflare Access):** Zero Trust → Access → Applications →
   *Add self-hosted* → domínio `odin.seudominio.com` → política `Allow` para o
   seu e-mail. Agora há uma tela de login antes mesmo de chegar no token do Odin.

WebSocket já funciona pelo túnel sem configuração extra (o chat usa
`/api/ws/{id}`).

---

## Rodar como serviço (systemd de sistema)

O unit de hosting reinicia sozinho e já vem **endurecido**: `ProtectSystem=strict`
(raiz de arquivos somente leitura), `ProtectHome`, `PrivateDevices`,
`RestrictNamespaces`, sem capabilities, `UMask=0077` e mais. Só o repositório e o
workspace ficam graváveis (`ReadWritePaths`).

```bash
sudo ./scripts/install-service.sh                 # usa ODIN_WORKSPACE do .env
# ou: sudo ./scripts/install-service.sh --user odin --workspace /var/lib/odin/workspace
./scripts/install-service.sh --print              # pré-visualiza o unit, sem sudo
systemctl status odin.service
journalctl -u odin.service -f
systemd-analyze security odin.service             # nota de exposição
```

> Não confunda com `scripts/install-autostart.sh`, que instala um unit
> `--user` para uso **local** (desktop/Hyprland). Use o `install-service.sh`
> para hospedagem.

### Usuário dedicado

O padrão é rodar como o usuário que invocou o `sudo` (prático em dev). Para
separar privilégios na hospedagem, crie uma conta dedicada e aponte o unit para
ela:

```bash
sudo useradd --system --home /var/lib/odin --create-home --shell /usr/sbin/nologin odin
sudo chown -R odin:odin . backend/.venv        # repo precisa ser legível/executável
sudo ./scripts/install-service.sh --user odin --workspace /var/lib/odin/workspace
```

O instalador escolhe `ProtectHome=true` (esconde `/home`, `/root` e `/run/user`)
quando o repositório e o workspace **não** estão sob `$HOME`; caso contrário usa
`ProtectHome=read-only`, porque `ReadWritePaths` não consegue abrir exceção
dentro de um `/home` escondido. Ele também adiciona a `ReadWritePaths` o
diretório de um `DATABASE_URL`/`ODIN_MEMORY_PATH` absoluto (senão
`ProtectSystem=strict` bloquearia a escrita do banco).

### O que o sandbox custa

Diretivas **de propósito não** aplicadas, para não conflitar com a função do
Odin (que executa comandos):

| Diretiva | Por que não |
|---|---|
| `PrivateNetwork` | o backend fala com o túnel em loopback e com as APIs dos LLMs |
| `PrivateUsers` | o agente roda comandos como o próprio usuário do serviço |
| `SystemCallFilter` | o agente executa ferramentas arbitrárias (`python`, `node`, `git`…); um filtro de syscalls quebraria casos legítimos |
| `RestrictAddressFamilies` | idem: comandos do agente usam Unix/netlink/inet |
| `MemoryDenyWriteExecute` | risco de quebrar bibliotecas com JIT/trampolines (`cffi`, numba) |
| `RootDirectory` | o agente precisa enxergar o workspace e o repo reais |

`RestrictNamespaces=true` **bloqueia docker/podman dentro do agente**; se
precisar, troque para `false` no `deploy/odin.service` e registre o motivo.
Com o sistema de arquivos só-leitura, caches de `pip`/`npm` sob `$HOME` falham —
aponte-os para um diretório gravável (linhas `#Environment=XDG_CACHE_HOME=…`
comentadas no final do unit).

---

## Segurança

- **Boot seguro:** o backend **se recusa a iniciar** se `ODIN_HOST` não for
  loopback e `ODIN_API_TOKEN` estiver vazio. Ou seja, um bind exposto sem token
  não sobe (`backend/app/main.py`).
- **Token:** obrigatório para hospedar. Gere com `openssl rand -hex 32`.
  Falhas repetidas de token por cliente retornam **429** (limite em
  `ODIN_AUTH_MAX_FAILURES` / `ODIN_AUTH_WINDOW_SECONDS`).
- **Segredo de sessão (`ODIN_SESSION_SECRET`):** assina os tokens de login do
  painel (issue #13). Deixe **vazio** para derivá-lo do `ODIN_API_TOKEN`, ou
  gere um próprio com `openssl rand -hex 32` para rotacionar o login do painel
  sem trocar o token da API. **NUNCA** versione um valor real: quem tem o
  segredo forja uma sessão válida sem saber o token. O startup avisa
  (`INSECURE CONFIGURATION`) se detectar um valor público/placeholder. Rotacionar
  o segredo — ou o token de que ele deriva — **invalida todas as sessões**
  existentes do painel (todos precisam logar de novo).
- **Comandos perigosos agora exigem aprovação** (`backend/app/security/policy.py`):
  `rm`, `rmdir`, `chmod`, `chown`, `chgrp`, `truncate` (destrutivos), `ssh`,
  `scp`, `sftp`, `rsync`, `nc`, `ncat`, `telnet` (remotos) e `curl`, `wget`
  (rede). Eles pedem approve no painel/app em vez de rodar direto. Só `git`,
  `python`, `node`, `npm`, etc. continuam automáticos.
- **Firewall:** com o túnel, não abra 80/443/8000. `sudo ufw allow OpenSSH` é
  o bastante.
- **`/api/health`** é público (healthcheck) e mostra workspace/modelo; não é
  segredo, mas saiba que é acessível sem token.

Se você **não** quiser a fricção de aprovar comandos destrutivos, isso é uma
escolha consciente: remova os itens de `DESTRUCTIVE_EXECUTABLES` /
`REMOTE_EXECUTABLES` / `NETWORK_EXECUTABLES` em `policy.py`.

---

## Backup

SQLite não tem migrations e o workspace guarda seus arquivos:

```bash
./scripts/backup.sh                 # ~/.local/state/odin/backups
```

Agende no cron (ex.: diário às 3h) ou num systemd timer. Mantenha o destino
**fora** do workspace. Opcional: sincronize a pasta com Backblaze B2 / Drive.

---

## Verificação

```bash
curl -s http://127.0.0.1:8000/api/health            # deve responder JSON
curl -s https://odin.seudominio.com/api/conversations # 401 sem token
# de fora da rede: a porta 8000 NÃO deve responder
```

Checklist final: painel abre pelo domínio, Login do Access aparece, token setado
no cliente, chat responde e um tool call funciona.

---

## Solução de problemas

| Sintoma | Causa provável |
|---|---|
| Backend não sobe: "Refusing to start" | `ODIN_HOST` não-loopback sem `ODIN_API_TOKEN` |
| 401 no painel | `localStorage['odin_api_token']` diferente do `.env` |
| 429 ao logar | muitas falhas de token; espere a janela ou reinicie o backend |
| Painel em branco / sem UI | `frontend/dist` ausente → rode `./scripts/build.sh` |
| 404 em rota da API que existe | catch-all do SPA devolve `index.html`; confira em `/openapi.json` |
| App mobile não conecta | URL aponta para `127.0.0.1`; use a URL do túnel |
