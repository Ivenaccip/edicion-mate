#!/usr/bin/env python3
"""Construye la máscara fija de "verde en sombra" para la llave por zonas.

La cámara no se mueve, así que las zonas donde la tela verde está en sombra (cerca de la mesa, esquinas)
son siempre las mismas. Ahí el verde queda a distancia UV 0.08-0.10 del color clave y un chromakey global
con similarity=0.08 las deja parpadeando. En esta máscara se usa una tolerancia mayor (0.13), que sigue
lejos del negro de la ropa y la laptop (0.156).

Criterio por píxel, en al menos --fraccion de varios frames del raw (la zona debe ser estática: el spill
sobre pelo, manos o silla se mueve con la persona y así queda fuera):
  verdoso (G > 1.6*max(R,B)) y distancia UV al clave entre dist_min y dist_max.
Luego dilatación y pluma para que el borde de la zona no se note.

Uso: mascara_sombras.py raw.mp4 mascara.png [--frames 12] [--ancho 1080] [--rotar ccw --encuadre 9:16]
"""
import argparse, cv2, numpy as np
from verde_util import prep_vf, muestras_yuv, rgb_de_yuv, uv_de_hex

def preparar(fr, rotar, encuadre, ancho):
    if rotar == "ccw": fr = cv2.rotate(fr, cv2.ROTATE_90_COUNTERCLOCKWISE)
    if encuadre == "9:16":
        h, w = fr.shape[:2]; nh = int(w * 16 / 9); y0 = (h - nh) // 2; fr = fr[y0:y0 + nh]
    if ancho and fr.shape[1] != ancho:
        h, w = fr.shape[:2]; fr = cv2.resize(fr, (ancho, int(round(h * ancho / w))), interpolation=cv2.INTER_AREA)
    return fr

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw"); ap.add_argument("salida")
    ap.add_argument("--frames", type=int, default=12); ap.add_argument("--ancho", type=int, default=1080, help="salida 9:16: ancho x ancho*16/9")
    ap.add_argument("--rotar", choices=["no", "ccw"], default="ccw"); ap.add_argument("--encuadre", choices=["no", "9:16"], default="9:16")
    ap.add_argument("--clave", default="1e7032"); ap.add_argument("--dist-min", type=float, default=0.065); ap.add_argument("--dist-max", type=float, default=0.14)
    ap.add_argument("--fraccion", type=float, default=0.9, help="fracción de frames en que el píxel debe cumplir el criterio")
    ap.add_argument("--dilatar", type=int, default=10); ap.add_argument("--pluma", type=float, default=1)
    a = ap.parse_args()
    ku, kv = uv_de_hex(a.clave)
    # planos U/V nativos (el mismo espacio que compara chromakey), ver verde_util.py
    Y, U, V = muestras_yuv(a.raw, a.frames, prep_vf(a.rotar, a.encuadre, a.ancho, a.ancho * 16 // 9))
    r, g, b = rgb_de_yuv(Y, U, V)
    d = np.sqrt((U - ku) ** 2 + (V - kv) ** 2) / 255.0
    verdoso = g > 1.6 * np.maximum(r, b)
    acum = (verdoso & (d >= a.dist_min) & (d <= a.dist_max)).astype(np.float32).sum(axis=0); usados = Y.shape[0]
    acum = (acum / max(usados, 1) >= a.fraccion).astype(np.uint8)
    # limpiar motas y ensanchar
    acum = cv2.morphologyEx(acum, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    acum = cv2.dilate(acum, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * a.dilatar + 1, 2 * a.dilatar + 1)))
    masc = cv2.GaussianBlur(acum.astype(np.float32) * 255, (0, 0), a.pluma)
    masc = np.clip(masc, 0, 255).astype(np.uint8)
    # PNG RGBA con los cuatro canales iguales, para maskedmerge sobre entradas rgba
    cv2.imwrite(a.salida, np.dstack([masc, masc, masc, masc]))
    print(f"{a.salida}: {masc.shape[1]}x{masc.shape[0]}, zona ancha = {(masc > 127).mean() * 100:.1f} % del cuadro")

if __name__ == "__main__":
    main()
