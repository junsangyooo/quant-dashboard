// Shared steps of the 기록 · 그날 · 규칙 specs: problem watch (console, CSP, network), axe, and the
// screenshots at 390×844 and 1440×900 (HDR_SHOTS overrides the folder).
import AxeBuilder from '@axe-core/playwright';
import { expect, type Page, type TestInfo } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';

const SHOTS = process.env.HDR_SHOTS ?? join('test-results', 'hdr-shots');

/** Collects CSP violations, console errors, page errors and any /api/ request that left the page. */
export async function watch(page: Page): Promise<string[]> {
  const problems: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') problems.push(`console: ${msg.text()}`);
  });
  page.on('pageerror', (err) => problems.push(`pageerror: ${err.message}`));
  page.on('request', (req) => {
    if (new URL(req.url()).pathname.startsWith('/api/')) problems.push(`network: ${req.url()}`);
  });
  await page.addInitScript(() => {
    document.addEventListener('securitypolicyviolation', (e) => {
      console.error(`CSP ${e.violatedDirective} ${e.blockedURI}`);
    });
  });
  return problems;
}

export async function settle(page: Page): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForLoadState('networkidle');
}

/**
 * Runs `fn` with the sticky header and bottom tabs in the normal flow (CSSOM only, CSP-safe):
 * what they cover depends on the scroll position, and a full-page capture would draw them
 * mid-page. Every page bottom clears the tab bar when scrolled to the end (checked at 390).
 */
async function unstuck<T>(page: Page, fn: () => Promise<T>): Promise<T> {
  await page.evaluate(() => {
    for (const el of document.querySelectorAll<HTMLElement>('header, nav')) {
      if (getComputedStyle(el).position === 'sticky') {
        el.dataset.hdrSticky = '1';
        el.style.position = 'static';
      }
    }
  });
  try {
    return await fn();
  } finally {
    await page.evaluate(() => {
      for (const el of document.querySelectorAll<HTMLElement>('[data-hdr-sticky]')) {
        el.style.position = '';
        delete el.dataset.hdrSticky;
      }
    });
  }
}

export async function axe(page: Page): Promise<void> {
  await settle(page);
  const results = await unstuck(page, () =>
    new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze(),
  );
  expect(
    results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`),
  ).toEqual([]);
}

/** Full-page screenshot; an open modal sheet is captured whole by growing the viewport to it. */
export async function shoot(page: Page, info: TestInfo, name: string): Promise<void> {
  await settle(page);
  mkdirSync(SHOTS, { recursive: true });
  const path = join(SHOTS, `${name}-${info.project.name}.png`);
  const dialog = page.locator('dialog[open]');
  if ((await dialog.count()) > 0) {
    const size = page.viewportSize();
    const height = await dialog.evaluate((d) => d.scrollHeight);
    if (size)
      await page.setViewportSize({ width: size.width, height: Math.max(size.height, height) });
    await page.screenshot({ path });
    if (size) await page.setViewportSize(size);
    return;
  }
  await unstuck(page, () => page.screenshot({ path, fullPage: true }));
}

export function isMobile(info: TestInfo): boolean {
  return info.project.name.startsWith('mobile');
}
