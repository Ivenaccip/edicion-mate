#!/usr/bin/env python3
"""Quita el verde de IMG_7889 (o cualquier raw sobre pantalla verde) y escribe una secuencia RGBA.

Tres métodos, comparables entre sí:
  chromakey : llave por crominancia (misma fórmula que el filtro `chromakey` de FFmpeg: distancia en UV)
  rvm       : matting por IA (Robust Video Matting, ONNX, CPU). Solo personas: borra laptop, silla, mesa.
  hibrido   : alfa = max(chromakey, rvm). La IA arregla pelo y lentes; la llave conserva el escritorio.
Siempre se aplica despill (quita el reflejo verde en pelo, piel y bordes) y un suavizado del borde.

Uso:
  quitar_verde.py raw.mp4 salida_dir/ --metodo hibrido --rotar ccw --encuadre 9:16 --ancho 1080 --inicio-s 12 --dur-s 3
  quitar_verde.py fotograma.png salida_rgba.png --metodo chromakey
Luego FFmpeg arma el WebM con alfa o el MP4 compuesto (ver docs/02-capa-visual.md).
"""
import argparse, os, sys, time, json
import numpy as np
import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

VERDE_KEY = (0x1e, 0x70, 0x32)  # promedio medido en IMG_7889 (R, G, B)

def rgb_a_uv(rgb):
    r, g, b = rgb
    u = -0.169 * r - 0.331 * g + 0.5 * b + 128
    v = 0.5 * r - 0.419 * g - 0.081 * b + 128
    return u, v

def alfa_chromakey(bgr, color=VERDE_KEY, similitud=0.08, mezcla=0.0):
    """Replica `chromakey` de FFmpeg: distancia euclídea en el plano UV, normalizada a 0..1."""
    yuv = cv2.cvtColor(bgr, cv2.COLOR_BGR2YUV).astype(np.float32)
    u, v = yuv[:, :, 1], yuv[:, :, 2]
    ku, kv = rgb_a_uv(color)
    d = np.sqrt((u - ku) ** 2 + (v - kv) ** 2) / 255.0
    if mezcla > 0:
        a = np.clip((d - similitud) / mezcla, 0, 1)
    else:
        a = (d > similitud).astype(np.float32)
    return a.astype(np.float32)

def despill(bgr, alfa, fuerza=0.5):
    """Baja el verde donde G supera al promedio de R y B (reflejo del fondo). Solo sobre píxeles visibles."""
    f = bgr.astype(np.float32)
    b, g, r = f[:, :, 0], f[:, :, 1], f[:, :, 2]
    limite = (r + b) / 2.0
    exceso = np.clip(g - limite, 0, None)
    g2 = g - exceso * fuerza
    f[:, :, 1] = g2
    # el verde quitado se devuelve como luminancia para no oscurecer el pelo
    f[:, :, 0] += exceso * fuerza * 0.3; f[:, :, 2] += exceso * fuerza * 0.3
    out = np.clip(f, 0, 255).astype(np.uint8)
    vis = alfa > 0
    res = bgr.copy(); res[vis] = out[vis]
    return res

def suavizar_borde(alfa, erosion_px=1, pluma_px=1.5):
    a = alfa
    if erosion_px > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * erosion_px + 1, 2 * erosion_px + 1))
        a = cv2.erode(a, k)
    if pluma_px > 0:
        a = cv2.GaussianBlur(a, (0, 0), pluma_px)
    return np.clip(a, 0, 1)

class Keyer:
    def __init__(self, metodo, modelo=None, similitud=0.08, mezcla=0.0, fuerza_despill=0.5, erosion=1, pluma=1.5):
        self.metodo = metodo; self.similitud = similitud; self.mezcla = mezcla
        self.fuerza = fuerza_despill; self.erosion = erosion; self.pluma = pluma
        self.rvm = None
        if metodo in ("rvm", "hibrido"):
            import matting_rvm
            self.mrvm = matting_rvm
            self.rvm = matting_rvm.cargar(modelo)
            self.rec = matting_rvm.estado_inicial()
        self.t_ck = self.t_rvm = 0.0; self.n = 0

    def reiniciar(self):
        if self.rvm is not None: self.rec = self.mrvm.estado_inicial()

    def procesar(self, bgr):
        alfa = None
        if self.metodo in ("chromakey", "hibrido"):
            t = time.time(); a_ck = alfa_chromakey(bgr, similitud=self.similitud, mezcla=self.mezcla); self.t_ck += time.time() - t
            alfa = a_ck
        if self.metodo in ("rvm", "hibrido"):
            t = time.time(); a_rvm, self.rec = self.mrvm.inferir(self.rvm, bgr, self.rec); self.t_rvm += time.time() - t
            alfa = a_rvm if alfa is None else np.maximum(alfa, a_rvm)
        if self.metodo != "rvm":
            alfa = suavizar_borde(alfa, self.erosion, self.pluma)
        bgr2 = despill(bgr, alfa, self.fuerza) if self.fuerza > 0 else bgr
        self.n += 1
        a8 = (alfa * 255 + 0.5).astype(np.uint8)
        return np.dstack([bgr2, a8])

