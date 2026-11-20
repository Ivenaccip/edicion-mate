# Editor mínimo de pausas (Fase 1, sin transcript)

Primer "editor" real: escucha la señal, encuentra todas las pausas, decide cuáles acortar
y aplica los cortes con crossfade. Entrega el audio editado y un EDL en JSON con cada decisión.

```bash
. .venv/bin/activate
python prototipos/editor-pausas/editor_pausas.py entrada.wav salida.wav
# genera salida.wav y salida.edl.json
```

## Reglas (constantes al inicio del script)
| Regla | Valor | Qué significa |
|---|---|---|
| UMBRAL_DB | -35 dB | Energía por debajo del nivel de voz para contar como pausa |
| MIN_PAUSA | 120 ms | Menos que esto es articulación, no pausa |
| PAUSA_MAX | 450 ms | Solo se acortan pausas más largas que esto |
| PAUSA_OBJETIVO | 250 ms | A cuánto se dejan las pausas acortadas |
| PAUSA_BORDE | 150 ms | Silencio que se deja al inicio y al final |
| CROSSFADE | 15 ms | En cada empalme |

Nunca corta dentro de voz: el recorte siempre ocurre en el centro de la pausa.

## Resultado con la nota de WhatsApp (15.13 s)
10 pausas encontradas, 2 acortadas, 0.35 s quitados. Pausa más larga: 480 ms en 9.73–10.21 s,
dejada en 250 ms.

## Qué le falta para ser el editor de verdad
1. **Transcript con tiempos por palabra** para saber qué se dijo, detectar muletillas y
   saber si una pausa larga es intención (Charlie susurrando) o relleno.
2. **Criterio editorial**: hoy la regla es "toda pausa > 450 ms se acorta". El editor real
   debe decidir por contexto (antes de un dato fuerte, una pausa larga se queda).
3. **Pasar el EDL al auditor**: el EDL ya lista cada empalme; el auditor de Essentia los
   mide uno por uno.
