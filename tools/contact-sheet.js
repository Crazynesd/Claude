#!/usr/bin/env node
/*
 * contact-sheet.js — se hele siden som ÉN ting, ikke som N folds.
 *
 *   node tools/contact-sheet.js <url> [--sel "<css>"] [--out <dir>] [--only mobile|desktop]
 *
 * Skyder hver fold OG hver overgang (viewport centreret på sømmen), på mobil og desktop,
 * og samler det i ét kontaktark du åbner i browseren.
 *
 * Pointen: du kan ikke SE diskontinuitet ved at scrolle — du oplever den over tid og
 * hjernen udglatter den. Side om side afslører den sig på et sekund.
 *
 * Rapporterer også:
 *   - fold-højder (rytme: er tempoet bevidst eller tilfældigt?)
 *   - sømfarver (fold N's bund vs. fold N+1's top — ens = handoff, forskellig = hård kant)
 *
 * Mekanisk lane: ingen model, ingen ændringer på siden. Kun læsning.
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const VIEWPORTS = {
  mobile: { width: 390, height: 844, deviceScaleFactor: 2, isMobile: true },
  desktop: { width: 1440, height: 900, deviceScaleFactor: 1 },
};

// Fallback-kæde: vi ved ikke hvordan siden er markeret op, så vi prøver det mest
// specifikke først og falder tilbage til "de direkte børn af den største wrapper".
const DEFAULT_SELECTORS = [
  '.pl-wrap > section', '.pl-wrap > div',
  'main > section', 'main > div',
  'body > section',
  '[id^="shopify-section"]',
];

/* Finder et Chromium der faktisk findes på maskinen, uanset hvilket build
 * den installerede playwright-version tilfældigvis forventer. */
function detectChrome() {
  const roots = [process.env.PLAYWRIGHT_BROWSERS_PATH, '/opt/pw-browsers'].filter(Boolean);
  for (const root of roots) {
    if (!fs.existsSync(root)) continue;
    const dirs = fs.readdirSync(root)
      .filter(d => d.startsWith('chromium-'))
      .sort().reverse();
    for (const d of dirs) {
      const p = path.join(root, d, 'chrome-linux', 'chrome');
      if (fs.existsSync(p)) return p;
    }
  }
  return null;
}

function args() {
  const a = process.argv.slice(2);
  const url = a.find(x => !x.startsWith('--'));
  const get = k => { const i = a.indexOf(`--${k}`); return i === -1 ? null : a[i + 1]; };
  if (!url) {
    console.error('brug: node tools/contact-sheet.js <url> [--sel "<css>"] [--out <dir>] [--only mobile|desktop]');
    process.exit(1);
  }
  return { url, sel: get('sel'), out: get('out') || 'contact-sheet', only: get('only') };
}

/* Scroll hele siden igennem så IntersectionObserver-reveals (.pl-reveal o.l.) faktisk
 * fyrer. Uden det her skyder man tomme folds og tror designet er i stykker. */
async function settle(page) {
  await page.evaluate(async () => {
    const h = document.body.scrollHeight;
    for (let y = 0; y < h; y += Math.round(innerHeight * 0.6)) {
      scrollTo(0, y);
      await new Promise(r => setTimeout(r, 90));
    }
    scrollTo(0, h);
    await new Promise(r => setTimeout(r, 400));
    scrollTo(0, 0);
    await new Promise(r => setTimeout(r, 400));
  });
  await page.waitForTimeout(600);
}

