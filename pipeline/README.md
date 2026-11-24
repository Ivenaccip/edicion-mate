# pipeline/ — Fase 1: raw → short editado

| Script | Entrada | Salida |
|---|---|---|
| `transcribir.py` | audio/video | `*.palabras.json` (tiempos por palabra; backends `whisper` o `assemblyai`) |
| `seleccionar_tomas.py` | `raw.palabras.json` + `raw_audio.wav` + EDL de pausas | `raw.edl.json` (mejor toma por línea, retomas y apartes fuera) + `tomas.md` (plan legible) |
| `cortar_video.py` | `raw.mp4` + `raw.edl.json` | `cuerpo.mp4` (solo cortes) + `cuerpo.aplicado.json` |

```bash
. .venv/bin/activate
python pipeline/cortar_video.py raw.mp4 raw.edl.json cuerpo_576.mp4           # preview 576p
python pipeline/cortar_video.py raw.mp4 raw.edl.json cuerpo_1080.mp4 --final  # 1080p
```

## cortar_video.py: cómo corta
1. Lee los tramos `quitar` del EDL y calcula el complemento (tramos a conservar).
2. Redondea cada borde al frame más cercano. Desfase máximo registrado: 15 ms (medio frame a 30 fps).
3. Video: `trim` + `concat` en un `filter_complex`, recodificado (nunca `-c copy`).
4. Audio: corte en numpy con los **mismos** tiempos redondeados. En cada empalme, fundido de salida
   de 7.5 ms y fundido de entrada de 7.5 ms **sin solapar**. Un crossfade solapado acorta el audio
   15 ms por empalme y FFmpeg recorta el video para igualarlo (se midió: −1.35 frames con 3 empalmes).
5. `cuerpo.aplicado.json` guarda tramos conservados, empalmes en el tiempo de salida y duraciones.

## Validación (20 nov 2026, video de prueba 720x1280 30 fps con contador de frames + audio de la nota 2)
| Verificación | Resultado |
|---|---|
| Duración | 277 frames (9.233 s) vs 278 esperados: −0.59 frames, dentro de ±1 |
| Corte en el frame correcto | Por índice de frame: salida 46→orig 118, 47→172; 147→272, 148→324; 262→438, 263→446. Exacto. |
| Auditor Essentia sobre el audio del video | 0 discontinuidades, 0 clics, 0 huecos; sin voz a ningún lado de los 3 empalmes |
| Re-transcripción AssemblyAI (editado vs raw) | 25/25 palabras, mismo orden, 0 faltantes |

Imagen: `docs/img/fase1_empalmes_por_frame.png`.

**Lección:** para comprobar en qué frame cae un corte, extraer por índice (`select=eq(n\,N)`), no por
tiempo (`-ss`). La búsqueda por tiempo de FFmpeg cayó un frame tarde en los tres empalmes y
parecía un error de corte que no existía.

## Cómo fabricar el video de prueba
```bash
ffmpeg -y -f lavfi -i "testsrc2=size=720x1280:rate=30" -i nota2.wav -t 15.35 \
  -vf "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='frame %{n}':fontsize=64:fontcolor=white:box=1:boxcolor=black@0.7:x=(w-tw)/2:y=h/2-80,\
drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='%{pts\:hms}':fontsize=64:fontcolor=yellow:box=1:boxcolor=black@0.7:x=(w-tw)/2:y=h/2+20" \
  -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -c:a aac -shortest raw_prueba.mp4
```

## Siguiente paso (del handoff)
Paso 2: unir editor + transcript en un solo `plan` que escriba qué palabra va antes y después de
cada pausa en el EDL. Paso 3: captions ASS desde `palabras.json` remapeadas con el EDL. Paso 4:
`pipeline/editar.py raw.mp4` como un solo comando.

## Primer video real: IMG_7889.MP4 (20 nov 2026)
Raw de celular: 4K 4096x2160, 29.97 fps, 44.6 s, grabado en vertical **sin bandera de rotación**
(se rota con `--rotar ccw`). Descargado de Drive por HTTPS directo (679 MB; el conector de Drive no
sirve para archivos grandes porque devuelve el contenido en la respuesta).

