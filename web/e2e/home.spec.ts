// SCR-HOME in the browser (e2e build + production CSP): the 완료 조건 that need layout, focus,
// timing or navigation, axe on every state, and a screenshot of every state at 390×844 and
// 1440×900 (attached to the report and written under test-results/).
import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page, type TestInfo } from '@playwright/test';

const STATES = [
  'home.paper',
  'home.live',
  'home.live-first',
  'home.withdraw',
  'home.stale',
  'home.partial',
  'home.offline',
  'home.other-device',
  'home.first-day',
  'home.empty',
  'home.holiday',
  'home.loading',
  'home.check-failed',
  'home.live-todo',
  'home.push-undelivered',
] as const;

/** Console errors, page errors and CSP violations while the page runs. */
async function watch(page: Page) {
  const problems: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') problems.push(`console: ${msg.text()}`);
  });
  page.on('pageerror', (err) => problems.push(`pageerror: ${err.message}`));
  await page.addInitScript(() => {
    document.addEventListener('securitypolicyviolation', (e) => {
      console.error(`CSP ${e.violatedDirective} ${e.blockedURI}`);
    });
  });
  return problems;
}

async function shoot(page: Page, info: TestInfo, name: string) {
  await page.evaluate(() => document.fonts.ready);
  const path = info.outputPath(`${name}.${info.project.name}.png`);
  await page.screenshot({ path, fullPage: true });
  await info.attach(name, { path, contentType: 'image/png' });
}

