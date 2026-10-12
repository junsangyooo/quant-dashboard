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
  // 계좌별 보기 (2026-10-12): the switch on 한국 ₩ · 미국 $, before the first fill, dollars only, empty
  'home.account-kr',
  'home.account-us',
  'home.before-fill',
  'home.us-cash',
  'home.us-empty',
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

/**
 * axe over the whole page at once. At a scroll position the 390 tab bar (sticky) lies over
 * whatever is under it, and target-size reads that overlap as crowding — it moved onto the
 * 구성 rows and 표로 보기 once the 계좌 switch and tiles grew the hero. A viewport as tall as the
 * page shows every target clear (the rule of the full run, e2e/full/checks.ts).
 */
async function axe(page: Page) {
  const size = page.viewportSize();
  if (size) {
    const height = await page.evaluate(() => document.documentElement.scrollHeight);
    if (height > size.height) await page.setViewportSize({ width: size.width, height });
  }
  try {
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
      .analyze();
    return results.violations.map(
      (v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`,
    );
  } finally {
    if (size) await page.setViewportSize(size);
  }
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

// ── 계좌별 보기 (the owner, 2026-10-12): 전체 · 한국 ₩ · 미국 $ ───────────────────────────────

/** The 자산 변동 card ends above the 390 tab bar (the whole graph without scrolling). */
async function graphAboveTabs(page: Page) {
  const trend = page.getByRole('region', { name: '자산 변동' });
  await expect(trend.getByRole('img').first()).toBeInViewport({ ratio: 1 });
  const tabs = page.getByRole('navigation').filter({ has: page.locator('svg') });
  const box = await trend.boundingBox();
  const bar = (await tabs.count()) > 0 ? await tabs.first().boundingBox() : null;
  if (box && bar) expect(box.y + box.height).toBeLessThanOrEqual(bar.y);
}

test('the switch shows each account in its own money; the graph stays in view', async ({
  page,
}, info) => {
  const problems = await watch(page);
  await page.goto('/?fixture=home.paper');
  const switcher = page.getByRole('radiogroup', { name: '계좌' });
  await expect(switcher.getByRole('radio', { name: '전체' })).toHaveAttribute(
    'aria-checked',
    'true',
  );
  await expect(total(page, '10,243,800원')).toBeInViewport();
  await expect(page.getByRole('button', { name: /환율 효과/ })).toBeInViewport();
  await expect(page.getByRole('link', { name: /한국 계좌/ })).toBeInViewport();
  await graphAboveTabs(page);

  await switcher.getByRole('radio', { name: '한국 ₩' }).click();
  await expect(page).toHaveURL(/[?&]account=kr(&|$)/);
  await expect(total(page, '5,368,683원')).toBeVisible();
  await expect(page.getByText('▲ +484,683원 · +9.41%')).toBeVisible();
  await expect(page.getByRole('region', { name: '계획' })).toHaveCount(0);
  await graphAboveTabs(page);
  expect(await axe(page)).toEqual([]);
  await shoot(page, info, 'home.switch-kr');

  await switcher.getByRole('radio', { name: '미국 $' }).click();
  await expect(page).toHaveURL(/[?&]account=us(&|$)/);
  await expect(total(page, '$3,526.56')).toBeVisible();
  await expect(page.getByText('▼ −$149.95 · −4.30%')).toBeVisible();
  const comp = page.getByRole('region', { name: '구성' });
  await expect(comp.getByText('$2,870.40')).toBeVisible();
  await expect(comp.getByText('계좌의 85.0%')).toBeVisible();
  await graphAboveTabs(page);
  expect(await axe(page)).toEqual([]);

  // Arrow keys move along the switch; 전체 drops the address' account.
  await switcher.getByRole('radio', { name: '미국 $' }).focus();
  await page.keyboard.press('ArrowRight');
  await expect(switcher.getByRole('radio', { name: '전체' })).toBeFocused();
  await expect(page).not.toHaveURL(/account=/);
  await expect(total(page, '10,243,800원')).toBeVisible();
  expect(problems).toEqual([]);
});

test('a tile opens its account; back returns to 전체', async ({ page }) => {
  await page.goto('/?fixture=home.paper');
  await page.getByRole('link', { name: /미국 계좌/ }).click();
  await expect(page).toHaveURL(/[?&]account=us(&|$)/);
  await expect(total(page, '$3,526.56')).toBeVisible();
  await page.goBack();
  await expect(total(page, '10,243,800원')).toBeVisible();
  await expect(page.getByRole('radio', { name: '전체' })).toHaveAttribute('aria-checked', 'true');
});

test('the switch opens an account one entry above 전체: back returns there', async ({ page }) => {
  await page.goto('/?fixture=home.paper');
  const switcher = page.getByRole('radiogroup', { name: '계좌' });
  await switcher.getByRole('radio', { name: '한국 ₩' }).click();
  await expect(page).toHaveURL(/[?&]account=kr(&|$)/);
  await switcher.getByRole('radio', { name: '미국 $' }).click();
  await expect(page).toHaveURL(/[?&]account=us(&|$)/);
  await page.goBack();
  await expect(page).not.toHaveURL(/account=/);
  await expect(total(page, '10,243,800원')).toBeVisible();
  await expect(switcher.getByRole('radio', { name: '전체' })).toHaveAttribute(
    'aria-checked',
    'true',
  );
});

test('손익 나눠 보기 adds 한국 + 미국 + 환율 효과 up to the P&L; the sheet holds the focus', async ({
  page,
}, info) => {
  await page.goto('/?fixture=home.paper');
  const opener = page.getByRole('button', { name: /환율 효과/ });
  await opener.click();
  const sheet = page.getByRole('dialog', { name: '손익 나눠 보기' });
  await expect(sheet).toBeVisible();
  await expect(
    sheet.getByRole('img', {
      name: '한국 계좌 +484,683원 · 미국 계좌 −207,291원 · 환율 효과 −33,592원 · 전체 손익 +243,800원',
    }),
  ).toBeVisible();
  await expect(sheet.getByText('미국 계좌 −$149.95 × 1,382.4원')).toBeVisible();
  await expect(sheet.getByRole('button', { name: '닫기' })).toBeFocused();
  expect(await axe(page)).toEqual([]);
  await shoot(page, info, 'home.split-sheet');
  await page.keyboard.press('Escape');
  await expect(sheet).toBeHidden();
  await expect(opener).toBeFocused();
});

test('미국 $ 변동 분해 counts 환전 as money in, in dollars', async ({ page }) => {
  await page.goto('/?fixture=home.account-us');
  await page.getByRole('button', { name: /3개월.*\$/ }).click();
  const sheet = page.getByRole('dialog', { name: '변동 분해 · 3개월' });
  await expect(sheet.getByRole('img', { name: /환전 \+\$251\.23/ })).toBeVisible();
  await expect(sheet.getByRole('img', { name: /지금 \$3,526\.56$/ })).toBeVisible();
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
  for (const id of [
    'home.paper',
    'home.live',
    'home.empty',
    'home.withdraw',
    'home.account-kr',
    'home.account-us',
    'home.us-empty',
  ]) {
    await page.goto(`/?fixture=${id}`);
    await expect(page.locator('.t-display')).toBeVisible();
    const text = await page.locator('body').innerText();
    expect(text).not.toMatch(/다\.|니다|었다|한다|된다/);
    expect(text).not.toContain('모의와 비교');
    expect(text).not.toContain('실계좌 − 모의');
  }
});
