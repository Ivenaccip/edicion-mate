# Capa visual: quitar el verde, fondos y composición base (20 nov 2026)

Sesión de pantalla verde sobre el raw real `IMG_7889.MP4` (4K vertical, verde oscuro #1e7032, ver
`HANDOFF-pantalla-verde.md`). Alcance: capa visual. No toca cortes ni audio.

## Resultado en una frase
**Ganador provisional: híbrido** = llave por crominancia (misma fórmula que `chromakey` de FFmpeg) unida
con el matting por IA (RVM): `alfa = max(chromakey, rvm)`. La IA pone el pelo y los lentes suaves; la llave
conserva laptop, silla, libreta y celular, que la IA borra porque solo entiende "persona".

| | A: FFmpeg `chromakey`+`despill` | B: RVM (IA, ONNX CPU) | C: híbrido max(A,B) |
|---|---|---|---|
| Verde restante (peor zona) | 0.4 % | 0.3 % | 0.5 % |
| Persona perdida (peor zona) | 8.6 % (silla, reflejos verdes) | **100 %** (laptop entera, silla 75 %) | 8.2 % |
| Pelo / lentes | borde duro, escalonado | suave, natural | suave (lo pone RVM) |
| Escritorio (laptop, silla, libreta) | se conserva | **se borra** | se conserva |
| Spill verde | `despill mix=0.5 expand=0` lo quita; `expand>0` tiñe la cara de magenta | queda un filo verde en el pelo si no hay despill | despill propio |
| Costo CPU (4 núcleos), 3 s a 1080p | 31 ms/frame (numpy) · FFmpeg puro 4K→576: 12.8 s (4.3× tiempo real) | 178 ms/frame = 16 s (5.3×) | 193 ms/frame = 17.4 s (5.8×) |
| Dependencias | solo FFmpeg | onnxruntime + pesos 15 MB (HF) | ambos |

Fotogramas: `img/capa-visual/IMG_7889_t12_comparacion_antes_A_B_C.jpg`, detalle de pelo y silla en
`img/capa-visual/detalle_pelo_silla_A_B_C.jpg`, despill en `img/capa-visual/despill_mix_0_03_05_05e02_08.jpg`.

## Lo que se midió y por qué importa

### El verde oscuro rompe las intuiciones de `chromakey`
`chromakey` mide distancia **solo en el plano UV** (crominancia) y la normaliza a 0..1. El verde medido
(31,112,50) cae en UV ≈ (111, 92); el negro de la sudadera y la silla cae en (128,128): distancia 0.156.
La piel cae a ~0.25. Por eso:
- `similarity` 0.25–0.40 (valores típicos en tutoriales) **borra a la persona entera**. Se midió: 100 % perdida.
- La ventana útil es **0.08–0.10 con `blend` 0.00**. `blend` ≥ 0.03 ya se come la silla y la sudadera.
- `hsvkey` (por tono) no sirve aquí: con `similarity` < 0.4 deja verde, con ≥ 0.4 borra la persona, porque
  mide distancia en el cono HSV y el valor (V) del verde está muy cerca del de los negros.
- `colorkey` (RGB) mata el negro con `similarity` ≥ 0.20 (distancia verde→negro en RGB = 0.286) y deja verde
  con 0.15. No tiene ventana.
- Lo que sí queda fuera de cualquier llave por color: los **reflejos verdes en el cuero de la silla** y en el
  celular. Son físicamente verdes. RVM también los pierde (silla 65/255). Solución futura: máscara de
  "zona de escritorio" fija (la cámara no se mueve) donde el alfa se fuerza a 1.

### Barrido de parámetros (fotograma t = 12 s, 45 combinaciones)
Métrica en `pipeline/visual/evaluar_key.py`: alfa medio en 5 zonas de verde puro y 5 zonas de persona
(cara, sudadera, silla, laptop, pelo). Los mejores:

