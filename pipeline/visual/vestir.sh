#!/usr/bin/env bash
# Capa visual sobre la carpeta de un raw (contrato de docs/ESTANDAR-PIPELINE-AUDIO.md).
#   vestir.sh <carpeta> --preview   # llave del cuerpo 1080 -> persona con alfa (1080 y 576), palabras remapeadas,
#                                   # assets al proyecto Hyperframes, render preview 576, auditor de llave
#   vestir.sh <carpeta> --final     # además render 1080
# Espera en <carpeta>: cuerpo_1080.mp4 (cortado con --fade 0), cuerpo_limpio.wav (audio final) o cuerpo_576.mp4,
# cuerpo_576.aplicado.json, raw.palabras.json. La máscara de sombras es por set: <carpeta>/mascara_sombras.png
# (si no existe se genera desde cuerpo_1080.mp4).
set -euo pipefail
DIR=$(cd "$1" && pwd); MODO=${2:---preview}
REPO=$(cd "$(dirname "$0")/../.." && pwd); V=$REPO/pipeline/visual; C=$REPO/composicion
. "$REPO/.venv/bin/activate"
cd "$DIR"
[ -f mascara_sombras.png ] || python "$V/mascara_sombras.py" cuerpo_1080.mp4 mascara_sombras.png --rotar no --encuadre no --frames 16 --fraccion 0.75 --dist-min 0.05 --dilatar 20 --pluma 1
# 1) llave sobre el cuerpo ya cortado (sin rotar/recortar: lo hizo cortar_video.py)
[ -f persona_1080_alfa.webm ] || { MASC_ESCRITORIO=$([ -f mascara_escritorio.png ] && echo mascara_escritorio.png || true) "$V/quitar_verde_ffmpeg.sh" --cuerpo cuerpo_1080.mp4 "$C/assets/fondo_degradado.png" persona_1080 mascara_sombras.png; }
[ -f persona_576_alfa.webm ] || ffmpeg -v error -y -c:v libvpx-vp9 -i persona_1080_alfa.webm -vf "scale=576:1024:flags=lanczos" -c:v libvpx-vp9 -pix_fmt yuva420p -auto-alt-ref 0 -b:v 0 -crf 26 -row-mt 1 -cpu-used 5 -an persona_576_alfa.webm
# 2) audio final del cuerpo: el limpio si existe, si no el del cuerpo
if [ -f cuerpo_limpio.wav ]; then ffmpeg -v error -y -i cuerpo_limpio.wav -c:a aac -ac 1 -b:a 160k voz_cuerpo.m4a; else ffmpeg -v error -y -i cuerpo_576.mp4 -vn -c:a aac -ac 1 -b:a 160k voz_cuerpo.m4a; fi
# 3) palabras en tiempo del cuerpo (solo captions)
python "$V/remapear_palabras.py" raw.palabras.json cuerpo_576.aplicado.json cuerpo.palabras.json
# 3b) captions desde las palabras remapeadas, inyectadas en la composición entre marcadores
python "$V/captions.py" cuerpo.palabras.json captions.html captions.js --fin "$(python -c "import json;print(json.load(open('cuerpo_576.aplicado.json'))['duracion_salida_s'])")"
python - "$C/index.html" captions.html captions.js <<'PY'
import re, sys
p, fh, fj = sys.argv[1:4]; s = open(p).read()
s = re.sub(r'(<!-- CAPTIONS -->\n).*?(\s*<!-- /CAPTIONS -->)', lambda m: m.group(1) + open(fh).read() + m.group(2), s, flags=re.S)
s = re.sub(r'(// CAPTIONS-TL\n).*?(\s*// /CAPTIONS-TL)', lambda m: m.group(1) + open(fj).read() + m.group(2), s, flags=re.S)
open(p, 'w').write(s); print('captions inyectadas')
PY
# 4) assets al proyecto Hyperframes (la composición es la plantilla del repo; los assets por video no van al repo)
mkdir -p "$C/assets/576"; cp persona_1080_alfa.webm "$C/assets/persona_cuerpo_alfa.webm"; cp persona_576_alfa.webm "$C/assets/576/persona_cuerpo_alfa.webm"
cp voz_cuerpo.m4a "$C/assets/voz_cuerpo.m4a"; cp voz_cuerpo.m4a "$C/assets/576/voz_cuerpo.m4a"
python - "$DIR/cuerpo_576.aplicado.json" "$C/index.html" <<'PY'
import json, re, sys
ap = json.load(open(sys.argv[1])); emp = ap.get("empalmes_en_salida_s", [])
p = sys.argv[2]; s = open(p).read()
s = re.sub(r'const EMPALMES = \[[^\]]*\];', 'const EMPALMES = ' + json.dumps([round(e, 3) for e in emp]) + ';', s)
open(p, 'w').write(s); print('empalmes en la composición:', emp)
PY
# 5) render
unset PUPPETEER_EXECUTABLE_PATH CHROME_PATH CHROME_BIN || true
"$V/hacer_preview.sh" >/dev/null
( cd "$C/preview" && rm -rf /tmp/hyperframes-extract-cache-0/hfcache-v10-* && npx -y hyperframes@0.9.72 render -o "$DIR/preview_576.mp4" --quiet 2>&1 | grep -i ' error' || true )
# 6) auditor de la llave sobre el cuerpo (ventana de 3 s en el centro)
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 cuerpo_576.mp4); INI=$(python -c "print(max(0, $DUR/2-1.5))")
python "$V/auditar_llave.py" cuerpo_1080.mp4 persona_1080_alfa.webm --rotar no --encuadre no --inicio-s "$INI" --dur-s 3 --umbral 0.085 --md pendientes_llave.md --json auditoria_llave.json || true
if [ "$MODO" = "--final" ]; then ( cd "$C" && rm -rf /tmp/hyperframes-extract-cache-0/hfcache-v10-* && npx -y hyperframes@0.9.72 render -o "$DIR/final_1080.mp4" --quiet 2>&1 | grep -i ' error' || true ); fi
ls -la "$DIR" | grep -E 'preview_576|final_1080|persona|pendientes'