async function axe(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
    .analyze();
  return results.violations.map(
    (v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`,
  );
}

const total = (page: Page, text: string) => page.locator('.t-display', { hasText: text });

test.describe('SCR-HOME states', () => {
  for (const id of STATES) {
    test(`${id}: renders, no axe violations, screenshot`, async ({ page }, info) => {
      const problems = await watch(page);
      await page.goto(`/?fixture=${id}`);
      await expect(
        page.getByRole('banner').getByRole('link', { name: /모의투자|실전/ }),
      ).toBeVisible();
      if (id === 'home.loading') {
        await expect(page.locator('[aria-busy="true"]')).toBeVisible();
      } else if (id === 'home.other-device') {
        await expect(total(page, '10,243,800원')).toBeVisible({ timeout: 10_000 });
      } else if (id === 'home.offline') {
        await expect(page.getByText('16:10 불러온 값 · 연결 안 됨')).toBeVisible({
          timeout: 10_000,
        });
      } else {
        await expect(page.locator('.t-display')).toBeVisible();
      }
      expect(await axe(page)).toEqual([]);
      await shoot(page, info, id);
      // The offline state logs the dropped shell requests; nothing else may.
      expect(problems.filter((p) => !p.includes('network down'))).toEqual([]);
    });
  }
});

test('모의투자 기본: the hero and the whole graph are visible without scrolling', async ({
  page,
}) => {
  await page.goto('/?fixture=home.paper');
  await expect(total(page, '10,243,800원')).toBeInViewport();
  const header = page.getByRole('banner');
  await expect(header.getByRole('link', { name: '모의투자' })).toBeInViewport();
  await expect(page.getByText('모의투자 자산 · 7/1부터')).toBeInViewport();
  await expect(page.getByText('▲ +243,800원 · +2.44%')).toBeInViewport();
  await expect(page.getByRole('button', { name: '손대지 않았을 때 +3.59%' })).toBeInViewport();
  await expect(page.getByRole('link', { name: /오늘 22:30 미국 매수 2주/ })).toBeInViewport();
  const trend = page.getByRole('region', { name: '자산 변동' });
  const graph = trend.getByRole('img', { name: /^내 자산/ });
  await expect(graph).toBeInViewport({ ratio: 1 });
  await expect(trend.getByRole('button', { name: '표식 범례' })).toBeInViewport({ ratio: 1 });
  // Nothing of the graph hides under the bottom tab bar (390).
  const tabs = page.getByRole('navigation').filter({ has: page.locator('svg') });
  const box = await trend.boundingBox();
  const bar = (await tabs.count()) > 0 ? await tabs.first().boundingBox() : null;
  if (box && bar) expect(box.y + box.height).toBeLessThanOrEqual(bar.y);
});

test('graph markers move with the keyboard and 표로 보기 reads the same values', async ({
  page,
}, info) => {
  await page.goto('/?fixture=home.paper');
  const trend = page.getByRole('region', { name: '자산 변동' });
  const first = trend.getByRole('link', { name: '8/21(금) 리밸런싱' });
  await first.focus();
  await page.keyboard.press('ArrowRight');
  await expect(trend.getByRole('link', { name: '9/14(월) 일부 실패' })).toBeFocused();
  await page.keyboard.press('Tab');
  if (info.project.name === 'mobile-390') {
    // 390: 9/30 and 10/7 would overlap (22.7px apart), so they share one '[2]' marker.
    const group = trend.getByRole('button', { name: '9/30(수) 배당 · 10/7(수) 리밸런싱 중' });
    await expect(group).toBeFocused();
    await expect(group).toHaveText('2');
  } else {
    await expect(trend.getByRole('link', { name: '9/30(수) 배당' })).toBeFocused();
    await page.keyboard.press('Tab');
    await expect(trend.getByRole('link', { name: '10/7(수) 리밸런싱 중' })).toBeFocused();
  }
  await page.keyboard.press('Tab');
  await expect(trend.getByRole('button', { name: '표식 범례' })).toBeFocused();

  await trend.getByRole('button', { name: '표로 보기' }).click();
  const table = trend.getByRole('table', { name: '표로 보기' });
  await expect(table.getByRole('row').nth(1)).toHaveText(/7\/7\s*10,021,000원\s*9,960,100원/);
  await expect(table.getByRole('row').last()).toHaveText(/10\/7\s*10,243,800원\s*10,358,700원/);
});

test("a grouped '[n]' marker lists its events; one opens that day (390)", async ({
  page,
}, info) => {
  test.skip(info.project.name !== 'mobile-390', 'the markers only overlap at 390');
  await page.goto('/?fixture=home.paper');
  await page.getByRole('button', { name: '9/30(수) 배당 · 10/7(수) 리밸런싱 중' }).click();
  const list = page.getByRole('dialog', { name: '사건 목록' });
  await expect(list.getByRole('link', { name: '9/30(수) 배당' })).toBeVisible();
  await list.getByRole('link', { name: '10/7(수) 리밸런싱 중' }).click();
  await expect(page).toHaveURL(/\/day\/2026-10-07/);
});

test('a marker opens that day: 8/21 10,084,600원 · +12,300원', async ({ page }) => {
  await page.goto('/?fixture=home.paper');
  await page.getByRole('link', { name: '8/21(금) 리밸런싱' }).click();
  await expect(page).toHaveURL(/\/day\/2026-08-21/);
  // 390: a sheet with the date as its h1; 1440: a panel beside 기록.
  await expect(page.getByRole('heading', { name: /8\/21\(금\)/ }).first()).toBeVisible();
  await expect(page.getByText('10,084,600원').first()).toBeVisible();
  await expect(page.getByText(/\+12,300원/).first()).toBeVisible();
});

test('the 계획 card gauge is the gauge of the first rule card on 계획', async ({ page }) => {
  await page.goto('/?fixture=home.paper');
  const card = page.getByRole('region', { name: '계획' });
  const gauge = card.getByRole('img', { name: /KOSPI200 ETF/ });
  const label = await gauge.getAttribute('aria-label');
  const needle = gauge.locator('line').first();
  const tip = [await needle.getAttribute('x2'), await needle.getAttribute('y2')];
  expect(label).toBe('KOSPI200 ETF +0.2%p · 리밸런싱까지 1.8%p');
  await card.getByRole('link', { name: '계획 보기' }).click();
  await expect(page).toHaveURL(/\/plan/);
  const first = page.getByRole('article').first();
  await expect(first).toHaveAccessibleName('지수 반반');
  const planGauge = first.getByRole('img', { name: /KOSPI200 ETF/ });
  await expect(planGauge).toHaveAttribute('aria-label', label ?? '');
  const planNeedle = planGauge.locator('line').first();
  expect([await planNeedle.getAttribute('x2'), await planNeedle.getAttribute('y2')]).toEqual(tip);
});

test('another device switches the mode: badge + chip, skeleton, then the new ledger', async ({
  page,
}, info) => {
  await page.goto('/?fixture=home.other-device');
  await expect(total(page, '10,112,670원')).toBeVisible();
  await expect(page.getByRole('banner').getByRole('link', { name: '실전' })).toBeVisible();
  await expect(page.getByText('16:11 다른 기기에서 실전 → 모의투자로 바뀜')).toBeVisible({
    timeout: 60_000,
  });
  await expect(page.getByRole('banner').getByRole('link', { name: '모의투자' })).toBeVisible();
  await expect(page.locator('[aria-busy="true"]')).toBeVisible();
  await expect(page.getByText('10,112,670원')).toHaveCount(0);
  await shoot(page, info, 'home.other-device.skeleton');
  await expect(total(page, '10,243,800원')).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText('16:11 다른 기기에서 실전 → 모의투자로 바뀜')).toBeVisible();
});

test("the connection drops: numbers stay, '16:10 불러온 값 · 연결 안 됨'", async ({ page }) => {
  await page.goto('/?fixture=home.offline');
  await expect(total(page, '10,243,800원')).toBeVisible();
  await expect(page.getByText('16:10 불러온 값 · 연결 안 됨')).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole('banner')).toContainText('연결 안 됨');
  await expect(total(page, '10,243,800원')).toBeVisible();
});

test('no session: the PIN page, with the way back', async ({ page }) => {
  await page.goto('/?fixture=home.permission');
  await expect(page).toHaveURL(/\/pin\?next=/);
});

test('sheets trap focus and close with Escape', async ({ page }) => {
  await page.goto('/?fixture=home.paper');
  const opener = page.getByRole('button', { name: '16:00 기준' });
  await opener.click();
  const sheet = page.getByRole('dialog', { name: '16:00 기준' });
  await expect(sheet).toBeVisible();
  await expect(sheet.getByText('환율 1,382.4원 16:00')).toBeVisible();
  // showModal(): focus moves into the sheet and the page behind is inert.
  await expect(sheet.getByRole('button', { name: '닫기' })).toBeFocused();
  // Tab never reaches the page behind the sheet.
  for (let i = 0; i < 3; i++) {
    await page.keyboard.press('Tab');
    const escaped = await page.evaluate(() => {
      const a = document.activeElement;
      return a !== null && a !== document.body && a.closest('dialog') === null;
    });
    expect(escaped).toBe(false);
  }
  await page.keyboard.press('Escape');
  await expect(sheet).toBeHidden();
  await expect(opener).toBeFocused();
});

test('390 rows open their second line; 1440 shows it from the start', async ({ page }, info) => {
  await page.goto('/?fixture=home.paper');
  const detail = page.getByText('115주 · 평균 32,005원');
  if (info.project.name === 'mobile-390') {
    await expect(detail).toHaveCount(0);
    await page.getByRole('button', { name: /KOSPI200 ETF/ }).click();
    await expect(detail).toBeVisible();
  } else {
    await expect(detail).toBeVisible();
    await expect(page.getByRole('button', { name: /KOSPI200 ETF/ })).toHaveCount(0);
  }
});

test('no 다 sentences; no 모의와 비교 or 실계좌 − 모의', async ({ page }) => {
  for (const id of ['home.paper', 'home.live', 'home.empty', 'home.withdraw']) {
    await page.goto(`/?fixture=${id}`);
    await expect(page.locator('.t-display')).toBeVisible();
    const text = await page.locator('body').innerText();
    expect(text).not.toMatch(/다\.|니다|었다|한다|된다/);
    expect(text).not.toContain('모의와 비교');
    expect(text).not.toContain('실계좌 − 모의');
  }
});