| Filtro | verde restante | persona perdida |
|---|---|---|
| `chromakey sim=0.08 blend=0` | 0.4 % | 8.4 % (silla 233/255) |
| `chromakey sim=0.10 blend=0` | 0.3 % | 9.1 % |
| `chromakey sim=0.06 blend=0.03` | 1.7 % | 8.3 % |
| `chromakey sim=0.08 blend=0.03` | 0.3 % | 9.3 % |
| `chromakey sim=0.10 blend=0.03` | 0.2 % | **62.6 %** |
| `hsvkey sim=0.40 blend=0.05` | 3.1 % | 87 % |

### RVM (Robust Video Matting)
- Pesos: `rvm_720x1280.onnx` (fp32, forma fija 9:16) del espejo `sentientsai/rvm-mobilenetv3` en Hugging Face
  (GitHub está bloqueado en el entorno). También está `SJTU-TES/RobustVideoMatting/rvm_mobilenetv3.pth`
  (PyTorch), pero PyTorch no se instaló: el índice CPU de PyTorch no es alcanzable y el de PyPI pesa > 1 GB.
- Corre a 720x1280 internos; el alfa se reescala al tamaño de trabajo. Estado recurrente entre frames: el
  primer frame sale peor (500 ms y bordes más gruesos); del segundo en adelante 178 ms/frame.
- Es un modelo de **personas**: borra todo lo que no es humano. Para este encuadre (laptop, silla, libreta)
  no sirve solo.
- Hyperframes trae `hyperframes remove-background` (modelo local vía onnxruntime-node). No se probó: por lo
  anterior, cualquier matting de persona va a borrar el escritorio igual.

## Formato con alfa y Chrome
- Secuencia RGBA → **WebM VP9 `yuva420p`** con `-auto-alt-ref 0` (obligatorio para que libvpx conserve el alfa).
  3 s a 1080x1920: ~0.9 MB.
- **Verificado en Chromium headless** (`pipeline/visual/probar_alfa_chrome.cjs`): el `<video>` con el WebM
  sobre fondo magenta deja ver el fondo donde había verde (alfa 0) y la cara queda opaca (alfa 255).
  Hyperframes usa el mismo motor, y el render de la composición base lo confirma.
- ProRes 4444 `.mov` queda como formato de intercambio (`-c:v prores_ks -profile:v 4444 -pix_fmt yuva444p10le`).

## Fondos de prueba (`composicion/assets/`)
1. `fondo_plano.png`: color plano #14161f (provisional, hasta tener la paleta).
2. `fondo_degradado.png`: degradado navy→morado con viñeta (el de los clips entregados).
3. `fondo_broll.png`: b-roll desenfocado (frame final del TikTok de referencia del usuario, gblur 18).

## Referencia de look: TikTok de fundamentos.ai (descargado con Apify)
`https://www.tiktok.com/@fundamentos.ai/video/7611273219009498375` (576x1024, 24 fps, 44.6 s). Fotogramas
en `img/capa-visual/referencia_tiktok_*`. Lo que se ve, y que define la composición base:
- Persona keyeada, **con su laptop y su silla** (confirma que la IA sola no sirve), en el tercio inferior.
- Detrás de la persona, una **tarjeta con esquinas redondeadas** (b-roll cálido, bokeh de oficina) desde
  ~70 % de la altura hacia abajo; arriba, pantalla completa de capturas/b-roll del tema.
