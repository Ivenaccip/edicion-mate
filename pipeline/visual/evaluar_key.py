#!/usr/bin/env python3
"""Mide qué tan bien una imagen RGBA quitó el verde del fotograma de referencia IMG_7889 (2160x3840).

Zonas fijas (en coordenadas del fotograma 2160x3840, rotado y recortado 9:16):
  verde: cinco zonas donde solo hay pantalla verde (las del handoff).
  persona: cara, sudadera, silla, laptop; alfa debe ser 255.
Salida: alfa medio en cada zona y dos resúmenes: "verde_restante" (0 ideal) y "persona_perdida" (0 ideal).
"""
import sys, json
import numpy as np
from PIL import Image

W, H = 2160, 3840
# (x0, y0, x1, y1)
ZONAS_VERDE = {
    "arriba-izq": (100, 100, 700, 900),
    "arriba-der": (1460, 100, 2060, 900),
    "centro-arriba": (780, 100, 1380, 1200),
    "lado-izq-medio": (40, 1500, 340, 2500),
    "lado-der-medio": (1900, 1500, 2120, 2500),
}
ZONAS_PERSONA = {
    "cara": (820, 1700, 1100, 2000),
    "sudadera": (700, 2300, 1000, 2600),
    "silla": (1260, 1850, 1500, 2100),
    "laptop": (300, 2900, 1200, 3300),
    "pelo": (820, 1520, 1050, 1620),
}

def evaluar(ruta):
    im = Image.open(ruta).convert("RGBA")
    if im.size != (W, H):
        im = im.resize((W, H), Image.BILINEAR)
    a = np.asarray(im)[:, :, 3].astype(np.float32)
    res = {"verde": {}, "persona": {}}
    for n, (x0, y0, x1, y1) in ZONAS_VERDE.items():
        res["verde"][n] = float(a[y0:y1, x0:x1].mean())
    for n, (x0, y0, x1, y1) in ZONAS_PERSONA.items():
        res["persona"][n] = float(a[y0:y1, x0:x1].mean())
    res["verde_restante"] = max(res["verde"].values()) / 255 * 100   # % alfa que quedó en el peor rincón verde
    res["persona_perdida"] = (255 - min(res["persona"].values())) / 255 * 100  # % alfa perdido en la peor zona de persona
    return res

if __name__ == "__main__":
    for ruta in sys.argv[1:]:
        r = evaluar(ruta)
        print(f"{ruta.split('/')[-1]:36s} verde_restante={r['verde_restante']:5.1f}%  persona_perdida={r['persona_perdida']:5.1f}%  "
              f"verde={ {k: round(v) for k, v in r['verde'].items()} }  persona={ {k: round(v) for k, v in r['persona'].items()} }")
