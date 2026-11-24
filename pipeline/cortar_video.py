#!/usr/bin/env python3
"""
Aplica un EDL al video: raw.mp4 + raw.edl.json -> cuerpo.mp4 (solo cortes, sin captions).

  python pipeline/cortar_video.py raw.mp4 raw.edl.json cuerpo.mp4            # preview 576p
  python pipeline/cortar_video.py raw.mp4 raw.edl.json cuerpo.mp4 --final    # 1080p

Cómo corta:
  1. Lee los tramos "quitar" del EDL y calcula su complemento: los tramos a conservar.
  2. Redondea cada borde al frame más cercano (fps del video) para que video y audio
     compartan exactamente los mismos tiempos y no se acumule desfase.
  3. Video: con --fade 0, select de los tramos en un solo paso; con fundidos, trim + concat (ojo: encola
     frames y en 4K largo se queda sin memoria). Recodificado: el corte exacto cae entre keyframes, -c copy no sirve.
  4. Audio: se corta en numpy con los mismos tiempos redondeados. En cada empalme, fundido
     de salida en los últimos 7.5 ms del tramo anterior y fundido de entrada en los primeros
     7.5 ms del siguiente, SIN solapar (un crossfade solapado acortaría el audio y desfasaría
     el video). Luego se muxea con el video.
  5. Escribe <salida>.aplicado.json con los tramos conservados, los empalmes en el tiempo
     del video editado y el desfase máximo de redondeo.
"""
import sys, json, subprocess, argparse, tempfile
from pathlib import Path
import numpy as np, soundfile as sf

CROSSFADE_MS = 15
FADE_CORTE_S = 0.1   # fundido a negro de salida/entrada en cada empalme (regla del usuario, 21 nov)

def ffprobe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                          "-show_entries", "stream=r_frame_rate,width,height:format=duration",
                          "-of", "json", str(path)], check=True, capture_output=True, text=True).stdout
    j = json.loads(out); s = j["streams"][0]; n, d = s["r_frame_rate"].split("/")
    return float(n) / float(d), int(s["width"]), int(s["height"]), float(j["format"]["duration"])

def tramos_conservar(quitar, duracion, fps):
    """Complemento de los tramos quitados, con bordes redondeados al frame."""
    f = lambda t: round(round(t * fps) / fps, 6)
    q = sorted((f(a), f(b)) for a, b in quitar)
    desfase = max((abs(f(t) - t) for ab in quitar for t in ab), default=0.0)
    keep, cursor = [], 0.0
    for a, b in q:
        if a > cursor: keep.append((cursor, a))
        cursor = max(cursor, b)
    if cursor < duracion: keep.append((cursor, f(duracion) if f(duracion) <= duracion else duracion))
    return keep, desfase

