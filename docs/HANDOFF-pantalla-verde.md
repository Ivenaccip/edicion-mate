# Handoff — sesión de recursos visuales de pantalla verde

> **Estado (20 nov 2026, noche):** puntos 1–4 hechos y documentados en `docs/02-capa-visual.md`
> (comparación A/B/C, WebM con alfa verificado en Chrome, 3 fondos de prueba, composición base en
> `composicion/`). Pendiente: spec visual y assets del usuario, captions, máscara fija del escritorio.

## Contexto en 5 líneas
Proyecto `edicion-mate`: pipeline de edición automática de shorts **del usuario** (graba en vertical 4K
con celular sobre pantalla verde). Charlie Sebastian fue solo el ejemplo de donde salió el diseño.
Leer antes: `docs/00-analisis-y-fases.md`, `docs/01-decisiones-tecnicas.md`, `docs/HANDOFF.md`
(estado general) y `pipeline/README.md` (lo que ya funciona). Esta sesión NO toca cortes ni audio:
trabaja la **capa visual**: quitar el verde, fondos, composición y recursos gráficos.

## Decisiones ya tomadas (no reabrir)
- Composición y motion graphics: **Hyperframes** (HTML + CSS + GSAP, Apache 2.0). Cortes y concat: FFmpeg.
- Encuadre final: **9:16**, recorte centrado. Preview a 576x1024, final a 1080x1920.
- Orden del pipeline: `cortar_video.py` (EDL → cuerpo) → **capa visual (esta sesión)** → captions → render 7 CTAs.
- El preview para el auditor es 576p; la calidad final se renderiza solo tras aprobación.

## El raw de referencia: IMG_7889.MP4
| Dato | Valor |
|---|---|
| Origen | Drive, 679 MB: `https://drive.google.com/file/d/1l4_VLVfkUtzMi6Zy-rJANz1kqRtZRrP1/view` |
| Descarga | `curl -L -o IMG_7889.MP4 "https://drive.usercontent.google.com/download?id=1l4_VLVfkUtzMi6Zy-rJANz1kqRtZRrP1&export=download&confirm=t"` (hosts ya permitidos en el entorno) |
| Formato | H.264 4096x2160, 29.97 fps, 44.6 s, AAC estéreo 48 kHz, bt709 |
| Orientación | Grabado en vertical **sin bandera de rotación**: rotar 90° antihorario (`transpose=2`) → 2160x4096 |
| Recorte 9:16 | Tras rotar: `crop=iw:iw*16/9` → 2160x3840, centrado |
| Fotograma de referencia | `docs/img/IMG_7889_referencia_1080x1920.jpg` (ya rotado y recortado) |

### El verde, medido en el fotograma (t = 12 s)
| Zona | RGB | Tono / Sat / Luz |
|---|---|---|
| arriba-izquierda | (25,108,44) | H 133° S 62 % L 26 % |
| arriba-derecha | (43,124,65) | H 136° S 48 % L 33 % |
| centro-arriba | (32,117,52) | H 134° S 57 % L 29 % |
| lado izquierdo medio | (16,85,30) | H 132° S 68 % L 20 % |
| lado derecho medio | (37,125,61) | H 136° S 54 % L 32 % |
| **promedio** | **(31,112,50) = #1e7032** | H ≈ 134° |

Lo que esto implica para el key:
- El verde es **oscuro y poco saturado** (L 20–33 %), no el verde brillante ideal. La llave por tono
  (hue ≈ 134° ±8°) es más robusta que la llave por color RGB.
- **Iluminación desigual**: el lado izquierdo está 40 niveles más oscuro en G que el derecho. Un
  `chromakey` con similitud única va a dejar restos a un lado o comerse sombras al otro. Hace falta
  tolerancia por zona o un matting que no dependa del color.
- Desviación por zona ±2–9: el fondo es liso (tela/panel sin arrugas visibles en esa zona).
- Esperar **spill verde** en lentes, pelo y bordes de la sudadera negra.

### Elementos en cuadro (ver fotograma)
Persona sentada, sudadera negra, lentes. Silla gamer negra con logotipo. Laptop ROG abierta con
stickers, libreta, celular sobre la mesa. Todo ocupa el tercio inferior-centro. Hay verde a ambos
lados y arriba.

## Qué construir en esta sesión
1. **Quitar el verde** con dos candidatos y comparar en el mismo fotograma y en un clip de 3 s:
   - A) FFmpeg: `chromakey` (o `colorkey`) + `despill` + `alphamerge`; ajustar similarity/blend por
     el verde medido. Rápido, sin modelos. Probar también `hsvkey` por tono.
   - B) Matting por IA que no depende del verde: Robust Video Matting (RVM, PyTorch, MIT) o MODNet.
     Más limpio en pelo y lentes; necesita descargar pesos (GitHub/HF permitidos: huggingface.co y
     sus CDN ya están en la lista; GitHub releases puede requerir añadir `github.com` y
     `objects.githubusercontent.com`).
   Criterio: bordes de pelo y lentes, spill, costo por segundo en CPU (4 núcleos, sin GPU aquí).
2. **Formato con alfa** para pasar a Hyperframes: WebM VP9 con `-pix_fmt yuva420p` (Chrome lo
   reproduce con transparencia en `<video>`) o ProRes 4444 `.mov` para intercambio. Verificar que
   Hyperframes/Chrome headless respeta el alfa.
3. **Fondos**: definir 2–3 fondos de prueba (color plano de marca, degradado, imagen/video de b-roll
   desenfocado) y compararlos con la persona keyeada a 576p.
4. **Composición base en Hyperframes**: proyecto con capa fondo + capa persona + zona reservada para
   captions (tercio inferior) + zona para logo. Sin captions todavía (la spec no existe).
5. **Entregar**: un preview 576p de IMG_7889 con el verde quitado y un fondo, más el fotograma 1080
   antes/después, y documentar en `pipeline/README.md` o `docs/02-capa-visual.md`.

## Entorno (contenedor nuevo cada sesión)
```bash
apt-get update -q && apt-get install -y -q espeak-ng
python3 -m venv .venv && . .venv/bin/activate
pip install -r prototipos/essentia-cortes/requirements.txt faster-whisper requests scipy
node --version   # Hyperframes pide Node >= 22; instalar con: npx hyperframes init (ver hyperframes.heygen.com)
```
Variables/hosts ya en el entorno `edicion-mate`: `ASSEMBLYAI_API_KEY`, api.assemblyai.com, huggingface.co
y CDN, drive.google.com, drive.usercontent.google.com.

## Pendientes del lado del usuario (pedir al inicio)
- **Spec visual**: fuente, tamaño, borde, color y posición de captions; palabras por bloque.
- **Assets de marca**: logo, paleta, fondo(s) que quiere usar, música si aplica.
- Si tiene un video de referencia ya editado con el look que busca, es lo más valioso.

## Reglas de trabajo que el usuario espera
- Explicar despacio y paso a paso cuando se trata de configuraciones de UI.
- Entregar archivos (fotogramas, video) cuando se produce algo visual, no solo describirlo.
- Commitear y pushear a `claude/charming-planck-lmkxqj` conforme se avanza (o a la rama que la sesión reciba).
- Al dar ideas: 90 % sobre cosas que el usuario no conoce.
