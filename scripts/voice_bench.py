#!/usr/bin/env python3
"""Reproducible pt-BR voice-engine benchmark for Odin (issue #23).

This is the *core* of the benchmark: it runs ONE engine at a time in the
current interpreter and prints a single JSON object with the measured numbers.
The shell orchestrator (``scripts/voice-bench.sh``) creates an isolated venv,
builds the hardware context and calls this file once per engine in a fresh
subprocess, so per-engine peak RSS/CPU can be attributed cleanly and a heavy
engine (torch) never pollutes the numbers of a light one.

Design rules
------------
* **Never invent numbers.** Any engine that is missing, cannot be imported or
  fails mid-run reports ``"error"`` plus a message and *no* metrics. A missing
  value is emitted as ``null``, never guessed.
* **No runtime dependency.** Nothing here is imported by the Odin backend; the
  file is only executed inside the throwaway venv that ``voice-bench.sh``
  builds. ``backend/requirements.txt`` is never touched.
* **stdlib only for orchestration.** ``jiwer`` is used for WER/CER when
  available, otherwise a small internal Levenshtein implementation is used so
  a partial install still yields a comparable number.

Subcommands
-----------
    list                       engines this script knows about
    context                    machine/context report (JSON)
    plan                       print what would be installed / run (no side effects)
    run                        spawn one subprocess per engine and render a report
    _one                       internal: run a single engine in this process
    tts-one                    internal: run a single TTS engine in this process

Metrics emitted per engine (STT)
--------------------------------
    load_s          wall time to build/load the model
    first_output_s  wall time from start of the request to the first emitted
                    word/segment (approximate for non-streaming engines)
    total_s         wall time for the whole transcription
    rtf             total_s / audio_duration_s  (lower is better, <1 is faster
                    than real time)
    wer, cer        error rates against the reference transcript
    peak_rss_mb     peak resident set of *this* process (model included)
    cpu_s           user+sys CPU seconds consumed
    text            the hypothesis (for eyeballing / debugging)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any, Callable

# --------------------------------------------------------------------------- #
# Engine registry
# --------------------------------------------------------------------------- #

# Each entry: label -> how to install it (shown in `plan`) and which extra
# knob it needs. Kept here so the shell script and this file never disagree.
STT_ENGINES: dict[str, dict[str, Any]] = {
    "faster-whisper": {
        "install": ["faster-whisper==1.2.1"],
        "needs": "pip + a CTranslate2 wheel for this Python",
        "note": "CTranslate2 backend, int8 on CPU, native pt-BR",
    },
    "openai-whisper": {
        "install": ["openai-whisper==20250625"],
        "needs": "pip (torch) + a system ffmpeg",
        "note": "reference implementation, slowest on CPU",
    },
    "whisper.cpp": {
        "install": [],  # built/installed outside pip
        "needs": "a `whisper-cli` (or legacy `main`) binary on PATH",
        "note": "MIT C/C++ port; best fit for the mobile app",
    },
    "vosk": {
        "install": ["vosk==0.3.45"],
        "needs": "pip + the pt model zip (downloaded on first run)",
        "note": "streaming Kaldi; low RAM, weak pt-BR WER",
    },
    "whistle": {
        "install": ["cactus-needle==3.2.4"],
        "needs": "pip (Cactus C++ engine + weights fetched on first use)",
        "note": "16.9 MB edge model; NO pt-BR out of the box",
    },
    "stt-api": {
        "install": ["httpx>=0.27"],
        "needs": "GROQ_API_KEY in the environment",
        "note": "Groq whisper-large-v3-turbo cloud API",
    },
}

TTS_ENGINES: dict[str, dict[str, Any]] = {
    "kokoro": {
        "install": ["kokoro==0.9.4", "soundfile"],
        "needs": "pip (torch) + a system espeak-ng",
        "note": "Apache-2.0, 82M, pt-BR voices (pf_dora/pm_alex/pm_santa)",
    },
    "piper": {
        "install": ["piper-tts==1.8.0"],
        "needs": "pip (GPL-3.0 code) + a voice .onnx + espeak-ng",
        "note": "fastest CPU VITS; pt-BR faber/cadu voices (CC0)",
    },
}


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #


def _now() -> float:
    return time.perf_counter()


def peak_rss_mb() -> float:
    """Peak RSS of this process in MiB (Linux: ru_maxrss is KiB)."""
    import resource

    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def cpu_seconds() -> float:
    import resource

    r = resource.getrusage(resource.RUSAGE_SELF)
    return r.ru_utime + r.ru_stime


def _normalize(text: str) -> str:
    """pt-BR-friendly normalisation shared by WER and CER.

    Mirrors the intent of the Whisper normalizers: NFKC, lower-case, drop
    punctuation, collapse whitespace. We do **not** strip accents, because a
    missing accent in pt-BR is a real error worth counting.
    """
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _levenshtein(a: list[Any], b: list[Any]) -> int:
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def wer_cer(reference: str, hypothesis: str) -> tuple[float, float, str]:
    """Return (WER, CER, backend) where backend names the implementation used."""
    ref, hyp = _normalize(reference), _normalize(hypothesis)
    ref_tokens, hyp_tokens = ref.split(), hyp.split()
    try:  # preferred: the same library the WER literature uses
        import jiwer  # type: ignore

        wer = float(jiwer.wer(ref or " ", hyp or " "))
        cer = float(jiwer.cer(ref or " ", hyp or " "))
        return wer, cer, "jiwer"
    except Exception:
        pass
    wer = _levenshtein(ref_tokens, hyp_tokens) / max(len(ref_tokens), 1)
    cer = _levenshtein(list(ref), list(hyp)) / max(len(ref), 1)
    return wer, cer, "builtin-levenshtein"


def audio_duration(path: Path) -> float | None:
    """Duration in seconds, via soundfile or ffprobe; None if unavailable."""
    try:
        import soundfile as sf  # type: ignore

        return float(sf.info(str(path)).duration)
    except Exception:
        pass
    if shutil.which("ffprobe"):
        try:
            out = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=nw=1:nk=1",
                    str(path),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            return float(out.stdout.strip())
        except Exception:
            return None
    return None


def read_reference(path: Path | None, inline: str | None) -> str | None:
    if inline:
        return inline
    if path and path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return None


def model_cache_dir() -> Path:
    d = Path(os.environ.get("VOICE_BENCH_MODEL_DIR", "/tmp/odin-voice-bench/models"))
    d.mkdir(parents=True, exist_ok=True)
    return d


# --------------------------------------------------------------------------- #
# STT engine runners. Each returns (text, first_output_s, load_s). Total time is
# measured by the caller so every engine is timed identically.
# --------------------------------------------------------------------------- #


def run_faster_whisper(audio: Path, model_size: str, language: str):
    from faster_whisper import WhisperModel  # type: ignore

    t0 = _now()
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    load_s = _now() - t0

    t1 = _now()
    segments, _info = model.transcribe(
        str(audio),
        language=language,
        beam_size=5,
        vad_filter=True,
        word_timestamps=True,
        condition_on_previous_text=False,
    )
    first: float | None = None
    parts: list[str] = []
    for seg in segments:  # the generator is lazy: this is where work happens
        if first is None:
            first = _now() - t1
        parts.append(seg.text)
    return "".join(parts).strip(), (first if first is not None else _now() - t1), load_s


def run_openai_whisper(audio: Path, model_size: str, language: str):
    import whisper  # type: ignore

    t0 = _now()
    model = whisper.load_model(model_size)
    load_s = _now() - t0
    t1 = _now()
    result = model.transcribe(str(audio), language=language, fp16=False)
    return str(result.get("text", "")).strip(), _now() - t1, load_s


def run_whisper_cpp(audio: Path, model_size: str, language: str):
    binary = shutil.which("whisper-cli") or shutil.which("main") or shutil.which("whisper-cpp")
    if not binary:
        raise RuntimeError(
            "no whisper.cpp binary on PATH (build it and expose `whisper-cli`)"
        )
    model = os.environ.get("VOICE_BENCH_WHISPERCPP_MODEL")
    if not model:
        raise RuntimeError("set VOICE_BENCH_WHISPERCPP_MODEL=/path/to/ggml-*.bin")
    t0 = _now()
    out = subprocess.run(
        [binary, "-m", model, "-f", str(audio), "-l", language, "-nt"],
        capture_output=True,
        text=True,
        check=True,
    )
    total = _now() - t0
    # whisper.cpp has no streaming contract here: first output == total.
    return out.stdout.strip(), total, 0.0


def run_vosk(audio: Path, model_size: str, language: str):
    import wave

    import vosk  # type: ignore

    model_dir = model_cache_dir() / "vosk-model-small-pt-0.3"
    t0 = _now()
    if not model_dir.is_dir():
        _download_vosk_pt(model_dir)
    model = vosk.Model(str(model_dir))
    load_s = _now() - t0

    rec = vosk.KaldiRecognizer(model, 16000)
    t1 = _now()
    first: float | None = None
    parts: list[str] = []
    with wave.open(str(audio), "rb") as wf:
        while True:
            data = wf.readframes(4000)
            if not data:
                break
            if rec.AcceptWaveform(data):
                text = json.loads(rec.Result()).get("text", "")
                if first is None and text:
                    first = _now() - t1
                parts.append(text)
            else:
                partial = json.loads(rec.PartialResult()).get("partial", "")
                if first is None and partial:
                    first = _now() - t1
    tail = json.loads(rec.FinalResult()).get("text", "")
    if tail:
        parts.append(tail)
    return " ".join(p for p in parts if p).strip(), (first or _now() - t1), load_s


def _download_vosk_pt(target: Path) -> None:
    import urllib.request
    import zipfile

    url = "https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip"
    archive = model_cache_dir() / "vosk-model-small-pt-0.3.zip"
    if not archive.is_file():
        print(f"[voice-bench] downloading {url}", file=sys.stderr)
        urllib.request.urlretrieve(url, archive)
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(model_cache_dir())


def run_whistle(audio: Path, model_size: str, language: str):
    import needle  # type: ignore

    t0 = _now()
    engine = needle.Whistle()
    load_s = _now() - t0
    t1 = _now()
    # The API returns text plus the milliseconds to the first token; the exact
    # key is looked up defensively because it has changed across releases.
    result = engine.transcribe(str(audio), language=language) if language else engine.transcribe(str(audio))
    if not isinstance(result, dict):
        result = {"text": str(result)}
    first_ms = None
    for key in ("ms_to_first_token", "first_token_ms", "time_to_first_token_ms", "ttft_ms"):
        if isinstance(result.get(key), (int, float)):
            first_ms = float(result[key])
            break
    total = _now() - t1
    first = (first_ms / 1000.0) if first_ms is not None else total
    return str(result.get("text", "")).strip(), first, load_s


def run_stt_api(audio: Path, model_size: str, language: str):
    import httpx  # type: ignore

    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is not set")
    model = os.environ.get("VOICE_BENCH_GROQ_MODEL", "whisper-large-v3-turbo")
    t0 = _now()
    with open(audio, "rb") as fh:
        resp = httpx.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {key}"},
            files={"file": (audio.name, fh, "audio/wav")},
            data={"model": model, "language": language, "response_format": "json"},
            timeout=120.0,
        )
    resp.raise_for_status()
    total = _now() - t0
    text = str(resp.json().get("text", "")).strip()
    # Cloud API is not streamed here: first output == total.
    return text, total, 0.0


STT_RUNNERS: dict[str, Callable[[Path, str, str], tuple[str, float, float]]] = {
    "faster-whisper": run_faster_whisper,
    "openai-whisper": run_openai_whisper,
    "whisper.cpp": run_whisper_cpp,
    "vosk": run_vosk,
    "whistle": run_whistle,
    "stt-api": run_stt_api,
}


# --------------------------------------------------------------------------- #
# TTS runners. Each returns (time_to_first_chunk_s, total_s, audio_s_written).
# --------------------------------------------------------------------------- #


def run_tts_kokoro(text: str, out_path: Path, voice: str):
    import numpy as np  # type: ignore
    import soundfile as sf  # type: ignore
    from kokoro import KPipeline  # type: ignore

    lang_code = os.environ.get("VOICE_BENCH_KOKORO_LANG", "p")  # 'p' = pt-BR
    pipeline = KPipeline(lang_code=lang_code)
    t0 = _now()
    first: float | None = None
    chunks: list[Any] = []
    for _gs, _ps, audio in pipeline(text, voice=voice):
        if first is None:
            first = _now() - t0
        chunks.append(audio)
    total = _now() - t0
    if not chunks:
        raise RuntimeError("kokoro produced no audio")
    audio = np.concatenate([np.asarray(c) for c in chunks])
    sf.write(str(out_path), audio, 24000)
    return (first or total), total, float(len(audio)) / 24000.0


def run_tts_piper(text: str, out_path: Path, voice: str):
    import wave

    from piper import PiperVoice  # type: ignore

    model = os.environ.get("VOICE_BENCH_PIPER_MODEL")
    if not model:
        raise RuntimeError(
            "set VOICE_BENCH_PIPER_MODEL=/path/to/pt_BR-*.onnx "
            "(e.g. rhasspy/piper-voices pt/pt_BR/faber/medium)"
        )
    v = PiperVoice.load(model)
    t0 = _now()
    first: float | None = None
    total_frames = 0
    rate = 22050
    with wave.open(str(out_path), "wb") as wf:
        for chunk in v.synthesize(text):
            if first is None:
                first = _now() - t0
            frames = chunk.audio_int16_bytes
            if wf.getnframes() == 0:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(chunk.sample_rate)
                rate = chunk.sample_rate
            wf.writeframes(frames)
            total_frames += len(frames) // 2
    total = _now() - t0
    return (first or total), total, total_frames / float(rate)


TTS_RUNNERS: dict[str, Callable[[str, Path, str], tuple[float, float, float]]] = {
    "kokoro": run_tts_kokoro,
    "piper": run_tts_piper,
}


# --------------------------------------------------------------------------- #
# Subcommands
# --------------------------------------------------------------------------- #


def cmd_list(_args: argparse.Namespace) -> int:
    print(json.dumps(
        {
            "stt": {k: v["note"] for k, v in STT_ENGINES.items()},
            "tts": {k: v["note"] for k, v in TTS_ENGINES.items()},
        },
        indent=2,
        ensure_ascii=False,
    ))
    return 0


def machine_context() -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "platform": sys.platform,
        "python": sys.version.split()[0],
    }
    for tool in ("lscpu", "free", "nvidia-smi", "ffmpeg", "espeak-ng", "whisper-cli"):
        ctx[f"has_{tool}"] = bool(shutil.which(tool))
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        for line in cpuinfo.read_text().splitlines():
            if line.lower().startswith("model name"):
                ctx["cpu"] = line.split(":", 1)[1].strip()
                break
    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        for line in meminfo.read_text().splitlines():
            if line.startswith("MemTotal"):
                kb = int(line.split()[1])
                ctx["mem_total_gb"] = round(kb / 1024 / 1024, 1)
                break
    try:
        ctx["cpu_count"] = os.cpu_count()
    except Exception:
        pass
    return ctx


def cmd_context(_args: argparse.Namespace) -> int:
    print(json.dumps(machine_context(), indent=2, ensure_ascii=False))
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    engines = [e for e in args.engines.split(",") if e]
    print(f"pip installs (isolated venv, NOT backend/requirements.txt):")
    pkgs: list[str] = []
    for e in engines:
        meta = STT_ENGINES.get(e) or TTS_ENGINES.get(e)
        if not meta:
            print(f"  {e}: UNKNOWN")
            continue
        pkgs += meta["install"]
        print(f"  {e:16} needs: {meta['needs']}")
    print(f"  shared: jiwer soundfile numpy")
    print(f"resolved package list: {' '.join(sorted(set(pkgs)))}")
    print(f"audio:    {args.audio or '(synthesised with espeak-ng if absent)'}")
    print(f"reference:{args.reference or args.reference_file or '(sidecar .txt next to the audio)'}")
    print(f"output:   {args.out}")
    return 0


def _one(args: argparse.Namespace) -> int:
    audio = Path(args.audio).expanduser()
    reference = read_reference(
        Path(args.reference_file).expanduser() if args.reference_file else None,
        args.reference,
    )
    model_size = args.model
    language = args.language
    out: dict[str, Any] = {"engine": args.engine, "audio": str(audio)}
    try:
        if not audio.is_file():
            raise RuntimeError(f"audio not found: {audio}")
        runner = STT_RUNNERS[args.engine]
        dur = audio_duration(audio)
        t_start = _now()
        text, first_s, load_s = runner(audio, model_size, language)
        total_s = _now() - t_start
        out.update(
            {
                "audio_s": dur,
                "load_s": round(load_s, 3),
                "first_output_s": round(first_s, 3),
                "total_s": round(total_s, 3),
                "rtf": round(total_s / dur, 3) if dur else None,
                "text": text,
                "cpu_s": round(cpu_seconds(), 2),
                "peak_rss_mb": round(peak_rss_mb(), 1),
            }
        )
        if reference:
            wer, cer, backend = wer_cer(reference, text)
            out.update({"wer": round(wer, 4), "cer": round(cer, 4), "wer_backend": backend})
        else:
            out.update({"wer": None, "cer": None, "wer_backend": None})
    except Exception as exc:  # never invent a number: report and stop
        out.update({"error": f"{type(exc).__name__}: {exc}"})
    print("@@VOICE_BENCH@@" + json.dumps(out, ensure_ascii=False))
    return 0


def _tts_one(args: argparse.Namespace) -> int:
    out_path = Path(args.tts_out).expanduser()
    out: dict[str, Any] = {"engine": args.engine, "text": args.text}
    try:
        runner = TTS_RUNNERS[args.engine]
        first_s, total_s, audio_s = runner(args.text, out_path, args.voice)
        out.update(
            {
                "first_chunk_s": round(first_s, 3),
                "total_s": round(total_s, 3),
                "audio_out_s": round(audio_s, 3),
                "rtf": round(total_s / audio_s, 3) if audio_s else None,
                "peak_rss_mb": round(peak_rss_mb(), 1),
                "cpu_s": round(cpu_seconds(), 2),
                "out": str(out_path),
            }
        )
        # Optional intelligibility loop: re-transcribe our own TTS output.
        if args.roundtrip_engine:
            label = run_roundtrip(args.roundtrip_engine, out_path, args.language)
            out["roundtrip_text"] = label
    except Exception as exc:
        out.update({"error": f"{type(exc).__name__}: {exc}"})
    print("@@VOICE_BENCH@@" + json.dumps(out, ensure_ascii=False))
    return 0


def run_roundtrip(engine: str, audio: Path, language: str) -> str:
    runner = STT_RUNNERS[engine]
    text, _first, _load = runner(audio, "small", language)
    return text


def _spawn(py_cmd: list[str], env: dict[str, str]) -> dict[str, Any]:
    """Run one engine subprocess and parse its single @@VOICE_BENCH@@ line."""
    proc = subprocess.run(py_cmd, capture_output=True, text=True, env=env)
    for line in proc.stdout.splitlines():
        if line.startswith("@@VOICE_BENCH@@"):
            return json.loads(line[len("@@VOICE_BENCH@@"):])
    return {
        "error": "no metrics emitted",
        "stderr": (proc.stderr or "").strip().splitlines()[-3:],
        "returncode": proc.returncode,
    }


def _render_report(rows: list[dict[str, Any]], ctx: dict[str, Any], args: argparse.Namespace) -> str:
    lines: list[str] = []
    lines.append("# Resultados do benchmark de voz (pt-BR)")
    lines.append("")
    lines.append("> Gerado por `scripts/voice-bench.sh` (issue #23). Não editar à mão.")
    lines.append("")
    lines.append(f"- Comando: `VOICE_BENCH_ENGINES=\"{args.engines}\" ./scripts/voice-bench.sh`")
    lines.append(f"- Data (UTC): {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}")
    lines.append(f"- Áudio: `{args.audio or '(sintetizado)'}`" + (f"  ({audio_duration(Path(args.audio).expanduser())}s)" if args.audio and Path(args.audio).expanduser().is_file() else ""))
    lines.append(f"- Hardware: {ctx.get('cpu', '?')} — {ctx.get('cpu_count', '?')} vCPU, {ctx.get('mem_total_gb', '?')} GiB RAM, Python {ctx.get('python')}")
    lines.append(f"- GPU: {'sim' if ctx.get('has_nvidia-smi') else 'não'}")
    lines.append("")
    lines.append("| engine | audio (s) | load (s) | 1ª saída (s) | total (s) | RTF | WER | CER | RSS pico (MiB) | CPU (s) | erro |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        if r.get("error"):
            lines.append(f"| {r.get('engine')} | — | — | — | — | — | — | — | — | — | {r['error']} |")
            continue
        def fmt(key: str, digits: int = 2) -> str:
            v = r.get(key)
            return "—" if v is None else f"{v:.{digits}f}"
        lines.append(
            "| {e} | {a} | {l} | {f} | {t} | {rtf} | {wer} | {cer} | {rss} | {cpu} |  |".format(
                e=r.get("engine"),
                a=fmt("audio_s"),
                l=fmt("load_s"),
                f=fmt("first_output_s"),
                t=fmt("total_s"),
                rtf=fmt("rtf", 3),
                wer=("%.2f%%" % (r["wer"] * 100)) if r.get("wer") is not None else "—",
                cer=("%.2f%%" % (r["cer"] * 100)) if r.get("cer") is not None else "—",
                rss=fmt("peak_rss_mb", 1),
                cpu=fmt("cpu_s"),
            )
        )
    lines.append("")
    lines.append("## Hipóteses (transcrições)")
    lines.append("")
    for r in rows:
        if r.get("text"):
            lines.append(f"- **{r['engine']}**: {r['text']}")
    lines.append("")
    return "\n".join(lines)


def cmd_run(args: argparse.Namespace) -> int:
    engines = [e for e in args.engines.split(",") if e]
    ctx = machine_context()
    env = dict(os.environ)
    py = [sys.executable, str(Path(__file__).resolve())]
    rows: list[dict[str, Any]] = []
    if args.audio:
        env["VOICE_BENCH_AUDIO"] = args.audio
    for engine in engines:
        print(f"[voice-bench] running {engine} …", file=sys.stderr)
        cmd = py + [
            "_one",
            "--engine", engine,
            "--audio", args.audio or "",
            "--language", args.language,
            "--model", args.model,
        ]
        if args.reference:
            cmd += ["--reference", args.reference]
        if args.reference_file:
            cmd += ["--reference-file", args.reference_file]
        rows.append(_spawn(cmd, env))

    if args.tts_text:
        for engine in [e for e in args.tts_engines.split(",") if e]:
            print(f"[voice-bench] running TTS {engine} …", file=sys.stderr)
            out_wav = Path(args.tts_out or "/tmp/odin-voice-bench/tts-out.wav")
            out_wav.parent.mkdir(parents=True, exist_ok=True)
            cmd = py + [
                "tts-one",
                "--engine", engine,
                "--text", args.tts_text,
                "--tts-out", str(out_wav),
                "--voice", args.voice,
                "--language", args.language,
            ]
            if args.roundtrip_engine:
                cmd += ["--roundtrip-engine", args.roundtrip_engine]
            rows.append(_spawn(cmd, env))

    report = _render_report(rows, ctx, args)
    if args.out:
        out_path = Path(args.out).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        print(f"[voice-bench] wrote {out_path}", file=sys.stderr)
    print(report)
    return 0 if all(not r.get("error") for r in rows) else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    for name, fn in (("list", cmd_list), ("context", cmd_context)):
        sp = sub.add_parser(name)
        sp.set_defaults(func=fn)

    sp = sub.add_parser("plan")
    sp.add_argument("--engines", default="faster-whisper,whisper.cpp,vosk,whistle,stt-api")
    sp.add_argument("--audio", default=None)
    sp.add_argument("--reference", default=None)
    sp.add_argument("--reference-file", default=None)
    sp.add_argument("--out", default=None)
    sp.set_defaults(func=cmd_plan)

    sp = sub.add_parser("run")
    sp.add_argument("--engines", default="faster-whisper,vosk,whistle,stt-api")
    sp.add_argument("--audio", default=None)
    sp.add_argument("--reference", default=None)
    sp.add_argument("--reference-file", default=None)
    sp.add_argument("--language", default="pt")
    sp.add_argument("--model", default="small")
    sp.add_argument("--out", default=None)
    sp.add_argument("--tts-text", default=None)
    sp.add_argument("--tts-engines", default="kokoro,piper")
    sp.add_argument("--tts-out", default=None)
    sp.add_argument("--voice", default="pf_dora")
    sp.add_argument("--roundtrip-engine", default=None)
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("_one")
    sp.add_argument("--engine", required=True)
    sp.add_argument("--audio", required=True)
    sp.add_argument("--reference", default=None)
    sp.add_argument("--reference-file", default=None)
    sp.add_argument("--language", default="pt")
    sp.add_argument("--model", default="small")
    sp.set_defaults(func=_one)

    sp = sub.add_parser("tts-one")
    sp.add_argument("--engine", required=True)
    sp.add_argument("--text", required=True)
    sp.add_argument("--tts-out", required=True)
    sp.add_argument("--voice", default="pf_dora")
    sp.add_argument("--language", default="pt")
    sp.add_argument("--roundtrip-engine", default=None)
    sp.set_defaults(func=_tts_one)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
