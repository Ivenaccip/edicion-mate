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

## AssemblyAI vs Whisper en las pausas largas (nov 2026)
Se transcribió la nota 2 con `python pipeline/transcribir.py nota2.ogg --backend assemblyai`
(modelo que reportó la API: `universal-3-5-pro`, confianza global 0.995, 25 palabras en ~4 s).
Tiempos de Whisper: `salida/nota2.palabras.json`. Tiempos de AssemblyAI: `salida/nota2.assemblyai.palabras.json`.
Imagen: `salida/nota2_whisper_vs_assemblyai.png`.

**Respuesta a la pregunta del handoff: AssemblyAI sí respeta los bordes reales de palabra. No estira sobre las pausas.**

| Pausa real (energía) | Whisper (small) | AssemblyAI (universal-3-5-pro) |
|---|---|---|
| 0.00–2.66 s, 2660 ms (antes de hablar) | 'Segunda' 2.56–3.06 s | 'Segunda' 2.49–3.17 s |
| 3.82–5.88 s, 2060 ms | 'esta' 4.12–6.26 s, dura 2140 ms, 90 % silencio | 'audio.' termina 3.72 s, 'Esta' empieza 6.28 s: **hueco de 2559 ms** entre palabras |
| 8.97–11.02 s, 2050 ms | 'para' 8.82–11.56 s, dura 2740 ms, 87 % silencio | 'espaciados' termina 9.11 s, 'para' empieza 11.43 s: **hueco de 2321 ms** |

Whisper no reporta ningún hueco mayor a 420 ms en toda la nota. AssemblyAI reporta los dos huecos largos
tal cual. Con AssemblyAI, un editor que lea solo el transcript sí sabría que hay dos pausas de 2 s.

### Precisión de los bordes (medida contra la señal)
- Fin de palabra antes de la pausa: AssemblyAI termina 'audio.' 103 ms antes de que la energía caiga
  y 'espaciados' 142 ms después de que cae. Error de borde del orden de ±150 ms.
- Inicio de palabra después de la pausa: 'para' empieza en 11.43 s y la voz fuerte arranca en 11.40 s
  (lo que `silencedetect` marcó como fin de silencio en 11.02 s era una respiración a −31/−36 dB).
  'Esta' empieza en 6.28 s pero la voz ya está a −15 dB en 6.10 s: AssemblyAI se comió ~180 ms del
  arranque y dejó la palabra en 80 ms. Es el único borde claramente recortado.
- Confianza por palabra: 23 de 25 en 0.98–1.00; las más bajas son 'para' (0.93) y 'espaciados' (0.99).

### Qué cambia y qué no
- **No cambia la regla**: dónde cortar lo sigue decidiendo la señal. Aunque AssemblyAI pone bordes
  mucho mejores, el error de ±150 ms y el recorte de 'Esta' bastan para mochar una sílaba si se corta
  en el timestamp. El editor por energía corta en el centro de la pausa, lejos de ambos bordes.
- **Sí cambia la utilidad del transcript**: con AssemblyAI el transcript sirve para saber *qué* pausa
  hay entre *qué* palabras (contexto editorial: "pausa larga antes de un dato fuerte"). Con Whisper
  small esa información simplemente no existía.
- Lo mismo se ve en la nota 1: Whisper estiró 'a' a 1.58 s, 'la' a 1.16 s y 'modificación' a 1.50 s;
  AssemblyAI deja esas palabras en 0.08, 0.19 y 0.64 s y reporta los huecos (1.13 s, 0.68 s, 1.10 s).
  Whisper además transcribió 'primer' donde AssemblyAI dice 'primera' (lo correcto).

### Muletillas (`disfluencies`)
Se corrió la nota 2 con `disfluencies=True` (por defecto) y con `--sin-muletillas`. Las dos corridas
dan las mismas 25 palabras con los mismos tiempos (solo cambia la confianza en 5 palabras, y 'ver'
termina 16 ms antes). No apareció ningún "eh", "mm" ni "este" porque **la nota no tiene muletillas**:
la prueba confirma que la opción no rompe nada, pero no confirma que las detecte. Falta probar con
un audio que sí tenga muletillas reales (idealmente de Charlie).

### Detalles de la API verificados
- Encabezado: `authorization: <llave>` funciona igual con y sin prefijo `Bearer` en AssemblyAI v2.
- `speech_model` (singular) ya está deprecado y devuelve 400. Hay que mandar
  `speech_models: ["universal-3-5-pro", "universal-2"]`; la respuesta trae `speech_model_used`.
- Tiempo total por nota de 15 s: subida + transcripción + espera ≈ 4 s.
