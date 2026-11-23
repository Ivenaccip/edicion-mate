# Handoff — estado general (actualizado 20 nov 2026, noche)

> Sesión paralela de **capa visual / pantalla verde**: ver `docs/HANDOFF-pantalla-verde.md` y sus
> resultados en `docs/02-capa-visual.md` (llave híbrida chromakey+RVM, WebM con alfa, composición Hyperframes).
> Esta sesión (cortes + audio) y aquella no se pisan: una produce `cuerpo.mp4`, la otra lo viste.

## Qué es este proyecto
Recrear el sistema de edición automática de shorts de Charlie Sebastian que construyó un editor
profesional con Claude Code: Notion dispara → editor (agente) corta y compone → auditor revisa con
`pendientes.md` → render 7 CTAs → dashboard, Telegram, Drive, Blotato.
Leer en este orden: `docs/00-analisis-y-fases.md`, `docs/01-decisiones-tecnicas.md`, este archivo.

## Decisiones ya tomadas (no reabrir)
- Motor de composición: **Hyperframes** (no Remotion). Cortes y concat: **FFmpeg**.
- **Dónde cortar lo decide la señal, no el transcript.** Validado dos veces: Whisper small estira las
  pausas dentro de las palabras vecinas (90 % de la "palabra" era silencio), y AssemblyAI, aunque pone
  bordes buenos, tiene error de ±150 ms y recortó el arranque de una palabra. Se corta en el centro de
  la pausa medida por energía, nunca en el timestamp de una palabra.
- Capa B del auditor: **Essentia** (DiscontinuityDetector) + métrica "voz a ambos lados del corte".
- Transcripción en producción: **AssemblyAI** (`universal-3-5-pro`). Whisper local queda como respaldo
  sin red. El resto del pipeline solo ve la lista `[{"w", "ini", "fin"}]`, no sabe qué backend fue.
- Representación intermedia: **EDL en JSON** con cada decisión y su tiempo en segundos. El editor lo
  produce, el renderer lo ejecuta, el auditor lo lee para saber dónde medir.

## Resultados de esta sesión
1. **AssemblyAI validado** con las dos notas de voz reales (`prototipos/editor-pausas/README.md`,
   sección "AssemblyAI vs Whisper"). Respeta los bordes de palabra y reporta las pausas largas como
   huecos de 2.56 s y 2.32 s. 25 palabras en ~4 s por nota de 15 s. Con AssemblyAI el transcript sí
   sirve para saber *entre qué palabras* hay una pausa larga (contexto editorial). Imagen:
   `prototipos/editor-pausas/salida/nota2_whisper_vs_assemblyai.png`.
2. **Bug de API corregido** en `pipeline/transcribir.py`: `speech_model` está deprecado (400); ahora
   se manda `speech_models: ["universal-3-5-pro", "universal-2"]`. El encabezado `authorization`
   funciona con y sin `Bearer`. Nueva bandera `--sin-muletillas`.
3. **Muletillas**: `disfluencies` on/off da las mismas palabras y tiempos en la nota 2. Prueba
   inconclusa porque la nota no tiene muletillas; falta un audio que sí las tenga.
4. **Audios editados entregados al usuario** (nota 1: 15.13→14.87 s; nota 2: 15.35→9.32 s). Los
   escuchó y le parecieron bien. Los `.wav`/`.mp3` no van al repo (gitignore); el EDL sí.
5. **Duda del usuario respondida**: el EDL ya trae los tiempos exactos (ms) de cada tramo quitado, y
   audio y video comparten reloj, así que esos mismos tiempos sirven para cortar el video. Lo que no
   existe todavía es el script que aplica el EDL al video. Eso es la Fase 1.

## Qué hay en el repo
| Ruta | Qué es | Estado |
|---|---|---|
| `prototipos/essentia-cortes/prototipo.py` | Auditor de señal: mide discontinuidades, clics, huecos y voz a ambos lados en cada corte | Validado |
| `prototipos/editor-pausas/editor_pausas.py` | Editor por energía: encuentra pausas, acorta las > 450 ms a 250 ms, crossfade 15 ms, escribe `.edl.json` | Validado con 2 notas |
| `pipeline/transcribir.py` | Transcriptor con backends `whisper` / `assemblyai`, salida uniforme por palabra | Ambos validados |
| `prototipos/editor-pausas/salida/*.palabras.json` | Tiempos por palabra de Whisper y AssemblyAI para las 2 notas | Referencia |
| `prototipos/editor-pausas/salida/*.edl.json` | EDL de las ediciones hechas | Referencia |

