#!/usr/bin/env python3
"""Elige la mejor toma de cada línea repetida y escribe el EDL que las deja (retomas fuera, por transcript).

Un raw grabado "a varias tomas" repite cada frase del guion hasta que sale: IMG_7924 dice 3 líneas en 116 s,
con 2-7 intentos por línea, apartes al equipo ("¿Sí?", "Siento que estoy diciendo mucho") y un arranque en falso.
El editor de pausas no ve nada de eso (no hay pausas largas); aquí decide el transcript, y la señal decide dónde
cortar (valle de energía en la pausa que rodea a la toma elegida). Principios del estándar respetados.

Pasos:
  1 tomas    = tramos de palabras; una toma termina cuando el texto vuelve a empezar con las mismas 3 palabras
               (reinicio), en fin de oración seguido de pausa, o en pausa > 0.6 s.
  2 líneas   = tomas consecutivas que empiezan igual o se parecen (Jaccard de palabras >= 0.5).
               Una línea de UNA toma metida entre tomas de otra línea es un aparte: fuera.
               Una línea de una toma incompleta (sin . ? !) al final del raw es charla al equipo: fuera.
  3 mejor    = por línea: completa (termina en . ? !) > sin tartamudeo (sin bigrama repetido) > más larga > la última.
  4 bordes   = la voz real por energía (ventanas de 10 ms, raw_audio.wav; el transcriptor da fines ~0.1 s tarde) y
               --pausa-empalme (0.25 s) de silencio total por empalme, mitad en cada lado; --aire (0.15 s) al final.
  5 EDL      = quitar = complemento de las tomas elegidas + las pausas acortadas del editor que caen dentro de ellas.
Uso: seleccionar_tomas.py raw.palabras.json raw_audio.wav raw.edl.json [--salida raw.edl.json] [--md tomas.md]
    (sin --salida solo imprime el plan). --forzar-toma LINEA:TOMA elige a mano (índices del plan);
    --terminar-en LINEA:PALABRA recorta la toma elegida tras esa palabra (corte en el valle entre palabras).
"""
import argparse, json, re, unicodedata, difflib
import numpy as np, soundfile as sf

def norm(w):
    w = unicodedata.normalize("NFD", w.lower()); w = "".join(c for c in w if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9ñ]", "", w)

def termina(w): return w[-1:] in ".?!"

def dividir_tomas(pal, gap_max=0.6):
    tomas, ini = [], 0; toks = [norm(p["w"]) for p in pal]
    for j in range(1, len(pal)):
        gap = pal[j]["ini"] - pal[j - 1]["fin"]
        reinicio = j - ini >= 3 and toks[j:j + 3] == toks[ini:ini + 3]
        if reinicio or gap > gap_max or (termina(pal[j - 1]["w"]) and gap > 0.25):
            tomas.append((ini, j)); ini = j
    tomas.append((ini, len(pal)))
    return tomas

def jaccard(a, b):
    a, b = set(a), set(b); return len(a & b) / max(len(a | b), 1)

def agrupar(pal, tomas):
    lineas = []
    for t in tomas:
        toks = [norm(p["w"]) for p in pal[t[0]:t[1]]]
        if lineas:
            prev = lineas[-1]; ptoks = [norm(p["w"]) for p in pal[prev[-1][0]:prev[-1][1]]]
            if toks[:3] == ptoks[:3] or jaccard(toks, ptoks) >= 0.5: prev.append(t); continue
        lineas.append([t])
    # apartes: línea de una toma entre dos líneas que son la misma (empiezan igual) -> se funden esas dos y el aparte sale
    i = 1; apartes = []
    while i < len(lineas) - 1:
        a, b, c = lineas[i - 1], lineas[i], lineas[i + 1]
        ta = [norm(p["w"]) for p in pal[a[-1][0]:a[-1][1]]]; tc = [norm(p["w"]) for p in pal[c[0][0]:c[0][1]]]
        if len(b) == 1 and (ta[:3] == tc[:3] or jaccard(ta, tc) >= 0.5):
            apartes.append(b[0]); a.extend(c); del lineas[i:i + 2]
        else: i += 1
    return lineas, apartes