| Paso | Resultado |
|---|---|
| AssemblyAI | 108 palabras en 4.8 s. Detectó la muletilla "eh" (disfluencies funciona en habla real). |
| Retoma | El raw empieza con un intento fallido ("...de estar, eh, ok.") y vuelve a arrancar. El editor de pausas no lo ve (no hay pausa larga). Se quitó con el transcript: del inicio al centro de la pausa entre "ok." (8.37 s) y "Y" (8.93 s) = 8.765 s. |
| Editor de pausas | 7 pausas, acortó el silencio inicial y los 2.7 s finales. Entre medio el habla es continua. |
| Corte 4K → 576p | 22 s de proceso. 33.266 s de salida vs 33.267 esperados (−0.02 frames). |
| Re-transcripción | 96/96 palabras esperadas tras el corte, mismo orden, 0 faltantes. Las 12 de la retoma ausentes a propósito. |
| Auditor | Sin empalmes internos (un solo tramo conservado). 4 discontinuidades en todo el archivo, dentro de palabras fuertes, que no coinciden con las 7 del raw: transitorios de habla con el mic de la cámara a −4.6 dBFS de pico, no cortes. **Confirma que el auditor debe medir solo en los empalmes del EDL**, no en todo el archivo. |

Archivos: `pipeline/salida/IMG_7889.edl.json`, `IMG_7889.palabras.json`, `IMG_7889_cuerpo_576.aplicado.json`.
Fotograma: `docs/img/IMG_7889_cuerpo_576_frame.jpg`.

### Lo que este video destapó para el editor (paso 2)
1. **Detector de retomas**: frase repetida casi igual al inicio → quitar el primer intento. Con
   AssemblyAI es comparar n-gramas de palabras consecutivas; el corte va al centro de la pausa
   anterior al segundo intento.
2. **Rotación**: leer la bandera `rotation` del contenedor y, si no existe, pedir confirmación.
3. **Encuadre 9:16**: el raw rotado queda 2160x4096 (≈0.53), el short es 0.5625. Falta decidir
   recorte o barras. Pendiente de la spec visual.
4. **Audio**: el preview es mono; el render final debe conservar estéreo si el raw lo trae.

## `limpiar_audio.py`: respiraciones y pops
El usuario oyó "soplidos" en IMG_7889. Medido: 9 respiraciones entre frases, varias a −10/−16 dBFS
con la voz en −23.5 dBFS promedio (casi al mismo nivel), y 13 pops breves de graves en consonantes.

Tres capas, todas suaves:
1. Paso-alto global 85 Hz (quita retumbe de aire, no toca la voz).
2. De-pop: en cada ráfaga donde los graves < 150 Hz dominan, se mezcla ~30 ms de una versión
   filtrada a 220 Hz. La consonante se conserva, el golpe desaparece.
3. Respiraciones: en cada hueco entre palabras (según AssemblyAI) con energía > piso + 6 dB, se baja
   −12 dB con fundidos de 30 ms. Nunca se silencia: a −12 dB suena natural, a silencio suena a corte.

Resultado en IMG_7889: picos de respiración de −10.3 → −15.9 dBFS (21.9 s) y −18.1 → −30.2 (27.1 s).
Las que bajaron poco (13.15 s: −0.7 dB) tienen el pico pegado al borde de la palabra, dentro del
fundido: ahí AssemblyAI pone el fin de palabra antes de tiempo y el detector no se atreve a tocarlo.
Mejora pendiente: localizar el núcleo de la respiración por energía dentro del hueco, no usar el
hueco entero.

```bash
python pipeline/limpiar_audio.py cuerpo_audio.wav cuerpo.palabras.json limpio.wav --video cuerpo.mp4 cuerpo_limpio.mp4
```

## Viento en el micrófono (21 nov 2026)
El "soplido" que oía el usuario **no eran las respiraciones**: eran golpes de aire al micrófono.
Diagnóstico por espectro (tramos de artefacto vs voz limpia de 14.7 s):
- Pops: **+15 dB entre 20–100 Hz y +12 dB entre 100–150 Hz** sobre la voz. Es un retumbe de banda
  ancha, no una resonancia fina. 83 ráfagas en 33 s con exceso > 10 dB; el de-pop v1 atrapaba 13.
- Respiraciones: 15 dB **por debajo** de la voz en casi todo el espectro; solo +1..+4 dB en 3–8 kHz.

Un contacto de audio del usuario recomendó (nota de voz, transcrita en `prototipos/editor-pausas/salida/nota3_audio_consejos.palabras.json`):
1. **Dead cat** (paraviento de pelo) en el micrófono al grabar. Es la solución de verdad: evita el
   problema en origen. Recomendación que pasa al checklist de grabación.
2. En software, un filtro notch sobre los picos de resonancia. Como el pico medido es una banda
   ancha de graves, se implementó como **filtro de graves dinámico** (capa 2 de `limpiar_audio.py`):
   por cada 10 ms se mide cuánto sobresalen los graves (<150 Hz) sobre los medios (150–2000 Hz)
   respecto a lo típico de la voz, y con esa medida se mezcla de forma continua una versión
   filtrada a 200 Hz. Un notch fijo habría tocado la fundamental de la voz (100–150 Hz) siempre.

