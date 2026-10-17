# Amostras de áudio pt-BR (benchmark de voz — issue #23)

Esta pasta é o lugar canônico de onde `scripts/voice-bench.sh` pega o áudio de
teste. Nada aqui é obrigatório: se estiver vazia, o script tenta sintetizar uma
amostra com `espeak-ng -v pt-br` (e avisa que o WER resultante é **relativo**).

## Como adicionar uma amostra

1. Coloque um WAV **PCM 16 bits, mono, 16 kHz** aqui, com o nome
   `pt-br.wav` (ou `pt-br-<algo>.wav` — o script pega o primeiro `pt-br*.wav`).
2. Crie a transcrição exata ao lado, em `pt-br.txt` (mesmo nome-base, `.txt`).
3. Rode:

   ```bash
   ./scripts/voice-bench.sh
   ```

Para converter um arquivo qualquer:

```bash
ffmpeg -i entrada.m4a -ac 1 -ar 16000 -c:a pcm_s16le pt-br.wav
```

## Recomendações

- **3–5 frases curtas** (~10–30 s no total), incluindo um número e um nome
  próprio (ex.: "São José dos Campos", "abrir o projeto X") para estressar
  pontuação/acentos.
- Acentos **contam** no WER (a normalização não remove acentos). Escreva a
  referência com a acentuação correta.
- Para comparar com números externos, use um recorte de **Common Voice pt** ou
  **FLEURS `pt_br`** — são os conjuntos com WER publicado (Vosk/Groq) e mais
  próximos de uma comparação "limpa".

## Por que não versionar o WAV aqui

Áudio de voz real é dado pessoal/licenciado. Prefira gerar localmente ou apontar
`VOICE_BENCH_AUDIO` para um caminho fora do repositório:

```bash
VOICE_BENCH_AUDIO=~/voz/pt-br.wav \
VOICE_BENCH_REFERENCE_FILE=~/voz/pt-br.txt \
./scripts/voice-bench.sh
```

WAVs não são ignorados por padrão pelo `.gitignore` do repo — evite `git add`
de áudio pessoal.
