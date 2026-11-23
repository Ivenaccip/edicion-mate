#!/usr/bin/env python3
"""Remapea los tiempos por palabra del raw al tiempo del cuerpo (video ya cortado), para captions.

Regla del contrato (docs/ESTANDAR-PIPELINE-AUDIO.md): a cada palabra se le resta la suma de los tramos
quitados antes de ella; los tramos conservados están en cuerpo.aplicado.json. Las palabras que caen
dentro de un tramo quitado se descartan (no están en el cuerpo). Una palabra que cruza un borde se recorta
al tramo conservado. Los tiempos resultantes sirven para captions, no para cortar (error de ±170 ms).

Uso: remapear_palabras.py raw.palabras.json cuerpo.aplicado.json cuerpo.palabras.json
"""
import sys, json

def remapear(palabras, conservados):
    out = []
    acumulado = 0.0  # duración de cuerpo antes del tramo actual
    for ini, fin in conservados:
        dur = fin - ini
        for w in palabras:
            a, b = w["ini"], w["fin"]
            if b <= ini or a >= fin: continue
            a2, b2 = max(a, ini), min(b, fin)
            if b2 - a2 < 0.02: continue            # resto de palabra de < 20 ms: no vale como caption
            out.append({**w, "ini": round(acumulado + (a2 - ini), 3), "fin": round(acumulado + (b2 - ini), 3), "raw_ini": a, "raw_fin": b})
        acumulado += dur
    out.sort(key=lambda w: w["ini"])
    return out, acumulado

def main():
    raw, aplicado, salida = sys.argv[1:4]
    palabras = json.load(open(raw)); ap = json.load(open(aplicado))
    conservados = ap["tramos_conservados"]
    out, dur = remapear(palabras, conservados)
    json.dump(out, open(salida, "w"), ensure_ascii=False, indent=0)
    print(f"{len(palabras)} palabras del raw -> {len(out)} en el cuerpo ({dur:.3f} s, {len(conservados)} tramos); descartadas {len(palabras)-len(out)}")
    if out: print("primera:", out[0]["w"], out[0]["ini"], "| última:", out[-1]["w"], out[-1]["fin"])

if __name__ == "__main__":
    main()
