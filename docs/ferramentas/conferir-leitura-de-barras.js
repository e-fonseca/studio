/* Confere se a câmera da contagem lê de verdade um código de barras.
 *
 * O teste do Django não consegue fazer isto: ler código de barras pede navegador com
 * câmera. Então aqui a câmera é de mentira — o Chromium aceita um arquivo de vídeo no
 * lugar dela — e o vídeo mostra a etiqueta REAL da loja (VASO GARRAFA M JUNCO, código
 * 0000000047463), nos três tamanhos em que ela aparece na prateleira.
 *
 * Foi assim que, em 21/10/2026, se descobriu que o defeito era a resolução pedida à
 * câmera e não o leitor: trocando só `width: ideal` de 1280 para 1920, a cena do meio
 * saiu de "nunca lida em quinze segundos" para "lida em 0,0 s".
 *
 * Como rodar, com o servidor de desenvolvimento no ar em 127.0.0.1:8099:
 *
 *     python3 docs/ferramentas/montar-etiqueta-falsa.py /tmp/camfalsa
 *     node docs/ferramentas/conferir-leitura-de-barras.js medio /tmp/camfalsa
 *
 * Sai zero quando leu e um quando não leu, então serve em script. As cenas são
 * `perto`, `medio` e `longe`; `longe` NÃO é lida de propósito, e é a prova de que o
 * recado da tela mandando encostar na etiqueta tem razão de existir.
 *
 * O Chromium sem tela não tem o `BarcodeDetector`, então o que se confere aqui é o
 * caminho da biblioteca — o mais fraco dos dois. Lendo por ele, lê pelo outro.
 */
const { chromium } = require('/opt/node-tools/node_modules/playwright');
const CENA = process.argv[2];
const PASTA = process.argv[3] || '/tmp/camfalsa';
(async () => {
  const b = await chromium.launch({
    executablePath: process.env.CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
    args: ['--no-sandbox', '--use-fake-ui-for-media-stream',
           '--use-fake-device-for-media-stream',
           `--use-file-for-fake-video-capture=${PASTA}/${CENA}.y4m`],
  });
  const ctx = await b.newContext({ viewport: { width: 390, height: 900 }, permissions: ['camera'] });
  await ctx.addInitScript(() => { try { const d = new Date().toISOString().slice(0,10);
    localStorage.setItem('cabana:lembretes:'+d,'1');
    localStorage.setItem('cabana:tour:/sistema/inventario/1/camera/','1'); } catch(e){} });
  const p = await ctx.newPage();
  const erros = [];
  p.on('pageerror', e => erros.push(String(e)));
  await p.goto('http://127.0.0.1:8099/sistema/entrar/', { waitUntil: 'domcontentloaded' });
  await p.fill('#id_username','edson'); await p.fill('#id_password','senha-de-teste-123');
  await p.click('button[type=submit]'); await p.waitForLoadState('domcontentloaded');
  await p.goto('http://127.0.0.1:8099/sistema/inventario/1/camera/', { waitUntil: 'networkidle' });

  const comeco = Date.now();
  let lido = '';
  while (Date.now() - comeco < 15000) {
    lido = await p.inputValue('#produto');
    if (lido) break;
    await p.waitForTimeout(150);
  }
  const estado = await p.evaluate(() => ({
    recado: (document.getElementById('camera-recado') || {}).textContent,
    qualLeitor: (document.getElementById('camera-qual-leitor') || {}).textContent,
    video: (() => { const v = document.getElementById('camera-video');
      return v ? { w: v.videoWidth, h: v.videoHeight, pronto: v.readyState } : null; })(),
    areaVisivel: !document.getElementById('area-camera').hidden,
  }));
  console.log(JSON.stringify({
    cena: CENA, lido, segundos: ((Date.now()-comeco)/1000).toFixed(1), ...estado, erros
  }, null, 1));
  await b.close();
  process.exit(lido ? 0 : 1);
})().catch(e => { console.error('ERRO', e.message); process.exit(2); });
