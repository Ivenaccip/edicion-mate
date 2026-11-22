#!/usr/bin/env bash
# Genera composicion/preview/: la misma composición declarada a 576x1024 (zoom CSS 576/1080) con assets a 576.
# Uso: hacer_preview.sh  (desde la raíz del repo). Luego: cd composicion/preview && npx hyperframes render -o out/preview_576.mp4
set -euo pipefail
cd "$(dirname "$0")/../../composicion"
rm -rf preview && mkdir -p preview/compositions preview/vendor preview/assets preview/out
cp vendor/* preview/vendor/
cp hyperframes.json preview/ && sed 's/"name": *"composicion"/"name": "composicion-preview"/' meta.json > preview/meta.json && cp package.json preview/
cp assets/576/* preview/assets/
# index: canvas 576x1024, el contenido sigue en px de 1080 y se escala con zoom
python3 - <<'PY'
import re
s = open('index.html').read()
s = s.replace('data-width="1080" data-height="1920"', 'data-width="576" data-height="1024"')
s = s.replace('<meta name="viewport" content="width=1080, height=1920" />', '<meta name="viewport" content="width=576, height=1024" />')
s = s.replace('html, body { width: 1080px; height: 1920px;', 'html, body { width: 576px; height: 1024px;')
s = s.replace('#root { position: relative; width: 1080px; height: 1920px;', '#root { position: relative; width: 1080px; height: 1920px; zoom: 0.533333;')
s = s.replace('data-composition-src="compositions/siguenos.html"', 'data-composition-src="compositions/siguenos.html"')
open('preview/index.html', 'w').write(s)
t = open('compositions/siguenos.html').read()
t = t.replace('data-width="1080" data-height="1920"', 'data-width="576" data-height="1024"')
t = t.replace('html, body { width: 1080px; height: 1920px;', 'html, body { width: 576px; height: 1024px;')
t = t.replace('#siguenos { position: relative; width: 1080px; height: 1920px;', '#siguenos { position: relative; width: 1080px; height: 1920px; zoom: 0.533333;')
open('preview/compositions/siguenos.html', 'w').write(t)
PY
echo "preview/ generado:"; ls preview preview/assets
