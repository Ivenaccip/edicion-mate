#!/usr/bin/env python3
"""Captions desde cuerpo.palabras.json (tiempos ya remapeados al cuerpo): bloques de 2-3 palabras con la
palabra activa resaltada, como en el TikTok de referencia. Escribe dos fragmentos que vestir.sh inyecta en
composicion/index.html entre los marcadores <!-- CAPTIONS --> ... <!-- /CAPTIONS --> y // CAPTIONS-TL ... // /CAPTIONS-TL.

Reglas de bloque: máximo --max palabras (3); se corta en puntuación final (. ? !) y en huecos > --hueco s (0.5);
un bloque se muestra desde su primera palabra hasta la primera palabra del siguiente (o fin + 0.4 s).
Estilo provisional (hasta la spec): Inter ExtraBold 66 px, blanco con contorno negro (.texto-doble), activa en caja azul.

Uso: captions.py cuerpo.palabras.json captions.html captions.js [--max 3] [--hueco 0.5] [--fin 32.74]
"""
import argparse, json, html

def bloques(palabras, maximo, hueco):
    out, act = [], []
    for w in palabras:
        if act and (len(act) >= maximo or w["ini"] - act[-1]["fin"] > hueco):
            out.append(act); act = []
        act.append(w)
        if w["w"].rstrip().endswith((".", "?", "!")):
            out.append(act); act = []
    if act: out.append(act)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("palabras"); ap.add_argument("salida_html"); ap.add_argument("salida_js")
    ap.add_argument("--max", type=int, default=3); ap.add_argument("--hueco", type=float, default=0.5); ap.add_argument("--fin", type=float, default=None)
    a = ap.parse_args()
    pal = json.load(open(a.palabras)); bl = bloques(pal, a.max, a.hueco)
    fin = a.fin or (pal[-1]["fin"] + 0.4)
    h, js = [], []
    for i, b in enumerate(bl):
        spans = "".join(f'<span class="pal" data-t="{w["ini"]:.3f}">{html.escape(w["w"])}</span>' for w in b)
        h.append(f'        <div class="bloque" id="cap{i}">{spans}</div>')
        t0 = b[0]["ini"]; t1 = bl[i + 1][0]["ini"] if i + 1 < len(bl) else min(fin, b[-1]["fin"] + 0.4)
        js.append(f'      capBloque("#cap{i}", {t0:.3f}, {t1:.3f});')
    open(a.salida_html, "w").write("\n".join(h) + "\n")
    open(a.salida_js, "w").write("\n".join(js) + "\n")
    print(f"{len(pal)} palabras -> {len(bl)} bloques (media {len(pal)/max(len(bl),1):.1f} palabras, {fin/max(len(bl),1):.2f} s por bloque)")

if __name__ == "__main__":
    main()