- Captions: bloques de **2–3 palabras**, sans bold blanca (tipo Montserrat/Poppins), **palabra activa con
  caja azul** (#2F8FFF aprox.), centradas a ~55 % de la altura, encima del pecho (a veces pisan el pelo).
- Títulos en condensada mayúscula sobre fondo abstracto; paleta naranja/salmón (#E07B4A) con el asterisco.
- Cierre: fondo de oficina desenfocado con un robot, persona al centro.

## Composición base en Hyperframes (`composicion/`)
`index.html`: capa 0 fondo (`<img>`/`<video muted>` a 1080x1920) → capa 1 tarjeta redondeada con b-roll →
capa 2 persona (`<video>` WebM con alfa) + `<audio>` de voz aparte → capa 3 zona de captions → capa 4 zona
de logo. Todo parametrizado con variables CSS (`--captions-y`, `--logo-*`, `--tarjeta-y`, `--guias`).
GSAP está vendorizado en `composicion/vendor/` porque el render no debe depender de un CDN.
`npm run check`: 0 errores. Render 1080x1920 con `npx hyperframes@0.9.72 render -o out/x.mp4`; el preview
576 se hace escalando con FFmpeg (el render no tiene preset de 576).
Captura con guías y sin guías: `img/capa-visual/composicion_base_guias_y_limpia_t1.5s.jpg`.

## Comandos
```bash
. .venv/bin/activate && export RVM_ONNX=models/rvm_720x1280.onnx   # pesos: HF sentientsai/rvm-mobilenetv3
# secuencia RGBA (híbrido) de 3 s desde t=12, trabajando a 1080 de ancho
python pipeline/visual/quitar_verde.py IMG_7889.MP4 seq_hibrido --metodo hibrido --rotar ccw --encuadre 9:16 --ancho 1080 --inicio-s 12 --dur-s 3
# WebM con alfa + MP4 576 compuesto sobre un fondo, con la voz del raw
pipeline/visual/secuencia_a_video.sh seq_hibrido composicion/assets/fondo_degradado.png IMG_7889.MP4 12 3 salida
# comprobar que Chrome respeta el alfa
node pipeline/visual/probar_alfa_chrome.cjs salida_alfa.webm captura.png
# solo FFmpeg (candidato A), 4K → 576 con llave a 1080
ffmpeg -ss 12 -t 3 -i IMG_7889.MP4 -i fondo.png -filter_complex "[0:v]transpose=2,crop=iw:iw*16/9,scale=1080:1920,format=rgba,chromakey=color=0x1e7032:similarity=0.08:blend=0.00,despill=type=green:mix=0.5:expand=0,scale=576:1024[p];[1:v]scale=576:1024[f];[f][p]overlay=format=auto,format=yuv420p" -map 0:a -c:v libx264 -preset veryfast -crf 20 -c:a aac salida_576.mp4
```

## Costos que hay que arreglar antes de producción
- `quitar_verde.py` escribe PNG por frame: 25 de los 44 s del híbrido son escritura de PNG a 1080x1920.
  Siguiente paso: entubar frames crudos a FFmpeg por stdin (`-f rawvideo -pix_fmt bgra`) y encodear VP9
  directo. Estimado: híbrido a ~6× tiempo real en 4 núcleos (un short de 45 s ≈ 4.5 min).
- A 576 de ancho de trabajo el chromakey baja a ~10 ms/frame; RVM no cambia (siempre 720x1280 internos).
- La GPU de la máquina de producción (pendiente del usuario) cambia esto: RVM en CUDA corre a > 60 fps.

## Decisiones tomadas en esta sesión
1. Llave: híbrido chromakey+RVM. Chromakey puro es el respaldo sin modelos (pelo escalonado pero usable).
2. Parámetros del chromakey para este set: `color=0x1e7032 similarity=0.08 blend=0.00`, despill
   `mix=0.5 expand=0`, borde: erosión 1 px + pluma 1.5 px.
3. Alfa hacia Hyperframes: WebM VP9 yuva420p. ProRes 4444 solo para intercambio.
4. La voz va en `<audio>` separado del `<video>` de la persona, para que limpieza de audio y capa visual
   no se pisen.

## Pendientes
- Del usuario: spec visual (fuente, tamaño, borde, color, posición de captions, palabras por bloque),
  logo, paleta, fondos definitivos, música; y confirmar si el escritorio (laptop/silla) se queda en cuadro
  como en el TikTok de referencia.
- Máscara fija de "zona de escritorio" para que los reflejos verdes en la silla y el celular no abran huecos.
- Entubar a FFmpeg sin PNG intermedios (arriba).
- Probar el WebM en `<video>` de Hyperframes con b-roll en video (no solo imagen) de fondo.
- Captions: siguiente sesión, con la spec. La zona está reservada en la composición.
