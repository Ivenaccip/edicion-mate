#!/usr/bin/env python3
"""
Limpia respiraciones y pops en una pista de voz, usando el transcript para saber dónde hay
habla y dónde no.

  python pipeline/limpiar_audio.py audio.wav palabras.json salida.wav [--video in.mp4 out.mp4]

Tres capas, todas suaves y reversibles (los parámetros están arriba):
  1. Filtro paso-alto global a 85 Hz: quita el retumbe de aire sin tocar la voz.
  2. De-viento (antes "de-pop"): el aire que golpea el micrófono (P, B, M, o soplar al hablar)
     mete un retumbe de 20–150 Hz que sobresale +10..+20 dB sobre la voz. Medido en IMG_7889:
     83 ráfagas en 33 s. Se calcula por frame cuánto sobresalen los graves respecto a los
     medios (150–2000 Hz) frente a lo típico de la voz, y con esa medida se mezcla de forma
     CONTINUA una versión filtrada a POP_HP_HZ: 0 % cuando no hay viento, 100 % cuando el
     exceso pasa de VIENTO_DB_MAX. Es un filtro de graves dinámico, no un notch fijo: un
     notch fijo tocaría la fundamental de la voz (100–150 Hz) todo el tiempo.
  3. Respiraciones: dentro de cada hueco entre palabras (AssemblyAI, con margen) se clasifica
     cada frame de 10 ms por la señal: VOZ = tiene armónicos (planitud espectral baja);
     RESPIRACIÓN = ruido sin tono (planitud alta o muchos cruces por cero) por encima del
     piso, y a >= 60 ms de cualquier frame de voz. Solo se atenúa la respiración, RESP_DB
     (−12 dB) con fundidos de 20 ms. Así un error de ±170 ms en los tiempos por palabra no
     hace que se baje el arranque de la palabra siguiente (pasó en la v1).
Escribe <salida>.limpieza.json con cada intervención.
"""
import sys, json, argparse, subprocess
from pathlib import Path
import numpy as np, soundfile as sf
from scipy.signal import butter, sosfilt, sosfiltfilt