def cortar_audio(path, keep, out_wav, fade_s=FADE_CORTE_S, cola_s=0.0):
    x, sr = sf.read(path, dtype="float32")
    if x.ndim > 1: x = x.mean(axis=1)
    k = int(sr * max(fade_s, CROSSFADE_MS / 2000))         # el fundido de corte manda; mínimo 7.5 ms
    piezas = [x[int(round(a * sr)):int(round(b * sr))].copy() for a, b in keep]
    for i, p in enumerate(piezas):
        if i > 0 and len(p) >= k:               p[:k]  *= np.linspace(0, 1, k, dtype=np.float32)
        if i < len(piezas) - 1 and len(p) >= k: p[-k:] *= np.linspace(1, 0, k, dtype=np.float32)
    if cola_s > 0:
        # cola: el final no se corta en seco. Se añaden cola_s de "aire" tomados del último tramo (los últimos cola_s,
        # que son la pausa tras la última palabra) invertidos para que empalmen sin salto, con fundido a cero.
        n = int(cola_s * sr); aire = piezas[-1][-n:][::-1].copy() if len(piezas[-1]) >= n else np.zeros(n, np.float32)
        piezas.append(aire * np.linspace(1, 0, len(aire), dtype=np.float32))
    y = np.concatenate(piezas)
    sf.write(out_wav, y, sr)
    return len(y) / sr

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video"); ap.add_argument("edl"); ap.add_argument("salida")
    ap.add_argument("--final", action="store_true", help="1080p, preset slow; por defecto preview 576p veryfast")
    ap.add_argument("--rotar", choices=["ccw", "cw", "180"], help="rotar el video (celulares sin bandera de rotación)")
    ap.add_argument("--encuadre", choices=["9:16", "16:9", "1:1"], help="recortar centrado a esta proporción (tras rotar)")
    ap.add_argument("--fade", type=float, default=FADE_CORTE_S, help="segundos de fundido a negro de salida y de entrada en cada empalme (0 = corte seco)")
    ap.add_argument("--cola-s", type=float, default=0.0, help="segundos de cola al final: último frame congelado y aire del final con fundido (el corte seco al final suena mal)")
    a = ap.parse_args()

    fps, w, h, dur = ffprobe(a.video)
    edl = json.load(open(a.edl))
    quitar = [e["quitar"] for e in edl["edl"] if "quitar" in e]
    keep, desfase = tramos_conservar(quitar, dur, fps)
    esperado = sum(b - x for x, b in keep)
    # empalmes en el tiempo del video editado: fin acumulado de cada tramo salvo el último
    empalmes, acc = [], 0.0
    for x, b in keep[:-1]:
        acc += b - x; empalmes.append(round(acc, 3))

    with tempfile.TemporaryDirectory() as td:
        wav_full = Path(td) / "full.wav"; wav_cut = Path(td) / "cut.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", a.video, "-vn", "-ac", "1", str(wav_full)], check=True)
        dur_audio = cortar_audio(wav_full, keep, wav_cut, a.fade, a.cola_s)

        def fades(i, x, b):
            d = b - x; fo = a.fade if (i < len(keep) - 1 and d > 2 * a.fade) else 0; fi = a.fade if (i > 0 and d > 2 * a.fade) else 0
            f = ""
            if fi: f += f",fade=t=in:st=0:d={fi}"
            if fo: f += f",fade=t=out:st={d - fo:.4f}:d={fo}"
            return f
        if a.fade > 0:
            # trim + concat: cada tramo es una rama y concat las consume en orden, así que ffmpeg encola los frames
            # de las ramas que aún no toca. En 4K eso son ~13 MB por frame: con muchos tramos o raws largos se
            # queda sin memoria (IMG_7924: 8 tramos, 116 s -> SIGKILL). Solo se usa cuando hay fundidos.
            partes = "".join(f"[0:v]trim=start={x}:end={b},setpts=PTS-STARTPTS{fades(i, x, b)}[v{i}];" for i, (x, b) in enumerate(keep))
            concat = "".join(f"[v{i}]" for i in range(len(keep))) + f"concat=n={len(keep)}:v=1:a=0[vc];"
        else:
            # corte seco: select en un solo paso (sin ramas ni colas), frames con t en [x, b) de cada tramo conservado
            expr = "+".join(f"gte(t\\,{x})*lt(t\\,{b})" for x, b in keep)
            cola = f",tpad=stop_mode=clone:stop_duration={a.cola_s}" if a.cola_s > 0 else ""
            partes = f"[0:v]select='{expr}',setpts=N/FRAME_RATE/TB{cola}[vc];"; concat = ""
        rot = {"ccw": "transpose=2,", "cw": "transpose=1,", "180": "transpose=1,transpose=1,"}.get(a.rotar, "")
        corto = 1080 if a.final else 576            # lado corto: 576p preview, 1080p final; sirve vertical y horizontal
        if a.encuadre:
            aw, ah = (int(v) for v in a.encuadre.split(":"))
            # recorte centrado a la proporción pedida: el lado que sobra se recorta, el otro se conserva
            crop = (f"crop='if(gt(iw/ih,{aw}/{ah}),ih*{aw}/{ah},iw)':'if(gt(iw/ih,{aw}/{ah}),ih,iw*{ah}/{aw})',")
            largo = corto * max(aw, ah) // min(aw, ah)
            escala = f"[vc]{rot}{crop}scale={corto if ah > aw else largo}:{largo if ah > aw else corto}:flags=lanczos[vout]"
        else:
            escala = f"[vc]{rot}scale='if(gt(iw,ih),-2,{corto})':'if(gt(iw,ih),{corto},-2)':flags=lanczos[vout]"
        preset, crf = ("slow", 18) if a.final else ("veryfast", 23)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", a.video, "-i", str(wav_cut),
                        "-filter_complex", partes + concat + escala, "-map", "[vout]", "-map", "1:a",
                        "-r", str(int(round(fps))), "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
                        "-shortest", a.salida], check=True)

    _, _, _, dur_out = ffprobe(a.salida)
    info = {"entrada": a.video, "edl": a.edl, "salida": a.salida, "fps": fps, "modo": "final" if a.final else "preview", "rotar": a.rotar, "encuadre": a.encuadre,
            "duracion_original_s": round(dur, 3), "tramos_quitados": quitar, "tramos_conservados": [[x, b] for x, b in keep],
            "empalmes_en_salida_s": empalmes, "desfase_redondeo_max_ms": round(desfase * 1000, 2),
            "duracion_esperada_s": round(esperado + a.cola_s, 3), "duracion_audio_cortado_s": round(dur_audio, 3),
            "duracion_salida_s": round(dur_out, 3), "diferencia_frames": round((dur_out - esperado - a.cola_s) * fps, 2),
            "crossfade_ms": CROSSFADE_MS, "fade_corte_s": a.fade, "cola_s": a.cola_s}
    Path(a.salida).with_suffix(".aplicado.json").write_text(json.dumps(info, ensure_ascii=False, indent=1))
    print(f"{a.video} ({dur:.3f} s) -> {a.salida} ({dur_out:.3f} s), esperado {esperado:.3f} s, "
          f"diferencia {info['diferencia_frames']:+.2f} frames, desfase de redondeo máx {info['desfase_redondeo_max_ms']} ms")
    print(f"tramos conservados: {len(keep)}, empalmes en salida: {empalmes}")

if __name__ == "__main__":
    main()
