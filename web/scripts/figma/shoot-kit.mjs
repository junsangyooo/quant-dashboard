// Screenshot every [data-figma-id] box of /_kit at 2x, each isolated with ?only=<id> so it
// sits on whole pixels at the page origin. Pair the PNGs with figma_tools.py export/compare.
// usage (dev server running): node scripts/figma/shoot-kit.mjs <outDir> [baseUrl] [ids,comma,separated]
import { createRequire } from 'node:module';
import { mkdirSync, writeFileSync } from 'node:fs';

const require = createRequire(new URL('../../package.json', import.meta.url));
const { chromium } = require('@playwright/test');

const out = process.argv[2];
const base = process.argv[3] ?? 'http://127.0.0.1:5180';
const only = process.argv[4] ? process.argv[4].split(',') : null;
mkdirSync(out, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width: 1520, height: 1000 },
  deviceScaleFactor: 2,
});
const logs = [];
page.on('console', (m) => {
  if (m.type() === 'error' || m.type() === 'warning') logs.push(`${m.type()}: ${m.text()}`);
});
page.on('pageerror', (e) => logs.push(`pageerror: ${e.message}`));

await page.goto(`${base}/_kit`, { waitUntil: 'networkidle' });
await page.evaluate(() => document.fonts.ready);
const fontOk = await page.evaluate(() => document.fonts.check('600 13px Pretendard'));
const ids =
  only ??
  (await page.$$eval('[data-figma-id]', (els) => els.map((e) => e.getAttribute('data-figma-id'))));
if (!only) await page.screenshot({ path: `${out}/_full.png`, fullPage: true });

const sizes = {};
for (const id of ids) {
  await page.goto(`${base}/_kit?only=${encodeURIComponent(id)}`, { waitUntil: 'networkidle' });
  await page.evaluate(() => document.fonts.ready);
  const el = page.locator(`[data-figma-id="${id}"]`).first();
  const box = await el.boundingBox();
  sizes[id] = box
    ? [box.x, box.y, Math.round(box.width * 100) / 100, Math.round(box.height * 100) / 100]
    : null;
  await el.screenshot({ path: `${out}/${id.replaceAll(':', '-')}.png` });
}
const result = { fontOk, count: ids.length, logs, sizes };
writeFileSync(`${out}.json`, JSON.stringify(result));
console.log(JSON.stringify({ fontOk, count: ids.length, logs: logs.slice(0, 10) }));
await browser.close();