HP_GLOBAL_HZ = 85
POP_HP_HZ = 200; VIENTO_DB_MIN = 5; VIENTO_DB_MAX = 12; VIENTO_SUAVIZADO_MS = 15
RESP_DB = -12.0; RESP_MIN_MS = 60; RESP_SOBRE_PISO_DB = 4; RESP_FADE_MS = 20; RESP_HUECO_MIN_MS = 100
VOZ_PLANITUD_MAX = 0.06; RESP_PLANITUD_MIN = 0.10; RESP_ZCR_MIN = 0.12; DIST_VOZ_MS = 60; HUECO_MARGEN_MS = 200
RESP_EXT_MS = 40   # extender la zona atenuada a cada lado (sigue a >= 20 ms de la voz) para que el fundido no se coma el núcleo

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

    # 2) de-viento: filtro de graves dinámico guiado por el exceso de graves frente a la voz
    low = sosfilt(butter(4, 150, "lowpass", fs=sr, output="sos"), x)
    mid = sosfilt(butter(4, [150, 2000], "bandpass", fs=sr, output="sos"), x)
    rl = np.array([np.sqrt(np.mean(low[i*n:(i+1)*n]**2)) for i in range(nf)])
    rm = np.array([np.sqrt(np.mean(mid[i*n:(i+1)*n]**2)) for i in range(nf)])
    rel = 20*np.log10((rl + 1e-9) / (rm + 1e-9))
    ref = np.median(rel[db > np.percentile(db, 60)])              # graves/medios típico de la voz
    exceso = rel - ref
    g = np.clip((exceso - VIENTO_DB_MIN) / (VIENTO_DB_MAX - VIENTO_DB_MIN), 0, 1)
    g[db < piso + 6] = 0                                          # en silencio no hay nada que filtrar
    # a muestras, con suavizado (ataque/relajación) para que el filtro entre y salga sin clics
    gm = np.repeat(g, n)[:len(y)]; gm = np.pad(gm, (0, len(y) - len(gm)), mode="edge")
    ks = int(sr * VIENTO_SUAVIZADO_MS / 1000); kern = np.ones(ks) / ks
    gm = np.convolve(gm, kern, mode="same").astype(np.float32)
    y_hp = sosfiltfilt(butter(4, POP_HP_HZ, "highpass", fs=sr, output="sos"), y).astype(np.float32)
    y = y * (1 - gm) + y_hp * gm
    pops, i = [], 0                                               # para el reporte: tramos con g > 0.5
    while i < nf:
        if g[i] > 0.5:
            j = i
            while j < nf and g[j] > 0.5: j += 1
            pops.append((i * n, j * n)); i = j
        else: i += 1

    # 3) respiraciones: clasificar frames por la señal dentro de los huecos entre palabras
    plan = np.zeros(nf); zcr = np.zeros(nf); win = np.hanning(n)
    for i in range(nf):
        s_ = x[i*n:(i+1)*n]; spec = np.abs(np.fft.rfft(s_ * win)) + 1e-9
        plan[i] = np.exp(np.mean(np.log(spec))) / np.mean(spec)
        zcr[i] = np.mean(np.abs(np.diff(np.sign(s_)))) / 2
    voz = (plan < VOZ_PLANITUD_MAX) & (db > nivel_voz - 20)
    ruido = ((plan > RESP_PLANITUD_MIN) | (zcr > RESP_ZCR_MIN)) & (db > piso + RESP_SOBRE_PISO_DB)
    dv = int(DIST_VOZ_MS / 10)
    lejos_de_voz = np.array([not voz[max(0, i-dv):i+dv+1].any() for i in range(nf)])
    en_hueco = np.zeros(nf, dtype=bool); m = int(HUECO_MARGEN_MS / 10)
    for p, q in zip(w, w[1:]):
        if (q["ini"] - p["fin"]) * 1000 >= RESP_HUECO_MIN_MS:
            en_hueco[max(0, int(p["fin"]*100) - m):int(q["ini"]*100) + m] = True
    cand = ruido & lejos_de_voz & en_hueco
    resp, i = [], 0
    while i < nf:
        if cand[i]:
            j = i
            while j < nf and cand[j]: j += 1
            if (j - i) * 10 >= RESP_MIN_MS:
                t0, t1 = i / 100, j / 100
                p = next((p["w"] for p in reversed(w) if p["fin"] <= t0 + 0.2), "")
                q = next((q["w"] for q in w if q["ini"] >= t1 - 0.2), "")
                ext = int(sr * RESP_EXT_MS / 1000)
                resp.append((max(0, i * n - ext), min(len(x), j * n + ext), float(db[i:j].max()), p, q))
            i = j
        else: i += 1
    mr = rampa_mask(len(y), [(r[0], r[1]) for r in resp], int(sr*RESP_FADE_MS/1000))
    gan = 10 ** (a.resp_db / 20)
    y = y * (1 - mr * (1 - gan))

    sf.write(a.salida, y, sr)
    rep = {"entrada": a.audio, "salida": a.salida, "nivel_voz_dbfs": round(float(nivel_voz),1), "piso_dbfs": round(float(piso),1),
           "paso_alto_hz": HP_GLOBAL_HZ, "viento_hp_hz": POP_HP_HZ, "viento_umbral_db": [VIENTO_DB_MIN, VIENTO_DB_MAX],
           "pops": [{"ini": round(p0/sr,3), "fin": round(p1/sr,3)} for p0, p1 in pops],
           "respiraciones": [{"ini": round(r[0]/sr,3), "fin": round(r[1]/sr,3), "pico_dbfs": round(r[2],1), "entre": [r[3], r[4]], "gan_db": a.resp_db} for r in resp]}
    Path(a.salida).with_suffix(".limpieza.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    print(f"ráfagas de viento filtradas: {len(pops)}, respiraciones atenuadas {a.resp_db} dB: {len(resp)}  -> {a.salida}")
    if a.video:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", a.video[0], "-i", a.salida, "-map", "0:v", "-map", "1:a",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", a.video[1]], check=True)
        print(f"video con audio limpio: {a.video[1]}")

if __name__ == "__main__":
    main()
