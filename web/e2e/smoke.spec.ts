import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

// Every page answers from a fixture bundle (src/fixtures/bundles/<state id>.ts): no server.
const HOME = '/?fixture=home.paper';

/** Collects CSP violations, console errors and any /api/ request that left the page. */
async function watch(page: Page) {
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

test('home renders the shell under the production CSP', async ({ page, isMobile }) => {
  const problems = await watch(page);
  const response = await page.goto(HOME);
  expect(response?.headers()['content-security-policy']).toContain("script-src 'self'");

  const header = page.getByRole('banner');
  await expect(header.getByText('quant', { exact: true })).toBeVisible();
  await expect(header.getByRole('link', { name: '모의투자' })).toHaveAttribute('href', '/mode');
  await expect(header.getByRole('link', { name: '정상 · 08:30 확인' })).toHaveAttribute(
    'href',
    '/health',
  );
  await expect(header.getByRole('link', { name: '설정' })).toHaveAttribute('href', '/account');

  // Self-hosted Pretendard is in use.
  await page.evaluate(() => document.fonts.ready);
  expect(await page.evaluate(() => document.fonts.check('600 13px Pretendard', '모의투자'))).toBe(
    true,
  );

  const current = page.getByRole('link', { name: '자산', exact: true }).filter({ visible: true });
  await expect(current).toHaveAttribute('aria-current', 'page');

  if (isMobile) {
    // 390: fixed 56px header, 4 bottom tabs pinned to the viewport bottom.
    expect((await header.boundingBox())?.height).toBe(56);
    const tabs = page.getByRole('navigation').filter({ has: page.locator('svg') });
    await expect(tabs.getByRole('link')).toHaveCount(4);
    const box = await tabs.boundingBox();
    expect(box?.height).toBe(64);
    expect((box?.y ?? 0) + (box?.height ?? 0)).toBe(844);
  } else {
    // 1440: 64px header, centred tabs inside a 1200 column, no bottom bar.
    expect((await header.boundingBox())?.height).toBe(64);
    const tabs = header.getByRole('navigation');
    await expect(tabs).toBeVisible();
    const t = await tabs.boundingBox();
    expect(Math.round((t?.x ?? 0) + (t?.width ?? 0) / 2)).toBe(720);
    await expect(page.getByRole('navigation').filter({ has: page.locator('svg') })).toHaveCount(0);
  }

  expect(problems).toEqual([]);
});

test('skip link is the first stop and jumps to main', async ({ page }) => {
  await page.goto(HOME);
  await expect(page.getByRole('banner').getByRole('link', { name: '모의투자' })).toBeVisible();
  await page.keyboard.press('Tab');
  const skip = page.getByRole('link', { name: '본문으로 건너뛰기' });
  await expect(skip).toBeFocused();
  await expect(skip).toBeInViewport();
  await page.keyboard.press('Enter');
  await expect(page.locator('#main')).toBeFocused();
});

test('sub-pages drop the bottom tabs and show ‹ title', async ({ page }) => {
  await page.goto('/health?fixture=home.paper');
  await expect(page.getByRole('heading', { level: 1, name: '작동' })).toBeVisible();
  await expect(page.getByRole('link', { name: '뒤로' })).toHaveAttribute('href', '/');
  await expect(page.getByRole('navigation').filter({ has: page.locator('svg') })).toHaveCount(0);
});

test('home.first-day loads from its bundle with no network', async ({ page }) => {
  const problems = await watch(page);
  await page.goto('/?fixture=home.first-day');
  const header = page.getByRole('banner');
  await expect(header.getByRole('link', { name: '모의투자' })).toBeVisible();
  await expect(header.getByRole('link', { name: '정상 · 08:30 확인' })).toBeVisible();
  expect(problems).toEqual([]);
});

for (const path of [HOME, '/health?fixture=home.paper', '/pin']) {
  test(`no axe violations on ${path}`, async ({ page }) => {
    await page.goto(path);
    if (path !== '/pin') {
      await expect(page.getByRole('banner').getByRole('link', { name: '모의투자' })).toBeVisible();
    }
    await page.evaluate(() => document.fonts.ready);
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
      .analyze();
    expect(results.violations.map((v) => `${v.id}: ${v.nodes.length}`)).toEqual([]);
  });
}
