# Resultados do benchmark de voz (pt-BR)

> **Status: PENDENTE — nenhuma engine foi executada ainda.**
>
> Este arquivo é um *placeholder* versionado para que o link em
> [`voice-engines.md`](voice-engines.md#64-resultados) resolva antes da primeira
> execução. Ele é **sobrescrito** por `scripts/voice-bench.sh` e não deve ser
> editado à mão.

## Por que está pendente

A avaliação #23 é *docs-only* e não instalou nenhuma engine de voz (torch,
ctranslate2, onnxruntime, modelos) — o enunciado pede para manter o repositório
leve e marcar números não medidos como pendentes em vez de estimá-los.
Ver [§7 de `voice-engines.md`](voice-engines.md#7-o-que-não-foi-medido-pendente-honesto).

## Como preencher

```bash
# STT local rápido + API (se GROQ_API_KEY estiver no ambiente)
VOICE_BENCH_ENGINES="faster-whisper,vosk,stt-api" \
VOICE_BENCH_AUDIO=~/voz/pt-br.wav \
VOICE_BENCH_REFERENCE_FILE=~/voz/pt-br.txt \
./scripts/voice-bench.sh

# TTS + loop de inteligibilidade
VOICE_BENCH_TTS_TEXT="bom dia, sou o odin" ./scripts/voice-bench.sh
```

O script grava uma tabela com **WER, CER, tempo de carga, latência até a 1ª
saída, latência total, RTF, RAM pico e CPU** por engine. Engine ausente ou que
falha aparece como uma linha com `erro` — o script nunca inventa um número.

## Hardware alvo

| Item | Valor |
|---|---|
| CPU | Intel Core i5-7200U @ 2.50 GHz — 2 núcleos / 4 threads |
| GPU | nenhuma |
| RAM | 23.4 GiB |
| SO | Arch Linux (kernel 7.2.9) |
| Python | 3.14.8 (venv do backend) |
