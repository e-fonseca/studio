/* Mede o contraste de cada letra visível nas telas do sistema (1.43.0).
 *
 * Feito para a tela escura (docs/tela-escura.md): o sistema inteiro trocou de cor de uma
 * vez, e conferir no olho trinta e tantas telas em dois tamanhos deixa passar a letra que
 * ficou cinza escuro em cima de marrom escuro. Aqui o navegador abre cada tela, como uma
 * pessoa de verdade (com login), no computador (1600px) e no celular (390px), e para cada
 * texto visível calcula a conta do WCAG entre a cor da letra e o fundo onde ela está de
 * fato: soma as camadas meio transparentes de baixo para cima até achar uma opaca.
 *
 * Mínimos: 4,5:1 para letra comum; 3:1 para letra grande (24px, ou 18,66px em negrito) e
 * para as estrelas da reputação, que são desenho e não texto (o número de estrelas também
 * está escrito, escondido, para o leitor de tela). Procura ainda "ilhas claras": quadro
 * grande de fundo claro, sobra do tema de antes. A etiqueta de código de barras é branca
 * de propósito (o leitor precisa de preto no branco) e não conta.
 *
 * Como rodar, com o servidor de desenvolvimento no ar em 127.0.0.1:8099:
 *
 *     CABANA_SENHA='senha do usuário de teste' \
 *       node docs/ferramentas/conferir-contraste.js edson docs/ferramentas/telas-para-conferir.txt /tmp/prints
 *
 * O terceiro argumento é opcional: com ele, guarda o print de cada tela (até 5000px de
 * altura). Sai zero quando nada ficou abaixo do mínimo, um quando ficou, então serve em
 * script. O relatório completo vai para relatorio-contraste.json na pasta dos prints (ou
 * na pasta de onde se rodou).
 */
const { chromium } = require('/opt/node-tools/node_modules/playwright');
const fs = require('fs');
const path = require('path');
const BASE = process.env.CABANA_ENDERECO || 'http://127.0.0.1:8099';

