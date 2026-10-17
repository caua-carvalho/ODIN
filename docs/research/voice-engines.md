# Avaliação de engines de voz (STT/TTS) para o Odin — issue #23

- **Issue:** [#23 — \[P2\] Avaliar Needle, Whistle e Whisper para voz](https://github.com/caua-carvalho/ODIN/issues/23)
- **Alimenta:** [#22 — Criar camada modular de voz (STT/TTS)](https://github.com/caua-carvalho/ODIN/issues/22)
- **Tipo:** pesquisa (docs-only). Este commit **não** altera runtime, `backend/requirements.txt` nem o painel.
- **Status das informações de projeto:** **verificado em 2026-10-16** contra os repositórios oficiais, o GitHub API, PyPI e o Hugging Face Hub.
- **Status dos números de qualidade/latência/recursos:** **PENDENTE** — nenhuma engine foi instalada nesta máquina. Ver
  [§7 O que NÃO foi medido](#7-o-que-não-foi-medido-pendente-honesto).

---

## TL;DR — a decisão

| Camada | Decisão | Engine |
|---|---|---|
| **STT (local, padrão)** | **Integrar em #22** | `faster-whisper` (Whisper small/base `int8` na CPU) |
| **STT (API, fallback)** | **Integrar como provider opcional** | Groq `whisper-large-v3-turbo` (o Odin já tem `groq_api_key`) |
| **STT (mobile)** | **Adaptar depois** | `whisper.cpp` (MIT, C/C++, sem Python) |
| **STT (edge/bateria)** | **Apenas referência** | Vosk; `distil-whisper` como assistente de decodificação |
| **STT (Needle/Whistle)** | **Apenas referência (bloqueado)** | Whistle **não tem pt-BR**; Needle não é STT |
| **TTS (local, padrão)** | **Integrar em #22** | Kokoro-82M (Apache-2.0, vozes pt-BR) |
| **TTS (alternativa CPU)** | **Adaptar / alternativa** | Piper (vozes pt-BR CC0; código GPL-3.0 ⚠️) |
| **TTS (XTTS)** | **Apenas referência** | Coqui/XTTS — sem manutenção desde 2024 e pesos não-comerciais |

O achado que mais muda o plano: **o requisito é pt-BR** (issue #22: "validada em português brasileiro"), e a dupla
**Needle/Whistle da Cactus Compute não suporta português** — Whistle cobre 7 idiomas e nenhum é `pt`. Isso rebaixa
os dois a "referência" até que um fine-tune pt-BR prove WER aceitável.

---

## 1. Como ler esta avaliação (confiança)

| Bloco | Confiança | Como foi obtido |
|---|---|---|
| Repositório, licença, deps, release+data, manutenção | **Alta** | GitHub API + PyPI JSON + HF Hub, 2026-10-16 |
| Idioma suportado (pt-BR) | **Alta** | Model cards e README oficiais |
| Números de WER/latência/RAM **deste documento** | **Ausente (PENDENTE)** | Não medido aqui — ver §7 |
| Números de terceiros (Vosk, Groq, `freds0` pt-BR) | **Média** | Publicados pelos autores; **não reproduzidos** e com conjuntos de teste diferentes — servem de ordem de grandeza, não de comparação limpa |
| Latência "esperada" e fit de hardware | **Média/baixa** | Inferência a partir da arquitetura/tamanho do modelo no hardware alvo; a medir |

Regra seguida: **nenhum número foi inventado**. Onde não há medição, está escrito "pendente".

---

## 2. Hardware alvo (medido)

Contexto real desta máquina (`scripts/voice-bench.sh` imprime este bloco):

| Item | Valor |
|---|---|
| CPU | Intel Core i5-7200U @ 2.50 GHz (Kaby Lake, 2017) — **2 núcleos / 4 threads**, sem AVX-512 |
| GPU | **nenhuma** (`nvidia-smi` ausente) |
| RAM | 23.4 GiB (16 GiB disponíveis na amostra) |
| SO | Arch Linux, kernel 7.2.9 |
| Python (venv do backend) | 3.14.8 |
| Tooling | `ffmpeg` presente; `espeak-ng` **ausente** (necessário p/ Piper e Kokoro G2P); `whisper-cli` ausente |

Implicações diretas na escolha:

- **Sem GPU** → tudo roda em CPU. `Whisper large-v3` em 2 núcleos fica **mais lento que o tempo real**; a escolha
  viável é `base`/`small` (ou `large-v3-turbo` só via API).
- **Processador de 15 W de 2017** → prioridade a modelos ≤ ~250M parâmetros (whisper small/Base, Vosk small,
  Whistle, Kokoro 82M, Piper VITS).
- **Laptop sempre-on** (ver `deploy/` e `logind`) → RAM/CPU ociosos importam; um modelo grande residente piora
  bateria e concorre com o backend.

> **Aviso de compatibilidade (real):** o venv do backend é **Python 3.14**. `ctranslate2` e `onnxruntime` (deps de
> faster-whisper / Piper) podem não ter *wheel* para 3.14. O benchmark isola tudo num venv próprio e, se um wheel
> faltar, reporta o erro — não trava o Odin. Confirmar antes de fixar a escolha na #22.

---

## 3. Achado de enquadramento: "Needle, Whistle e Whisper" não são três alternativas do mesmo tipo

A issue lista três nomes como se fossem concorrentes diretos. Não são:

- **Needle** ([`cactus-compute/needle`](https://github.com/cactus-compute/needle)) — **não é uma engine de voz.** É um
  *foundation model* de tool-calling/extração estruturada para dispositivos minúsculos (8–29 MB). Faz ASR **por
  carona**, porque incorpora o Whistle no mesmo runtime.
- **Whistle** ([`Cactus-Compute/whistle`](https://huggingface.co/Cactus-Compute/whistle), mesmo repo/engine) — **essa
  sim é a engine STT** da Cactus Compute. É o "Needle com ouvidos".
- **Whisper** ([`openai/whisper`](https://github.com/openai/whisper)) — a engine STT multilíngue da OpenAI (o
  "padrão de fato"), com os runtimes derivados `faster-whisper` e `whisper.cpp`.

Logo, a comparação útil de STT é **Whistle × Whisper (e seus runtimes) × Vosk**, e Needle fica de fora do escopo de
voz (poderia interessar a outra camada — roteamento de tools no edge — mas isso é outra issue).

---

## 4. Tabela comparativa — STT

Datas = release/tag mais recente observada em 2026-10-16.

| Projeto | Repositório oficial | Licença | Tipo | Dependências principais | Última release (data) | Manutenção | pt-BR |
|---|---|---|---|---|---|---|---|
| **Needle** | [cactus-compute/needle](https://github.com/cactus-compute/needle) · [PyPI](https://pypi.org/project/cactus-needle/) | Apache-2.0 | Local, CPU, edge (8–29 MB) | `cactus-needle` (engine C++ + Python); telemetria **ligada por padrão** | **3.2.4 — 2026-10-16** | **Muito ativa** (14.1k★; commit 2026-10-16) | ❌ (não é STT: tool-calling) |
| **Whistle** | mesmo repo · [HF `Cactus-Compute/whistle`](https://huggingface.co/Cactus-Compute/whistle) | Apache-2.0 | Local, CPU, edge (arquivo único **16.9 MB**) | mesma engine do Needle (`.cact`) | lançado **2026-10-02**; distribuído em `cactus-needle` 3.2.4 | **Ativa** (~40k downloads/mês no HF) | ❌ **7 idiomas: en, de, fr, es, it, nl, pl** → **sem pt**; exigiria fine-tune |
| **Whisper (OpenAI)** | [openai/whisper](https://github.com/openai/whisper) | MIT | Local (torch) + API hospedada | `torch`, `ffmpeg` | **v20250625 — 2025-06-26** | Estável/baixa frequência (push 2026-08-31; 110k★) | ✅ 99+ idiomas |
| **faster-whisper** | [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) | MIT | Local (CPU `int8` / GPU) | `ctranslate2`, `av`, `onnxruntime`, `tokenizers` | **v1.2.1 — 2025-10-31** | **Ativa** (push 2026-10-16; 25.9k★) | ✅ |
| **whisper.cpp** | [ggml-org/whisper.cpp](https://github.com/ggml-org/whisper.cpp) | MIT | Local (CPU/GPU, C/C++) | **nenhuma** (ggml embutido) | **v1.9.5 — 2026-10-06** | **Muito ativa** (54.4k★) | ✅ |
| **distil-whisper** | [huggingface/distil-whisper](https://github.com/huggingface/distil-whisper) | MIT | Local (`transformers`) | `transformers`, `torch` | sem release no repo; peso **distil-large-v3** | **Baixa** (push 2025-01-08; 4.1k★) | ⚠️ oficial **só inglês**; pt por fine-tune comunitário ([freds0/distil-whisper-large-v3-ptbr](https://huggingface.co/freds0/distil-whisper-large-v3-ptbr)) |
| **Vosk** | [alphacep/vosk-api](https://github.com/alphacep/vosk-api) | Apache-2.0 (modelos variam) | Local, **streaming**, baixo RAM | `libvosk` (Kaldi) | **v0.3.50 — 2024-04-22** (PyPI `vosk` 0.3.45, 2022) | Moderada (push 2026-10-15; releases raros) | ⚠️ existe, fraco: WER publicado **32.6%** (small) / **27.7%** (fb big, GPL) |
| **Groq Whisper (API)** | [console.groq.com/docs/speech-to-text](https://console.groq.com/docs/speech-to-text) | serviço (proprietário) | **API** cloud | `httpx` (o Odin já usa) | `whisper-large-v3-turbo` | Ativa | ✅ |

Notas de licença que importam:

- **Vosk modelos pt:** `vosk-model-small-pt-0.3` é **Apache-2.0**; o modelo grande *FalaBrasil* é **GPLv3.0** — cuidado
  se o Odin for distribuído.
- **Whistle/Needle:** Apache-2.0, mas a telemetria vem **ligada por padrão** no binário (desligar com
  `NEEDLE_TELEMETRY=0` e `DO_NOT_TRACK=1`) — relevante para um assistente local/privacy-first.
- **`distil-whisper`** é MIT, mas o *checkpoint* pt-BR citado é de terceiro e não tem a mesma garantia do projeto
  original.

### Números publicados (referência, **não** reproduzidos aqui)

| Fonte | Conjunto | Valor | Link |
|---|---|---|---|
| Vosk `small-pt-0.3` | CommonVoice test | **WER 32.60%** | [alphacephei](https://alphacephei.com/vosk/models) |
| Vosk `pt-fb` big (GPL) | CommonVoice test | WER 27.70% | idem |
| Groq `whisper-large-v3` | (conjunto não especificado pelo Groq) | WER 10.3% | [groqdocs](https://console.groq.com/docs/speech-to-text) |
| Groq `whisper-large-v3-turbo` | idem | WER 12% | idem |
| `freds0/distil-whisper-large-v3-ptbr` | CommonVoice 16 validation | **WER 8.221%** | [HF](https://huggingface.co/freds0/distil-whisper-large-v3-ptbr) |
| Whistle | LibriSpeech/SPGISpeech/Earnings-22/FLEURS (en e as 7 línguas) | baricos no card; **pt não avaliado** | [HF](https://huggingface.co/Cactus-Compute/whistle) |

> Esses conjuntos **não são comparáveis entre si** (idioma, normalização e split diferentes). Servem de ordem de
> grandeza. A comparação limpa é a do §6, a ser executada.

---

## 5. Tabela comparativa — TTS (a "voz de resposta")

| Projeto | Repositório oficial | Licença (código / modelo) | Tipo | Dependências | Última release (data) | Manutenção | pt-BR |
|---|---|---|---|---|---|---|---|
| **Kokoro-82M** | [hexgrad/kokoro](https://github.com/hexgrad/kokoro) · [HF](https://huggingface.co/hexgrad/Kokoro-82M) | **Apache-2.0** (código e pesos) | Local, 82M, CPU/GPU | `torch`, `misaki`, `espeak-ng` | HF **v1.0 — 2025-01-27**; PyPI `kokoro` 0.9.4 — 2025-04-05 | Moderada (repo push 2025-08-06; HF ativo) | ✅ **`pf_dora`** (F), `pm_alex`, `pm_santa` (M) |
| **Piper** | [OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl) (o antigo [rhasspy/piper](https://github.com/rhasspy/piper) está **arquivado**) | código **GPL-3.0** ⚠️ / vozes **CC0** | Local, VITS/ONNX, CPU rápido | `onnxruntime`, `espeak-ng` | **v1.8.0 — 2026-09-04** | **Ativa** (push 2026-10-16) | ✅ [`pt_BR/faber`](https://huggingface.co/rhasspy/piper-voices/tree/main/pt/pt_BR), `cadu` (medium, CC0) |
| **Coqui TTS / XTTS-v2** | [coqui-ai/TTS](https://github.com/coqui-ai/TTS) | código **MPL-2.0** / pesos XTTS-v2 **CPML (não-comercial)** ⚠️ | Local, torch, GPU recomendada | `torch`, `transformers` | **v0.22.0 — 2023-12-12** | **Inativa** (push 2024-08-16; empresa encerrou) | ✅ 17 idiomas |
| **Groq Orpheus (API)** | [groqdocs](https://console.groq.com/docs/speech-to-text) | serviço | API | `httpx` | `canopylabs/orpheus-v1-english` | Ativa | ❌ só inglês/árabe |

---

## 6. Benchmark reproduzível

### 6.1 Dataset (pt-BR)

Prioridade de resolução, em `scripts/voice-bench.sh`:

1. `VOICE_BENCH_AUDIO=/caminho/pt-br.wav` (+ `VOICE_BENCH_REFERENCE` ou `VOICE_BENCH_REFERENCE_FILE`).
2. Amostra versionada em `docs/research/samples/pt-br*.wav` (com `.txt` de referência ao lado).
   **Recomendado:** gravar 3–5 frases curtas (~10–30 s) ou usar um recorte de **Common Voice pt** /
   **FLEURS `pt_br`** (que também é o conjunto com WER publicado, permitindo comparação externa).
3. Fallback automático: **síntese com `espeak-ng -v pt-br`** (documentado e reproduzível, mas voz robótica — o WER
   resultante é **comparação relativa entre engines**, não qualidade absoluta).

### 6.2 Comando único

```bash
# tudo (STT local + API se GROQ_API_KEY existir), com relatório em Markdown:
./scripts/voice-bench.sh

# só as engines locais rápidas, num WAV próprio:
VOICE_BENCH_ENGINES="faster-whisper,vosk" \
VOICE_BENCH_AUDIO=~/voz/pt-br.wav \
VOICE_BENCH_REFERENCE_FILE=~/voz/pt-br.txt \
./scripts/voice-bench.sh

# incluir TTS + loop de inteligibilidade (STT sobre a própria síntese):
VOICE_BENCH_TTS_TEXT="bom dia, sou o odin" ./scripts/voice-bench.sh

# ver o plano (nada é instalado):
VOICE_BENCH_DRY_RUN=1 ./scripts/voice-bench.sh
```

Isolamento: o script cria um venv **próprio** em `$VOICE_BENCH_DIR/venv` (padrão `/tmp/odin-voice-bench`), com versões
**fixadas** (`faster-whisper==1.2.1`, `vosk==0.3.45`, `cactus-needle==3.2.4`, `kokoro==0.9.4`, `piper-tts==1.8.0`, …) e
imprime `pip freeze` no log. **`backend/requirements.txt` não é tocado.**

### 6.3 Métricas

| Métrica | Como é medida | Observação |
|---|---|---|
| **WER / CER** | `jiwer` (ou Levenshtein interno) contra a referência, após normalização NFKC/minúsculas/pontuação | acentos **são** contados |
| **Tempo de carga** | wall time para construir/carregar o modelo | exclui download do peso na 1ª execução |
| **Latência até a 1ª saída** | wall time até o 1º token/segmento/parcial | **aproximada** onde a engine não faz streaming de verdade |
| **Latência total + RTF** | wall time total ÷ duração do áudio (<1 = mais rápido que o real) | |
| **RAM pico** | `ru_maxrss` do processo da engine (modelo incluído) | cada engine roda em **subprocesso próprio** |
| **CPU** | `user+sys` consumidos | |
| **GPU** | N/A neste host | |
| **Round-trip TTS** | transcrever a própria síntese e comparar com o texto | mede inteligibilidade pt-BR da voz |

A metodologia completa está documentada no cabeçalho de [`scripts/voice_bench.py`](../../scripts/voice_bench.py) e
[`scripts/voice-bench.sh`](../../scripts/voice-bench.sh).

### 6.4 Resultados

**PENDENTE.** Nenhuma engine foi instalada/executada nesta avaliação (ver §7). Ao rodar o comando acima, o relatório
preenchido é gravado em [`docs/research/voice-bench-results.md`](voice-bench-results.md) — o script recusa-se a
inventar números: engine ausente/que falha vira uma linha com `erro`, nunca um valor estimado.

---

## 7. O que **NÃO** foi medido (pendente honesto)

Nada abaixo foi executado aqui. Instalar faster-whisper/Whistle/Kokoro traria centenas de MB–GB (torch,
ctranslate2, onnxruntime) para uma tarefa que o enunciado pede para manter leve, e o Python 3.14 do backend pode nem
ter wheels. Portanto **não há WER, latência nem consumo reais neste documento.**

| Pendência | Por que | Como fechar |
|---|---|---|
| WER pt-BR de **Whisper/faster-whisper**, Vosk, Whistle, distil-pt | engines não instaladas | rodar `scripts/voice-bench.sh` com amostra pt-BR |
| Latência (1ª saída / total / RTF) no i5-7200U | idem | idem |
| RAM/CPU por engine | idem | idem |
| Qualidade/inteligibilidade do **Kokoro** e **Piper** em pt-BR | TTS não instalado; `espeak-ng` ausente | `VOICE_BENCH_TTS_TEXT=… ./scripts/voice-bench.sh` |
| WER de **Whistle após fine-tune pt-BR** | exige LoRA (`{"language":"pt"}`) e GPU/plataforma Cactus | spike separado, se a #22 quiser tentar |
| Wheels de `ctranslate2`/`onnxruntime` para **Python 3.14** | não verificado | `pip install` no venv isolado |
| WER absoluto (vs. relativo) | amostra própria ≠ conjunto publicado | fixar Common Voice / FLEURS `pt_br` |

O fallback `espeak-ng` **não está instalado** nesta máquina; sem ele e sem amostra, o benchmark roda apenas
latência/RAM (sem WER) e diz isso explicitamente.

---

## 8. Decisão

Colunas de justificativa pedidas na issue: **licença · manutenção · latência · custo · fit p/ laptop sempre-on.**

| # | Engine | Camada | Decisão | Licença | Manutenção | Latência (esperada) | Custo | Fit laptop (2c, sem GPU) | Justificativa |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **faster-whisper** (`small`/`base` int8) | STT | **Integrar em #22** (padrão local) | MIT ✅ | Ativa (v1.2.1, push 2026-10-16) | boa com `base/small`; `large` = lento | **grátis** | ✅ (modelos ≤ ~250M) | pt-BR nativo, VAD embutido, `int8` na CPU, sem `ffmpeg` (usa `av`), word timestamps, ecossistema enorme. Melhor risco/benefício. |
| 2 | **Groq `whisper-large-v3-turbo`** | STT | **Integrar como provider opcional** | serviço | Ativa | **muito baixa** (216× tempo real) | **US$ 0,04/h** (mín. 10 s) | ✅ (só rede) | Fallback quando a CPU está ocupada; o Odin **já tem** `groq_api_key` e já filtra `whisper` no catálogo de modelos. Custo desprezível p/ uso pessoal. |
| 3 | **whisper.cpp** | STT | **Adaptar depois (mobile)** | MIT ✅ | Muito ativa (v1.9.5) | boa (quantizado) | grátis | ✅ | Sem Python/torch → ideal para o app Expo/mobile; alternativa offline ao provider local. |
| 4 | **distil-whisper** | STT | **Referência / adaptar se faltar latência** | MIT ✅ | Baixa (2025-01) | ~6× faster que large | grátis | ✅ | Só como *assistant model* (speculative decoding) com faster-whisper; pt-BR depende de checkpoint de terceiro → validar WER antes. |
| 5 | **Vosk** (`small-pt`) | STT | **Apenas referência** | Apache-2.0 ✅ (modelo grande é GPL) | Moderada | excelente/streaming | grátis | ✅✅ (RAM baixíssima) | Único real candidato a *always-on*/baixo consumo, mas WER pt publicado **~32%** é ruim p/ transcrição. Guardar p/ wake-word/streaming barato. |
| 6 | **Whistle** (Cactus) | STT | **Apenas referência (bloqueado)** | Apache-2.0 ✅ | Ativa (2026-10) | exemplar (16.9 MB, edge) | grátis | ✅✅ | Atraente em tamanho/latência/CPU, mas **não tem pt-BR** (7 idiomas). Reabrir só se um fine-tune pt-BR (`needle whistle finetune … "language":"pt"`) provar WER aceitável. |
| 7 | **Needle** (Cactus) | — | **Apenas referência (fora de escopo)** | Apache-2.0 ✅ | Ativa | n/a (tool-calling) | grátis | ✅ | **Não é engine de voz.** Eventual interesse em roteamento de tools no edge; telemetria ligada por padrão. |
| 8 | **Kokoro-82M** | TTS | **Integrar em #22** (padrão local) | **Apache-2.0** ✅ | Moderada (HF v1.0) | baixa (82M, CPU ok) | **grátis** | ✅ | Licença permissiva de verdade, **3 vozes pt-BR** (incl. feminina), roda em CPU — a melhor combinação para pt-BR local. |
| 9 | **Piper** | TTS | **Alternativa / adaptar** | código **GPL-3.0** ⚠️ · vozes CC0 | Ativa (v1.8.0) | **a melhor em CPU** | grátis | ✅✅ | Vozes pt-BR boas e muito rápidas; porém **GPL-3.0** no código é risco se o Odin for distribuído. Dá para usar o **ONNX standalone** (sem a lib `piper-tts`) e manter só as vozes CC0. |
| 10 | **Coqui TTS / XTTS-v2** | TTS | **Apenas referência** | pesos **CPML (não-comercial)** ⚠️ | **Inativa** (2024) | pesada (GPU) | grátis p/ uso não-comercial | ❌ (GPU recomendada) | Pesos não-comerciais + projeto sem manutenção + peso demais para 2 núcleos. Não usar. |
| 11 | **Groq Orpheus (API)** | TTS | **Referência** | serviço | Ativa | baixa | US$ 22/M chars | ✅ | **Sem pt-BR** hoje → não serve. |

### 8.1 Contrato sugerido para a camada da #22 (decorre da tabela)

- Duas interfaces (`SpeechToText`, `TextToSpeech`) + providers plugáveis, **espelhando** o padrão de
  `backend/app/agent/providers/` (catálogo + `factory` + seleção em runtime). Ver
  [`backend/app/agent/providers/catalog.py`](../../backend/app/agent/providers/catalog.py).
- Providers-alvo: STT `faster-whisper` (local, padrão) e `groq` (API, fallback); TTS `kokoro` (padrão) e `piper`
  (alternativa). Formato de entrada canônico: **PCM 16 kHz mono** (o que Whisper, Vosk, Whisper.cpp e Whistle
  aceitam), o que também simplifica o mobile.
- Nenhuma dependência de áudio entra em `backend/requirements.txt` sem decisão explícita — a #22 deve tratá-las como
  **extras opcionais** (import tardio), como já se faz com o SDK MCP.

---

## 9. Riscos e bloqueadores

| Risco | Impacto | Mitigação |
|---|---|---|
| Wheels de `ctranslate2`/`onnxruntime` ausentes p/ **Python 3.14** | bloqueia faster-whisper/Piper no venv atual | testar cedo; se preciso, venv separado com 3.12 p/ a camada de voz |
| **Whistle sem pt-BR** | inviabiliza o uso direto | manter como referência; fine-tune é spike separado |
| `espeak-ng` ausente | quebra G2P do Kokoro/Piper e o fallback de síntese | instalar `espeak-ng` (pacote do sistema) ao ativar TTS |
| CPU de 2 núcleos concorrendo com o backend | latência sobe sob carga; bateria | preferir `base`/`small`; oferecer o provider de API como escape |
| GPL-3.0 do Piper | contaminação de licença se distribuído | usar ONNX standalone + vozes CC0, ou ficar com Kokoro |
| Telemetria ligada por padrão no binário da Cactus | privacidade em "assistente local" | se algum dia adotar: `NEEDLE_TELEMETRY=0`/`DO_NOT_TRACK=1` |
| WER "publicado" de fontes diferentes | decisão mal calibrada | rodar o §6 com amostra fixa antes de fechar a #22 |

---

## 10. Referências (verificadas em 2026-10-16)

- Cactus Compute — Needle: <https://github.com/cactus-compute/needle> · PyPI: <https://pypi.org/project/cactus-needle/> · pesos: <https://huggingface.co/Cactus-Compute/needle3>
- Cactus Compute — Whistle: <https://huggingface.co/Cactus-Compute/whistle>
- OpenAI Whisper: <https://github.com/openai/whisper> · release v20250625: <https://github.com/openai/whisper/releases/tag/v20250625>
- faster-whisper: <https://github.com/SYSTRAN/faster-whisper> · v1.2.1: <https://github.com/SYSTRAN/faster-whisper/releases/tag/v1.2.1>
- whisper.cpp: <https://github.com/ggml-org/whisper.cpp> · v1.9.5: <https://github.com/ggml-org/whisper.cpp/releases/tag/v1.9.5>
- distil-whisper: <https://github.com/huggingface/distil-whisper> · pt-BR: <https://huggingface.co/freds0/distil-whisper-large-v3-ptbr>
- Vosk: <https://github.com/alphacep/vosk-api> · modelos (WER publicado): <https://alphacephei.com/vosk/models>
- Groq Speech-to-Text (preços/WER publicados): <https://console.groq.com/docs/speech-to-text>
- Coqui TTS/XTTS: <https://github.com/coqui-ai/TTS>
- Piper: <https://github.com/OHF-Voice/piper1-gpl> · vozes pt-BR: <https://huggingface.co/rhasspy/piper-voices/tree/main/pt/pt_BR>
- Kokoro-82M: <https://github.com/hexgrad/kokoro> · <https://huggingface.co/hexgrad/Kokoro-82M>
