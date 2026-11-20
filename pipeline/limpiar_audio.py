#!/usr/bin/env python3
"""
Limpia respiraciones y pops en una pista de voz, usando el transcript para saber dónde hay
habla y dónde no.

  python pipeline/limpiar_audio.py audio.wav palabras.json salida.wav [--video in.mp4 out.mp4]

Tres capas, todas suaves y reversibles (los parámetros están arriba):
  1. Filtro paso-alto global a 85 Hz: quita el retumbe de aire sin tocar la voz.
  2. De-pop: en cada ráfaga de graves (<150 Hz dominando) dentro de una palabra, se mezcla
     durante ~30 ms una versión filtrada a 220 Hz. La consonante se oye, el golpe no.
  3. Respiraciones: en cada hueco entre palabras con energía claramente por encima del piso
     de ruido, se baja el volumen RESP_DB (−12 dB) con fundidos de 30 ms. No se silencia:
     una respiración a −12 dB suena natural; a −inf suena a corte.
Escribe <salida>.limpieza.json con cada intervención.
"""
import sys, json, argparse, subprocess
from pathlib import Path
import numpy as np, soundfile as sf
from scipy.signal import butter, sosfilt, sosfiltfilt

HP_GLOBAL_HZ = 85
POP_HP_HZ = 220; POP_RATIO = 0.7; POP_MARGEN_MS = 15
RESP_DB = -12.0; RESP_MIN_MS = 80; RESP_SOBRE_PISO_DB = 6; RESP_FADE_MS = 30; RESP_HUECO_MIN_MS = 120

def rampa_mask(n_total, intervalos, fade):
    """Máscara 0..1 que vale 1 dentro de los intervalos (en muestras) con fundidos de `fade` muestras."""
    m = np.zeros(n_total, dtype=np.float32)
    for a, b in intervalos:
        a, b = max(0, a), min(n_total, b)
        if b - a <= 0: continue
        m[a:b] = 1.0
        f = min(fade, (b - a) // 2)
        if f > 0:
            m[a:a+f] = np.linspace(0, 1, f); m[b-f:b] = np.linspace(1, 0, f)
    return m

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio"); ap.add_argument("palabras"); ap.add_argument("salida")
    ap.add_argument("--video", nargs=2, metavar=("IN", "OUT"), help="remuxear el audio limpio en este video")
    ap.add_argument("--resp-db", type=float, default=RESP_DB, help="atenuación de respiraciones en dB (por defecto -12)")
    a = ap.parse_args()
    x, sr = sf.read(a.audio, dtype="float32")
    if x.ndim > 1: x = x.mean(axis=1)
    w = json.load(open(a.palabras))
    n = int(sr * 0.01); nf = len(x) // n
    rms = np.array([np.sqrt(np.mean(x[i*n:(i+1)*n]**2)) for i in range(nf)]); db = 20*np.log10(np.maximum(rms, 1e-9))
    nivel_voz, piso = np.percentile(db, 90), np.percentile(db, 5)

    # 1) paso-alto global
    y = sosfiltfilt(butter(2, HP_GLOBAL_HZ, "highpass", fs=sr, output="sos"), x).astype(np.float32)

    # 2) pops: ráfagas donde los graves dominan, dentro de palabras
    low = sosfilt(butter(4, 150, "lowpass", fs=sr, output="sos"), x)
    rl = np.array([np.sqrt(np.mean(low[i*n:(i+1)*n]**2)) for i in range(nf)]); ratio = rl / np.maximum(rms, 1e-9)
    pops, i = [], 0
    while i < nf:
        if ratio[i] > POP_RATIO and db[i] > nivel_voz - 12:
            j = i
            while j < nf and ratio[j] > 0.5: j += 1
            pops.append((i*n - int(sr*POP_MARGEN_MS/1000), j*n + int(sr*POP_MARGEN_MS/1000))); i = j
        else: i += 1
    y_pop = sosfiltfilt(butter(2, POP_HP_HZ, "highpass", fs=sr, output="sos"), y).astype(np.float32)
    mp = rampa_mask(len(y), pops, int(sr*0.005))
    y = y * (1 - mp) + y_pop * mp

    # 3) respiraciones: huecos entre palabras con energía sobre el piso
    resp = []
    for p, q in zip(w, w[1:]):
        g0, g1 = p["fin"], q["ini"]
        if (g1 - g0) * 1000 < RESP_HUECO_MIN_MS: continue
        seg = db[int(g0*100):int(g1*100)]
        if (seg > piso + RESP_SOBRE_PISO_DB).sum() * 10 >= RESP_MIN_MS:
            resp.append((int(g0*sr), int(g1*sr), float(seg.max()), p["w"], q["w"]))
    mr = rampa_mask(len(y), [(r[0], r[1]) for r in resp], int(sr*RESP_FADE_MS/1000))
    gan = 10 ** (a.resp_db / 20)
    y = y * (1 - mr * (1 - gan))

    sf.write(a.salida, y, sr)
    rep = {"entrada": a.audio, "salida": a.salida, "nivel_voz_dbfs": round(float(nivel_voz),1), "piso_dbfs": round(float(piso),1),
           "paso_alto_hz": HP_GLOBAL_HZ,
           "pops": [{"ini": round(p0/sr,3), "fin": round(p1/sr,3)} for p0, p1 in pops],
           "respiraciones": [{"ini": round(r[0]/sr,3), "fin": round(r[1]/sr,3), "pico_dbfs": round(r[2],1), "entre": [r[3], r[4]], "gan_db": a.resp_db} for r in resp]}
    Path(a.salida).with_suffix(".limpieza.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    print(f"pops tratados: {len(pops)}, respiraciones atenuadas {a.resp_db} dB: {len(resp)}  -> {a.salida}")
    if a.video:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", a.video[0], "-i", a.salida, "-map", "0:v", "-map", "1:a",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", a.video[1]], check=True)
        print(f"video con audio limpio: {a.video[1]}")

if __name__ == "__main__":
    main()
