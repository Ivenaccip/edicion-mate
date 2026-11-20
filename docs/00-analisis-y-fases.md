# Análisis del sistema de edición automatizada (transcript del editor) y fases para recrearlo

Fuente: nota de voz de 7 min de un editor profesional que automatizó la edición de los shorts de Charlie Sebastian con Claude Code, agentes y MCPs.

---

## 1. Qué construyó el editor (reconstrucción del sistema)

### Evolución cronológica
| Etapa | Qué hizo | Modelo | Resultado |
|---|---|---|---|
| 1. Claude + CapCut | Video de referencia ya editado + proyecto CapCut abierto para que Claude "aprendiera" el estilo (captions: fuente System, tamaño 7, borde). MCPs: Higgsfield, Notion, Drive, Hyperframes. Claude descarga el video del Drive, crea proyecto `DD. Tema`, dos timelines (CTA TikTok / CTA Instagram). | Sonnet 5.5 (effort alto) | 2–3 semanas. Mucha depuración manual (motion graphics mal puestos, cortes). |
| 2. Edición autónoma (sin CapCut) | Claude edita y renderiza solo. Agrega un repo para "escuchar" el audio y no depender solo del transcript (Charlie susurra las últimas palabras y se cortaban). | Sonnet 5.5 alto | Mejora grande en cortes. |
| 3. Salto de modelo | Editor pasa a Opus 5.5. | Opus 5.5 | ~20k tokens más por video, cortes mucho mejores. |
| 4. Multi-CTA | 7 renders por video, un CTA por red social ("entra al link", "comenta la palabra", "entra al primer comentario"). | Opus | 7 outputs/video. |
| 5. Triggers | Cuando Charlie sube el video a Notion se lanza un editor. 3 editores en paralelo (límite: CPU de la compu). | — | 1.5–2 h por tanda. |
| 6. Editor + Auditor | Editor termina → Auditor revisa checklist → escribe `pendientes.md` → Editor corrige → v2 → Auditor… hasta cero pendientes → render. Máx. observado: 5 rondas. | Opus (editor) | Calidad consistente sin revisión humana por ronda. |
| 7. Preview barato | Antes de auditar renderiza UN solo video a ~576p (~10 MB). Solo cuando pasa auditoría renderiza los 7 en 1080. | — | Ahorro grande de tiempo de render. |
| 8. Entrega | Videos al dashboard ("el de la clase"). Bot de Telegram reporta estado cada 15 min. Humano revisa → sube a Drive → Dani programa publicaciones con Blotato. | — | Pipeline cerrado. |

### Arquitectura resultante (lo que hay que recrear)
```
Notion (Charlie sube video) ──trigger──▶ Cola de trabajos (máx. 3 en paralelo)
                                              │
                                              ▼
                               ┌──────── EDITOR (Opus) ────────┐
                               │ 1. descarga video (Drive)      │
                               │ 2. transcript + análisis audio │
                               │ 3. plan de cortes (EDL)        │
                               │ 4. captions + motion graphics  │
                               │ 5. render preview 576p         │
                               └───────────────┬────────────────┘
                                               ▼
                               ┌──────── AUDITOR ──────────────┐
                               │ checklist → pendientes.md      │◀──┐
                               └───────────────┬────────────────┘   │ loop
                                       ¿pendientes vacío?           │ (≤5)
                                        no ─────────────────────────┘
                                        sí
                                               ▼
                               Render final 1080 × 7 CTAs ──▶ Dashboard
                                               │
                                     Telegram (cada 15 min)
                                               │
                              Humano revisa → Drive → Dani → Blotato
```

### Componentes del sistema
1. **Ingesta**: Notion (disparador + metadatos), Google Drive (archivo fuente).
2. **Análisis**: transcript con timestamps por palabra + "escucha" real del audio (detectar susurros, respiraciones, intención).
3. **Decisión de edición**: plan de cortes, zooms, dónde van los motion graphics, dónde entra cada CTA.
4. **Render**: captions con estilo fijo, overlays (Hyperframes), b-roll o imágenes (Higgsfield), audio, exportación.
5. **QA automático**: agente auditor con checklist y loop de correcciones.
6. **Variantes**: 7 CTAs por red.
7. **Orquestación**: trigger desde Notion, concurrencia 3, estados por video.
8. **Observabilidad y entrega**: dashboard, Telegram, Drive, Blotato.