def puntuar(pal, t, n_max):
    ws = [p["w"] for p in pal[t[0]:t[1]]]; toks = [norm(w) for w in ws]
    completa = termina(ws[-1]) and not ws[-1].endswith("-")
    big = list(zip(toks, toks[1:])); tartamudeo = len(big) != len(set(big))
    return completa * 10 + (not tartamudeo) * 5 + 3 * len(toks) / n_max, completa, tartamudeo

def valle(x, sr, t0, t1):
    """Centro de la ventana de 20 ms con menos energía entre t0 y t1 (t en s)."""
    a, b = int(t0 * sr), int(t1 * sr)
    if b - a < sr // 50: return (t0 + t1) / 2
    seg = x[a:b]; n = sr // 50; m = len(seg) // n
    rms = np.sqrt((seg[: m * n].reshape(m, n) ** 2).mean(axis=1))
    return (a + (int(rms.argmin()) + 0.5) * n) / sr

def callada(x, sr, t, umbral_db=-40):
    """Ventana de 10 ms en t por debajo de umbral_db relativo al pico del archivo."""
    n = sr // 100; a = int(t * sr); seg = x[a:a + n]; ref = float(np.abs(x).max()) or 1.0
    return 20 * np.log10(max(float(np.sqrt((seg ** 2).mean())), 1e-9) / ref) < umbral_db

