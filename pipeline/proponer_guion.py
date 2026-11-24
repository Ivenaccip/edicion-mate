#!/usr/bin/env python3
"""Propone el guion final de un raw grabado a varias tomas, a partir del transcript, para que una persona lo revise.

Regla del estándar: cuando el raw repite líneas, charla con el equipo o tiene apartes, el transcript decide qué se
queda, y la decisión se escribe como guion (una frase por línea). seleccionar_tomas.py --guion busca luego la toma
más parecida a cada frase. Este script escribe la primera versión de ese guion y un diagnóstico.

Cómo propone:
  1 tomas     = las de seleccionar_tomas.dividir_tomas (reinicio de las mismas 3 palabras, fin de oración, pausa).
  2 descarta  = tomas incompletas (no terminan en . ? !), tomas con tartamudeo (bigrama repetido), charla con el
                equipo (<= 3 palabras que no sean "número N ..."; o con marcadores: ajá, eh, ¿no?, ¿sí?, "no me
                acuerdo", "siento que", "ya", "ok").
  3 agrupa    = tomas parecidas (difflib >= 0.6 sobre texto normalizado, o mismas 3 primeras palabras) y se queda
                con la última de cada grupo (la que el presentador dio por buena).
  4 ordena    = por tiempo de la toma elegida.
Antes de clasificar, las tomas de habla continua partidas por una pausa (sin fin de oración ni reinicio) se funden.
Diagnóstico "a varias tomas" si hay >= 2 grupos con repeticiones (dos líneas dichas más de una vez).
Uso: proponer_guion.py raw.palabras.json guion.propuesto.txt [--json diagnostico.json]
"""
import argparse, json, re, difflib, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from seleccionar_tomas import dividir_tomas, norm, termina

CHARLA = re.compile(r"\b(aja|eh|ok|okey|ya|si no ya|no me acuerdo|siento que|no se si|puedo hacer|como mas|es mas como|cuando fue|cuando salio|aunque bueno|no importa)\b")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("palabras"); ap.add_argument("salida"); ap.add_argument("--json")
    ap.add_argument("--parecido", type=float, default=0.6)
    a = ap.parse_args()
    d = json.load(open(a.palabras)); pal = d["palabras"] if isinstance(d, dict) else d
    tomas = dividir_tomas(pal)
    # habla continua: una toma que no termina en . ? ! y cuya siguiente no es un reinicio (mismas 3 palabras) ni
    # viene tras una pausa larga es la misma frase partida por una pausa; se funden antes de clasificar
    fund = []
    for t in tomas:
        if fund:
            p = fund[-1]; ult = pal[p[1] - 1]["w"]; gap = pal[t[0]]["ini"] - pal[p[1] - 1]["fin"]
            reinicio = [norm(x["w"]) for x in pal[t[0]:t[0] + 3]] == [norm(x["w"]) for x in pal[p[0]:p[0] + 3]]
            if not termina(ult) and not ult.endswith("-") and not reinicio and gap < 1.5:
                fund[-1] = (p[0], t[1]); continue
        fund.append(t)
    tomas = fund
    info = []
    for (i0, i1) in tomas:
        ws = [p["w"] for p in pal[i0:i1]]; toks = [norm(w) for w in ws]; txt = " ".join(toks)
        completa = termina(ws[-1]) and not ws[-1].endswith("-")
        big = list(zip(toks, toks[1:])); tartamudeo = len(big) != len(set(big))
        numero = re.match(r"^numero \d", txt) is not None
        charla = (len(toks) <= 3 and not numero) or (CHARLA.search(txt) is not None and len(toks) <= 8)
        info.append({"ini": pal[i0]["ini"], "fin": pal[i1 - 1]["fin"], "texto": " ".join(ws), "norm": txt,
                     "completa": completa, "tartamudeo": tartamudeo, "charla": charla, "n": len(toks)})
    validas = [t for t in info if t["completa"] and not t["tartamudeo"] and not t["charla"]]
    # agrupar parecidas: cada toma va al grupo de la primera a la que se parece
    grupos = []
    for t in validas:
        for g in grupos:
            r = difflib.SequenceMatcher(None, g[-1]["norm"], t["norm"]).ratio()
            if r >= a.parecido or g[-1]["norm"].split()[:3] == t["norm"].split()[:3]:
                g.append(t); break
        else: grupos.append([t])
    elegidas = sorted((g[-1] for g in grupos), key=lambda t: t["ini"])
    repetidos = sum(1 for g in grupos if len(g) > 1); descartadas = len(info) - len(validas)
    varias = repetidos >= 2   # dos o más líneas dichas más de una vez: el raw se grabó a varias tomas
    Path(a.salida).write_text("\n".join(t["texto"] for t in elegidas) + "\n", encoding="utf-8")
    diag = {"tomas": len(info), "descartadas": descartadas, "grupos": len(grupos), "grupos_repetidos": repetidos,
            "frases_propuestas": len(elegidas), "a_varias_tomas": bool(varias),
            "duracion_propuesta_s": round(sum(t["fin"] - t["ini"] for t in elegidas), 1),
            "frases": [{"ini": t["ini"], "fin": t["fin"], "texto": t["texto"]} for t in elegidas],
            "descartes": [{"ini": t["ini"], "texto": t["texto"], "motivo": "incompleta" if not t["completa"] else "tartamudeo" if t["tartamudeo"] else "charla"} for t in info if t not in validas]}
    if a.json: Path(a.json).write_text(json.dumps(diag, ensure_ascii=False, indent=1))
    print(f"tomas {len(info)}, descartadas {descartadas}, grupos {len(grupos)} ({repetidos} con repeticiones) -> {len(elegidas)} frases, {diag['duracion_propuesta_s']} s; a varias tomas: {varias}")
    for t in elegidas: print(f"  {t['ini']:7.2f}  {t['texto']}")

if __name__ == "__main__":
    main()
