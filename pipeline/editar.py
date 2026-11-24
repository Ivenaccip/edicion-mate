#!/usr/bin/env python3
"""Un comando: raw.mp4 -> carpeta del contrato con cortes, audio limpio y capa visual.

  python pipeline/editar.py raw.mp4 --rotar ccw --hasta visual        # preview 576 listo para el auditor
  python pipeline/editar.py raw.mp4 --rotar ccw --hasta final         # además render 1080
  python pipeline/editar.py raw.mp4 --rotar ccw --guion guion.txt     # raw a varias tomas: corta por el guion revisado

Etapas (cada una se salta si su salida ya existe, salvo --forzar):
  1 transcribir  pipeline/transcribir.py --backend assemblyai          -> raw.palabras.json
  2 plan         editor_pausas.py (pausas, señal) + proponer_guion.py (¿a varias tomas? -> guion.propuesto.txt)
                 + seleccionar_tomas.py (tomas por guion o automático, bordes por señal) -> raw.edl.json, tomas.md
                 Si el raw es a varias tomas y no hay guion.txt (o --guion), se detiene con código 3 para que una
                 persona revise el guion propuesto.
  3 cortar       pipeline/cortar_video.py --fade 0 (576 y 1080)        -> cuerpo_576.mp4, cuerpo_1080.mp4, cuerpo_576.aplicado.json
  4 separar      .venv-df/bin/python pipeline/separar_voz.py           -> cuerpo_voz.wav
  5 limpiar      pipeline/limpiar_audio.py (parámetros del estándar)   -> cuerpo_limpio.wav (+ cuerpo_576 remuxeado)
  6 vestir       pipeline/visual/vestir.sh --preview | --final         -> preview_576.mp4, pendientes_llave.md, final_1080.mp4
El fundido de 0.1 s por empalme lo pinta la composición (capa persona), por eso el corte va con --fade 0.
Principios del estándar que esto respeta: la señal decide dónde cortar; preview 576 para iterar; 1080 solo con --hasta final.
"""
import argparse, json, os, shutil, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VENV = REPO / ".venv" / "bin" / "python"
VENV_DF = REPO / ".venv-df" / "bin" / "python"