async function findFolds(page, sel) {
  return page.evaluate(({ sel, defaults }) => {
    // Effektiv baggrundsfarve: gennemsigtige elementer arver visuelt fra forælderen.
    const bgOf = el => {
      let n = el;
      while (n && n !== document.documentElement) {
        const c = getComputedStyle(n).backgroundColor;
        if (c && !/rgba\(0, 0, 0, 0\)|transparent/.test(c)) return c;
        n = n.parentElement;
      }
      return getComputedStyle(document.body).backgroundColor || 'rgb(255, 255, 255)';
    };

    const candidates = sel ? [sel] : defaults;
    let best = [];
    for (const s of candidates) {
      const els = [...document.querySelectorAll(s)]
        // Bort med usynlige og med bittesmå bånd (topbars, dividers) — de er ikke folds.
        .filter(el => {
          const r = el.getBoundingClientRect();
          return r.height > innerHeight * 0.25 && getComputedStyle(el).display !== 'none';
        });
      if (els.length > best.length) best = els;
      if (best.length >= 3) break;
    }

    const top = el => el.getBoundingClientRect().top + scrollY;
    return best.map((el, i) => {
      const r = el.getBoundingClientRect();
      return {
        i: i + 1,
        tag: el.tagName.toLowerCase(),
        id: el.id || el.className?.toString().split(' ')[0] || '',
        y: Math.round(top(el)),
        h: Math.round(r.height),
        bgTop: bgOf(el),
        // Bunden af folden: den sidste synlige efterkommer bestemmer hvad øjet ser ved sømmen.
        bgBottom: bgOf([...el.querySelectorAll('*')].filter(c => c.getBoundingClientRect().height > 8).pop() || el),
      };
    });
  }, { sel, defaults: DEFAULT_SELECTORS });
}

async function shoot(page, dir, name, y, h, pageW) {
  const full = await page.evaluate(() => document.body.scrollHeight);
  const clip = {
    x: 0, width: pageW,
    y: Math.max(0, Math.round(y)),
    height: Math.max(1, Math.min(Math.round(h), full - Math.max(0, y))),
  };
  if (clip.height < 2) return null;
  const file = path.join(dir, `${name}.png`);
  await page.screenshot({ path: file, fullPage: true, clip });
  return path.basename(file);
}

async function run(url, vpName, vp, outRoot, sel) {
  const dir = path.join(outRoot, vpName);
  fs.mkdirSync(dir, { recursive: true });

  // Miljøet har et forudinstalleret Chromium der ikke nødvendigvis matcher playwright-
  // versionens forventede build. CHROME_PATH vinder; ellers auto-detektér.
  const exe = process.env.CHROME_PATH || detectChrome();
  const proxy = process.env.HTTPS_PROXY || process.env.https_proxy;
  const browser = await chromium.launch({
    args: ['--hide-scrollbars'],
    ...(exe ? { executablePath: exe } : {}),
    ...(proxy ? { proxy: { server: proxy, bypass: process.env.NO_PROXY || '' } } : {}),
  });
  const ctx = await browser.newContext({
    // Proxy'er med egen CA terminerer TLS; ellers fejler hver goto på certifikatet.
    ignoreHTTPSErrors: !!proxy,
    viewport: { width: vp.width, height: vp.height },
    deviceScaleFactor: vp.deviceScaleFactor,
    isMobile: !!vp.isMobile,
    hasTouch: !!vp.isMobile,
    // Motion slås fra: vi vil fotografere designet, ikke fange animationer halvvejs.
    reducedMotion: 'reduce',
  });
  const page = await ctx.newPage();

  await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
  await settle(page);

  const folds = await findFolds(page, sel);
  if (folds.length < 2) {
    await browser.close();
    return { vpName, error: `fandt kun ${folds.length} fold(s) — angiv selector med --sel "<css>"` };
  }

  const shots = [];
  for (const f of folds) {
    const file = await shoot(page, dir, `fold-${String(f.i).padStart(2, '0')}`, f.y, f.h, vp.width);
    shots.push({ kind: 'fold', ...f, file });
  }

  // Sømmene: viewport centreret på grænsen, så begge sider er i samme billede.
  const seams = [];
  for (let i = 0; i < folds.length - 1; i++) {
    const a = folds[i], b = folds[i + 1];
    const boundary = b.y;
    const file = await shoot(page, dir, `seam-${String(i + 1).padStart(2, '0')}`,
      boundary - vp.height / 2, vp.height, vp.width);
    seams.push({
      kind: 'seam', i: i + 1, from: a.i, to: b.i, file,
      above: a.bgBottom, below: b.bgTop,
      hardCut: a.bgBottom !== b.bgTop,
    });
  }

  await browser.close();
  return { vpName, vp, folds: shots, seams };
}

