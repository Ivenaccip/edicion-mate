# Estándar del pipeline de cortes y audio (candidato, 23 nov 2026)

Rama: `claude/charming-planck-lmkxqj` en `github.com/Ivenaccip/edicion-mate`.
Esta parte del sistema produce el **cuerpo** del short: video cortado, 9:16, con audio limpio.
La capa visual (pantalla verde, fondos, captions, Hyperframes) recibe ese cuerpo y lo viste.

## Cadena estándar (en este orden)
| # | Paso | Script | Entrada | Salida |
|---|---|---|---|---|
| 1 | Transcribir | `pipeline/transcribir.py --backend assemblyai` | `raw.mp4` o `.wav` | `raw.palabras.json` (palabras con `ini`/`fin` en s, muletillas incluidas) |
| 2 | Plan de cortes | `prototipos/editor-pausas/editor_pausas.py` (+ retoma por transcript, hoy manual) | audio del raw | `raw.edl.json` (tramos `quitar`) |
| 3 | Cortar video | `pipeline/cortar_video.py --rotar ccw --encuadre 9:16 --fade 0.1` | `raw.mp4` + `raw.edl.json` | `cuerpo_576.mp4` (preview) o `--final` 1080x1920; `cuerpo.aplicado.json` |
| 4 | Separar voz | `.venv-df/bin/python pipeline/separar_voz.py` (DeepFilterNet3) | audio del cuerpo | `cuerpo_voz.wav` |
| 5 | Limpiar | `pipeline/limpiar_audio.py --hp-hz 100 --viento-hz 300 --viento-db 3 9 --resp-db -18` | `cuerpo_voz.wav` + `palabras.json` | `cuerpo_limpio.wav` + `cuerpo_limpio.limpieza.json`; con `--video` remuxea |
| 6 | Auditar | `prototipos/essentia-cortes/prototipo.py` (detectar + voz a ambos lados en cada empalme) + re-transcribir y diff | `cuerpo.mp4` + EDL | lista de pendientes (cero = aprobado) |

Pasos 4 y 5 son el **candidato a estándar de audio** pendiente de veredicto de oído: DeepFilterNet3 y
después el filtro dinámico de graves. Si el usuario prefiere solo uno, se quita el otro sin tocar nada más.

## Parámetros fijados
- Rotación: raws del celular llegan 4096x2160 sin bandera → `--rotar ccw`. Verificar con un fotograma.
- Encuadre: 9:16 centrado. Preview 576x1024; final 1080x1920 (`--final`, preset slow, CRF 18).
- Fundido en cada empalme interno: 0.1 s a negro, salida y entrada, video y audio. No al inicio/fin.
- Pausas: > 450 ms se acortan a 250 ms; borde inicial/final a 150 ms; corte siempre en el centro
  de la pausa medida por energía, nunca en un timestamp de palabra.
- Retoma: frase repetida al inicio → quitar el primer intento hasta el centro de la pausa previa al segundo.
- Audio: paso-alto 100 Hz; de-viento dinámico 300 Hz entre +3 y +9 dB de exceso de graves;
  respiraciones (ruido sin tono, lejos de voz) a −18 dB; de-pop/respiración nunca sobre frames con voz.
- Transcripción: AssemblyAI `universal-3-5-pro`, español, `disfluencies=True`. Whisper local solo de respaldo.

## Contrato de salida para la capa visual
Por cada raw, la capa de cortes entrega una carpeta con:
```
<nombre>/
  cuerpo_576.mp4            # preview: 576x1024, 9:16, 29.97 fps, audio limpio AAC mono 160k
  cuerpo_1080.mp4           # solo tras aprobación: 1080x1920, audio estéreo si el raw lo trae (pendiente)
  cuerpo.aplicado.json      # tramos conservados, empalmes en segundos de salida, fps, rotación, encuadre
  raw.edl.json              # decisiones de corte con razón ("acortar a 250 ms", "quitar retoma")
  raw.palabras.json         # palabras con tiempos del RAW (para captions hay que remapear con el EDL)
  cuerpo_limpio.limpieza.json  # qué se tocó en el audio y dónde
```
Regla para captions: los tiempos de `raw.palabras.json` son del raw. Para el cuerpo, a cada palabra
se le resta la suma de los tramos quitados antes de ella (están en `cuerpo.aplicado.json`).
Los tiempos por palabra tienen error de hasta ±170 ms: sirven para captions, no para cortar.

## Principios que no se negocian
1. **La señal decide dónde cortar; el transcript decide qué quitar.** Validado tres veces con datos.
2. El auditor mide solo en los empalmes del EDL, no en todo el archivo.
3. Nada que toque audio actúa sobre frames clasificados como voz.
4. Preview 576p para iterar; 1080 solo cuando el auditor aprueba.

## Entornos
- `.venv`: essentia, faster-whisper, requests, scipy, soundfile, matplotlib (numpy ≥ 2).
- `.venv-df`: torch 2.6.0 cpu + torchaudio 2.6.0 + deepfilternet + safetensors. Separado porque torch baja numpy.
- Hosts permitidos en el entorno de nube `edicion-mate`: api.assemblyai.com, huggingface.co y CDN,
  drive.google.com, drive.usercontent.google.com, download.pytorch.org, download-r2.pytorch.org.
  GitHub queda bloqueado por el proxy aunque esté en la lista; los pesos de DeepFilterNet3 salen de
  Hugging Face (`fal/DeepFilterNet3`).
- Variable: `ASSEMBLYAI_API_KEY`.

## Lo que falta en esta capa
- `pipeline/editar.py raw.mp4`: un comando que encadene 1–6 (paso 4 del handoff).
- Detector de retomas automático (hoy la retoma se marcó a mano con el transcript).
- Render final con audio estéreo.
- Exportador OTIO/EDL con marcadores para revisión manual en DaVinci (opcional).
