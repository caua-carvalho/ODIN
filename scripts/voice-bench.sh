#!/usr/bin/env bash
# =============================================================================
# voice-bench.sh — reproducible pt-BR voice-engine benchmark for Odin (issue #23)
# =============================================================================
#
# ONE COMMAND:
#
#     ./scripts/voice-bench.sh
#
# What it does, in order:
#   1. prints the hardware/context block (CPU, RAM, GPU, tools, Python);
#   2. finds (or, as a last resort, synthesises) a pt-BR audio sample;
#   3. creates an ISOLATED virtualenv under $VOICE_BENCH_DIR and installs only
#      the engines you asked for — backend/requirements.txt is NEVER touched;
#   4. runs each engine in its own subprocess and writes a Markdown report to
#      docs/research/voice-bench-results.md.
#
# Nothing is uploaded by this script except an optional Groq API call when the
# `stt-api` engine is selected AND GROQ_API_KEY is set.
#
# Configuration (all optional, all via environment):
#   VOICE_BENCH_DIR            work + virtualenv dir      [/tmp/odin-voice-bench]
#   VOICE_BENCH_ENGINES        STT engines, comma list    [faster-whisper,vosk,whistle,stt-api]
#   VOICE_BENCH_AUDIO          path to a 16 kHz mono WAV  [(auto: sample/ espeak-ng)]
#   VOICE_BENCH_REFERENCE      reference transcript       [(auto: sidecar .txt)]
#   VOICE_BENCH_SAMPLE_DIR     where to look for samples  [docs/research/samples]
#   VOICE_BENCH_OUT            report path                [docs/research/voice-bench-results.md]
#   VOICE_BENCH_WHISPER_MODEL  faster-whisper size        [small]
#   VOICE_BENCH_SKIP_INSTALL   1 = reuse an existing venv [0]
#   VOICE_BENCH_TTS_TEXT       if set, also bench TTS
#   VOICE_BENCH_DRY_RUN        1 = print the plan and exit [0]
#   GROQ_API_KEY               needed by the `stt-api` engine
#
# See docs/research/voice-engines.md for the methodology and the decision.
# =============================================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

WORK_DIR="${VOICE_BENCH_DIR:-/tmp/odin-voice-bench}"
VENV_DIR="${WORK_DIR}/venv"
ENGINES="${VOICE_BENCH_ENGINES:-faster-whisper,vosk,whistle,stt-api}"
SAMPLE_DIR="${VOICE_BENCH_SAMPLE_DIR:-${REPO_ROOT}/docs/research/samples}"
OUT="${VOICE_BENCH_OUT:-${REPO_ROOT}/docs/research/voice-bench-results.md}"
WHISPER_MODEL="${VOICE_BENCH_WHISPER_MODEL:-small}"
SKIP_INSTALL="${VOICE_BENCH_SKIP_INSTALL:-0}"
DRY_RUN="${VOICE_BENCH_DRY_RUN:-0}"
PYTHON_BIN="${VOICE_BENCH_PYTHON:-python3}"

BENCH_PY="${REPO_ROOT}/scripts/voice_bench.py"

