"""Lectura de frames en el mismo espacio UV que usa `chromakey`, compartida por medir_verde, mascara_sombras y auditar_llave.

`chromakey` compara los planos U/V nativos del video con el clave convertido de RGB con la matriz BT.601 de rango
completo (U = -0.169R - 0.331G + 0.5B + 128; V = 0.5R - 0.419G - 0.081B + 128). Si se leen frames en rgb24 y se
recalcula UV (o se usa cv2.COLOR_BGR2YUV, que lleva otros coeficientes), las distancias salen escaladas ~10-15 % y el
umbral medido no coincide con la similarity real. Aquí se leen los planos U/V tal cual (yuv444p rawvideo, sin matriz).
"""
import subprocess, numpy as np

def prep_vf(rotar="no", encuadre="no", ancho=1080, alto=1920):
    vf = []
    if rotar == "ccw": vf.append("transpose=2")
    if rotar == "cw": vf.append("transpose=1")
    if encuadre == "9:16": vf.append("crop=iw:iw*16/9")
    vf.append(f"scale={ancho}:{alto}")
    return vf

def leer_yuv(video, vf, ancho=1080, alto=1920, antes=(), dur=None):
    """Devuelve (Y, U, V) float32 de forma (n, alto, ancho) con los planos nativos (sin conversión de matriz)."""
    cmd = ["ffmpeg", "-v", "error", *antes, "-i", video, *(["-t", str(dur)] if dur else []),
           "-vf", ",".join(vf + ["format=yuv444p"]), "-pix_fmt", "yuv444p", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    n = len(raw) // (ancho * alto * 3)
    d = np.frombuffer(raw[: n * ancho * alto * 3], np.uint8).reshape(n, 3, alto, ancho).astype(np.float32)
    return d[:, 0], d[:, 1], d[:, 2]

def muestras_yuv(video, k, vf, ancho=1080, alto=1920):
    """k frames repartidos por el video (uno por -ss), concatenados."""
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
                               capture_output=True, text=True).stdout.strip() or 0)
    Y, U, V = [], [], []
    for i in range(k):
        y, u, v = leer_yuv(video, vf + ["select=eq(n\\,0)"], ancho, alto, antes=("-ss", f"{(i + 0.5) * dur / k:.3f}"), dur=0.5)
        if len(y): Y.append(y[0]); U.append(u[0]); V.append(v[0])
    return np.stack(Y), np.stack(U), np.stack(V)

def rgb_de_yuv(Y, U, V):
    """RGB aproximado (BT.601 rango completo) solo para clasificar píxeles (verdoso / no verdoso)."""
    r = Y + 1.402 * (V - 128); g = Y - 0.344 * (U - 128) - 0.714 * (V - 128); b = Y + 1.772 * (U - 128)
    return np.clip(r, 0, 255), np.clip(g, 0, 255), np.clip(b, 0, 255)

def uv_de_hex(h):
    h = h.lower().removeprefix("0x").lstrip("#"); r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return -0.169 * r - 0.331 * g + 0.5 * b + 128, 0.5 * r - 0.419 * g - 0.081 * b + 128

def hex_de_yuv(y, u, v):
    r, g, b = rgb_de_yuv(np.float32(y), np.float32(u), np.float32(v))
    return "".join(f"{int(round(float(c))):02x}" for c in (r, g, b))
