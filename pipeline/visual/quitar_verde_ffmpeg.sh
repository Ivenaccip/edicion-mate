#!/usr/bin/env bash
# Quita el verde con FFmpeg (método elegido): chromakey por zonas + despill, y escribe
#   1) WebM VP9 con alfa a 1080x1920 (para Hyperframes), con borde erosionado 1 px y plumado 1.1 px
#   2) MP4 576x1024 compuesto sobre un fondo, con el audio del raw (preview)
# La llave usa dos tolerancias: 0.08 en general y 0.13 dentro de la máscara de sombras
# (pipeline/visual/mascara_sombras.py), unidas con maskedmerge. Sin máscara, usa 0.08 en todo.
# Uso: quitar_verde_ffmpeg.sh raw.mp4 inicio_s dur_s fondo.png salida_base [mascara.png]
#      quitar_verde_ffmpeg.sh --cuerpo cuerpo_1080.mp4 fondo.png salida_base [mascara.png]
#        (entrada ya rotada, encuadrada y cortada por cortar_video.py: sin -ss/-t ni transpose/crop)
set -euo pipefail
if [ "$1" = "--cuerpo" ]; then
  RAW=$2; INI=0; DUR=0; FONDO=$3; OUT=$4; MASC=${5:-}; PREP="scale=1080:1920,format=rgba"; SEEK=()
else
  RAW=$1; INI=$2; DUR=$3; FONDO=$4; OUT=$5; MASC=${6:-}; PREP="transpose=2,crop=iw:iw*16/9,scale=1080:1920,format=rgba"; SEEK=(-ss "$INI" -t "$DUR")
fi
CLAVE=0x1e7032; SIM=0.085; SIM_SOMBRA=0.11
# Máscara de escritorio opcional (MASC_ESCRITORIO=ruta.png): fuerza opaco bajo la línea de la mesa, donde reflejos
# verdes (pantalla del celular, cuero) abrirían huecos. La cámara no se mueve, así que es fija por set.
MASC_ESCRITORIO=${MASC_ESCRITORIO:-}
# Borde: el chromakey con blend=0 deja el alfa binario (escalera y filo oscuro). Se erosiona 1 px (quita el filo de
# píxeles mezclados) y se pluma con gblur de 1.1 px para que el borde se integre con cualquier fondo.
BORDE="split[c][a];[a]alphaextract,erosion,gblur=sigma=1.1[a2];[c][a2]alphamerge"
DESPILL="despill=type=green:mix=0.5:expand=0,format=rgba,${BORDE},format=rgba"
if [ -n "$MASC" ]; then
  KEY="[0:v]${PREP},split=3[a][b][o];[a]chromakey=color=${CLAVE}:similarity=${SIM}:blend=0[ka];[b]chromakey=color=${CLAVE}:similarity=${SIM_SOMBRA}:blend=0[kb];[2:v]scale=1080:1920,format=rgba[m];[ka][kb][m]maskedmerge,${DESPILL}[k]"
  EXTRA=(-i "$MASC")
else
  KEY="[0:v]${PREP},split=2[a][o];[a]chromakey=color=${CLAVE}:similarity=${SIM}:blend=0,${DESPILL}[k]"
  EXTRA=()
fi
if [ -n "$MASC_ESCRITORIO" ]; then
  # donde la máscara de escritorio es blanca se toma el fotograma original (opaco); el resto, la llave
  IDX=$(( ${#EXTRA[@]} / 2 + 2 )); EXTRA+=(-i "$MASC_ESCRITORIO")
  KEY="${KEY};[${IDX}:v]scale=1080:1920,format=rgba[d];[k][o][d]maskedmerge,format=rgba[p]"
else
  KEY="${KEY};[k]null[p];[o]nullsink"
fi
# 1) WebM con alfa
ffmpeg -v error -y "${SEEK[@]}" -i "$RAW" -i "$FONDO" "${EXTRA[@]}" -filter_complex "$KEY" -map "[p]" \
  -c:v libvpx-vp9 -pix_fmt yuva420p -auto-alt-ref 0 -b:v 0 -crf 24 -row-mt 1 -cpu-used 4 -an "${OUT}_alfa.webm"
# 2) preview 576 compuesto
ffmpeg -v error -y "${SEEK[@]}" -i "$RAW" -i "$FONDO" "${EXTRA[@]}" -filter_complex "${KEY};[p]scale=576:1024:flags=lanczos[ps];[1:v]scale=576:1024[f];[f][ps]overlay=format=auto,format=yuv420p[v]" \
  -map "[v]" -map 0:a -c:v libx264 -preset veryfast -crf 20 -c:a aac -ac 1 -b:a 96k -shortest "${OUT}_576.mp4"
ls -la "${OUT}_alfa.webm" "${OUT}_576.mp4"
