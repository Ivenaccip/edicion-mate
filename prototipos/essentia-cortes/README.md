# Prototipo: detección de cortes mal hechos con Essentia

Valida la **capa B** del auditor (`docs/01-decisiones-tecnicas.md`, secciones 3 y 5):
¿puede un detector de señal, sin IA, encontrar un corte sucio en voz?

## Cómo correr
```bash
# Linux / macOS / WSL. En Windows nativo no hay wheel de Essentia.
sudo apt-get install -y espeak-ng ffmpeg      # solo si no tienes un WAV de voz
python3 -m venv .venv && . .venv/bin/activate
pip install -r prototipos/essentia-cortes/requirements.txt
python prototipos/essentia-cortes/prototipo.py             # voz sintética en español
python prototipos/essentia-cortes/prototipo.py charlie.wav # cuando llegue la muestra real
```
Salida en `salida/`: `limpio.wav`, `sucio.wav`, `hueco.wav`, `detecciones.png` y la tabla en consola.

## Qué fabrica
| Versión | Cómo se hizo | Simula |
|---|---|---|
| limpio | Acorta una pausa cortando solo dentro del silencio, crossfade 15 ms | Corte bien hecho |
| sucio | Corta en medio de una vocal y pega con el pico de la siguiente vocal, sin crossfade | Palabra mochada |
| hueco | Igual que sucio pero con 50 ms de ceros entre las partes | Render con hueco |

## Resultado (voz sintética espeak-ng, 17.7 s, nov 2026)
| Versión | VozAmbosLados | Discontinuity | Click | Gaps |
|---|---|---|---|---|
| limpio | no | 0 en el corte (1 falso en otro punto) | 21 falsos | marca la pausa natural |
| sucio | **SÍ** | **SÍ, exacto** | **SÍ, exacto** | no |
| hueco | no (hay ceros después) | **SÍ, en ambos bordes del hueco** | SÍ | **SÍ, exacto** |

Imagen: `salida/detecciones.png` (zoom ±1 s alrededor del corte).

## Resultado con voz real (nota de WhatsApp, Opus 48 kHz, 15.1 s, nov 2026)
| Versión | VozAmbosLados | Discontinuity | Click | Gaps |
|---|---|---|---|---|
| original sin tocar | - | 0 | 0 | 0 |
| limpio | no | 0 | 0 | 0 |
| sucio | **SÍ** | **SÍ, exacto** | **SÍ, exacto** | 0 |
| hueco | no | **SÍ, ambos bordes** | SÍ, ambos bordes | **SÍ, exacto** |

Imagen: `salida/detecciones_voz_real.png`. **Cero falsos positivos en los tres detectores** con los umbrales por defecto, tanto en el audio intacto como en el corte limpio. Los falsos de ClickDetector y GapsDetector eran un artefacto de la voz sintética, no un problema de calibración. Audio con compresión fuerte (20 kbps) y pico a 0 dBFS, es decir, condiciones peores que el video real.

## Conclusiones
1. **DiscontinuityDetector es el detector principal.** Cero falsos en el corte limpio, acierto exacto en sucio y hueco con los umbrales por defecto.
2. **Un corte en medio de una palabra puede ser físicamente continuo.** En una corrida anterior el empalme vocal→vocal cayó por azar en un punto donde la onda casi no salta (de -0.199 a -0.187) y ningún detector lo vio. Por eso se añadió `VozAmbosLados`: energía de voz 30 ms antes y 30 ms después del corte. Esa métrica es la que detecta "corté en medio del habla" aunque la onda sea suave.
3. **ClickDetector y GapsDetector funcionan en voz real sin calibrar.** Los falsos que daban con espeak-ng (pulsos glotales que parecen clics, silencio digital en las pausas) desaparecen con una grabación real. Los umbrales por defecto quedan como punto de partida para Fase 2.
4. **Confirmar con audio del video de Charlie** (micrófono y compresión distintos) antes de dar los umbrales por definitivos.
5. **Lo que no puede hacer ninguna de estas capas:** saber si la palabra quedó completa. Eso lo da el diff de re-transcripción (capa 1 del auditor) y la opinión del modelo de audio nativo (capa A).

## Parámetros que quedaron
- `DiscontinuityDetector(frameSize=512, hopSize=256)` por defecto.
- `ClickDetector(detectionThreshold=30)` por defecto; pendiente calibrar.
- `GapsDetector(minimumTime=10, prepowerThreshold=-30)`.
- `VozAmbosLados(ventana=30 ms, umbral=10 % del RMS global)`.
- Tolerancia de acierto: ±60 ms respecto al corte real.
