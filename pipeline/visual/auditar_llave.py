#!/usr/bin/env python3
"""Auditor de la llave de verde (capa 1, determinista). Detecta "estática" (píxeles que entran y salen
de la máscara frame a frame) y dice cuánto habría que mover el umbral y dónde.

Entradas: el raw (para medir el verde) y el WebM con alfa que produjo la llave (para medir el parpadeo).
Salida: JSON + bloque de pendientes en el formato del auditor (timestamp, criterio, evidencia, acción).

Cómo decide:
 0. Solo celdas estáticas en el raw (desviación temporal de luma ≤ --mov-max): el borde de una persona que se
    mueve también conmuta, pero no es ruido de llave.
 1. Parpadeo. Para cada celda de la cuadrícula (40x40 px a 1080p) mide la tasa de conmutación: fracción de
    pares de frames consecutivos en que el píxel cruza entre transparente y visible. Celda sospechosa si la
    tasa media > --tasa-max (2 %) y la celda no es ni toda opaca ni toda transparente.
 2. Verde en esa celda. En los frames del raw, toma los píxeles verdosos (G > 1.6·max(R,B)) y mide su distancia
    UV al color clave (la misma distancia que usa `chromakey`). Umbral necesario = percentil 95 + margen.
 3. Techo. El umbral no puede acercarse al negro de la ropa/silla: distancia del negro al clave (0.156 para
    #1e7032). Techo = esa distancia − margen. Si el necesario cabe bajo el techo con holgura y es ≤ --global-max,
    recomienda subir el umbral global; si no, recomienda llave por zona (mascara_sombras.py + quitar_verde_ffmpeg.sh).

Uso:
  auditar_llave.py raw.mp4 llave_alfa.webm --inicio-s 12 --dur-s 3 --umbral 0.08 --json salida.json --md pendientes.md
"""
import argparse
import json, subprocess, sys
from verde_util import leer_yuv, rgb_de_yuv, uv_de_hex
import numpy as np