function medir() {
  const DESENHO = '.estrela, .estrelas-escolha label';
  const PAPEL = '.etiqueta-produto';
  function cor(c) {
    const m = (c || '').match(/rgba?\(([^)]+)\)/); if (!m) return null;
    const p = m[1].split(/[\s,\/]+/).filter(Boolean).map(Number);
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  }
  function lum(k) { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(k.r) + 0.7152 * f(k.g) + 0.0722 * f(k.b); }
  function sobre(cima, baixo) { const a = cima.a; return { r: cima.r * a + baixo.r * (1 - a), g: cima.g * a + baixo.g * (1 - a), b: cima.b * a + baixo.b * (1 - a), a: 1 }; }
  function hex(k) { return '#' + [k.r, k.g, k.b].map((v) => Math.round(v).toString(16).padStart(2, '0')).join(''); }
  function razao(a, b) { const la = lum(a), lb = lum(b); return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05); }
  function fundo(el) {
    const camadas = [];
    for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
      const cs = getComputedStyle(e);
      const c = cor(cs.backgroundColor);
      if (c && c.a > 0) { camadas.push(c); if (c.a >= 0.999) break; }
      // Degradê ou foto por trás, sem cor sólida por cima: a conta não é confiável.
      if (cs.backgroundImage && cs.backgroundImage !== 'none') return null;
    }
    let base = { r: 255, g: 255, b: 255, a: 1 };
    for (let i = camadas.length - 1; i >= 0; i--) base = sobre(camadas[i], base);
    return base;
  }
  function nome(el) {
    let s = el.tagName.toLowerCase();
    const cl = (el.getAttribute('class') || '').trim().split(/\s+/).filter(Boolean).slice(0, 2);
    if (cl.length) s += '.' + cl.join('.');
    const pai = el.parentElement;
    if (pai) { const pc = (pai.getAttribute('class') || '').trim().split(/\s+/).filter(Boolean)[0]; s = pai.tagName.toLowerCase() + (pc ? '.' + pc : '') + ' > ' + s; }
    return s;
  }
  function visivel(el) {
    if (!el.getClientRects().length) return false;
    const r = el.getBoundingClientRect(); if (r.width < 2 || r.height < 2) return false;
    for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.visibility === 'hidden' || cs.display === 'none' || Number(cs.opacity) === 0) return false;
    }
    return true;
  }
  const falhas = [], ilhas = [];
  let conferidos = 0, sem_conta = 0;
  for (const el of document.querySelectorAll('body *')) {
    if (['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'OPTION'].includes(el.tagName)) continue;
    if (el.closest('.oculto-visualmente')) continue;
    const campo = ['INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName) && !['hidden', 'checkbox', 'radio', 'file', 'submit', 'button', 'range', 'color'].includes((el.type || '').toLowerCase());
    const temTexto = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    const cs = getComputedStyle(el);
    const fc = cor(cs.backgroundColor);
    if (fc && fc.a >= 0.9 && lum(fc) > 0.5 && !el.closest(PAPEL) && visivel(el)) {
      const r = el.getBoundingClientRect();
      if (r.width * r.height > 2500) ilhas.push({ el: nome(el), fundo: hex(fc) });
    }
    if ((!temTexto && !campo) || !visivel(el) || el.closest(':disabled, [aria-disabled="true"]') || el.closest(PAPEL)) continue;
    const tc = cor(el instanceof SVGElement ? cs.fill : cs.color);
    const f = fundo(el);
    if (!tc || !f) { sem_conta++; continue; }
    const letra = sobre(tc, f);
    const r = razao(letra, f);
    conferidos++;
    const tam = parseFloat(cs.fontSize), peso = parseInt(cs.fontWeight, 10) || 400;
    const minimo = (tam >= 24 || (tam >= 18.66 && peso >= 700) || el.matches(DESENHO)) ? 3 : 4.5;
    if (r < minimo) {
      const texto = campo ? '[campo] ' + (el.value || el.placeholder || '') : [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent.trim()).join(' ');
      falhas.push({ el: nome(el), texto: texto.slice(0, 50), letra: hex(letra), fundo: hex(f), razao: Math.round(r * 100) / 100, minimo });
    }
  }
  return { falhas, ilhas, conferidos, sem_conta, rola: document.documentElement.scrollWidth > innerWidth, altura: document.documentElement.scrollHeight };
}

(async () => {
  const [,, usuario, arquivoRotas, pasta] = process.argv;
  if (!usuario || !arquivoRotas || !process.env.CABANA_SENHA) {
    console.error('uso: CABANA_SENHA=... node conferir-contraste.js <usuario> <arquivo-de-rotas> [pasta-dos-prints]');
    process.exit(2);
  }
  const rotas = fs.readFileSync(arquivoRotas, 'utf8').split('\n').map((l) => l.trim()).filter((l) => l && !l.startsWith('#'));
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', args: ['--no-sandbox'] });
  const relatorio = [];
  let problemas = 0;
  for (const [tamanho, largura] of [['computador', 1600], ['celular', 390]]) {
    const ctx = await browser.newContext({ viewport: { width: largura, height: 900 } });
    // Sem os avisos do dia e sem o passo a passo da primeira visita, que cobrem a tela.
    const hoje = new Date().toISOString().slice(0, 10);
    await ctx.addInitScript(([h, ps]) => { try { localStorage.setItem('cabana:lembretes:' + h, '1'); for (const p of ps) localStorage.setItem('cabana:tour:' + p, '1'); } catch (e) {} }, [hoje, rotas.map((c) => c.split('?')[0])]);
    const page = await ctx.newPage();
    const erros = [];
    page.on('pageerror', (e) => erros.push(String(e)));
    await page.goto(BASE + '/sistema/entrar/');
    await page.fill('input[name=username]', usuario);
    await page.fill('input[name=password]', process.env.CABANA_SENHA);
    await Promise.all([page.waitForNavigation(), page.click('button[type=submit]')]);
    for (const rota of rotas) {
      erros.length = 0;
      const resposta = await page.goto(BASE + rota, { waitUntil: 'networkidle', timeout: 90000 });
      const r = await page.evaluate(medir);
      if (pasta) {
        await page.screenshot({ path: path.join(pasta, `${usuario}${rota.replace(/\W+/g, '_')}-${tamanho}.png`), fullPage: true, clip: { x: 0, y: 0, width: largura, height: Math.min(r.altura, 5000) } });
      }
      const status = resposta ? resposta.status() : 0;
      const ruim = r.falhas.length + r.ilhas.length + (r.rola ? 1 : 0) + erros.length + (status === 200 ? 0 : 1);
      problemas += ruim;
      relatorio.push({ rota, tamanho, status, ...r, erros: [...erros] });
      console.log(`${ruim ? 'VER ' : 'ok  '} ${tamanho.padEnd(10)} ${status} ${rota}  textos ${r.conferidos}, abaixo do mínimo ${r.falhas.length}, ilhas claras ${r.ilhas.length}${r.rola ? ', ROLA DE LADO' : ''}${erros.length ? ', ERRO NO JAVASCRIPT' : ''}`);
    }
    await ctx.close();
  }
  fs.writeFileSync(path.join(pasta || '.', 'relatorio-contraste.json'), JSON.stringify(relatorio, null, 1));
  await browser.close();
  process.exit(problemas ? 1 : 0);
})();
