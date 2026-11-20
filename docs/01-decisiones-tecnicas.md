# Decisiones técnicas: "escuchar", motor de render y auditor

Resultado de investigación (nov 2026) sobre los tres huecos abiertos en `00-analisis-y-fases.md`.

---

## 1. "Escuchar" el video en vez de cortar por transcript

### Por qué WhisperX corta palabras a la mitad
No es que WhisperX "no escuche". Son tres errores apilados:

1. **Error del timestamp.** WhisperX alinea con un modelo fonético (wav2vec 2.0) y su error de borde por palabra ronda los 65 ms según el README de CrisperWhisper 2.0 (que reporta ~30 ms para sí mismo). Si cortas exactamente en el fin de la palabra, 65 ms de error ya mochan la última sílaba.
2. **Cortar en el timestamp y no en el silencio.** El fin de una palabra no es el fin del sonido: hay decaimiento, reverb y respiración. Un corte limpio va en el valle de energía posterior, no en el borde de la palabra.
3. **El VAD trata el susurro como silencio.** El detector de actividad de voz (VAD) con umbral alto clasifica la cola susurrada de Charlie como "no hay voz" y el segmento termina antes.

### No existe "un repo que escuche". Existe una combinación de tres capas
| Capa | Para qué | Herramienta recomendada | Alternativas |
|---|---|---|---|
| **A. Qué se dijo** (captions, texto) | Palabras con tiempos precisos | **Qwen3-ASR + Qwen3-ForcedAligner-0.6B** (Apache 2.0, el de menor error de timing en arXiv 2609.15218) | CrisperWhisper 2.0 (verbatim, detecta muletillas); ElevenLabs Scribe v2 o AssemblyAI (API, timestamps nativos sin alineación) |
| **B. Dónde cortar** (bordes reales de habla) | Encontrar valles de energía y silencios | **Silero VAD** con `speech_pad_ms` 300–500 y umbral bajo + `ffmpeg silencedetect` con `noise` relativo al piso de ruido | auto-editor (`--margin 0.2s`, corte por loudness; buen baseline) |
| **C. Intención** (¿la cola susurrada importa?) | Tono, énfasis, pausas con intención | **Gemini Pro con audio nativo** (los papers muestran que Flash cae a leer el transcript) | Qwen3-Omni, Voxtral (open weights, pero dependen de un VAD externo) |

### Regla de corte propuesta (la que de verdad evita mochar palabras)
```
corte_valido(t) =
    t >= fin_ultima_palabra + 120 ms          # margen sobre el error del aligner
    AND energia(t) es mínimo local            # valle, no borde
    AND VAD(t) == silencio con umbral bajo    # el susurro cuenta como voz
    AND t <= inicio_siguiente_palabra - 80 ms
```
Si no hay un `t` que cumpla, **no se corta ahí**. Esto convierte el problema de "modelo que escuche" en "nunca cortar donde no hay silencio real".

### Verificación posterior (lo usa el auditor)
Re-transcribir el render y hacer diff contra el transcript esperado. Cualquier palabra faltante o truncada aparece como diferencia. Es la prueba más barata y objetiva de "se escuchan todas las palabras".

---

## 2. Hyperframes vs Remotion

**Son alternativas entre sí, no complementos.** Ambos renderizan HTML en Chrome headless y lo encodean con FFmpeg. Se elige uno.

| | HyperFrames (HeyGen) | Remotion |
|---|---|---|
| Lenguaje | HTML + CSS + GSAP, sin build step | React, necesita bundler y proyecto |
| Diseñado para | Agentes que escriben el HTML | Equipos de desarrollo React |
| Licencia | Apache 2.0, sin límite de equipo | Gratis para individuos y empresas ≤3 personas; Company License arriba de eso |
| Madurez | Joven (2026), comunidad pequeña | Maduro, ecosistema grande, Lambda para render en nube |
| Captions | Skill `/embedded-captions`; 20 skills para agentes (`npx skills add heygen-com/hyperframes`) | Paquete de captions + integración con whisper.cpp |
| Requisitos | Node ≥ 22 + FFmpeg | Node + FFmpeg |
| Nube | Render hospedado por HeyGen, cobro por minuto | Remotion Lambda |