Resultado v3 en IMG_7889: graves en los golpes −5..−13 dB, nivel total de voz casi intacto
(p. ej. "meses" 9.4 s: graves −33.2 → −45.9 dB, voz −28.7 → −32.0 dB).

## Fundido de 0.1 s en cada empalme (regla del usuario)
`cortar_video.py --fade 0.1` (por defecto): fundido a negro de salida en los últimos 100 ms del tramo
anterior y de entrada en los primeros 100 ms del siguiente, en video y audio con los mismos tiempos.
Solo en empalmes internos; no al inicio ni al final. Se omite en tramos más cortos que 0.2 s.
`--fade 0` = corte seco. Imagen: `docs/img/fase1_fade_0.1s_empalme.png`.

## Separar la voz del viento con un modelo: `separar_voz.py` (21 nov 2026)
Pregunta del usuario: "¿podrías separar el viento?". Se probaron dos separadores sobre el audio de IMG_7889:

| Método | Graves en golpe "meses" | Voz limpia (12–13 s) | Veredicto |
|---|---|---|---|
| noisereduce (sustracción espectral no estacionaria) | −31.4 → −39.4 dB | **−28.9 → −41.7 dB** | Descartado: se come 13 dB de voz |
| **DeepFilterNet3** (red de mejora de voz, CPU) | −31.4 → −38.7 dB | −28.9 → −29.1 dB | Separa viento sin tocar la voz. 33 s de audio en 0.8 s |
| filtro dinámico v4 (sin modelo) | −31.4 → −47.4 dB | −28.9 → −29.3 dB | Más graves fuera, pero solo graves |
| **DeepFilterNet3 + filtro v4** | ver tabla en consola | ≈ intacta | Candidato a estándar |

DeepFilterNet actúa en todo el espectro (también baja respiraciones 1 dB y fondo 1.2 dB); el filtro
dinámico solo en graves. Juntos cubren el viento completo.

Infra: torch rompe el entorno principal (baja numpy), por eso va en `.venv-df`. Los pesos oficiales
están en GitHub, que el proxy del entorno bloquea aunque el host esté permitido (GitHub va por otro
canal); se usa la copia Apache-2.0 de Hugging Face `fal/DeepFilterNet3` convertida a checkpoint.
Hosts añadidos: download.pytorch.org, download-r2.pytorch.org.

## Segundo video real: IMG_7924.MP4 (24 nov 2026), grabado a varias tomas
4K 4096x2160, 29.97 fps, 115.9 s, 1.76 GB, mismo set (rotar ccw). 3 líneas de guion repetidas 2, 9 y 5 veces,
con apartes al equipo y charla final. Lo que cambió en el pipeline por este video:

| Problema | Arreglo |
|---|---|
| `editar.py` llamaba mal al transcriptor (salida posicional) y al editor de pausas (le pasaba el MP4) | Transcriptor con `--salida`; el editor recibe `raw_audio.wav` y su EDL queda en `raw.pausas.edl.json`. |
| Con 8 tramos sobre 4K, `trim`+`concat` encoló miles de frames y ffmpeg murió por memoria (SIGKILL) | Con `--fade 0` el corte usa `select` en un solo paso (sin ramas). `trim`+`concat` solo si hay fundidos. |
| La retoma era manual y aquí había 19 tomas | `seleccionar_tomas.py`: tomas por reinicio de las mismas 3 palabras / fin de oración / pausa; líneas por parecido; mejor toma = completa > sin tartamudeo > más larga > la última; apartes (una toma entre dos tomas de la misma línea) fuera; charla final incompleta fuera; bordes en el valle de energía (20 ms) de la pausa que rodea la toma. Plan en `tomas.md`; `--forzar-toma LINEA:TOMA` para cambiar una elección. |
| El verde es distinto en cada grabación (este: claro, UV 101,79; IMG_7889: oscuro, UV 109,94) | `pipeline/visual/medir_verde.py` mide el clave y propone SIM / SIM_SOMBRA / TECHO en `llave.env`; `vestir.sh` lo genera si falta y lo pasa al keyer, a la máscara y al auditor. |
| Máscara y auditor medían la distancia UV en un espacio distinto al de `chromakey` (rgb24 recalculado / cv2) | `verde_util.py`: todos leen los planos U/V nativos (yuv444p) y convierten el clave con la misma matriz que `chromakey`. |

Resultado: 273 palabras → 56; 3 tramos; cuerpo 18.23 s (esperado 18.285, −1.55 frames por redondeo + 1 frame de
cola). Tomas elegidas: 8.05–11.87 s, 58.14–66.63 s, 82.55–88.48 s del raw.
