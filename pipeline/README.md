# pipeline/ — Fase 1: raw → short editado

| Script | Entrada | Salida |
|---|---|---|
| `transcribir.py` | audio/video | `*.palabras.json` (tiempos por palabra; backends `whisper` o `assemblyai`) |
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
