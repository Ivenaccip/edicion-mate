#!/usr/bin/env bash
# Convierte una secuencia RGBA (salida de quitar_verde.py) en:
#   1) WebM VP9 con alfa (yuva420p) al tamaño de la secuencia  -> para Hyperframes / Chrome
#   2) MP4 preview 576x1024 compuesto sobre un fondo, con el audio del raw desde --inicio-s
# Uso: secuencia_a_video.sh seq_dir fondo.png raw.mp4 inicio_s dur_s salida_base [fps]
set -euo pipefail
SEQ=$1; FONDO=$2; RAW=$3; INI=$4; DUR=$5; OUT=$6; FPS=${7:-30000/1001}
ffmpeg -v error -y -framerate "$FPS" -i "$SEQ/%05d.png" \
  -c:v libvpx-vp9 -pix_fmt yuva420p -auto-alt-ref 0 -b:v 0 -crf 24 -row-mt 1 -cpu-used 4 "${OUT}_alfa.webm"
ffmpeg -v error -y -framerate "$FPS" -i "$SEQ/%05d.png" -i "$FONDO" -ss "$INI" -t "$DUR" -i "$RAW" \
  -filter_complex "[1:v]scale=576:1024[f];[0:v]scale=576:1024:flags=lanczos[p];[f][p]overlay=format=auto,format=yuv420p" \
  -map 2:a -c:v libx264 -preset veryfast -crf 20 -c:a aac -ac 1 -b:a 96k -shortest "${OUT}_576.mp4"
ls -la "${OUT}_alfa.webm" "${OUT}_576.mp4"
