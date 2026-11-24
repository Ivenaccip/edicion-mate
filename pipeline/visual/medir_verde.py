#!/usr/bin/env python3
"""Mide el verde de un set y propone la llave: color clave, tolerancia global, tolerancia en sombras y techo.

Cada grabación tiene su verde (luz, exposición, tela). IMG_7889 era verde oscuro (#1e7032, UV 111,92) y IMG_7924
verde claro (UV ~101,79); con el clave del otro la llave queda corrida. Por eso la llave se mide por video, en el
mismo espacio UV que usa chromakey (verde_util.py):
  clave   = mediana UV de los píxeles "muy verdes" (G > 1.5*max(R,B)) en N frames, con la luma mediana del fondo
  fondo   = distancia UV al clave de esos píxeles: p50/p95/p99/max (lo que la llave tiene que cubrir)
  persona = distancia UV al clave de los píxeles no verdosos (G <= 1.2*max(R,B)): p1 (lo que NO debe tocar)
  SIM        = min(fondo_p99 + 0.02, persona_p1 - 0.06), acotado a [0.07, 0.16]
  SIM_SOMBRA = min(SIM + 0.03, persona_p1 - 0.05)
  TECHO      = persona_p1 - 0.04   (por encima de esto la llave se come ropa/pelo; el auditor lo usa como tope)
Escribe <salida>.env (CLAVE/SIM/SIM_SOMBRA/TECHO para quitar_verde_ffmpeg.sh y vestir.sh) y <salida>.json.
Uso: medir_verde.py cuerpo_1080.mp4 llave [--frames 12] [--rotar ccw --encuadre 9:16]
"""
import argparse, json, numpy as np
from pathlib import Path
from verde_util import prep_vf, muestras_yuv, rgb_de_yuv, hex_de_yuv

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video"); ap.add_argument("salida", help="base de salida: escribe <salida>.env y <salida>.json")
    ap.add_argument("--frames", type=int, default=12)
    ap.add_argument("--rotar", choices=["no", "ccw"], default="no"); ap.add_argument("--encuadre", choices=["no", "9:16"], default="no")
    a = ap.parse_args()
    Y, U, V = muestras_yuv(a.video, a.frames, prep_vf(a.rotar, a.encuadre))
    r, g, b = rgb_de_yuv(Y, U, V)
    mv = g > 1.5 * np.maximum(r, b); mfg = g <= 1.2 * np.maximum(r, b)
    if mv.mean() < 0.05: raise SystemExit("menos del 5 % del cuadro es verde: ¿es un raw con pantalla verde?")
    ku, kv, ky = float(np.median(U[mv])), float(np.median(V[mv])), float(np.median(Y[mv]))
    d = np.sqrt((U - ku) ** 2 + (V - kv) ** 2) / 255.0
    fondo = np.percentile(d[mv], [50, 95, 99, 100]); persona_p1 = float(np.percentile(d[mfg], 1))
    sim = float(np.clip(min(fondo[2] + 0.02, persona_p1 - 0.06), 0.07, 0.16))
    sim_sombra = float(min(sim + 0.03, persona_p1 - 0.05)); techo = float(persona_p1 - 0.04)
    clave = hex_de_yuv(ky, ku, kv)
    res = {"video": a.video, "frames": int(mv.shape[0]), "verde_pct": round(float(mv.mean()) * 100, 1),
           "clave_uv": [round(ku, 1), round(kv, 1)], "clave_luma": round(ky, 1), "clave_hex": clave,
           "fondo_dist": {k: round(float(x), 3) for k, x in zip(("p50", "p95", "p99", "max"), fondo)},
           "persona_dist_p1": round(persona_p1, 3),
           "propuesta": {"SIM": round(sim, 3), "SIM_SOMBRA": round(sim_sombra, 3), "TECHO": round(techo, 3)}}
    base = Path(a.salida)
    base.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    base.with_suffix(".env").write_text(f"CLAVE=0x{clave}\nSIM={sim:.3f}\nSIM_SOMBRA={sim_sombra:.3f}\nTECHO={techo:.3f}\n")
    print(json.dumps(res, ensure_ascii=False))

if __name__ == "__main__":
    main()
