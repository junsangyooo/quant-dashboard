// Shared steps for the 작동 · 모의투자·실전 · 설정 · 입장 specs (e2e build, production CSP, fixtures).
import AxeBuilder from '@axe-core/playwright';
import { expect, type Locator, type Page, type TestInfo } from '@playwright/test';

/** The 예시-값표 screen time (§0): 2026-10-07(수) 16:10 KST. */
export const AT_1610 = new Date('2026-10-07T16:10:00+09:00');

/** Console errors, page errors, CSP violations and any request that left the page. */
export async function watch(page: Page): Promise<string[]> {
  const problems: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error' && !/status of (403|404|409|500|501)/.test(msg.text())) {
      problems.push(`console: ${msg.text()}`);
    }
  });
  page.on('pageerror', (err) => problems.push(`pageerror: ${err.message}`));
  page.on('request', (req) => {
    const url = new URL(req.url());
    if (url.hostname !== '127.0.0.1') problems.push(`external: ${req.url()}`);
  });
  await page.addInitScript(() => {
    document.addEventListener('securitypolicyviolation', (e) => {
      console.error(`CSP ${e.violatedDirective} ${e.blockedURI}`);
    });
  });
  return problems;
}

/** Pin Date to the fixture's clock; timers keep running. */
export async function pinClock(page: Page, at: Date = AT_1610): Promise<void> {
  await page.clock.setFixedTime(at);
}

/**
 * A screenshot in the test's output folder. A modal state shoots the viewport only: the backdrop
 * covers the viewport, so a full-page shot would show the page below it undimmed.
 */
export async function shoot(
  page: Page,
  info: TestInfo,
  name: string,
  { fullPage = true }: { fullPage?: boolean } = {},
): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
  // No hover left over from the last click.
  await page.mouse.move(0, 0);
  // No focus ring, and from the top: a full-page shot of a scrolled page paints the sticky header
  // where the viewport was.
  await page.evaluate(() => {
    (document.activeElement as HTMLElement | null)?.blur();
    window.scrollTo({ top: 0, behavior: 'instant' });
  });
  // Let the page paint at the new scroll position before the capture (else a stale frame).
  await page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            resolve();
          });
        });
      }),
  );
  const path = info.outputPath(`${name}.${info.project.name}.png`);
  await page.screenshot({ path, fullPage });
  await info.attach(name, { path, contentType: 'image/png' });
}

export async function axe(page: Page): Promise<string[]> {
  await page.evaluate(() => document.fonts.ready);
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
    .analyze();
  return results.violations.map(
    (v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`,
  );
}

/**
 * Tab and Shift+Tab never reach the page behind an open modal dialog and keep coming back to it.
 * A native modal <dialog> lets focus step once out to the browser's own UI between its last and
 * first control (the page then reports document.body) — never onto an element behind it.
 */
export async function expectFocusTrapped(page: Page, dialog: Locator, presses = 8): Promise<void> {
  for (const key of ['Tab', 'Shift+Tab']) {
    let inside = 0;
    for (let i = 0; i < presses; i++) {
      await page.keyboard.press(key);
      const where = await dialog.evaluate((d) => {
        const active = document.activeElement;
        if (d.contains(active)) return 'dialog';
        return active === null || active === document.body ? 'browser' : 'page';
      });
      expect(where).not.toBe('page');
      if (where === 'dialog') inside++;
    }
    expect(inside).toBeGreaterThan(presses / 2);
  }
}