log()  { printf '\033[1;34m[voice-bench]\033[0m %s\n' "$*" >&2; }
warn() { printf '\033[1;33m[voice-bench] WARN:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[voice-bench] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

[[ -f "${BENCH_PY}" ]] || die "missing ${BENCH_PY}"

# --------------------------------------------------------------------------- #
# 0. tooling sanity
# --------------------------------------------------------------------------- #
command -v "${PYTHON_BIN}" >/dev/null 2>&1 || die "python3 not found"
log "python: $("${PYTHON_BIN}" -V 2>&1)"

if ! command -v ffmpeg >/dev/null 2>&1; then
  warn "ffmpeg not found — resampling/synthesis of the sample will be limited"
fi

# --------------------------------------------------------------------------- #
# 1. hardware / context
# --------------------------------------------------------------------------- #
log "hardware context:"
"${PYTHON_BIN}" "${BENCH_PY}" context | sed 's/^/  /'

# --------------------------------------------------------------------------- #
# 2. resolve the dataset (audio + reference)
# --------------------------------------------------------------------------- #
AUDIO="${VOICE_BENCH_AUDIO:-}"
REFERENCE_FILE="${VOICE_BENCH_REFERENCE_FILE:-}"

if [[ -z "${AUDIO}" ]]; then
  # Prefer a checked-in/recorded sample; fall back to a documented synthesis.
  if compgen -G "${SAMPLE_DIR}/pt-br*.wav" >/dev/null 2>&1; then
    AUDIO="$(ls "${SAMPLE_DIR}"/pt-br*.wav | head -n1)"
    log "using sample: ${AUDIO}"
  elif command -v espeak-ng >/dev/null 2>&1; then
    AUDIO="${WORK_DIR}/pt-br-espeak.wav"
    mkdir -p "${WORK_DIR}"
    REFERENCE_FILE="${WORK_DIR}/pt-br-espeak.txt"
    cat >"${REFERENCE_FILE}" <<'TXT'
bom dia odin, qual é a previsão do tempo para são josé dos campos hoje
abra o projeto e mostre as tarefas pendentes da semana
TXT
    log "no sample found — synthesising a pt-BR reference with espeak-ng"
    log "  (robotic voice: WER here is a RELATIVE comparison, not absolute quality)"
    # -x/--ipa not needed; -w writes a wav; then normalise to 16 kHz mono PCM16.
    espeak-ng -v pt-br -s 150 -w "${WORK_DIR}/pt-br-espeak-raw.wav" \
      "bom dia odin, qual é a previsão do tempo para são josé dos campos hoje. abra o projeto e mostre as tarefas pendentes da semana."
    if command -v ffmpeg >/dev/null 2>&1; then
      ffmpeg -y -loglevel error -i "${WORK_DIR}/pt-br-espeak-raw.wav" -ac 1 -ar 16000 -c:a pcm_s16le "${AUDIO}"
    else
      warn "ffmpeg missing — passing the espeak-ng 22 kHz wav through unchanged"
      cp "${WORK_DIR}/pt-br-espeak-raw.wav" "${AUDIO}"
    fi
  else
    warn "no pt-br sample and no espeak-ng: engines will run WITHOUT WER (latency/RAM only)"
    warn "put a 16 kHz mono WAV at ${SAMPLE_DIR}/pt-br.wav and a ${SAMPLE_DIR}/pt-br.txt reference"
  fi
fi

if [[ -n "${REFERENCE_FILE}" && -z "${VOICE_BENCH_REFERENCE:-}" ]]; then
  export VOICE_BENCH_REFERENCE_FILE="${REFERENCE_FILE}"
fi

# --------------------------------------------------------------------------- #
# 3. isolated virtualenv + pinned installs
# --------------------------------------------------------------------------- #
resolve_packages() {
  # The package list is owned by voice_bench.py so it can never drift.
  "${PYTHON_BIN}" "${BENCH_PY}" plan --engines "$1" --audio "${AUDIO:-}" \
    --reference-file "${REFERENCE_FILE:-}" --out "${OUT}" \
    | sed -n 's/^resolved package list: //p'
}

PACKAGES="$(resolve_packages "${ENGINES}")"
log "engines : ${ENGINES}"
log "packages: ${PACKAGES:-<none>}"

if [[ "${DRY_RUN}" == "1" ]]; then
  log "dry run — stopping before install"
  "${PYTHON_BIN}" "${BENCH_PY}" plan --engines "${ENGINES}" --audio "${AUDIO:-}" \
    --reference-file "${REFERENCE_FILE:-}" --out "${OUT}"
  exit 0
fi

if [[ "${SKIP_INSTALL}" != "1" ]]; then
  if [[ ! -d "${VENV_DIR}" ]]; then
    log "creating isolated venv at ${VENV_DIR}"
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
  fi
  VENV_PY="${VENV_DIR}/bin/python"
  log "upgrading pip"
  "${VENV_PY}" -m pip install --quiet --upgrade pip wheel
  if [[ -n "${PACKAGES}" ]]; then
    # shellcheck disable=SC2086
    log "installing (pinned): ${PACKAGES} jiwer soundfile numpy"
    # shellcheck disable=SC2086
    "${VENV_PY}" -m pip install --quiet ${PACKAGES} jiwer soundfile numpy
  fi
  "${VENV_PY}" -m pip freeze | sed 's/^/  installed: /' >&2
else
  VENV_PY="${VENV_DIR}/bin/python"
  [[ -x "${VENV_PY}" ]] || die "VOICE_BENCH_SKIP_INSTALL=1 but ${VENV_PY} does not exist"
fi

# --------------------------------------------------------------------------- #
# 4. run
# --------------------------------------------------------------------------- #
log "running benchmark (engine output goes to ${OUT})"
ARGS=(run
  --engines "${ENGINES}"
  --language pt
  --model "${WHISPER_MODEL}"
  --out "${OUT}"
)
[[ -n "${AUDIO}" ]] && ARGS+=(--audio "${AUDIO}")
[[ -n "${VOICE_BENCH_REFERENCE:-}" ]] && ARGS+=(--reference "${VOICE_BENCH_REFERENCE}")
[[ -n "${REFERENCE_FILE:-}" ]] && ARGS+=(--reference-file "${REFERENCE_FILE}")
if [[ -n "${VOICE_BENCH_TTS_TEXT:-}" ]]; then
  ARGS+=(--tts-text "${VOICE_BENCH_TTS_TEXT}" --tts-engines "${VOICE_BENCH_TTS_ENGINES:-kokoro,piper}")
fi

# Run with the same interpreter so the measurement reflects the same runtime
# (torch/CTranslate2 versions) the venv installed.
PYTHONPATH="${WORK_DIR}" "${VENV_PY}" "${BENCH_PY}" "${ARGS[@]}"

log "done. Report: ${OUT}"