**Qué hacen y qué no.** Sirven para la **capa de composición**: captions animadas, overlays, motion graphics, pantalla de CTA, logo. **No sustituyen a FFmpeg para cortar** el talking head: los cortes, el concat y el audio del raw siguen siendo FFmpeg.

**Recomendación:** HyperFrames. El que escribe la composición es un agente, no un humano; sin build step hay menos cosas que fallan; y la licencia no se rompe cuando el equipo pasa de 3 personas (tú, Charlie, Dani…). Remotion solo si ya hay alguien que viva en React.

### Arquitectura de render resultante
```
raw.mp4 ──FFmpeg (cortes por regla de la sección 1)──▶ cuerpo.mp4 + palabras.json
                                                            │
                        HyperFrames (captions + overlays + CTA_i) ◀──┘
                                                            │
                       FFmpeg concat: cuerpo + cola_CTA_i ──▶ 7 finales 1080
```
El cuerpo se renderiza una vez; solo las 7 colas de CTA se renderizan por separado.

---

## 3. Auditor: cómo inspecciona el video y qué lo hace distinto del editor

### La diferencia clave: no comparten contexto
El editor tiene el plan (EDL), el raw y sus propias decisiones. **El auditor recibe únicamente**: el MP4 preview a 576p, el transcript original esperado y la checklist. Nunca ve el plan ni el razonamiento del editor. Así no puede "confiar" en lo que el editor dice que hizo; tiene que medirlo en el archivo.

### Dos capas de inspección
**Capa 1: determinista (scripts, sin LLM, segundos de ejecución)**
| Check | Herramienta | Detecta |
|---|---|---|
| Palabras completas | Re-transcribir render + diff contra transcript esperado | Palabras cortadas o faltantes |
| Volumen | `ffmpeg loudnorm` (pasada de medición) | LUFS fuera de objetivo (p. ej. −14 ±1), picos |
| Silencios | `ffmpeg silencedetect` | Huecos muertos, cortes "de la nada" |
| Frames congelados / negros | `ffmpeg freezedetect`, `blackdetect` | Saltos, render fallido |
| Formato | `ffprobe` | Duración, 9:16, fps, códec |
| Captions presentes | Comparar tiempos de palabras.json contra duración | Tramos sin caption |

**Capa 2: perceptual (LLM con visión)**
- Muestreo de frames: uno cada 2 s + uno en cada cambio de escena y en cada evento de la capa 1.
- Claude con visión evalúa con rúbrica: caption legible, no tapa la cara, overlay bien posicionado, CTA correcto para esa red, continuidad visual entre cortes.
- Audio: Gemini con audio nativo para "¿este corte suena natural?" si la capa 1 marcó algo dudoso.

### Formato de `pendientes.md`
```markdown
# Pendientes — <proyecto> — ronda <n>
Veredicto: RECHAZADO | APROBADO
Bloqueantes: 2 · Mayores: 1 · Menores: 3

## P-01 · BLOQUEANTE · 00:14.320
Criterio: todas las palabras se escuchan
Evidencia: diff transcript → falta "...todavía" (esperado 00:14.1–00:14.4)
Acción: mover corte a ≥ 00:14.55 (valle detectado en 00:14.58)
Estado: abierto

## P-02 · MAYOR · 00:31.000–00:33.500
Criterio: captions presentes
Evidencia: frames/00-31-000.png, 00-32-500.png sin caption
Acción: regenerar bloque de captions 31.0–33.5
Estado: abierto
```
Cada pendiente lleva **timestamp, criterio, evidencia verificable y acción**. El editor marca `Estado: resuelto` y el auditor vuelve a medir; no acepta la palabra del editor.

### Criterios de aprobación
- Cero bloqueantes y cero mayores. Hasta 2 menores permitidos.
- Máximo 5 rondas. En la quinta sin aprobación: se detiene y avisa por Telegram a un humano.
- Preview a 576p para todas las rondas; 1080 ×7 solo tras APROBADO.

---

## 4. Higgsfield y descarga de videos
Sin rol de Higgsfield en esta versión. Para descargar videos públicos: `yt-dlp` desde la terminal cubre YouTube, TikTok e Instagram sin navegador. La extensión de Chrome (Claude in Chrome) queda para páginas que requieran sesión iniciada.