function html(url, results) {
  const card = (r, s) => {
    if (s.kind === 'fold') {
      const vh = (s.h / r.vp.height).toFixed(2);
      return `<figure class="c fold">
        <img src="${r.vpName}/${s.file}" loading="lazy">
        <figcaption><b>Fold ${s.i}</b> <span class="m">${s.id || s.tag} · ${s.h}px · ${vh}×vh</span></figcaption>
      </figure>`;
    }
    return `<figure class="c seam ${s.hardCut ? 'bad' : 'ok'}">
      <div class="wrap"><img src="${r.vpName}/${s.file}" loading="lazy"><span class="line"></span></div>
      <figcaption><b>Søm ${s.from}→${s.to}</b>
        <span class="m">${s.hardCut ? '⚠ hård kant' : '✓ farve-handoff'}</span>
        <span class="sw" style="background:${s.above}"></span><span class="sw" style="background:${s.below}"></span>
      </figcaption>
    </figure>`;
  };

  const section = r => {
    if (r.error) return `<h2>${r.vpName}</h2><p class="err">${r.error}</p>`;
    // Flettet rækkefølge: fold 1, søm 1, fold 2, søm 2 … — læses som siden læses.
    const seq = [];
    r.folds.forEach((f, i) => { seq.push(f); if (r.seams[i]) seq.push(r.seams[i]); });
    const hs = r.folds.map(f => (f.h / r.vp.height).toFixed(2));
    const cuts = r.seams.filter(s => s.hardCut).length;
    return `<h2>${r.vpName} <span class="m">${r.vp.width}×${r.vp.height}</span></h2>
      <p class="sum">${r.folds.length} folds · ${r.seams.length} sømme ·
        <b class="${cuts ? 'bad-t' : 'ok-t'}">${cuts} hårde kanter</b><br>
        <span class="m">Rytme (fold-højde i vh): ${hs.join(' · ')}</span></p>
      <div class="grid">${seq.map(s => card(r, s)).join('')}</div>`;
  };

  return `<!doctype html><meta charset="utf-8"><title>Kontaktark</title>
<style>
 body{font:14px/1.5 -apple-system,system-ui,sans-serif;margin:0;padding:32px;background:#11131a;color:#e8e8ea}
 h1{font-size:18px;margin:0 0 4px} h2{font-size:15px;margin:40px 0 8px;text-transform:uppercase;letter-spacing:.1em}
 .m{opacity:.5;font-weight:400} .sum{margin:0 0 20px}
 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:20px;align-items:start}
 .c{margin:0;background:#1a1d26;border-radius:6px;overflow:hidden;border:1px solid #262a36}
 .c img{width:100%;display:block}
 .seam{border-color:#3a3f52} .seam.bad{border-color:#c0483c} .seam.ok{border-color:#3e8f5f}
 .wrap{position:relative}
 .line{position:absolute;left:0;right:0;top:50%;height:1px;background:rgba(255,0,80,.9);box-shadow:0 0 0 1px rgba(0,0,0,.4)}
 figcaption{padding:8px 10px;font-size:12px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
 .sw{width:14px;height:14px;border-radius:3px;border:1px solid rgba(255,255,255,.25)}
 .bad-t{color:#ff8b7e} .ok-t{color:#6fd39a} .err{color:#ff8b7e}
 a{color:#8ab4ff}
</style>
<h1>Kontaktark</h1>
<p class="m"><a href="${url}">${url}</a> · rød linje = sømmen mellem to folds</p>
${results.map(section).join('')}`;
}

(async () => {
  const { url, sel, out, only } = args();
  fs.mkdirSync(out, { recursive: true });

  const names = only ? [only] : Object.keys(VIEWPORTS);
  const results = [];
  for (const n of names) {
    process.stdout.write(`skyder ${n}… `);
    const r = await run(url, n, VIEWPORTS[n], out, sel);
    results.push(r);
    console.log(r.error ? `FEJL: ${r.error}` : `${r.folds.length} folds, ${r.seams.length} sømme`);
    if (!r.error) {
      r.seams.filter(s => s.hardCut).forEach(s =>
        console.log(`  ⚠ hård kant ved søm ${s.from}→${s.to}: ${s.above} → ${s.below}`));
    }
  }

  const index = path.join(out, 'index.html');
  fs.writeFileSync(index, html(url, results));
  console.log(`\nkontaktark: ${path.resolve(index)}`);
})().catch(e => { console.error(e.message); process.exit(1); });
