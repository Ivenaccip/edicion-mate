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
# el root queda a 576x1024 en layout (así se dimensiona el cuadro de captura) y un contenedor interno
# de 1080x1920 se escala con transform, que no cambia el layout.
s = s.replace('#root { position: relative; width: 1080px; height: 1920px;', '#root { position: relative; width: 576px; height: 1024px; overflow: hidden; }\n      #escala { position: absolute; left: 0; top: 0; width: 1080px; height: 1920px; transform: scale(0.533333); transform-origin: 0 0;')
s = re.sub(r'(<div id="root"[^>]*>)', r'\1\n      <div id="escala">', s, count=1)
s = s.replace('    </div>\n    <script>', '      </div>\n    </div>\n    <script>', 1)
s = s.replace('data-composition-src="compositions/siguenos.html"', 'data-composition-src="compositions/siguenos.html"')
open('preview/index.html', 'w').write(s)
t = open('compositions/siguenos.html').read()
t = t.replace('data-width="1080" data-height="1920"', 'data-width="576" data-height="1024"')
t = t.replace('html, body { width: 1080px; height: 1920px;', 'html, body { width: 576px; height: 1024px;')
t = t.replace('#siguenos { position: relative; width: 1080px; height: 1920px;', '#siguenos { position: relative; width: 576px; height: 1024px; overflow: hidden; }\n      #escala { position: absolute; left: 0; top: 0; width: 1080px; height: 1920px; transform: scale(0.533333); transform-origin: 0 0;')
t = re.sub(r'(<div id="siguenos"[^>]*>)', r'\1\n      <div id="escala">', t, count=1)
t = t.replace('    </div>\n    <script>', '      </div>\n    </div>\n    <script>', 1)
open('preview/compositions/siguenos.html', 'w').write(t)
PY
echo "preview/ generado:"; ls preview preview/assets
