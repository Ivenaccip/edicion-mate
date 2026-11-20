#!/usr/bin/env python3
"""
Prototipo: ¿detecta Essentia un corte mal hecho en voz?

1. Genera (o carga) un WAV de voz.
2. Fabrica tres versiones con un corte en la misma zona:
     limpio  -> corte en un silencio real + crossfade de 15 ms
     sucio   -> corte en medio de una vocal, sin crossfade (salto de onda)
     hueco   -> corte en medio de una vocal + 50 ms de silencio digital
3. Corre DiscontinuityDetector, ClickDetector y GapsDetector sobre cada una.
4. Imprime tabla y guarda forma de onda con las detecciones marcadas.

Uso:
    python prototipo.py                 # voz sintética (espeak-ng)
    python prototipo.py voz.wav         # tu propio audio (ej. 20-30 s de Charlie)
"""
import subprocess, sys, shutil
from pathlib import Path
import numpy as np
import soundfile as sf
import essentia.standard as es
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SR = 44100
AQUI = Path(__file__).parent
OUT = AQUI / "salida"
OUT.mkdir(exist_ok=True)

TEXTO = ("Hoy quiero contarte algo que casi nadie está viendo. "
         "Las empresas que adoptaron inteligencia artificial este año crecieron el doble. "
         "Y lo más interesante es lo que pasó en Latinoamérica. "
         "Quédate hasta el final porque el último dato cambia todo.")

# ---------------------------------------------------------------- audio base
def voz_sintetica(path: Path) -> None:
    if not shutil.which("espeak-ng"):
        sys.exit("No hay espeak-ng. Pasa un WAV como argumento o instala espeak-ng.")
    raw = path.with_suffix(".raw.wav")
    subprocess.run(["espeak-ng", "-v", "es-419", "-s", "150", "-w", str(raw), TEXTO], check=True)
    # a 44.1 kHz mono, que es lo que esperan los detectores por defecto
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw),
                    "-ar", str(SR), "-ac", "1", str(path)], check=True)
    raw.unlink()

def cargar(path: Path) -> np.ndarray:
    return es.MonoLoader(filename=str(path), sampleRate=SR)()

# ---------------------------------------------------------------- análisis de energía
def rms_por_frame(x, frame=1024, hop=256):
    n = 1 + (len(x) - frame) // hop
    return np.array([np.sqrt(np.mean(x[i*hop:i*hop+frame]**2)) for i in range(n)]), hop

def punto_en_vocal(x) -> int:
    """Muestra dentro de la zona más sonora de la mitad central del audio."""
    rms, hop = rms_por_frame(x)
    lo, hi = len(rms)//3, 2*len(rms)//3
    i = lo + int(np.argmax(rms[lo:hi]))
    return i*hop + 512

def silencio_mas_cercano(x, muestra, umbral_rel=0.02):
    """(inicio, fin) en muestras del silencio más cercano a `muestra` (RMS < umbral_rel * máx)."""
    rms, hop = rms_por_frame(x)
    quieto = rms < umbral_rel * rms.max()
    idx = np.where(quieto)[0]
    if len(idx) == 0:
        sys.exit("No encontré silencios en el audio.")
    # agrupar frames quietos contiguos y elegir el grupo más cercano
    grupos = np.split(idx, np.where(np.diff(idx) > 1)[0] + 1)
    spans = [(g[0] * hop + 512, g[-1] * hop + 512) for g in grupos if len(g) >= 4]
    return min(spans, key=lambda s: abs((s[0] + s[1]) / 2 - muestra))

# ---------------------------------------------------------------- fabricar versiones
def quitar(x, inicio, dur_ms=400):
    fin = inicio + int(SR * dur_ms / 1000)
    return x[:inicio], x[fin:]

def siguiente_vocal(x, desde, min_ms=300) -> int:
    """Primera muestra >= desde+min_ms que cae en zona sonora (RMS > 50 % del máximo)."""
    rms, hop = rms_por_frame(x)
    i0 = (desde + int(SR * min_ms / 1000)) // hop
    for i in range(i0, len(rms)):
        if rms[i] > 0.5 * rms.max():
            return i * hop + 512
    return desde + int(SR * min_ms / 1000)

def pegar_crossfade(a, b, ms=15):
    n = int(SR * ms / 1000)
    rampa = np.linspace(0, 1, n, dtype=np.float32)
    cruce = a[-n:] * (1 - rampa) + b[:n] * rampa
    return np.concatenate([a[:-n], cruce, b[n:]])

