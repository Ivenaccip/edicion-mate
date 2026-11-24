# Estándar del pipeline de cortes y audio (candidato, 23 nov 2026)

Rama: `claude/charming-planck-lmkxqj` en `github.com/Ivenaccip/edicion-mate`.
Esta parte del sistema produce el **cuerpo** del short: video cortado, 9:16, con audio limpio.
La capa visual (pantalla verde, fondos, captions, Hyperframes) recibe ese cuerpo y lo viste.

## Cadena estándar (en este orden)
| # | Paso | Script | Entrada | Salida |
|---|---|---|---|---|
| 1 | Transcribir | `pipeline/transcribir.py --backend assemblyai` | `raw.mp4` o `.wav` | `raw.palabras.json` (palabras con `ini`/`fin` en s, muletillas incluidas) |
| 2 | Plan de cortes | `editor_pausas.py` (pausas, por señal) + `proponer_guion.py` (diagnóstico y guion propuesto) + `seleccionar_tomas.py` (tomas por guion o automático; bordes por señal) | audio del raw + `raw.palabras.json` (+ `guion.txt` si es a varias tomas) | `raw.edl.json` + `tomas.md` + `guion.propuesto.txt` |
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
- ~~Detector de retomas automático~~ hecho: `pipeline/seleccionar_tomas.py` (24 nov, validado con IMG_7924: 19 tomas, 3 líneas).
- Render final con audio estéreo.
- Exportador OTIO/EDL con marcadores para revisión manual en DaVinci (opcional).

## Integración con la capa visual (23 nov 2026)
Las dos capas viven en el mismo árbol: `pipeline/` (cortes y audio) y `pipeline/visual/` + `composicion/` (visual).
Comando único: `python pipeline/editar.py raw.mp4 --rotar ccw --hasta visual|final` (etapas y salidas en su docstring).

Ajuste al contrato, sin tocar los principios: el cuerpo que va a la capa visual se corta con **`--fade 0`**.
El fundido de 0.1 s por empalme lo pinta la composición sobre la capa persona (opacidad 0 y vuelta en los
`empalmes_en_salida_s` de `cuerpo.aplicado.json`), porque un fundido a negro dentro del video keyeado
aparecería como un rectángulo negro sobre el fondo. El audio conserva su fundido en `cortar_video.py`.

La capa visual añade a la carpeta del raw:
```
cuerpo.palabras.json      # palabras remapeadas al tiempo del cuerpo (pipeline/visual/remapear_palabras.py); solo captions
mascara_sombras.png       # máscara de verde en sombra, una por set
persona_1080_alfa.webm    # llave chromakey por zonas + despill + borde (quitar_verde_ffmpeg.sh --cuerpo cuerpo_1080.mp4)
persona_576_alfa.webm     # derivada de la anterior, para el preview
voz_cuerpo.m4a            # cuerpo_limpio.wav (DeepFilterNet3 + limpiar_audio) en AAC, pista de voz de la composición
preview_576.mp4           # render de composicion/preview (Hyperframes), lo que ve el auditor
pendientes_llave.md       # auditor de la llave (pipeline/visual/auditar_llave.py)
final_1080.mp4            # solo con --hasta final
```
Corrección aplicada al EDL de IMG_7889: inicio en 9.30 s (la tos quedaba dentro; AssemblyAI la etiquetó como "Y").


## Regla de corte para raws grabados a varias tomas (24 nov 2026)

Hay dos tipos de entrada y el comando único los distingue solo:

| Tipo | Cómo se reconoce (`proponer_guion.py`) | Quién decide qué se queda | Cómo se corta |
|---|---|---|---|
| **Habla continua** (IMG_7889) | menos de 2 líneas repetidas | el agrupado automático de `seleccionar_tomas.py` (retomas y apartes fuera) | sigue sin parar |
| **A varias tomas** (IMG_7924, IMG_7922) | 2 o más líneas dichas más de una vez | **una persona**, con un guion de una frase por línea | `editar.py` se detiene (código 3) hasta que exista `guion.txt` o se pase `--guion`; luego `seleccionar_tomas.py --guion` toma la toma más parecida a cada frase (difflib ≥ 0.6, empate: la última) |

Pasos para el tipo "a varias tomas":
1. `python pipeline/editar.py raw.mp4 --rotar ccw` transcribe, saca las pausas y escribe `guion.propuesto.txt` + `guion.diagnostico.json` en la carpeta del raw. Se detiene.
2. Revisar `guion.propuesto.txt`: es un borrador (última toma completa de cada línea repetida, sin charla con el
   equipo). En IMG_7922 trajo 4 líneas de más y en IMG_7924 2; se borran, se corrige el orden y se guarda como `guion.txt`.
   Si una frase se quiere cortar antes de terminar, `--terminar-en LINEA:PALABRA` (IMG_7924: `2:llegar`).
3. Volver a correr el mismo comando: corta por el guion. `tomas.md` dice qué toma se usó para cada frase y con qué parecido.

Lo que no cambia: la señal sigue decidiendo dónde cae cada corte (voz real por energía, 0.25 s de silencio por
empalme, el aire se acerca a la voz si no está callado), y las pausas acortadas del editor se aplican dentro de cada
toma. Diagnóstico sobre los tres raws: IMG_7889 continuo (1 línea repetida → automático), IMG_7924 a varias tomas
(3 líneas repetidas, 19 tomas → 3 frases), IMG_7922 a varias tomas (6 líneas repetidas, 51 tomas → 8 frases, 44.7 s).

### Tartamudeos que el transcriptor funde (24 nov 2026)
En IMG_7922 el CTA decía "Si te quieres mantener, si te quieres mantener actualizado..." y AssemblyAI lo transcribió
como una sola frase ("actualizado" de 1.1 s), tanto en el raw completo como en el segmento aislado. Por eso el
selector no lo veía. Regla: cada toma elegida se revisa **por señal** con `pipeline/tartamudeo.py`: la trayectoria
espectral (log-mel, 10 ms) de una frase que se repite reaparece con un desfase de 0.5-2.4 s; si un bloque se parece
a su copia desplazada bastante más que a cualquier otro bloque del audio (distancia/referencia < 0.60) y la
alineación se confirma, se quita exactamente una repetición cortando en el aire previo y saltando al mismo punto de
la segunda. Hasta 3 repeticiones por toma. Validado: detecta el CTA de IMG_7922 y los 3 tartamudeos conocidos de
IMG_7924; no marca ninguna de las 10 tomas limpias de ambos. Sigue sin cortar dentro de voz: el salto cae en aire.