def preparar(fr, rotar, encuadre, ancho):
    if rotar == "ccw": fr = cv2.rotate(fr, cv2.ROTATE_90_COUNTERCLOCKWISE)
    if encuadre == "9:16":
        h, w = fr.shape[:2]; nh = int(w * 16 / 9); y0 = (h - nh) // 2; fr = fr[y0:y0 + nh]
    if ancho and fr.shape[1] != ancho:
        h, w = fr.shape[:2]; fr = cv2.resize(fr, (ancho, int(round(h * ancho / w))), interpolation=cv2.INTER_AREA)
    return fr

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("entrada"); ap.add_argument("salida")
    ap.add_argument("--metodo", choices=["chromakey", "rvm", "hibrido"], default="hibrido")
    ap.add_argument("--modelo", default=os.environ.get("RVM_ONNX", "rvm_720x1280.onnx"))
    ap.add_argument("--rotar", choices=["no", "ccw"], default="no")
    ap.add_argument("--encuadre", choices=["no", "9:16"], default="no")
    ap.add_argument("--ancho", type=int, default=0, help="ancho de trabajo (0 = el del raw)")
    ap.add_argument("--inicio-s", type=float, default=0.0); ap.add_argument("--dur-s", type=float, default=None)
    ap.add_argument("--similitud", type=float, default=0.08); ap.add_argument("--mezcla", type=float, default=0.0)
    ap.add_argument("--despill", type=float, default=0.5); ap.add_argument("--erosion", type=int, default=1); ap.add_argument("--pluma", type=float, default=1.5)
    a = ap.parse_args()
    k = Keyer(a.metodo, a.modelo, a.similitud, a.mezcla, a.despill, a.erosion, a.pluma)

    if a.entrada.lower().endswith((".png", ".jpg", ".jpeg")):
        fr = preparar(cv2.imread(a.entrada, cv2.IMREAD_COLOR), a.rotar, a.encuadre, a.ancho)
        t = time.time(); out = k.procesar(fr); dt = time.time() - t
        cv2.imwrite(a.salida, out); print(f"{a.salida}: {fr.shape[1]}x{fr.shape[0]} {a.metodo} {dt*1000:.0f} ms"); return

    cap = cv2.VideoCapture(a.entrada); fps = cap.get(cv2.CAP_PROP_FPS); n_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    ini = int(round(a.inicio_s * fps)); fin = n_total if a.dur_s is None else min(n_total, ini + int(round(a.dur_s * fps)))
    cap.set(cv2.CAP_PROP_POS_FRAMES, ini); os.makedirs(a.salida, exist_ok=True)
    t0 = time.time(); t_dec = 0.0; i = 0
    while ini + i < fin:
        t = time.time(); ok, fr = cap.read(); t_dec += time.time() - t
        if not ok: break
        fr = preparar(fr, a.rotar, a.encuadre, a.ancho)
        cv2.imwrite(os.path.join(a.salida, f"{i:05d}.png"), k.procesar(fr)); i += 1
    dt = time.time() - t0
    info = {"metodo": a.metodo, "frames": i, "fps": fps, "ancho": fr.shape[1], "alto": fr.shape[0], "segundos_video": i / fps,
            "total_s": round(dt, 2), "decodificar_s": round(t_dec, 2), "chromakey_s": round(k.t_ck, 2), "rvm_s": round(k.t_rvm, 2),
            "s_proceso_por_s_video": round(dt / (i / fps), 2)}
    json.dump(info, open(os.path.join(a.salida, "tiempos.json"), "w"), indent=1); print(json.dumps(info))

if __name__ == "__main__":
    main()
