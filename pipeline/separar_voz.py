#!/usr/bin/env python3
"""
Separa la voz del ruido (viento, pops, fondo) con DeepFilterNet3, un modelo de mejora de voz
que corre en CPU (33 s de audio en < 1 s).

Requiere su propio entorno (torch rompe el principal):
    python3 -m venv .venv-df && . .venv-df/bin/activate
    pip install "torch==2.6.0" "torchaudio==2.6.0" --index-url https://download.pytorch.org/whl/cpu
    pip install deepfilternet soundfile safetensors
    python pipeline/separar_voz.py --preparar-modelo      # descarga pesos de Hugging Face (fal/DeepFilterNet3)

Uso:
    .venv-df/bin/python pipeline/separar_voz.py entrada.wav salida.wav [--video in.mp4 out.mp4]

Los pesos oficiales viven en GitHub, que el entorno de nube no permite; la copia de Hugging Face
(config.ini + model.safetensors, Apache-2.0) se convierte al formato de checkpoint de la librería.
"""
import sys, argparse, subprocess, urllib.request
from pathlib import Path

MODELO = Path.home() / ".cache" / "dfn3"
HF = "https://huggingface.co/fal/DeepFilterNet3/resolve/main/"

def preparar_modelo():
    import torch
    from safetensors.torch import load_file
    (MODELO / "checkpoints").mkdir(parents=True, exist_ok=True)
    for f in ("config.ini", "model.safetensors"):
        if not (MODELO / f).exists(): urllib.request.urlretrieve(HF + f, MODELO / f)
    ck = MODELO / "checkpoints" / "model_120.ckpt.best"
    if not ck.exists(): torch.save(load_file(MODELO / "model.safetensors"), ck)
    print("modelo listo en", MODELO)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("entrada", nargs="?"); ap.add_argument("salida", nargs="?")
    ap.add_argument("--video", nargs=2, metavar=("IN", "OUT"))
    ap.add_argument("--preparar-modelo", action="store_true")
    a = ap.parse_args()
    if a.preparar_modelo: preparar_modelo(); return
    if not (MODELO / "config.ini").exists(): preparar_modelo()
    from df.enhance import enhance, init_df, load_audio, save_audio
    model, state, _ = init_df(model_base_dir=str(MODELO), log_level="WARNING")
    audio, _ = load_audio(a.entrada, sr=state.sr())
    out = enhance(model, state, audio)
    save_audio(a.salida, out, state.sr())
    print(f"voz separada -> {a.salida}")
    if a.video:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", a.video[0], "-i", a.salida, "-map", "0:v", "-map", "1:a",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", a.video[1]], check=True)
        print(f"video -> {a.video[1]}")

if __name__ == "__main__":
    main()
