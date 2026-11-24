#!/usr/bin/env python3
"""Detecta por señal un tartamudeo (una frase dicha dos veces seguidas) dentro de una toma.

Por qué por señal: el transcriptor funde las repeticiones ("Si te quieres mantener, si te quieres mantener
actualizado" sale como una sola frase), tanto en el raw completo como en el segmento aislado. La repetición sí se
ve en el audio: la trayectoria espectral (log-mel, 10 ms) de la primera frase vuelve a aparecer un poco después.

Método: bloques A = mel[P:P+L] y B = mel[P+S:P+S+L] (L 0.6-1.3 s, S = L..L+1.2 s: la pausa entre repeticiones).
Distancia = media de la distancia euclídea por frame, con B re-muestreado a velocidades 0.85-1.15 (la repetición
se dice a un ritmo parecido, no idéntico). Referencia = mediana de la distancia de A contra bloques lejanos del
mismo audio. Candidato si distancia / referencia < 0.60 (en IMG_7922 el tartamudeo real da 0.50-0.57 y los bloques
sin repetición quedan en 0.75-1.0). refinar() fija el corte (una repetición exacta, desde el aire anterior) y lo
comprueba; quitar_tartamudeos() repite hasta 3 veces (tomas con varios tartamudeos encadenados).

Uso de prueba: tartamudeo.py raw_audio.wav ini fin
"""
import sys, numpy as np
from scipy.signal import stft

def logmel(x, sr, n_mels=24, hop=0.01):
    nfft = 512; h = int(sr * hop)
    f, t, Z = stft(x, sr, nperseg=nfft, noverlap=nfft - h, padded=False, boundary=None)
    P = np.abs(Z) ** 2
    mel = lambda f: 2595 * np.log10(1 + f / 700); imel = lambda m: 700 * (10 ** (m / 2595) - 1)
    pts = imel(np.linspace(mel(80), mel(min(7600, sr / 2)), n_mels + 2)); idx = np.searchsorted(f, pts)
    fb = np.zeros((n_mels, len(f)))
    for i in range(n_mels):
        a, b, c = idx[i], idx[i + 1], idx[i + 2]
        if b > a: fb[i, a:b] = np.linspace(0, 1, b - a, endpoint=False)
        if c > b: fb[i, b:c] = np.linspace(1, 0, c - b, endpoint=False)
    M = np.log(fb @ P + 1e-8).T
    M -= M.mean(axis=0, keepdims=True)
    return M, hop

VEL = (0.85, 0.92, 1.0, 1.08, 1.15)

def dist(A, M, q, nL):
    """Distancia de A (nL frames) contra M desde el frame q, con B leído a varias velocidades."""
    mejor = np.inf
    for v in VEL:
        idx = q + np.round(np.arange(nL) * v).astype(int)
        if idx[-1] >= len(M): continue
        d = np.sqrt(((A - M[idx]) ** 2).sum(axis=1)).mean(); mejor = min(mejor, d)
    return mejor

def detectar(x, sr, umbral=0.60, paso_p=0.1, paso_s=0.05, M=None):
    """Candidatos (ratio, P, P+S, L) ordenados de mejor a peor, con ratio < umbral."""
    if M is None: M, hop = logmel(x, sr)
    hop = 0.01; n = len(M); fr = lambda s: int(round(s / hop)); T = n * hop
    cands = []
    for L in (0.45, 0.6, 0.9, 1.2):
        nL = fr(L)
        for P in np.arange(0, T - 2 * L, paso_p):
            A = M[fr(P):fr(P) + nL]
            if len(A) < nL: break
            lejos = [q for q in np.arange(0, T - L * 1.2, 0.5) if abs(q - P) > L + 1.3]
            refs = [dist(A, M, fr(q), nL) for q in lejos]
            if len(refs) < 3: continue
            ref = float(np.median(refs))
            for S in np.arange(L, L + 1.21, paso_s):
                if P + S + L * 1.15 > T: break
                r = dist(A, M, fr(P + S), nL) / ref
                if r < umbral: cands.append((float(r), float(P), float(P + S), float(L)))
    return sorted(cands)

