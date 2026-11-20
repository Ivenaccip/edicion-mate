#!/usr/bin/env python3
"""Matting por IA con Robust Video Matting (RVM, MobileNetV3) en ONNX Runtime, CPU.

Modelo: rvm_720x1280.onnx (forma fija 9:16, fp32), espejo en Hugging Face
`sentientsai/rvm-mobilenetv3`, derivado del release v1.0.0 de PeterL1n/RobustVideoMatting (GPL-3.0
el código, pesos publicados con el repo).

Uso:
  matting_rvm.py imagen.png salida_rgba.png              # un fotograma
  matting_rvm.py video.mp4 salida_dir/ --fps 30 --max-s 3   # secuencia PNG RGBA + alfa, con estado recurrente
El modelo trabaja a 720x1280; el alfa se reescala al tamaño original (bilineal) y el color del
primer plano es el de la imagen original (no el `fgr` del modelo), para no perder resolución.
"""
import argparse, os, sys, time
import numpy as np
import cv2
import onnxruntime as ort

MW, MH = 720, 1280

def cargar(ruta_modelo, hilos=4):
    so = ort.SessionOptions(); so.intra_op_num_threads = hilos
    return ort.InferenceSession(ruta_modelo, so, providers=["CPUExecutionProvider"])

def estado_inicial():
    return {"r1i": np.zeros((1, 16, 320, 180), np.float32), "r2i": np.zeros((1, 20, 160, 90), np.float32),
            "r3i": np.zeros((1, 40, 80, 45), np.float32), "r4i": np.zeros((1, 64, 40, 23), np.float32)}

def inferir(sess, bgr, rec):
    """bgr: imagen HxWx3 uint8. Devuelve (alfa HxW float32 0..1, rec nuevo)."""
    h, w = bgr.shape[:2]
    chico = cv2.resize(bgr, (MW, MH), interpolation=cv2.INTER_AREA)
    src = cv2.cvtColor(chico, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    src = src.transpose(2, 0, 1)[None]
    out = sess.run(["fgr", "pha", "r1o", "r2o", "r3o", "r4o"], {"src": src, **rec})
    pha = out[1][0, 0]
    rec = {"r1i": out[2], "r2i": out[3], "r3i": out[4], "r4i": out[5]}
    alfa = cv2.resize(pha, (w, h), interpolation=cv2.INTER_LINEAR)
    return np.clip(alfa, 0, 1), rec

def rgba(bgr, alfa):
    a = (alfa * 255 + 0.5).astype(np.uint8)
    return np.dstack([bgr, a])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("entrada"); ap.add_argument("salida")
    ap.add_argument("--modelo", default=os.environ.get("RVM_ONNX", "rvm_720x1280.onnx"))
    ap.add_argument("--fps", type=float, default=None, help="video: fps de muestreo (defecto: todos los frames)")
    ap.add_argument("--max-s", type=float, default=None, help="video: segundos máximos a procesar")
    ap.add_argument("--inicio-s", type=float, default=0.0)
    ap.add_argument("--rotar", choices=["no", "ccw"], default="no")
    ap.add_argument("--encuadre", choices=["no", "9:16"], default="no")
    a = ap.parse_args()
    sess = cargar(a.modelo)

    def preparar(fr):
        if a.rotar == "ccw": fr = cv2.rotate(fr, cv2.ROTATE_90_COUNTERCLOCKWISE)
        if a.encuadre == "9:16":
            h, w = fr.shape[:2]; nh = int(w * 16 / 9); y0 = (h - nh) // 2; fr = fr[y0:y0 + nh]
        return fr

    if a.entrada.lower().endswith((".png", ".jpg", ".jpeg")):
        bgr = preparar(cv2.imread(a.entrada, cv2.IMREAD_COLOR))
        t = time.time(); alfa, _ = inferir(sess, bgr, estado_inicial()); dt = time.time() - t
        cv2.imwrite(a.salida, rgba(bgr, alfa))
        print(f"{a.salida}: {bgr.shape[1]}x{bgr.shape[0]}, inferencia {dt*1000:.0f} ms")
        return

    cap = cv2.VideoCapture(a.entrada)
    fps_in = cap.get(cv2.CAP_PROP_FPS); n_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    os.makedirs(a.salida, exist_ok=True)
    rec = estado_inicial(); i = 0; n_out = 0; t0 = time.time(); t_inf = 0.0
    paso = 1 if not a.fps else max(1, round(fps_in / a.fps))
    ini = int(round(a.inicio_s * fps_in)); fin = n_total if a.max_s is None else min(n_total, ini + int(round(a.max_s * fps_in)))
    cap.set(cv2.CAP_PROP_POS_FRAMES, ini); i = ini
    while i < fin:
        ok, fr = cap.read()
        if not ok: break
        if (i - ini) % paso == 0:
            fr = preparar(fr)
            t = time.time(); alfa, rec = inferir(sess, fr, rec); t_inf += time.time() - t
            cv2.imwrite(os.path.join(a.salida, f"{n_out:05d}.png"), rgba(fr, alfa)); n_out += 1
        i += 1
    dt = time.time() - t0
    print(f"{n_out} frames en {dt:.1f} s (inferencia {t_inf:.1f} s, {t_inf/max(n_out,1)*1000:.0f} ms/frame) -> {a.salida}")

if __name__ == "__main__":
    main()
