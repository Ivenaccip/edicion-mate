# Handoff — agente auditor (capa 1: checks deterministas)

El auditor recibe solo el preview 576 (o el WebM con alfa en el caso de la llave), el transcript esperado y la
checklist. No ve el EDL ni el razonamiento del editor. Escribe `pendientes.md` con timestamp, criterio,
evidencia y acción (formato en `01-decisiones-tecnicas.md`, sección 3).

## Checks de capa 1
| Check | Herramienta | Estado |
|---|---|---|
| Palabras completas | re-transcribir + diff contra transcript esperado | validado en la sesión de cortes |
| Empalmes limpios | Essentia DiscontinuityDetector en los empalmes del EDL | validado |
| Volumen, silencios, frames negros/congelados, formato | ffmpeg loudnorm, silencedetect, blackdetect, freezedetect, ffprobe | pendiente de script |
| **Llave de verde sin parpadeo ni agujeros** | `pipeline/visual/auditar_llave.py` | **validado 21 nov** (abajo) |
| Captions presentes | comparar palabras.json con duración | pendiente (no hay captions aún) |

## Check de la llave: `auditar_llave.py`
```bash
python pipeline/visual/auditar_llave.py raw.mp4 persona_alfa.webm --inicio-s 12 --dur-s 3 --umbral 0.085 \
  --md pendientes_llave.md --json auditoria_llave.json --debug-png mapa.png
# exit 0 = APROBADO, 2 = RECHAZADO
```
Qué mide:
1. **Tasa de conmutación por píxel** en el alfa del WebM: fracción de pares de frames consecutivos en que el
   píxel cruza entre transparente y visible. El ruido ("estática") es conmutación alta y sostenida; un borde de
   la persona que se mueve también conmuta, pero el raw cambia ahí (desviación temporal de luma > 6) y se descarta.
2. Clasifica cada celda de 40x40 px por lo que hay en el raw:
   - **verde estático** (verdoso en ≥ 80 % de las muestras): el parpadeo es verde que se cuela.
   - **sólido estático** (persona o escritorio quietos): el parpadeo son agujeros intermitentes.
3. **Cuánto mover el umbral**: en las celdas de verde que se cuela mide la distancia UV del verde al color clave
   (la misma que usa `chromakey`). `umbral_necesario = percentil 95 + 0.015`. **Techo** = distancia del negro de
   la ropa al clave − 0.015 (0.141 para #1e7032). Regla:
   - necesario ≤ 0.10 y < techo → "subir umbral global a X".
   - si no → "llave por zona: `mascara_sombras.py` y chromakey X dentro de la máscara; no subir el global".
   - agujeros → "forzar alfa=1 con máscara fija de escritorio/persona, o bajar umbral local a Y".

Validación con IMG_7889 (clip 12–15 s):
| Llave | Veredicto | Hallazgo |
|---|---|---|
| chromakey 0.08 global | RECHAZADO | zona x 0–240, y 1120–1280: conmutación 10.1 %/frame, verde a p95 0.095 → necesario 0.11 → acción "llave por zona 0.13". Coincide con la esquina que el usuario vio. |
| 0.085 global + 0.13 en máscara de sombras | APROBADO | 63 celdas sospechosas, 59 son bordes en movimiento, 0 de verde, 0 agujeros. |

Mapa de conmutación antes/después: `img/capa-visual/auditor_llave_mapa_conmutacion_antes_despues.jpg`.
Informes de ejemplo: `pipeline/salida/IMG_7889_t12_3s_llave_pendientes_{antes,despues}.md`.

## Límites conocidos
- Mide en una ventana (3 s aquí). En producción: correr sobre todo el cuerpo o en 3 ventanas (inicio, medio, fin).
- Los bordes de la persona se descartan por movimiento; un borde quieto con spill fuerte puede pasar como
  agujero. El umbral `--mov-max 6` está ajustado a este set (luz fija, sensor de celular).
- La máscara de sombras es por set: si cambia cámara o luz, regenerarla antes de auditar.