def leer_frames(cmd, w, h, canales):
    raw = subprocess.run(cmd, capture_output=True).stdout
    n = len(raw) // (w * h * canales)
    return np.frombuffer(raw[: n * w * h * canales], np.uint8).reshape(n, h, w, canales)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw"); ap.add_argument("webm")
    ap.add_argument("--inicio-s", type=float, default=0); ap.add_argument("--dur-s", type=float, default=3)
    ap.add_argument("--rotar", choices=["no", "ccw"], default="ccw"); ap.add_argument("--encuadre", choices=["no", "9:16"], default="9:16")
    ap.add_argument("--ancho", type=int, default=1080); ap.add_argument("--alto", type=int, default=1920)
    ap.add_argument("--clave", default="1e7032"); ap.add_argument("--umbral", type=float, default=0.08)
    ap.add_argument("--celda", type=int, default=40); ap.add_argument("--tasa-max", type=float, default=0.02)
    ap.add_argument("--mov-max", type=float, default=6.0, help="desviación temporal máxima de luma (0-255) para considerar la celda estática")
    ap.add_argument("--margen", type=float, default=0.015); ap.add_argument("--global-max", type=float, default=0.10)
    ap.add_argument("--fps-muestra", type=float, default=10, help="fps a los que se lee el raw para medir el verde")
    ap.add_argument("--json"); ap.add_argument("--md")
    ap.add_argument("--debug-png", help="mapa de conmutación (gris) con las zonas marcadas en rojo y las descartadas por movimiento en azul")
    a = ap.parse_args()
    W, H, C = a.ancho, a.alto, a.celda
    prep = []
    if a.rotar == "ccw": prep.append("transpose=2")
    if a.encuadre == "9:16": prep.append("crop=iw:iw*16/9")
    prep.append(f"scale={W}:{H}")

    # 1) alfa del WebM, todos los frames
    alfa = leer_frames(["ffmpeg", "-v", "error", "-c:v", "libvpx-vp9", "-i", a.webm, "-vf", f"alphaextract,scale={W}:{H},format=gray", "-f", "rawvideo", "-"], W, H, 1)[..., 0]
    n = alfa.shape[0]
    if n < 2: sys.exit("el WebM no trae alfa o tiene menos de 2 frames")
    vis = alfa > 128   # visible = alfa por encima de la mitad: el plumado del borde (alfa 1-40) oscila por la cuantización VP9 y no es parpadeo de llave
    conmuta = (vis[1:] != vis[:-1]).mean(axis=0)            # tasa de conmutación por píxel
    media = vis.mean(axis=0)
    gh, gw = H // C, W // C
    tasa_c = conmuta[: gh * C, : gw * C].reshape(gh, C, gw, C).mean(axis=(1, 3))
    media_c = media[: gh * C, : gw * C].reshape(gh, C, gw, C).mean(axis=(1, 3))
    sospechosas = np.argwhere((tasa_c > a.tasa_max) & (media_c > 0.03) & (media_c < 0.97))

    # 2) verde en el raw, muestreado
    # planos U/V nativos del raw: el mismo espacio en que chromakey mide la distancia (verde_util.py)
    luma, u, v = leer_yuv(a.raw, prep + [f"fps={a.fps_muestra}"], W, H, antes=("-ss", str(a.inicio_s)), dur=a.dur_s)
    r, g, b = rgb_de_yuv(luma, u, v)
    ku, kv = uv_de_hex(a.clave)
    dist = np.sqrt((u - ku) ** 2 + (v - kv) ** 2) / 255.0
    verdoso = g > 1.6 * np.maximum(r, b)
    movimiento = luma.std(axis=0)                            # desviación temporal por píxel: alta donde la persona se mueve
    estatico = movimiento <= a.mov_max
    frac_verde = verdoso.mean(axis=0)                        # fracción de muestras en que el píxel es verdoso
    verde_est = estatico & (frac_verde >= 0.8)               # fondo verde que no cambia: aquí el parpadeo es ruido de llave
    solido_est = estatico & (frac_verde < 0.8)               # persona/escritorio estáticos (incl. bordes teñidos de verde): aquí el parpadeo son agujeros
    # a menos de 3 px de un borde que se mueve o de verde, el plumado (erosión 1 px + gblur 1.1) cruza el 50 % de alfa
    # cuando el borde se corre 1 px: eso no es agujero, es el borde. Se excluye esa franja (IMG_7903, 24 nov).
    from scipy.ndimage import binary_dilation
    franja = binary_dilation(~estatico | (frac_verde > 0.05), iterations=3)
    solido_est &= ~franja
    def por_celda(m): return m[: gh * C, : gw * C].reshape(gh, C, gw, C).mean(axis=(1, 3))
    conm_verde = por_celda(np.where(verde_est, conmuta, 0)) / np.maximum(por_celda(verde_est), 1e-6)
    conm_solido = por_celda(np.where(solido_est, conmuta, 0)) / np.maximum(por_celda(solido_est), 1e-6)
    peso_verde, peso_solido = por_celda(verde_est), por_celda(solido_est)
    mov_c = por_celda(movimiento)
    techo = np.hypot(128 - ku, 128 - kv) / 255.0 - a.margen   # distancia del negro al clave, menos margen

    hallazgos = []
    descartadas_mov = 0; agujeros = []
    for (cy, cx) in sospechosas:
        y0, x0 = cy * C, cx * C
        es_verde = peso_verde[cy, cx] >= 0.25 and conm_verde[cy, cx] > a.tasa_max
        es_agujero = peso_solido[cy, cx] >= 0.25 and conm_solido[cy, cx] > a.tasa_max
        if es_agujero:
            d_sol = dist[:, y0:y0 + C, x0:x0 + C][np.broadcast_to(solido_est[y0:y0 + C, x0:x0 + C], (dist.shape[0], C, C))]
            agujeros.append({"x0": int(x0), "y0": int(y0), "x1": int(x0 + C), "y1": int(y0 + C), "tasa_conmutacion": round(float(conm_solido[cy, cx]), 4),
                             "visible_medio": round(float(media_c[cy, cx]), 3), "dist_p05": round(float(np.percentile(d_sol, 5)), 3)})
        if not es_verde:                                     # borde en movimiento o sin verde estático: no es ruido de llave
            descartadas_mov += 1; continue
        d = dist[:, y0:y0 + C, x0:x0 + C][np.broadcast_to(verde_est[y0:y0 + C, x0:x0 + C], (dist.shape[0], C, C))]
        if d.size < 50: continue
        p50, p95 = float(np.percentile(d, 50)), float(np.percentile(d, 95))
        necesario = round(p95 + a.margen, 3)
        if necesario <= a.umbral: continue   # el verde ya cabe: el parpadeo viene de otra cosa (borde de la persona)
        hallazgos.append({"celda_xy": [int(x0), int(y0)], "tasa_conmutacion": round(float(conm_verde[cy, cx]), 4),
                          "visible_medio": round(float(media_c[cy, cx]), 3), "dist_verde_p50": round(p50, 3),
                          "dist_verde_p95": round(p95, 3), "umbral_necesario": necesario})
    # agrupar celdas vecinas en zonas (unión simple por adyacencia)
    zonas = []
    for h_ in sorted(hallazgos, key=lambda z: (z["celda_xy"][1], z["celda_xy"][0])):
        x, y = h_["celda_xy"]
        for z in zonas:
            if abs(x - z["x0"]) <= z["w"] + C and abs(y - z["y0"]) <= z["h"] + C:
                z["x1"], z["y1"] = max(z["x1"], x + C), max(z["y1"], y + C); z["x0"], z["y0"] = min(z["x0"], x), min(z["y0"], y)
                z["w"], z["h"] = z["x1"] - z["x0"], z["y1"] - z["y0"]; z["celdas"].append(h_); break
        else:
            zonas.append({"x0": x, "y0": y, "x1": x + C, "y1": y + C, "w": C, "h": C, "celdas": [h_]})
    for z in zonas:
        z["umbral_necesario"] = max(c["umbral_necesario"] for c in z["celdas"])
        z["tasa_conmutacion_max"] = max(c["tasa_conmutacion"] for c in z["celdas"])
        cabe_global = z["umbral_necesario"] <= a.global_max and z["umbral_necesario"] < techo
        z["accion"] = (f"subir umbral global de {a.umbral} a {z['umbral_necesario']}" if cabe_global else
                       f"llave por zona: mascara_sombras.py y chromakey {min(round(z['umbral_necesario'] + 0.02, 3), round(techo, 3))} dentro de la máscara (techo {techo:.3f} por el negro de la ropa); no subir el global")
        for c in z["celdas"]: c.pop("celda_xy", None)
    zonas_ag = []
    for h_ in sorted(agujeros, key=lambda z: (z["y0"], z["x0"])):
        for z in zonas_ag:
            if abs(h_["x0"] - z["x0"]) <= z["w"] + C and abs(h_["y0"] - z["y0"]) <= z["h"] + C:
                z["x1"], z["y1"] = max(z["x1"], h_["x1"]), max(z["y1"], h_["y1"]); z["x0"], z["y0"] = min(z["x0"], h_["x0"]), min(z["y0"], h_["y0"])
                z["w"], z["h"] = z["x1"] - z["x0"], z["y1"] - z["y0"]; z["celdas"].append(h_); break
        else:
            zonas_ag.append({**{k: h_[k] for k in ("x0", "y0", "x1", "y1")}, "w": C, "h": C, "celdas": [h_]})
    for z in zonas_ag:
        z["tasa_conmutacion_max"] = max(c["tasa_conmutacion"] for c in z["celdas"]); z["visible_medio"] = round(float(np.mean([c["visible_medio"] for c in z["celdas"]])), 3)
        z["dist_min_persona"] = min(c["dist_p05"] for c in z["celdas"])
        z["accion"] = (f"agujeros en persona/escritorio: su color está a {z['dist_min_persona']:.3f} del verde clave, por debajo o al filo del umbral {a.umbral}; "
                       f"forzar alfa=1 con máscara fija de escritorio/persona en esta zona (la cámara no se mueve) o bajar el umbral local a {max(round(z['dist_min_persona'] - a.margen, 3), 0.04)}")
        z.pop("celdas")
    veredicto = "APROBADO" if not zonas and not zonas_ag else "RECHAZADO"
    if a.debug_png:
        import cv2
        img = cv2.cvtColor(np.clip(conmuta * 255 * 5, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
        for (cy, cx) in sospechosas:
            col = (255, 80, 0) if mov_c[cy, cx] > a.mov_max else (0, 200, 255)
            cv2.rectangle(img, (cx * C, cy * C), (cx * C + C, cy * C + C), col, 2)
        for z in zonas: cv2.rectangle(img, (z["x0"], z["y0"]), (z["x1"], z["y1"]), (0, 0, 255), 4)
        for z in zonas_ag: cv2.rectangle(img, (z["x0"], z["y0"]), (z["x1"], z["y1"]), (0, 255, 0), 4)
        cv2.imwrite(a.debug_png, img)
    res = {"veredicto": veredicto, "frames_alfa": int(n), "umbral_actual": a.umbral, "techo_umbral": round(float(techo), 3),
           "celdas_sospechosas": int(len(sospechosas)), "celdas_descartadas_por_movimiento": descartadas_mov, "zonas_verde_se_cuela": [{k: v for k, v in z.items() if k != "celdas"} for z in zonas], "zonas_agujeros": zonas_ag}
    print(json.dumps(res, indent=1, ensure_ascii=False))
    if a.json: json.dump(res, open(a.json, "w"), indent=1, ensure_ascii=False)
    if a.md:
        t0 = a.inicio_s; lines = [f"# Pendientes — llave de verde — {a.webm.split('/')[-1]}", f"Veredicto: {veredicto}", f"Bloqueantes: 0 · Mayores: {len(zonas) + len(zonas_ag)} · Menores: 0", ""]
        for i, z in enumerate(zonas, 1):
            lines += [f"## P-{i:02d} · MAYOR · {int(t0 // 60):02d}:{t0 % 60:06.3f}–{int((t0 + a.dur_s) // 60):02d}:{(t0 + a.dur_s) % 60:06.3f}",
                      "Criterio: la máscara de la llave no parpadea (tasa de conmutación ≤ 2 % por píxel)",
                      f"Evidencia: zona x {z['x0']}–{z['x1']}, y {z['y0']}–{z['y1']} (1080x1920): conmutación máx. {z['tasa_conmutacion_max'] * 100:.1f} % por frame; "
                      f"verde en la zona a distancia p95 {max(c['dist_verde_p95'] for c in z['celdas']):.3f} del clave, umbral actual {a.umbral}, necesario {z['umbral_necesario']}, techo {techo:.3f}",
                      f"Acción: {z['accion']}", "Estado: abierto", ""]
        for j, z in enumerate(zonas_ag, len(zonas) + 1):
            lines += [f"## P-{j:02d} · MAYOR · {int(t0 // 60):02d}:{t0 % 60:06.3f}–{int((t0 + a.dur_s) // 60):02d}:{(t0 + a.dur_s) % 60:06.3f}",
                      "Criterio: la persona y el escritorio no tienen agujeros intermitentes",
                      f"Evidencia: zona x {z['x0']}–{z['x1']}, y {z['y0']}–{z['y1']} (1080x1920): conmutación máx. {z['tasa_conmutacion_max'] * 100:.1f} % por frame sobre píxeles sólidos estáticos, visibles solo el {z['visible_medio'] * 100:.0f} % del tiempo",
                      f"Acción: {z['accion']}", "Estado: abierto", ""]
        if not zonas and not zonas_ag: lines += ["Sin parpadeo de llave: ni verde que se cuela ni agujeros en zonas estáticas.", ""]
        open(a.md, "w").write("\n".join(lines))
    sys.exit(0 if veredicto == "APROBADO" else 2)

if __name__ == "__main__":
    main()
