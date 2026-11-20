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

## Resultado con la segunda nota (pausas largas a propósito, 15.35 s)
Transcript: "Segunda prueba de audio, esta prueba va a estar enfocada hacia los espaciados para poder
ver si los puede detectar y cortar de forma correcta."

6 pausas encontradas, 4 acortadas, 6.06 s quitados. Resultado: 9.25 s. El auditor de Essentia midió
los 4 empalmes: cero discontinuidades, cero clics, cero huecos, sin voz a ningún lado del corte.
Imagen: `salida/nota2_comparacion.png`.

## Hallazgo: Whisper no ve las pausas, la señal sí
Comparando las pausas detectadas por energía contra los tiempos por palabra de faster-whisper (small):

| Pausa real (energía) | Qué dice Whisper |
|---|---|
| 3.85–5.87 s, 2020 ms | 'esta' dura 2140 ms (4.12–6.26 s) y el 93 % de ese tramo es silencio |
| 8.99–10.92 s, 1930 ms | 'para' dura 2740 ms (8.82–11.56 s) y el 92 % de ese tramo es silencio |

Whisper reparte el silencio dentro de las palabras vecinas. Un editor que trabaje solo con el transcript
no sabría que hay una pausa de 2 s, y si "respeta los bordes de palabra" cortaría dentro del silencio
que Whisper etiquetó como 'para'. Esto confirma con datos la decisión de `docs/01-decisiones-tecnicas.md`:
**qué se dijo** sale del transcript; **dónde cortar** sale de la señal. Nunca al revés.

Archivos: `salida/nota1.palabras.json`, `salida/nota2.palabras.json` (tiempos por palabra de Whisper).

## Infra
- El modelo se descarga de Hugging Face; el entorno de nube necesita permitidos `huggingface.co`,
  `cdn-lfs.huggingface.co`, `us.aws.cdn.hf.co`, `cas-server.xethub.hf.co` y `cas-bridge.xethub.hf.co`.
- faster-whisper 1.x choca con la versión actual de PyAV; se evita pasando el audio como array
  float32 a 16 kHz en vez de la ruta del archivo.