Formato del EDL actual (lo produce `editor_pausas.py`):
```json
{"duracion_original_s": 15.354, "duracion_editada_s": 9.248, "reglas": {...},
 "edl": [{"pausa": [3.85, 5.87], "dur_ms": 2020, "accion": "acortar a 250 ms",
          "quitar": [3.975, 5.745], "quitado_ms": 1770}, ...]}
```

## Fase 1: raw → short editado, disparo manual
Objetivo del plan original: `ingest` → `transcribe` → `plan` → `render`, un video, un comando.
Con lo validado, el orden realista es:

### Paso 1. `pipeline/cortar_video.py`: aplicar el EDL al video — **HECHO y validado (ver `pipeline/README.md`)**
- Entrada: `raw.mp4` + `raw.edl.json`. Salida: `cuerpo.mp4` (solo cortes, sin captions).
- Convertir "quitar" en "conservar" (complemento de los tramos quitados sobre `[0, duración]`).
- **Redondear cada borde al frame** (a 30 fps, múltiplos de 33.33 ms) y cortar el audio con los
  mismos tiempos redondeados para que no se acumule desfase. Documentar el desfase máximo (≤ 1 frame).
- **Recodificar**, no `-c copy`: el corte exacto cae entre keyframes. Usar `select`/`aselect` o
  `trim`/`atrim` + `concat` en un solo `filter_complex`; `acrossfade` de 15 ms en audio. Preview a
  576p con `-preset veryfast`; final a 1080 solo cuando el auditor apruebe.
- Verificación: duración de salida = suma de tramos conservados ± 1 frame; el auditor de Essentia
  corre sobre el audio extraído del `cuerpo.mp4` y da cero marcas; re-transcribir con AssemblyAI y
  hacer diff contra el transcript del raw: cero palabras faltantes.

### Paso 2. Unir editor + transcript en un solo `plan`
- `editor_pausas.py` hoy decide solo por duración. Con AssemblyAI se sabe qué palabra va antes y
  después de cada pausa: guardar eso en el EDL (`"antes": "audio.", "despues": "Esta"`), así el
  criterio editorial y el auditor tienen contexto sin reabrir el audio.
- Regla provisional mientras no hay criterio de Charlie: pausa > 450 ms se acorta a 250 ms, salvo
  pausa final del video (se deja) y pausa antes de la última frase (se deja en 400 ms).
- Mover el editor de `prototipos/` a `pipeline/` solo cuando el paso 1 funcione.

### Paso 3. Captions mínimas
- ASS generado desde `palabras.json` (AssemblyAI), bloques de 3–4 palabras, remapeando tiempos con
  el EDL (restar lo quitado antes de cada palabra). Estilo provisional hasta tener la spec real.
- Hyperframes entra después, cuando exista spec visual; no bloquear la Fase 1 por eso.

### Paso 4. Un comando
`python pipeline/editar.py raw.mp4` → `raw.palabras.json`, `raw.edl.json`, `cuerpo_576.mp4`,
`auditoria.json`. Nada de Notion, Drive ni concurrencia todavía.

### Criterio de éxito de la Fase 1
Con un video de prueba del usuario: el corte del video cae en el tiempo que dice el EDL (comprobable
viendo el frame), ninguna palabra truncada en el diff de re-transcripción, cero marcas del auditor.

## Primera tarea de la próxima sesión (actualizado: el paso 1 ya está hecho; seguir con el paso 2)
1. Preparar entorno (contenedor nuevo cada vez):
   ```bash
   apt-get update -q && apt-get install -y -q espeak-ng
   python3 -m venv .venv && . .venv/bin/activate
   pip install -r prototipos/essentia-cortes/requirements.txt faster-whisper requests
   ```
   Verificar `ASSEMBLYAI_API_KEY` sin imprimirla. Hosts permitidos: api.assemblyai.com, huggingface.co
   y sus CDN.