def run(cmd, cwd):
    print("$", " ".join(str(c) for c in cmd)); subprocess.run([str(c) for c in cmd], cwd=cwd, check=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw"); ap.add_argument("--carpeta", help="carpeta de salida (por defecto <nombre del raw>/ junto al raw)")
    ap.add_argument("--rotar", choices=["ccw", "cw", "180"]); ap.add_argument("--encuadre", default="9:16")
    ap.add_argument("--hasta", choices=["cortes", "audio", "visual", "final"], default="visual")
    ap.add_argument("--forzar", action="store_true"); ap.add_argument("--cola", type=float, default=0.1, help="s de cola al final del cuerpo (aire con fundido)")
    ap.add_argument("--guion", help="guion final (una frase por línea) para seleccionar_tomas.py --guion; sin él, agrupado automático")
    a = ap.parse_args()
    raw = Path(a.raw).resolve(); d = Path(a.carpeta).resolve() if a.carpeta else raw.parent / raw.stem
    d.mkdir(parents=True, exist_ok=True)
    falta = lambda *n: a.forzar or not all((d / x).exists() for x in n)

    if falta("raw.palabras.json"):
        run([VENV, REPO / "pipeline/transcribir.py", raw, "--salida", d / "raw.palabras.json", "--backend", "assemblyai"], d)
    if falta("raw.edl.json"):
        if falta("raw.pausas.edl.json"):
            # el editor de pausas escucha un WAV y escribe <salida>.edl.json junto al audio editado (que no se usa)
            run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-vn", "-ac", "1", "-ar", "48000", d / "raw_audio.wav"], d)
            run([VENV, REPO / "prototipos/editor-pausas/editor_pausas.py", d / "raw_audio.wav", d / "raw.wav"], d)
            shutil.move(d / "raw.edl.json", d / "raw.pausas.edl.json")
        # ¿raw a varias tomas? proponer_guion.py escribe guion.propuesto.txt y el diagnóstico (dos o más líneas
        # repetidas = a varias tomas). Regla del estándar: en ese caso el guion revisado por una persona decide.
        run([VENV, REPO / "pipeline/proponer_guion.py", d / "raw.palabras.json", d / "guion.propuesto.txt", "--json", d / "guion.diagnostico.json"], d)
        guion = Path(a.guion).resolve() if a.guion else (d / "guion.txt" if (d / "guion.txt").exists() else None)
        diag = json.load(open(d / "guion.diagnostico.json"))
        if diag["a_varias_tomas"] and not guion:
            print(f"\nALTO: el raw se grabó a varias tomas ({diag['tomas']} tomas, {diag['grupos_repetidos']} líneas repetidas). "
                  f"Revisa {d / 'guion.propuesto.txt'} (una frase por línea, en orden), guárdalo como {d / 'guion.txt'} y vuelve a correr; "
                  "o pasa --guion archivo.txt. Sin guion no se corta un raw así.")
            sys.exit(3)
        # tomas: por guion (mejor toma de cada frase) o agrupado automático (líneas repetidas, apartes); bordes por señal
        run([VENV, REPO / "pipeline/seleccionar_tomas.py", d / "raw.palabras.json", d / "raw_audio.wav", d / "raw.pausas.edl.json",
             "--salida", d / "raw.edl.json", "--md", d / "tomas.md", *(["--guion", guion] if guion else [])], d)
        print("AVISO: revisa tomas.md (plan de tomas) antes de dar por bueno el corte.")
    rot = ["--rotar", a.rotar] if a.rotar else []
    if falta("cuerpo_576.mp4", "cuerpo_576.aplicado.json"):
        run([VENV, REPO / "pipeline/cortar_video.py", raw, d / "raw.edl.json", d / "cuerpo_576.mp4", *rot, "--encuadre", a.encuadre, "--fade", "0", "--cola-s", str(a.cola)], d)
    if falta("cuerpo_1080.mp4"):
        run([VENV, REPO / "pipeline/cortar_video.py", raw, d / "raw.edl.json", d / "cuerpo_1080.mp4", *rot, "--encuadre", a.encuadre, "--fade", "0", "--cola-s", str(a.cola), "--final"], d)
    if a.hasta == "cortes": return
    if falta("cuerpo_audio.wav"):
        run(["ffmpeg", "-v", "error", "-y", "-i", d / "cuerpo_576.mp4", "-vn", "-ac", "1", "-ar", "48000", d / "cuerpo_audio.wav"], d)
    if falta("cuerpo_voz.wav"):
        run([VENV_DF, REPO / "pipeline/separar_voz.py", d / "cuerpo_audio.wav", d / "cuerpo_voz.wav"], d)
    if falta("cuerpo_limpio.wav"):
        # palabras en tiempo del cuerpo para que la limpieza sepa dónde hay voz
        run([VENV, REPO / "pipeline/visual/remapear_palabras.py", d / "raw.palabras.json", d / "cuerpo_576.aplicado.json", d / "cuerpo.palabras.json"], d)
        run([VENV, REPO / "pipeline/limpiar_audio.py", d / "cuerpo_voz.wav", d / "cuerpo.palabras.json", d / "cuerpo_limpio.wav",
             "--hp-hz", "100", "--viento-hz", "300", "--viento-db", "3", "9", "--resp-db", "-18",
             "--video", d / "cuerpo_576.mp4", d / "cuerpo_576_limpio.mp4"], d)
    if a.hasta == "audio": return
    run([REPO / "pipeline/visual/vestir.sh", d, "--final" if a.hasta == "final" else "--preview"], d)

if __name__ == "__main__":
    main()
