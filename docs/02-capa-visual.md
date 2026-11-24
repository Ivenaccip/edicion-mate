# Capa visual: quitar el verde, fondos y composición base (20 nov 2026)

Sesión de pantalla verde sobre el raw real `IMG_7889.MP4` (4K vertical, verde oscuro #1e7032, ver
`HANDOFF-pantalla-verde.md`). Alcance: capa visual. No toca cortes ni audio.

## Resultado en una frase
**Elegido por el usuario (21 nov): A, FFmpeg `chromakey` + `despill`.** Sin modelos, un solo comando de FFmpeg,
y el escritorio se conserva. El híbrido queda documentado como mejora opcional del pelo si algún día hace falta.
Lo que sigue describe la comparación completa.

**Ganador técnico de la comparación: híbrido** = llave por crominancia (misma fórmula que `chromakey` de FFmpeg) unida
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
# método elegido, por zonas: máscara una vez por set + llave
python pipeline/visual/mascara_sombras.py IMG_7889.MP4 mascara.png
pipeline/visual/quitar_verde_ffmpeg.sh IMG_7889.MP4 12 3 composicion/assets/fondo_degradado.png salida mascara.png
# solo FFmpeg (candidato A), 4K → 576 con llave a 1080, sin zonas
ffmpeg -ss 12 -t 3 -i IMG_7889.MP4 -i fondo.png -filter_complex "[0:v]transpose=2,crop=iw:iw*16/9,scale=1080:1920,format=rgba,chromakey=color=0x1e7032:similarity=0.08:blend=0.00,despill=type=green:mix=0.5:expand=0,scale=576:1024[p];[1:v]scale=576:1024[f];[f][p]overlay=format=auto,format=yuv420p" -map 0:a -c:v libx264 -preset veryfast -crf 20 -c:a aac salida_576.mp4
```

## Costos que hay que arreglar antes de producción
- `quitar_verde.py` escribe PNG por frame: 25 de los 44 s del híbrido son escritura de PNG a 1080x1920.
  Siguiente paso: entubar frames crudos a FFmpeg por stdin (`-f rawvideo -pix_fmt bgra`) y encodear VP9
  directo. Estimado: híbrido a ~6× tiempo real en 4 núcleos (un short de 45 s ≈ 4.5 min).
- A 576 de ancho de trabajo el chromakey baja a ~10 ms/frame; RVM no cambia (siempre 720x1280 internos).
- La GPU de la máquina de producción (pendiente del usuario) cambia esto: RVM en CUDA corre a > 60 fps.

## Decisiones tomadas en esta sesión
1. Llave: **chromakey+despill de FFmpeg** (decisión del usuario, 21 nov). Híbrido chromakey+RVM solo si el pelo
   lo pide; RVM solo, descartado.
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

## De qué depende "la misma calidad que el TikTok" (21 nov 2026)
Pregunta del usuario: cómo llevar el raw de Drive al nivel del TikTok de referencia. Se midió el TikTok
(`tiktok_7611273219009498375.mp4`, 576x1024, 24 fps, 374 kbps) contra el raw y contra nuestro render base.

**En píxeles el raw ya gana**: 4K frente a 576p y 374 kbps. La "calidad" que se nota es editorial. Medido:

| Capa | TikTok de referencia | Raw / render base | Qué falta |
|---|---|---|---|
| Cortes | 13 cortes duros en 44.6 s (scdet), uno cada 3.4 s | sesión de cortes (EDL) | ya está en el otro carril |
| B-roll de fondo | cambia **cada 1.9 s** (24 cambios), capturas de UI, pantallas, oficina | fondo fijo | b-roll por tema: capturas reales o UI hecha en HTML |
| Captions | bloques de 2–3 palabras, **uno cada 0.6 s** (74 bloques), palabra activa en caja azul | ninguna | generar desde `palabras.json` + EDL |
| Luminosidad del cuadro | luma media **69 %** (fondos claros/cálidos) | 11.7 % (degradado oscuro) · raw 30 % | fondos claros, no oscuros |
| Color de la cara | saturación 49 %, cálida (b* +9.7) | render base 35 % · raw 35 % | grado ligero: saturate 1.3, contrast 1.06 |
| Escala de la persona | laptop ocupa 552–575 px de 576 (sin zoom), pelo empieza al 37 % | pelo al 33 % | igual; opcional bajar 4 % |
| Tarjeta detrás | b-roll cálido con esquinas redondeadas desde ~70 % de la altura | no | hecha (v2) |
| Título de apertura | condensada mayúscula sobre fondo abstracto, acento naranja | no | plantilla de título en Hyperframes |
| Logo | no visible en los frames muestreados | no | pendiente de assets |

### v2 de la composición (`composicion/index.html`)
Aplica sobre el mismo clip de 3 s todas las capas de la tabla salvo el título: fondo claro con degradado radial,
b-roll de terminal hecho en HTML (nítido a 1080, sin descargar nada, las líneas aparecen en tiempos fijos),
tarjeta cálida redondeada con sombra de contacto, grado ligero sobre la persona, captions con las palabras reales
de AssemblyAI entre 12.0 y 15.0 s agrupadas de 2–3 y palabra activa en caja azul, y logo provisional en zona
segura. `npm run check`: 0 errores (quedan avisos de estilo). Render 1080x1920: 25.6 s para 3 s.
La composición base anterior está en `composicion/compositions/base.html`.
Láminas: `img/capa-visual/brecha_raw_a_referencia_4x.jpg` y `img/capa-visual/composicion_v2_0.8_1.7_2.95s.jpg`.

Lo que hace que v2 todavía no sea la referencia: (1) el b-roll tiene que cambiar cada ~2 s y hablar del tema
(capturas reales o UI en HTML por bloque de guion); (2) las captions necesitan la spec (fuente, tamaño, color)
y el remapeo con el EDL para todo el short; (3) título de apertura y cierre; (4) assets de marca.

## "Estática" en la esquina inferior izquierda (21 nov): causa y arreglo
**Qué era.** Encima de la laptop, a la izquierda, la tela verde está en sombra: RGB ≈ (5,40,11) frente a (31,112,50)
del verde clave. Su distancia UV al clave es 0.084–0.100, justo por encima del umbral global 0.08. Como el umbral
cae en el nivel del ruido del sensor, cada píxel entra y sale frame a frame: la zona visible oscilaba entre 57 % y
88 % con saltos de 1.6 puntos por frame. Eso se ve como estática verde.

**Por qué no basta subir el umbral.** A 0.10 ya se pierde más silla y a 0.12 desaparece la persona entera (la
sudadera negra está a 0.156). Entre el verde en sombra (≤ 0.10) y el negro (0.156) sí hay hueco, pero solo
se puede aprovechar donde no hay persona.

**Arreglo: llave por zonas.** La cámara no se mueve, así que las sombras están siempre en el mismo sitio.
`pipeline/visual/mascara_sombras.py` muestrea 16 frames del raw y marca los píxeles que en ≥ 90 % de ellos son
verdosos y están a distancia 0.065–0.14 del clave (estáticos: el spill sobre pelo o manos se mueve y queda fuera),
abre, dilata 10 px y pluma 4 px. `pipeline/visual/quitar_verde_ffmpeg.sh` corre dos `chromakey` (0.08 global y
0.13 en la máscara) y los une con `maskedmerge`. Resultado en la zona: visible 4 % (es la manga, que debe quedar),
saltos de 0.34 puntos por frame, nada de verde. Máscara de este set: `pipeline/salida/IMG_7889_mascara_sombras_1080.png`
(0.9 % del cuadro). Imágenes: `img/capa-visual/estatica_esquina_antes_despues.jpg`, `img/capa-visual/mascara_sombras_sobre_raw.jpg`.

Si cambia la posición de la cámara o de la luz, se regenera la máscara con un comando; si no, se reutiliza.
Lo mismo sirve para cualquier otra sombra fija (p. ej. la esquina derecha si algún día aparece).

## Auditor de la llave (21 nov): cuánto mover el umbral y dónde
`pipeline/visual/auditar_llave.py` convierte la "estática" en un número y una acción. Ver `HANDOFF-auditor.md`.
Sobre el clip con chromakey 0.08 global reportó exactamente la esquina (x 0–240, y 1120–1280, conmutación 10 %
por frame), midió el verde ahí (p95 0.095) y pidió 0.11 como mínimo, por zona porque el techo del negro es 0.141.
Con 0.085 global + 0.13 en la máscara: APROBADO. El global subió de 0.08 a 0.085 porque el auditor encontró una
celda al filo (necesario 0.081); la persona no cambia (sigue a 0.156 del clave).

## v3: cuerpo completo con b-roll (22 nov 2026)
`composicion/index.html`, 33.27 s. Fuentes: cuatro clips del usuario (Pexels 8721923 robots, Pexels 12309688
público vertical, Pixabay 189046 globo, Pexels 16873592 clase), bajados de Drive y pre-recortados a 1280x720
(ventana flotante) o 1080x1920 (pantalla completa) en `composicion/assets/b*.mp4`. Persona: WebM con alfa del
cuerpo entero (llave por zonas, 12 MB). Contadores en HTML (+50,000, +70, +10, 13) en la franja superior.
Tarjeta "Síguenos" como sub-composición de 27.1 s al cierre. Sin captions (van al final, con la spec).

**Render: 1294 s (21.6 min) para 33 s a 1080x1920** en 4 núcleos. Causas medidas: Chromium del contenedor sin
`HeadlessExperimental.beginFrame` (cae a modo captura), persona extraída a 998 PNG de 1080x1920, nueve
elementos de video. Plan para acelerar: `npx hyperframes browser` (Chrome propio), variante de preview a
576x1024 con WebM de persona a 576, un solo `<video>` por clip con `data-media-start`, `--start/--end` para
rendir solo el tramo cambiado, y `npx hyperframes benchmark` para medir. Capturas: `img/capa-visual/composicion_v3_capturas.jpg`.

## Por qué el render v3 salió oscuro y sin b-roll (22 nov): HDR en un clip
Síntoma: en el MP4 rendido la persona tapaba todo con un fondo azul oscuro y tinte rojizo; título, b-roll y
contadores no se veían, pero las capturas (`snapshot`) sí los mostraban. Diagnóstico por eliminación (renders de
1 s quitando capas) y registrando los comandos de FFmpeg que lanza Hyperframes: la extracción de la persona
terminaba en `colorspace=all=bt2020:iall=bt709`, es decir, Hyperframes convertía **toda** la composición a
HDR, y ese filtro no conserva el canal alfa, así que la persona salía opaca con el fondo despillado (azul oscuro)
y el filtro `saturate(1.3)` lo volvía rojizo.

Causa raíz: el clip vertical de Pexels 12309688 viene de celular en **HLG BT.2020** (`arib-std-b67`). Hyperframes
detecta un clip HDR y pasa el resto a su transferencia. Arreglo: convertir el clip a SDR bt709 al pre-recortarlo:
```
zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p
```
más `-color_primaries bt709 -color_trc bt709 -colorspace bt709`. Regla para el pipeline: **todo b-roll entra en
SDR bt709**; `ffprobe` de `color_transfer` antes de usarlo (si dice `arib-std-b67` o `smpte2084`, tonemap).
Esto también explica por qué la v2 (sin b-roll) rindió bien y la v3 no.

## Aceleración del render (22 nov)
1. **Chrome propio de Hyperframes** (`npx hyperframes browser ensure` sin las variables `PUPPETEER_EXECUTABLE_PATH`,
   `CHROME_PATH` y `CHROME_BIN` del contenedor, que apuntan al Chromium de Playwright sin `beginFrame`). Con el
   clip de 3 s: 22 s frente a 25.6 s; la ganancia grande se mide en el render largo (abajo).
2. **Variante de preview a 576x1024**: `pipeline/visual/hacer_preview.sh` genera `composicion/preview/` con el
   canvas declarado a 576x1024 (`zoom: 0.5333` sobre el root, sin tocar los px del diseño) y assets a 576
   (`composicion/assets/576/`: persona WebM con alfa reescalada, b-roll a 576 o 684x384).

### Tiempos medidos (22 nov, 4 núcleos, 33.3 s de composición)
| Render | Tiempo | Factor |
|---|---|---|
| 1080x1920, Chromium del contenedor (modo captura de pantalla) | 1294 s | 1× |
| 1080x1920, Chrome propio de Hyperframes (`beginFrame`) | **221 s** | 5.9× más rápido |
| 576x1024 declarado + assets a 576, Chrome propio | **86 s** | 15× más rápido |

Regla: rondas del auditor con `composicion/preview/` (86 s); 1080 solo para el render final. Para activar el
Chrome propio hay que quitar `PUPPETEER_EXECUTABLE_PATH`, `CHROME_PATH` y `CHROME_BIN` del entorno antes de
`npx hyperframes render` (el contenedor las fija al Chromium de Playwright, que no tiene `beginFrame`).
Detalle del preview: los `<video>` a pantalla completa necesitan tamaño explícito en px (si no, toman el
intrínseco del asset a 576 y salen a la mitad) y la sub-composición no se escala por separado (ya vive dentro
del contenedor escalado).

### Frame 0 es la miniatura
El primer render tenía persona y título entrando desde opacidad 0, y al no estar la persona se veía la tarjeta
(un fotograma desenfocado del TikTok con una chamarra). Ahora todo está visible desde el frame 0, con solo un
leve asentamiento, y la tarjeta es un bokeh cálido en CSS, sin figuras. `img/capa-visual/v3_frame0_miniatura.jpg`.

## Logo (22 nov): blanco, abajo a la derecha, dentro de la zona segura
Assets del usuario: `Fundamentos Sin BACKGROUND.png` (negro) y `logo_white_b3xyxt.png` (blanco), 840x200 con alfa,
copiados a `composicion/assets/logo_{negro,blanco}.png`. Medido en el render final: la esquina inferior derecha
(mesa) tiene luminancia 40/255 estable; la libreta, justo encima, 157. El negro desaparece sobre la mesa y solo se
lee sobre la libreta, que se mueve; el blanco se lee en la esquina todo el video. **Elegido: blanco**.
Posición: no en la esquina literal, porque los últimos ~480 px de altura y los ~130 px de la derecha los tapan los
botones y el texto de TikTok, Reels y Shorts. Primero se puso a `top: 1370px` (dentro de la zona segura); el usuario lo quiere abajo, junto al celular: queda a `right: 108px; top: 1786px` (260 px de ancho), con sombra suave, asumiendo que la interfaz de la plataforma puede taparlo.
El píldora "fundamentos.ai" de arriba a la izquierda se quitó. Imagen: `img/capa-visual/logo_analisis_esquina_y_zonas_seguras.jpg`.

## Inicio del cuerpo movido a 9.30 s (23 nov)
El usuario oyó una tos antes de "Y estamos de regreso". Medido en el raw: eventos sonoros en 8.84–9.04 s
(−22.5 dBFS, la tos) y la frase a partir de 9.56 s (−7.7 dBFS). AssemblyAI había etiquetado la tos como la
palabra "Y" (8.93–9.10), por eso el corte anterior (8.765) la dejaba dentro. Nuevo corte en 9.30 s, en el valle
entre ambos (regla del proyecto: cortar por energía, no por timestamp de palabra). EDL actualizado en
`pipeline/salida/IMG_7889.edl.json`; cuerpo de 32.742 s. Todos los tiempos de la composición se corrieron
0.535 s (`data-start`, listas de GSAP y SFX). Lección para el editor (paso 2): una "palabra" de ≤ 2 letras aislada,
15 dB por debajo de la frase siguiente, es sospechosa de ruido no verbal.

## Primera corrida del comando único (23 nov 2026)
`python pipeline/editar.py IMG_7889.MP4 --rotar ccw --hasta visual`, 4 núcleos: cortes 576 y 1080 (42 s y 125 s),
separación de voz + limpieza (213 ráfagas de viento filtradas, 7 respiraciones a −18 dB), remapeo de 96 palabras al
cuerpo, llave sobre `cuerpo_1080.mp4`, persona a 576, preview 576 con Hyperframes y auditor de llave: APROBADO.
Total ≈ 8 min (312 s hasta la llave + 176 s desde la persona 576 hasta el preview). El audio de la composición ya
es `cuerpo_limpio.wav`, no el del raw.

## Primer render final (24 nov 2026)
`final_1080.mp4`: 1080x1920, 30 fps, 32.77 s, H.264 10.5 Mbps, AAC. Composición aprobada por el usuario en preview 576:
cortes y voz por la cadena de audio (DeepFilterNet3 + limpiar_audio), llave por zonas con máscaras de sombra y
escritorio, logo en la esquina inferior izquierda (360 px), campanita de arranque, contadores a 190/58 px con
contorno, captions provisionales de 2-3 palabras sobre la tapa de la laptop (top 1360), dos whoosh, pops y click.