def fabricar(x):
    corte_vocal = punto_en_vocal(x)
    ini, fin = silencio_mas_cercano(x, corte_vocal)
    margen = int(SR * 0.030)                      # deja 30 ms de silencio a cada lado
    corte_silencio = ini + margen
    # limpio: acortar la pausa (lo que hace un editor), cortando solo dentro del silencio
    limpio = pegar_crossfade(x[:corte_silencio], x[max(corte_silencio, fin - margen):])
    # vocal -> vocal: se mocha una palabra y se pega con la siguiente (el caso real)
    a = x[:corte_vocal]
    v = siguiente_vocal(x, corte_vocal)
    v = v + int(np.argmax(np.abs(x[v:v + int(SR * 0.020)])))   # pico dentro de 20 ms
    b = x[v:]
    sucio = np.concatenate([a, b])
    hueco = np.concatenate([a, np.zeros(int(SR * 0.050), dtype=np.float32), b])

    return {
        "limpio": (limpio, corte_silencio / SR),
        "sucio":  (sucio,  corte_vocal / SR),
        "hueco":  (hueco,  corte_vocal / SR),
    }

# ---------------------------------------------------------------- detectores
def detectar(x):
    """Devuelve {detector: [tiempos en s]}. Instancias nuevas por audio: son con estado."""
    res = {"Discontinuity": [], "Click": [], "Gaps": []}

    disc = es.DiscontinuityDetector(frameSize=512, hopSize=256)
    click = es.ClickDetector(frameSize=512, hopSize=256, sampleRate=SR)
    for i, fr in enumerate(es.FrameGenerator(x, frameSize=512, hopSize=256, startFromZero=True)):
        locs, _ = disc(fr)
        res["Discontinuity"] += [(i * 256 + l) / SR for l in locs]  # índice dentro del frame
        s, e = click(fr)
        res["Click"] += list(s)                                      # ya en segundos absolutos

    gaps = es.GapsDetector(frameSize=2048, hopSize=1024, sampleRate=SR,
                           minimumTime=10, prepowerThreshold=-30)
    for fr in es.FrameGenerator(x, frameSize=2048, hopSize=1024, startFromZero=True):
        s, e = gaps(fr)
        res["Gaps"] += list(s)
    return res

def voz_ambos_lados(x, corte_s, ventana_ms=30, umbral_rel=0.10):
    """True si hay energía de voz justo antes y justo después del corte.
    Independiente de si la onda es continua: detecta 'corté en medio del habla'."""
    c, w = int(corte_s * SR), int(SR * ventana_ms / 1000)
    ref = np.sqrt(np.mean(x**2))
    antes = np.sqrt(np.mean(x[max(0, c - w):c]**2))
    despues = np.sqrt(np.mean(x[c:c + w]**2))
    return antes > umbral_rel * ref and despues > umbral_rel * ref

def coincide(tiempos, corte, tol=0.060):
    return [t for t in tiempos if abs(t - corte) <= tol]

# ---------------------------------------------------------------- main
def main():
    if len(sys.argv) > 1:
        base = Path(sys.argv[1])
    else:
        base = OUT / "voz_sintetica.wav"
        voz_sintetica(base)
    x = cargar(base)
    print(f"Audio base: {base.name}  ({len(x)/SR:.1f} s)\n")

    versiones = fabricar(x)
    filas = []
    fig, axes = plt.subplots(len(versiones), 1, figsize=(14, 9), sharex=True)
    colores = {"Discontinuity": "red", "Click": "orange", "Gaps": "purple"}

    for ax, (nombre, (y, corte)) in zip(axes, versiones.items()):
        sf.write(OUT / f"{nombre}.wav", y, SR)
        det = detectar(y)
        filas.append((nombre, "VozAmbosLados", "-", voz_ambos_lados(y, corte)))
        t = np.arange(len(y)) / SR
        ax.plot(t, y, lw=0.4, color="0.3")
        ax.axvline(corte, color="green", ls="--", lw=1.5, label=f"corte real {corte:.3f}s")
        for d, tiempos in det.items():
            acierto = coincide(tiempos, corte)
            filas.append((nombre, d, len(tiempos), [round(a, 3) for a in acierto]))
            for tt in tiempos:
                ax.axvline(tt, color=colores[d], lw=0.8, alpha=0.7)
            if tiempos:
                ax.plot([], [], color=colores[d], label=f"{d} ({len(tiempos)})")
        ax.set_title(f"{nombre}  —  corte en {corte:.3f} s")
        ax.set_xlim(max(0, corte - 1.0), corte + 1.0)   # zoom ±1 s alrededor del corte
        ax.legend(loc="upper right", fontsize=8)
    axes[-1].set_xlabel("segundos")
    fig.tight_layout()
    fig.savefig(OUT / "detecciones.png", dpi=120)

    print(f"{'versión':<8} {'detector':<14} {'total':>5}  coincide con el corte (±60 ms)")
    print("-" * 70)
    for v, d, n, ac in filas:
        if d == "VozAmbosLados":
            marca = "SÍ (corte en medio del habla)" if ac else "no (corte en pausa)"
        else:
            marca = "SÍ " + str([float(a) for a in ac]) if ac else "no"
        print(f"{v:<8} {d:<14} {str(n):>5}  {marca}")
    print(f"\nImagen: {OUT/'detecciones.png'}")
    print(f"WAVs:   {OUT}/limpio.wav, sucio.wav, hueco.wav")

if __name__ == "__main__":
    main()