---

## 2. Marcas [?] del transcript: qué interpreto

| Marca | Interpretación | Confianza |
|---|---|---|
| "de los de Charlie [?]" | Charlie Sebastian (coincide con tus skills `videos-charlie` y `skill-charlie`). | Alta |
| "hacía mucho mejor los cortes [?]" | Literal: Opus decide mejor dónde cortar. | Alta |
| "el editor, que está en Opus [?]" | Consistente con la etapa 3. | Alta |
| "560p o 580p" | Casi seguro **576p** (1024×576 o 576×1024 en vertical), resolución estándar de preview. | Media-alta |
| "dashboard que tengo [?], el que hicimos en la clase [?]" | Un dashboard construido en una clase/curso. No sé cuál. **Necesito identificarlo.** | Baja |

---

## 3. Lo que el transcript NO dice y es crítico

Estos son los huecos que deciden la arquitectura. Si el editor te puede responder, cada uno ahorra días de prueba y error.

1. **Motor de render.** ¿Cómo "edita solo"? Probablemente FFmpeg para cortes/captions y Hyperframes para motion graphics, pero no lo dice. Alternativas: Remotion, MoviePy.
2. **El "repo para escuchar el video".** Candidatos: WhisperX (alineación por palabra), faster-whisper + VAD (Silero), o un modelo de audio (Gemini audio / análisis de energía) para detectar susurros. Define cómo se decide dónde cortar.
3. **Cómo el Auditor "ve" el video.** ¿Muestrea frames? ¿Analiza el audio? ¿Compara transcript vs. captions? Esto define si el auditor es confiable o solo lee el plan del editor.
4. **Formato de `pendientes.md`** y criterios de "ya está en check".
5. **Rol exacto de Higgsfield** (¿b-roll generado? ¿imágenes? ¿solo en la etapa CapCut?).
6. **Infraestructura**: compu local del editor (3 editores la saturan). ¿Mac/Windows/Linux? ¿GPU? ¿Dónde correrá el tuyo?
7. **Estructura de la base de Notion** que dispara el trigger (campos, estados).
8. **Mecanismo del trigger**: tarea programada de Claude Code que consulta Notion cada N minutos, o webhook.
9. **Especificación visual exacta**: fuente, tamaño, borde, color, posición, animación de captions, palabras por línea, lista de motion graphics, música/SFX, logo.
10. **Las 7 redes y el copy exacto de cada CTA.**

---

## 4. Fases para recrearlo y qué necesito en cada una

### Fase 0 — Materiales base y decisiones (sin código)
**Objetivo:** tener la "verdad" del estilo y del flujo antes de automatizar nada.

Necesito de ti:
- [ ] 2–3 videos **finales** de Charlie (ya editados por este sistema) y, si existen, sus **raws** correspondientes. El par raw→final es el dataset de referencia más valioso.
- [ ] Spec de captions: fuente, tamaño, borde, color, posición, animación, palabras por bloque, resaltado de palabra activa.
- [ ] Assets: logo, lower thirds, música de fondo, SFX, plantillas de motion graphics que usan.
- [ ] Lista de las 7 redes + texto/visual del CTA de cada una.
- [ ] Formato de salida: 9:16 1080×1920, fps, códec, bitrate, loudness objetivo.
- [ ] Convención de nombres confirmada: `DD. Tema` (día del mes + tema).
- [ ] Dónde correrá: tu máquina (specs) o nube.
- [ ] Acceso: Notion (workspace y base), Drive (carpeta), Telegram (crear bot), Blotato (cuenta de Dani), Higgsfield (si aplica).
- [ ] Confirmar si tu skill `video-edit` viene del editor o es tuyo. Si es del editor, ya tenemos ~40% del agente de edición documentado.

