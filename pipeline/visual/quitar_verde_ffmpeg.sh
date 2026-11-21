#!/usr/bin/env bash
# Quita el verde con FFmpeg (método elegido): chromakey por zonas + despill, y escribe
#   1) WebM VP9 con alfa a 1080x1920 (para Hyperframes)
#   2) MP4 576x1024 compuesto sobre un fondo, con el audio del raw (preview)
# La llave usa dos tolerancias: 0.08 en general y 0.13 dentro de la máscara de sombras
# (pipeline/visual/mascara_sombras.py), unidas con maskedmerge. Sin máscara, usa 0.08 en todo.
# Uso: quitar_verde_ffmpeg.sh raw.mp4 inicio_s dur_s fondo.png salida_base [mascara.png]
set -euo pipefail
RAW=$1; INI=$2; DUR=$3; FONDO=$4; OUT=$5; MASC=${6:-}
CLAVE=0x1e7032; SIM=0.08; SIM_SOMBRA=0.13
PREP="transpose=2,crop=iw:iw*16/9,scale=1080:1920,format=rgba"
DESPILL="despill=type=green:mix=0.5:expand=0,format=rgba"
if [ -n "$MASC" ]; then
  KEY="[0:v]${PREP},split=2[a][b];[a]chromakey=color=${CLAVE}:similarity=${SIM}:blend=0[ka];[b]chromakey=color=${CLAVE}:similarity=${SIM_SOMBRA}:blend=0[kb];[2:v]scale=1080:1920,format=rgba[m];[ka][kb][m]maskedmerge,${DESPILL}[p]"
  EXTRA=(-i "$MASC")
else
  KEY="[0:v]${PREP},chromakey=color=${CLAVE}:similarity=${SIM}:blend=0,${DESPILL}[p]"
  EXTRA=()
fi
# 1) WebM con alfa
ffmpeg -v error -y -ss "$INI" -t "$DUR" -i "$RAW" -i "$FONDO" "${EXTRA[@]}" -filter_complex "$KEY" -map "[p]" \
  -c:v libvpx-vp9 -pix_fmt yuva420p -auto-alt-ref 0 -b:v 0 -crf 24 -row-mt 1 -cpu-used 4 -an "${OUT}_alfa.webm"
# 2) preview 576 compuesto
ffmpeg -v error -y -ss "$INI" -t "$DUR" -i "$RAW" -i "$FONDO" "${EXTRA[@]}" -filter_complex "${KEY};[p]scale=576:1024:flags=lanczos[ps];[1:v]scale=576:1024[f];[f][ps]overlay=format=auto,format=yuv420p[v]" \
  -map "[v]" -map 0:a -c:v libx264 -preset veryfast -crf 20 -c:a aac -ac 1 -b:a 96k -shortest "${OUT}_576.mp4"
ls -la "${OUT}_alfa.webm" "${OUT}_576.mp4"