2. Pedir al usuario el **video de prueba** (ver abajo). Si aún no lo tiene, fabricar uno: `ffmpeg`
   con `testsrc` + reloj de frames (`drawtext` con `%{n}` y `%{pts}`) sobre el audio de la nota 2.
   Con el número de frame impreso en pantalla se comprueba a simple vista que el corte cae donde
   dice el EDL. Pedir la nota 2 de nuevo si hace falta (los `.ogg` no están en el repo).
3. Escribir `pipeline/cortar_video.py` (paso 1) y validarlo con las tres verificaciones.
4. Entregar al usuario el video editado y el EDL juntos, no solo la descripción.

## Hecho después del handoff (misma sesión, 20 nov tarde-noche)
- `pipeline/cortar_video.py` validado con video sintético (frame-exacto) y con el primer **video real**
  (IMG_7889.MP4, 4K vertical): ver `pipeline/README.md`. Soporta `--rotar` y escala por lado corto.
- AssemblyAI detecta muletillas en habla real ("eh"). Prueba de disfluencies cerrada.
- Hallazgo: el raw real traía una **retoma** (intento fallido + reinicio). Se quitó usando el transcript.
  El detector de retomas pasa a ser parte del paso 2.
- Hosts añadidos al entorno: drive.google.com, drive.usercontent.google.com (descarga directa de Drive).

## Aclaraciones del usuario (20 nov, noche)
- **Los videos son del usuario, no de Charlie.** Charlie era solo el ejemplo de donde salió el pipeline.
  IMG_7889 es su raw real: graba en vertical 4K con el celular, deja retomas al inicio. El **detector
  de retomas es parte fija del editor** (paso 2), no un extra.
- **Encuadre: 9:16** con recorte centrado. Implementado en `cortar_video.py --encuadre 9:16`.
- Preview a 576p está bien por ahora.
- Limpieza de audio (`limpiar_audio.py`, 3 capas) entregada para que el usuario la evalúe de oído.

## Limpieza de audio (último estado)
`limpiar_audio.py` v2: paso-alto 85 Hz, de-pop puntual, y respiraciones detectadas **por la señal**
(planitud espectral) nunca sobre frames con voz; la v1 bajaba arranques de palabra porque los tiempos
de AssemblyAI llegan hasta 170 ms tarde. Entregado a −18 dB. Falta el veredicto de oído del usuario y
el **timestamp exacto** del "soplido" que oye, para saber si es respiración o pop.

## Audio: estado al 21 nov
- El "soplido" eran golpes de aire al mic (viento), no respiraciones. `limpiar_audio.py` v3 tiene
  de-viento dinámico (ver `pipeline/README.md`). Consejo externo incorporado: **dead cat al grabar**.
- Regla nueva: **fundido 0.1 s** de salida/entrada en cada empalme (video y audio), implementada en
  `cortar_video.py --fade`.

- **Separación por modelo**: `pipeline/separar_voz.py` (DeepFilterNet3, entorno `.venv-df`). Quita
  viento en todo el espectro sin tocar la voz. Candidato a estándar: DeepFilterNet3 → `limpiar_audio.py`.

## Pendientes del lado del usuario
Nuevos:
- Veredicto de oído entre v4 (solo filtro), DFN (solo modelo) y DFN + filtro.
- Conseguir un dead cat para el micrófono antes del próximo raw.
- **Video corto de prueba** (20–30 s, celular, con pausas largas a propósito como la nota 2). Desbloquea
  el paso 1.
- **Audio con muletillas reales** ("eh", "este", "o sea") para cerrar la prueba de `disfluencies`.

Ya pedidos, aún sin respuesta:
- Audio o video de Charlie con una frase donde baje la voz al final.
- Un raw con su versión final editada, para extraer el criterio editorial.
- Sistema operativo y GPU de la máquina de producción (define fps/preset de render y concurrencia).
- Spec de captions (fuente, tamaño, borde, color, posición, palabras por bloque).

## Reglas de trabajo que el usuario espera
- Explicar despacio y paso a paso cuando se trata de configuraciones de UI.
- Entregar archivos (audio, video) cuando se edita algo, no solo describirlo. Los adjuntos del usuario
  llegan en `/root/.claude/uploads/<id>/`; copiarlos al scratchpad antes de usarlos.
- Commitear y pushear a la rama `claude/charming-planck-lmkxqj` conforme se avanza.
- Al dar ideas: 90 % sobre cosas que el usuario no conoce, 10 % sobre lo que ya sabe.