Decisiones que tomo yo salvo que digas lo contrario:
- Motor: **FFmpeg** (cortes, concat, audio) + **ASS subtitles** para captions + **Hyperframes** para motion graphics.
- Transcript: **WhisperX** (timestamps por palabra) + **VAD** + análisis de energía para detectar colas susurradas.
- Representación intermedia: un **EDL en JSON** (lista de segmentos, captions, overlays, CTA) que el editor produce y el renderer ejecuta. Esto hace auditable y reproducible cada decisión.

### Fase 1 — Pipeline mínimo, un video, disparo manual
**Objetivo:** raw → short editado con captions y un CTA, ejecutado por un comando.

Entregables: `ingest` (Drive → local), `transcribe` (palabras + tiempos), `plan` (Claude produce EDL), `render` (FFmpeg + ASS), un output 1080.
Necesito: 1 raw de Charlie + su versión final para comparar. Credenciales de Drive.
Criterio de éxito: el output es comparable al final humano en cortes y captions, aunque sin motion graphics.

### Fase 2 — Calidad de corte y "escuchar"
**Objetivo:** que no se coman susurros ni haya cortes de la nada.

Trabajo: integrar análisis de audio (energía, pausas, respiraciones), reglas de padding al final de frases, detección de muletillas vs. intención. Comparar Sonnet vs Opus en el plan de cortes con los mismos raws.
Necesito: 3–5 raws donde Charlie susurre o baje la voz al final; ejemplos concretos de "corte malo" que el editor haya visto.
Criterio: cero palabras cortadas en los raws de prueba.

### Fase 3 — Motion graphics, b-roll y 7 CTAs
**Objetivo:** paridad visual con el estilo actual y las 7 variantes.

Trabajo: plantillas Hyperframes para cada overlay; integración Higgsfield si se usa; **optimización clave**: renderizar el cuerpo UNA vez y concatenar 7 colas de CTA distintas (evita 7 renders completos).
Necesito: assets de Fase 0, lista de overlays con ejemplos de cuándo se usan, los 7 CTAs.

### Fase 4 — Agente Auditor y loop de correcciones
**Objetivo:** QA automático con `pendientes.md`.

Checklist inicial (del transcript): captions presentes; sin cortes de la nada; todas las palabras se escuchan; frames correctos; sin saltos; volumen correcto.
Trabajo: el auditor muestrea frames (ffprobe/escena), verifica alineación captions↔audio, mide loudness, revisa continuidad del EDL. Preview a 576p antes de auditar. Máximo de rondas configurable (5).
Necesito: tolerancias (p. ej. loudness −14 LUFS ±1, desfase de captions < 80 ms), ejemplos de `pendientes.md` reales si el editor los comparte.

### Fase 5 — Orquestación: Notion → cola → 3 editores
**Objetivo:** que Charlie suba el video y el sistema arranque solo.

Trabajo: base de Notion con estados (`Nuevo → Editando → Auditando → Render → Listo → Publicado`), tarea programada que consulta Notion, cola con lock para que dos editores no tomen el mismo video, concurrencia limitada por CPU.
Necesito: acceso a Notion, definir campos, decidir máquina (la concurrencia depende de ella).

### Fase 6 — Entrega, notificaciones y publicación
**Objetivo:** dashboard + Telegram + Drive + Blotato.

Trabajo: bot de Telegram con resumen cada 15 min; subida a Drive con estructura de carpetas; dashboard de estado (identificar el "de la clase" o hacer uno simple); opcionalmente programar en Blotato desde el pipeline para quitarle el paso manual a Dani.
Necesito: token de Telegram (lo creamos), carpeta destino en Drive, acceso a Blotato, saber qué dashboard es.

### Fase 7 — Costos, métricas y endurecimiento
Tokens por video (Sonnet vs Opus), tiempo por video, tasa de rondas de auditoría, errores por tipo. Reintentos, logs, limpieza de temporales.

---

## 5. Orden propuesto para empezar
1. Reunir materiales de Fase 0 (sobre todo pares raw→final y la spec de captions).
2. Responder los 10 huecos de la sección 3, aunque sea parcialmente.
3. Arrancar Fase 1 con un solo video y disparo manual.
4. No tocar triggers ni multi-agente hasta que un video salga bien a mano.
