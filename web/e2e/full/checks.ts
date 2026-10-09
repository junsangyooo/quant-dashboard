// What every screen of the full run must satisfy (real engine API, production build, production
// CSP): no console error, no failed or refused request, no CSP violation, axe 0, and no text that
// leaked from bad data ('undefined', 'NaN', 'null', '[object').
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { expect, type Page, type TestInfo } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

export interface Answer {
  method: string;
  path: string;
  status: number;
}

/** Leaked values a screen must never print. */
const LEAKS = /undefined|NaN|\bnull\b|\[object/g;

export class Checker {
  private problems: string[] = [];
  /** Refusals expected at this moment (no session yet, the deliberately wrong PIN). */
  private allowed: (answer: Answer) => boolean = () => false;
  private shots = 0;
  private readonly page: Page;
  private readonly info: TestInfo;

  private constructor(page: Page, info: TestInfo) {
    this.page = page;
    this.info = info;
  }

  static async attach(page: Page, info: TestInfo): Promise<Checker> {
    const c = new Checker(page, info);
    page.on('console', (msg) => {
      if (msg.type() !== 'error') return;
      const text = msg.text();
      // Chrome logs every 4xx/5xx fetch here too; the response listener judges those.
      if (/^Failed to load resource: the server responded with a status of \d+/.test(text)) return;
      c.problems.push(`console: ${text}`);
    });
    page.on('pageerror', (err) => c.problems.push(`pageerror: ${err.message}`));
    page.on('request', (req) => {
      if (new URL(req.url()).hostname !== '127.0.0.1') c.problems.push(`external: ${req.url()}`);
    });
    page.on('requestfailed', (req) => {
      const reason = req.failure()?.errorText ?? '';
      // A fetch the app cancelled on purpose (navigation, an unmounted query) is not a failure.
      if (reason.includes('ERR_ABORTED')) return;
      c.problems.push(`requestfailed: ${req.method()} ${req.url()} ${reason}`);
    });
    page.on('response', (res) => {
      if (res.status() < 400) return;
      const url = new URL(res.url());
      const answer = { method: res.request().method(), path: url.pathname, status: res.status() };
      if (c.allowed(answer)) return;
      c.problems.push(
        `response: ${answer.method} ${url.pathname}${url.search} ${String(answer.status)}`,
      );
    });
    await page.addInitScript(() => {
      document.addEventListener('securitypolicyviolation', (e) => {
        console.error(`CSP ${e.violatedDirective} ${e.blockedURI}`);
      });
    });
    return c;
  }

  allow(rule: (answer: Answer) => boolean): void {
    this.allowed = rule;
  }

  /** Nothing went wrong since the last call. */
  expectClean(label: string): void {
    const found = this.problems;
    this.problems = [];
    expect(found, `${label}: problems`).toEqual([]);
  }

  /** The page has loaded what it asked for and nothing is still a skeleton. */
  async settle(): Promise<void> {
    await this.page.waitForLoadState('networkidle');
    await expect(this.page.locator('[aria-busy="true"]')).toHaveCount(0);
    await this.page.evaluate(() => document.fonts.ready);
  }

  /** Every check of one screen; a screenshot when `shot` names it. */
  async screen(label: string, { shot }: { shot?: string } = {}): Promise<void> {
    await this.settle();
    const text = await this.page.locator('body').innerText();
    expect(text.match(LEAKS), `${label}: leaked text`).toBeNull();
    expect(await this.axeWholePage(), `${label}: axe`).toEqual([]);
    if (shot) await this.shoot(shot);
    this.expectClean(label);
  }

  /**
   * axe over the whole page at once. At a scroll position the sticky header and the 390 tab bar
   * lie over whatever content is under them, and target-size reads that overlap as crowding (a
   * calendar cell under the tab bar); a viewport as tall as the page shows every target clear.
   */
  private async axeWholePage(): Promise<string[]> {
    const size = this.page.viewportSize();
    // Grow the viewport to the page's height until the page stops growing with it (charts and
    // the shell re-measure after a resize), so no sticky bar lies over the content.
    for (let round = 0; size && round < 5; round++) {
      const height = await this.page.evaluate(() => document.documentElement.scrollHeight);
      const current = this.page.viewportSize()?.height ?? size.height;
      if (height <= current) break;
      await this.page.setViewportSize({ width: size.width, height });
      await this.page.evaluate(
        () =>
          new Promise<void>((resolve) => {
            let last = -1;
            let still = 0;
            const tick = () => {
              const h = document.documentElement.scrollHeight;
              still = h === last ? still + 1 : 0;
              last = h;
              if (still >= 3) resolve();
              else requestAnimationFrame(tick);
            };
            requestAnimationFrame(tick);
          }),
      );
    }
    try {
      const results = await new AxeBuilder({ page: this.page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
        .analyze();
      return results.violations.flatMap((v) =>
        v.nodes.map((n) => {
          const near = [...n.any, ...n.all, ...n.none]
            .flatMap((c) => c.relatedNodes ?? [])
            .map((r) => r.target.join(' '));
          return `${v.id}: ${n.target.join(' ')}${near.length ? ` (near ${near.join(', ')})` : ''}`;
        }),
      );
    } finally {
      if (size) await this.page.setViewportSize(size);
    }
  }

  /** Full-page screenshot in test-results/full-shots/<project>/, numbered in visiting order. */
  async shoot(name: string): Promise<void> {
    const dir = join('test-results', 'full-shots', this.info.project.name);
    mkdirSync(dir, { recursive: true });
    this.shots += 1;
    await this.page.mouse.move(0, 0);
    await this.page.evaluate(() => {
      (document.activeElement as HTMLElement | null)?.blur();
      window.scrollTo({ top: 0, behavior: 'instant' });
    });
    const file = join(dir, `${String(this.shots).padStart(2, '0')}-${name}.png`);
    await this.page.screenshot({ path: file, fullPage: true });
  }
}

/** Same-origin links on the page (path, query and hash as written). */
export async function linksOn(page: Page): Promise<string[]> {
  const hrefs = await page
    .locator('a[href^="/"]')
    .evaluateAll((anchors) => anchors.map((a) => a.getAttribute('href') ?? ''));
  return hrefs.filter((h) => h !== '' && !h.startsWith('/api'));
}
