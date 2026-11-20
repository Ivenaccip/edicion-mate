// Comprueba que Chrome (el mismo motor que usa Hyperframes) respeta el alfa de un WebM VP9 yuva420p.
// Carga un <video> con el WebM sobre un fondo magenta, busca t=1 s, lo dibuja en un canvas y mide
// píxeles: la zona que era verde debe ser magenta puro (fondo visible) y la cara no.
// Uso: node probar_alfa_chrome.cjs ruta.webm captura.png
const { chromium } = require('playwright');
const fs = require('node:fs');
(async () => {
  const [webm, captura] = process.argv.slice(2);
  const b64 = fs.readFileSync(webm).toString('base64');
  const html = `<!doctype html><html><body style="margin:0;background:#ff00ff;width:540px;height:960px;overflow:hidden">
  <video id="v" src="data:video/webm;base64,${b64}" muted playsinline style="width:540px;height:960px;display:block"></video>
  </body></html>`;
  const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium', args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 540, height: 960 }, deviceScaleFactor: 1 });
  await page.setContent(html);
  const res = await page.evaluate(() => new Promise((resolve) => {
    const v = document.getElementById('v');
    v.addEventListener('seeked', () => {
      const c = document.createElement('canvas'); c.width = 540; c.height = 960;
      const ctx = c.getContext('2d');
      ctx.fillStyle = '#ff00ff'; ctx.fillRect(0, 0, 540, 960);
      ctx.drawImage(v, 0, 0, 540, 960);
      const px = (x, y) => Array.from(ctx.getImageData(x, y, 1, 1).data.slice(0, 3));
      // alfa crudo del video (sin fondo): canvas limpio
      const c2 = document.createElement('canvas'); c2.width = 540; c2.height = 960;
      const x2 = c2.getContext('2d'); x2.drawImage(v, 0, 0, 540, 960);
      const alfa = (x, y) => x2.getImageData(x, y, 1, 1).data[3];
      resolve({ videoWidth: v.videoWidth, videoHeight: v.videoHeight, t: v.currentTime,
        zona_verde_rgb: px(60, 60), zona_verde_alfa: alfa(60, 60), zona_cara_rgb: px(240, 440), zona_cara_alfa: alfa(240, 440) });
    }, { once: true });
    v.addEventListener('loadedmetadata', () => { v.currentTime = 1.0; }, { once: true });
    v.load();
  }));
  await page.screenshot({ path: captura });
  await browser.close();
  const m = ([r, g, b]) => r > 240 && g < 15 && b > 240;
  res.fondo_visible_en_zona_verde = m(res.zona_verde_rgb) && res.zona_verde_alfa === 0;
  res.cara_opaca = !m(res.zona_cara_rgb) && res.zona_cara_alfa === 255;
  console.log(JSON.stringify(res));
  process.exit(res.fondo_visible_en_zona_verde && res.cara_opaca ? 0 : 1);
})();
