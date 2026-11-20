#!/usr/bin/env python3
"""
Editor mínimo de pausas (Fase 1, sin transcript).

Escucha la señal, encuentra todas las pausas, decide cuáles acortar y aplica
los cortes con crossfade. Entrega el audio editado y un EDL con cada decisión.

Reglas:
  - Pausa = tramo con energía < UMBRAL_DB relativo al nivel de voz, de >= MIN_PAUSA ms.
  - Se acortan solo las pausas > PAUSA_MAX ms; se dejan en PAUSA_OBJETIVO ms.
  - Nunca se corta dentro de voz: el recorte ocurre en el centro de la pausa.
  - Crossfade de CROSSFADE ms en cada empalme.
  - Inicio y fin del audio: se dejan PAUSA_BORDE ms.

Uso: python editor_pausas.py entrada.wav salida.wav
"""
import sys, json
from pathlib import Path
import numpy as np, soundfile as sf

UMBRAL_DB = -35      # energía por debajo del nivel de voz (percentil 90) para considerar pausa
MIN_PAUSA = 120      # ms: menos que esto no es pausa, es articulación
PAUSA_MAX = 450      # ms: pausas más largas se acortan
PAUSA_OBJETIVO = 250 # ms: a cuánto se dejan
PAUSA_BORDE = 150    # ms de silencio al inicio y al final
CROSSFADE = 15       # ms
VENTANA = 10         # ms por frame de energía

def db(x): return 20 * np.log10(np.maximum(x, 1e-9))

def pausas(x, sr):
    n = int(sr * VENTANA / 1000)
    nf = len(x) // n
    rms = np.array([np.sqrt(np.mean(x[i*n:(i+1)*n]**2)) for i in range(nf)])
    nivel_voz = np.percentile(db(rms), 90)
    quieto = db(rms) < nivel_voz + UMBRAL_DB
    out, i = [], 0
    while i < nf:
        if quieto[i]:
            j = i
            while j < nf and quieto[j]: j += 1
            dur = (j - i) * VENTANA
            if dur >= MIN_PAUSA:
                out.append((i * n, j * n, dur))
            i = j
        else:
            i += 1
    return out, nivel_voz

def crossfade(a, b, sr):
    k = int(sr * CROSSFADE / 1000)
    if len(a) < k or len(b) < k:          # trozo más corto que el fundido: unir sin fundir
        return np.concatenate([a, b])
    r = np.linspace(0, 1, k)
    return np.concatenate([a[:-k], a[-k:] * (1 - r) + b[:k] * r, b[k:]])

def editar(entrada, salida):
    x, sr = sf.read(entrada)
    if x.ndim > 1: x = x.mean(axis=1)
    lista, nivel = pausas(x, sr)
    edl, piezas, cursor, quitado = [], [], 0, 0.0
    for ini, fin, dur in lista:
        es_borde = ini == 0 or fin >= len(x) - int(sr * VENTANA / 1000)
        objetivo = PAUSA_BORDE if es_borde else PAUSA_OBJETIVO
        if dur <= (objetivo if es_borde else PAUSA_MAX):
            edl.append({"pausa": [round(ini/sr,3), round(fin/sr,3)], "dur_ms": dur, "accion": "se deja"})
            continue
        recorte = int(sr * (dur - objetivo) / 1000)
        if es_borde and ini == 0:
            c_ini, c_fin = ini, ini + recorte                 # inicio: quitar por el frente
        elif es_borde:
            c_ini, c_fin = fin - recorte, fin                 # final: quitar por atrás
        else:
            centro = (ini + fin) // 2
            c_ini, c_fin = centro - recorte // 2, centro + recorte // 2
        piezas.append(x[cursor:c_ini]); cursor = c_fin; quitado += recorte / sr
        edl.append({"pausa": [round(ini/sr,3), round(fin/sr,3)], "dur_ms": dur,
                    "accion": f"acortar a {objetivo} ms", "quitar": [round(c_ini/sr,3), round(c_fin/sr,3)],
                    "quitado_ms": round(recorte / sr * 1000)})
    piezas.append(x[cursor:])
    y = piezas[0]
    for p in piezas[1:]:
        y = p if len(y) == 0 else crossfade(y, p, sr)
    sf.write(salida, y, sr)
    resumen = {"entrada": str(entrada), "salida": str(salida), "sr": sr,
               "nivel_voz_dbfs": round(float(nivel), 1), "duracion_original_s": round(len(x)/sr, 3),
               "duracion_editada_s": round(len(y)/sr, 3), "quitado_s": round(quitado, 3),
               "pausas_encontradas": len(lista), "pausas_acortadas": sum(1 for e in edl if "quitar" in e),
               "reglas": {"UMBRAL_DB": UMBRAL_DB, "MIN_PAUSA": MIN_PAUSA, "PAUSA_MAX": PAUSA_MAX,
                          "PAUSA_OBJETIVO": PAUSA_OBJETIVO, "CROSSFADE": CROSSFADE},
               "edl": edl}
    Path(salida).with_suffix(".edl.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1))
    return resumen

if __name__ == "__main__":
    r = editar(sys.argv[1], sys.argv[2])
    print(f"original {r['duracion_original_s']} s -> editado {r['duracion_editada_s']} s  (quitado {r['quitado_s']} s)")
    print(f"pausas encontradas: {r['pausas_encontradas']}, acortadas: {r['pausas_acortadas']}\n")
    for e in r["edl"]:
        q = f"  quitar {e['quitar'][0]}-{e['quitar'][1]} ({e['quitado_ms']} ms)" if "quitar" in e else ""
        print(f"  {e['pausa'][0]:6.3f}-{e['pausa'][1]:6.3f}  {e['dur_ms']:5d} ms  {e['accion']}{q}")
    print(f"\nEDL: {Path(r['salida']).with_suffix('.edl.json')}")
