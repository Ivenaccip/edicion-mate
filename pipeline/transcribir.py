#!/usr/bin/env python3
"""
Transcriptor con backends intercambiables. Salida siempre igual: lista de palabras
[{"w": "hola", "ini": 0.52, "fin": 0.80}, ...] en segundos.

    python transcribir.py audio.wav --backend whisper      # local, CPU
    python transcribir.py audio.wav --backend assemblyai   # API (ASSEMBLYAI_API_KEY o proxy)

El resto del pipeline (editor, captions, auditor) no sabe qué backend se usó.
"""
import sys, json, time, argparse, subprocess, os
from pathlib import Path
import numpy as np

def _pcm16k(path):
    """Audio a float32 mono 16 kHz vía ffmpeg (evita PyAV y acepta ogg/mp4/wav)."""
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-ar", "16000", "-ac", "1",
                          "-f", "f32le", "-"], check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32)

def whisper(path, modelo="small", idioma="es"):
    from faster_whisper import WhisperModel
    m = WhisperModel(modelo, device="cpu", compute_type="int8")
    segs, _ = m.transcribe(_pcm16k(path), language=idioma, word_timestamps=True, vad_filter=False)
    return [{"w": w.word.strip(), "ini": round(w.start, 3), "fin": round(w.end, 3)} for s in segs for w in s.words]

def assemblyai(path, idioma="es", muletillas=True, modelos=("universal-3-5-pro", "universal-2")):
    """AssemblyAI v2. Verificado nov 2026: el encabezado `authorization: <llave>` funciona con y sin
    prefijo Bearer; `speech_model` (singular) ya está deprecado y da 400, hay que mandar
    `speech_models` (lista en orden de preferencia)."""
    import requests
    base = "https://api.assemblyai.com/v2"
    key = os.environ.get("ASSEMBLYAI_API_KEY", "proxy")   # el proxy del entorno inyecta la real
    h = {"authorization": key}
    with open(path, "rb") as f:
        up = requests.post(f"{base}/upload", headers=h, data=f, timeout=300)
    up.raise_for_status()
    body = {"audio_url": up.json()["upload_url"], "language_code": idioma,
            "speech_models": list(modelos), "disfluencies": muletillas, "punctuate": True, "format_text": True}
    r = requests.post(f"{base}/transcript", headers={**h, "content-type": "application/json"}, json=body, timeout=60)
    r.raise_for_status(); tid = r.json()["id"]
    while True:
        t = requests.get(f"{base}/transcript/{tid}", headers=h, timeout=60).json()
        if t["status"] == "completed": break
        if t["status"] == "error": raise RuntimeError(t.get("error"))
        time.sleep(2)
    print(f"[assemblyai] modelo usado: {t.get('speech_model')} · duración audio: {t.get('audio_duration')} s", file=sys.stderr)
    return [{"w": w["text"], "ini": round(w["start"] / 1000, 3), "fin": round(w["end"] / 1000, 3),
             "conf": round(w.get("confidence", 0), 2)} for w in t["words"]]

BACKENDS = {"whisper": whisper, "assemblyai": assemblyai}

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("audio"); ap.add_argument("--backend", default="whisper", choices=BACKENDS)
    ap.add_argument("--salida")
    ap.add_argument("--sin-muletillas", action="store_true", help="assemblyai: disfluencies=False (quita eh, mm, etc.)")
    a = ap.parse_args()
    kw = {"muletillas": not a.sin_muletillas} if a.backend == "assemblyai" else {}
    t0 = time.time(); palabras = BACKENDS[a.backend](a.audio, **kw); dt = time.time() - t0
    out = Path(a.salida or Path(a.audio).with_suffix(f".{a.backend}.palabras.json"))
    out.write_text(json.dumps(palabras, ensure_ascii=False, indent=0))
    print(f"[{a.backend}] {len(palabras)} palabras en {dt:.1f} s -> {out}")
    print(" ".join(p["w"] for p in palabras))