def refinar(x, sr, r, M=None):
    """Convierte un candidato (ratio, P, P+S, L) en el tramo a quitar [q0, q1): una repetición completa.
    q0 = ventana de 20 ms con menos energía en los 0.8 s antes de P (el aire antes de la primera repetición);
    S' = desfase en [S-0.35, S+0.35] que mejor alinea los 0.5 s que siguen a q0 con lo que sigue a q0+S'
    (así el corte salta al mismo punto de la segunda repetición y el resultado suena a una sola frase);
    q1 = q0 + S'. Se comprueba la alineación: si lo que sigue a q0 y lo que sigue a q1 no se parecen
    (ratio2 >= 0.65 contra bloques lejanos), el candidato era falso y devuelve None."""
    _, P, PS, L = r; S = PS - P
    if M is None: M, hop = logmel(x, sr)
    hop = 0.01; fr = lambda s: int(round(s / hop))
    n = sr // 50; t0 = max(0.0, P - 0.8); e = []
    for t in np.arange(t0, P + 0.001, 0.01):
        seg = x[int(t * sr):int(t * sr) + n]; e.append((float(np.sqrt((seg ** 2).mean())) if len(seg) else 1.0, t))
    q0 = min(e)[1]
    A = M[fr(q0):fr(q0) + fr(0.5)]
    cand = [(dist(A, M, fr(q0 + s2), len(A)), s2) for s2 in np.arange(max(0.3, S - 0.35), S + 0.351, 0.01) if fr(q0 + s2) + fr(0.5) * 1.15 < len(M)]
    if not cand: return None
    d2, S2 = min(cand)
    lejos = [q for q in np.arange(0, len(M) * hop - 0.6, 0.5) if abs(q - q0) > 1.5 and abs(q - q0 - S2) > 0.8]
    refs = [dist(A, M, fr(q), len(A)) for q in lejos]
    if len(refs) >= 3 and d2 / np.median(refs) >= 0.65: return None
    return float(q0), float(q0 + S2)

def quitar_tartamudeos(x, sr, max_pasadas=3):
    """Quita hasta max_pasadas repeticiones de una toma. Devuelve la lista de tramos [ini, fin) a QUITAR, en
    segundos relativos a la toma original (ya corregidos por las quitas previas)."""
    quitar = []; y = x.copy(); desplaz = []   # desplaz: (pos_en_y, largo) de cada quita, para mapear a x
    for _ in range(max_pasadas):
        M, _h = logmel(y, sr); cands = detectar(y, sr, M=M)
        tramo = None
        for c in cands[:12]:
            q = refinar(y, sr, c, M=M)
            if q: tramo = q; break
        if not tramo: break
        q0, q1 = tramo
        # mapear a tiempos del audio original: sumar lo ya quitado antes de q0
        o0 = q0 + sum(l for p, l in desplaz if p <= q0); o1 = o0 + (q1 - q0)
        quitar.append((o0, o1)); desplaz.append((q0, q1 - q0))
        y = np.concatenate([y[:int(q0 * sr)], y[int(q1 * sr):]])
    return quitar

if __name__ == "__main__":
    import soundfile as sf
    x, sr = sf.read(sys.argv[1], dtype="float32"); x = x.mean(axis=1) if x.ndim > 1 else x
    ini, fin = float(sys.argv[2]), float(sys.argv[3]); qs = quitar_tartamudeos(x[int(ini * sr):int(fin * sr)], sr)
    print("sin tartamudeo" if not qs else "quitar: " + ", ".join(f"{ini + a:.3f}-{ini + b:.3f} ({b - a:.2f} s)" for a, b in qs))