def borde_voz(x, sr, t_asr, hacia, lim, umbral_db=-40, busca=0.35, hueco=0.06):
    """Dónde termina (hacia=+1) o empieza (hacia=-1) la voz de verdad cerca del tiempo que dio el transcriptor
    (sus fines e inicios van tarde ~0.1 s). Ventanas de 10 ms; "callada" = por debajo de umbral_db relativo al pico.
    Fin: si t_asr suena, avanza hasta el primer hueco callado de >= `hueco` s y devuelve su inicio; si t_asr ya
    está callado, retrocede hasta la última ventana con voz. Inicio: simétrico. Nunca pasa de `lim`."""
    def callada(t): return globals()["callada"](x, sr, t, umbral_db)
    k = max(1, int(round(hueco / 0.01)))
    if hacia > 0:
        if callada(t_asr):
            t = t_asr
            while t > t_asr - busca and callada(t): t -= 0.01
            return t + 0.01
        t = t_asr; tope = min(t_asr + busca, lim)
        while t + k * 0.01 <= tope:
            if all(callada(t + j * 0.01) for j in range(k)): return t
            t += 0.01
        return min(t_asr, tope)
    if callada(t_asr):
        t = t_asr
        while t < t_asr + busca and callada(t): t += 0.01
        return t
    t = t_asr; tope = max(t_asr - busca, lim)
    while t - k * 0.01 >= tope:
        if all(callada(t - j * 0.01) for j in range(1, k + 1)): return t
        t -= 0.01
    return max(t_asr, tope)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("palabras"); ap.add_argument("audio"); ap.add_argument("edl_pausas")
    ap.add_argument("--salida"); ap.add_argument("--md"); ap.add_argument("--aire", type=float, default=0.15, help="s de aire tras la última palabra del cuerpo")
    ap.add_argument("--pausa-empalme", type=float, default=0.25, help="s de silencio total en cada empalme (regla del editor de pausas: 250 ms)")
    ap.add_argument("--forzar-toma", action="append", default=[], help="LINEA:TOMA (índices del plan)")
    ap.add_argument("--terminar-en", action="append", default=[], help="LINEA:PALABRA, la toma elegida termina tras la última PALABRA (p. ej. 2:llegar)")
    ap.add_argument("--guion", help="archivo de texto con el guion final, una frase por línea: para cada frase se elige la toma más parecida (difflib >= 0.6; empate: la última). Sustituye al agrupado automático; sirve cuando las tomas no repiten las mismas palabras o hay mucha charla con el equipo")
    a = ap.parse_args()
    d = json.load(open(a.palabras)); pal = d["palabras"] if isinstance(d, dict) else d
    x, sr = sf.read(a.audio, dtype="float32");  x = x.mean(axis=1) if x.ndim > 1 else x
    dur = len(x) / sr
    md = []; tomas = dividir_tomas(pal)
    if a.guion:
        # modo guion: cada frase del guion se empareja con la toma más parecida (texto normalizado)
        frases = [l.strip() for l in open(a.guion, encoding="utf-8") if l.strip()]
        txt = lambda t: " ".join(norm(p["w"]) for p in pal[t[0]:t[1]])
        lineas, apartes, usadas = [], [], set()
        for f in frases:
            nf = " ".join(norm(w) for w in f.split())
            cand = [(difflib.SequenceMatcher(None, nf, txt(t)).ratio(), i) for i, t in enumerate(tomas) if i not in usadas]
            r, i = max(cand, key=lambda c: (round(c[0], 2), c[1]))
            if r < 0.6: raise SystemExit(f"guion: ninguna toma se parece a '{f}' (mejor {r:.2f}: '{' '.join(p['w'] for p in pal[tomas[i][0]:tomas[i][1]])}')")
            usadas.add(i); lineas.append([tomas[i]]); md.append(f"- guion: '{f}' -> toma {tomas[i][0]}-{tomas[i][1]} (parecido {r:.2f})")
    else:
        lineas, apartes = agrupar(pal, tomas)
    forzadas = {int(f.split(":")[0]): int(f.split(":")[1]) for f in a.forzar_toma}
    terminar = {int(f.split(":")[0]): norm(f.split(":", 1)[1]) for f in a.terminar_en}
    plan, elegidas = [], []
    for li, L in enumerate(lineas):
        n_max = max(t[1] - t[0] for t in L); filas = []
        for ti, t in enumerate(L):
            s, comp, tart = puntuar(pal, t, n_max); filas.append((s, ti, t, comp, tart))
        mejor = max(filas, key=lambda f: (f[0], f[1]))  # empate: la última
        if li in forzadas: mejor = filas[forzadas[li]]
        ultima_incompleta = (not a.guion) and len(L) == 1 and not mejor[3] and L[0][1] == len(pal)
        plan.append((li, L, filas, mejor, ultima_incompleta))
        t = mejor[2]
        if li in terminar:   # recorte editorial: la toma termina tras la última aparición de la palabra
            js = [j for j in range(t[0], t[1]) if norm(pal[j]["w"]) == terminar[li]]
            if not js: raise SystemExit(f"--terminar-en: '{terminar[li]}' no está en la toma elegida de la línea {li}")
            t = (t[0], js[-1] + 1); md.append(f"- línea {li}: termina en '{pal[js[-1]]['w']}' ({pal[js[-1]]['fin']:.2f} s) por --terminar-en")
        if not ultima_incompleta: elegidas.append(t)
    # bordes por señal
    # bordes: la voz real (por energía) termina/empieza cerca de lo que dijo el transcriptor (sus fines suelen ir
    # tarde ~0.1 s). Cada empalme deja pausa_empalme en total: mitad al final del tramo, mitad al inicio del siguiente;
    # nunca se pisa la palabra vecina. El último tramo deja `aire` tras la última palabra.
    tramos = []; mitad = a.pausa_empalme / 2
    for k, (i0, i1) in enumerate(sorted(elegidas)):
        p0, p1 = pal[i0], pal[i1 - 1]
        prev_fin = pal[i0 - 1]["fin"] if i0 > 0 else 0.0; next_ini = pal[i1]["ini"] if i1 < len(pal) else dur
        voz_ini = borde_voz(x, sr, p0["ini"], -1, prev_fin); voz_fin = borde_voz(x, sr, p1["fin"], +1, next_ini)
        # la voz vecina real (el transcriptor también da inicios tarde: "en" tras "llegar" arrancaba 0.1 s antes)
        prev_voz = borde_voz(x, sr, prev_fin, +1, voz_ini) if i0 > 0 else 0.0
        sig_voz = borde_voz(x, sr, next_ini, -1, voz_fin) if i1 < len(pal) else dur
        ini = max(prev_voz + 0.01, voz_ini - mitad) if k > 0 else max(0.0, voz_ini - a.aire)
        fin = min(sig_voz - 0.01, voz_fin + (mitad if k < len(elegidas) - 1 else a.aire))
        # si el aire que se deja no está callado (una respiración fuerte o un sonido sin transcribir pegado a la
        # palabra), se acerca el corte a la voz hasta donde empieza lo callado: IMG_7924 traía un inhalo a -21 dB
        # antes de "Si quieres" que quedaba dentro del empalme
        while ini < voz_ini - 0.02 and not callada(x, sr, ini): ini += 0.01
        while fin > voz_fin + 0.02 and not callada(x, sr, fin - 0.01): fin -= 0.01
        tramos.append([round(ini, 3), round(fin, 3)]); md.append(f"- tramo {k}: voz {voz_ini:.2f}-{voz_fin:.2f} s (transcriptor {p0['ini']:.2f}-{p1['fin']:.2f}), corte {ini:.3f}-{fin:.3f}")
    # quitar = complemento + pausas acortadas del editor dentro de cada tramo
    edl_p = json.load(open(a.edl_pausas)); quitar = []; cursor = 0.0
    for ini, fin in tramos:
        if ini > cursor: quitar.append({"quitar": [round(cursor, 3), ini], "accion": "quitar retoma/aparte (por transcript)"})
        cursor = fin
    # la cola se quita hasta más allá del final: el audio (dur) puede ser unos ms más corto que el video y dejaría un frame suelto
    if cursor < dur: quitar.append({"quitar": [round(cursor, 3), round(dur + 1, 3)], "accion": "quitar cola (por transcript)"})
    for e in edl_p.get("edl", []):
        if "quitar" in e and any(ini + 0.3 < e["quitar"][0] and e["quitar"][1] < fin - 0.3 for ini, fin in tramos):
            quitar.append(dict(e, accion=e["accion"] + " (editor de pausas)"))
    quitar.sort(key=lambda e: e["quitar"][0])
    # plan legible
    md.append("# Plan de tomas\n"); md.append(f"Raw {dur:.1f} s, {len(pal)} palabras, {len(tomas)} tomas en {len(lineas)} líneas; apartes fuera: {len(apartes)}.\n")
    for li, L, filas, mejor, inc in plan:
        md.append(f"\n## Línea {li}" + ("  (charla final incompleta: fuera)" if inc else ""))
        for s, ti, t, comp, tart in filas:
            txt = " ".join(p["w"] for p in pal[t[0]:t[1]]); marca = "**ELEGIDA**" if (ti == mejor[1] and not inc) else ""
            md.append(f"- toma {ti}: {pal[t[0]]['ini']:.2f}-{pal[t[1]-1]['fin']:.2f} s, {'completa' if comp else 'incompleta'}{', tartamudeo' if tart else ''}, puntos {s:.1f} {marca}\n  > {txt}")
    for t in apartes: md.append(f"\n- aparte fuera: {pal[t[0]]['ini']:.2f}-{pal[t[1]-1]['fin']:.2f} s: " + " ".join(p["w"] for p in pal[t[0]:t[1]]))
    md.append("\n## Tramos que quedan\n" + "\n".join(f"- {i:.3f}-{f:.3f} s ({f-i:.2f} s)" for i, f in tramos))
    total = sum(f - i for i, f in tramos) - sum(e["quitar"][1] - e["quitar"][0] for e in quitar if "editor" in e["accion"])
    md.append(f"\nDuración estimada del cuerpo: {total:.1f} s")
    texto = "\n".join(md); print(texto)
    if a.md: open(a.md, "w").write(texto + "\n")
    if a.salida:
        out = dict(edl_p); out["edl"] = quitar; out["tramos_elegidos"] = tramos
        out["nota"] = "EDL combinado por seleccionar_tomas.py: mejor toma por línea (transcript) + pausas acortadas dentro de las tomas (señal)"
        json.dump(out, open(a.salida, "w"), ensure_ascii=False, indent=1); print("\nEDL escrito:", a.salida)

if __name__ == "__main__":
    main()
