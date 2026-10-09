// SCR-RULES 규칙 on the e2e build at 390 and 1440: tiles, the node-card flow and its lines, rule
// and lane selection, every state with axe and a screenshot.
import { expect, test } from '@playwright/test';
import { axe, isMobile, shoot, watch } from './hdr-helpers';

test('rules.index-half (1:60971 · 1:61916): six tiles; axe; screenshot', async ({ page }, info) => {
  const problems = await watch(page);
  await page.goto('/rules?fixture=rules.index-half');
  await expect(page.getByRole('heading', { level: 1, name: '지수 반반' })).toBeVisible();
  for (const v of [
    '50 : 50',
    '매일 08:30',
    '±2%p 넘으면',
    '리밸런싱 주문',
    '+9.5%',
    '다음 확인 10/8 08:30',
  ]) {
    await expect(page.getByText(v, { exact: true }).first()).toBeVisible();
  }
  await expect(page.getByText('중간값 · 세후 · 2015–25')).toBeVisible();
  await expect(page.getByText(/기대/)).toHaveCount(0);
  // The measured number is neutral (text/primary, not gain/loss red/blue).
  const color = await page
    .locator('p.t-heading-1', { hasText: '+9.5%' })
    .evaluate((el) => getComputedStyle(el).color);
  expect(color).toBe('rgb(25, 31, 40)');
  if (isMobile(info)) {
    await expect(page.getByRole('group', { name: '규칙' })).toBeVisible();
    await expect(page.getByText('보기 전용')).toHaveCount(0);
  } else {
    await expect(page.getByText('보기 전용')).toBeVisible();
    await expect(page.getByText('규칙 2개')).toBeVisible();
  }
  await expect(page.locator('input, textarea, select')).toHaveCount(0);
  // 지금 · 결과: the waiting 매수 is a dashed ring and the done line stops halfway to it.
  const ring = page.locator('svg[class*="nowRing"] circle');
  await expect(ring).toHaveCount(1);
  expect(await ring.evaluate((c) => getComputedStyle(c).strokeDasharray)).toBe('3px, 2px');
  const track = await page.locator('[class*="nowTrack"]').first().boundingBox();
  const done = await page.locator('[class*="nowTrackDone"]').first().boundingBox();
  expect((done?.width ?? 0) / (track?.width ?? 1)).toBeCloseTo(0.75, 2);
  await axe(page);
  await shoot(page, info, 'rules.index-half');
  expect(problems).toEqual([]);
});

test('rules.momentum (1:61226 · 1:62197): nine cards, lines in three styles, labels; axe; screenshot', async ({
  page,
}, info) => {
  const problems = await watch(page);
  await page.goto('/rules/momentum?fixture=rules.momentum');
  const canvas = page.getByRole('group', { name: '[예시] 종목 모멘텀 흐름' });
  await expect(canvas.getByRole('article')).toHaveCount(9);
  await expect(canvas.getByText('· 마지막 판단 10/7 08:30')).toBeVisible();
  const edges = canvas.locator('svg[class*="edges"] > g[class*="edge"]');
  await expect(edges).toHaveCount(9);
  const dashes = await edges.evaluateAll((gs) =>
    gs.map((g) => {
      const path = g.querySelector('path');
      return [g.getAttribute('class') ?? '', path ? getComputedStyle(path).strokeDasharray : ''];
    }),
  );
  const byStyle = (part: string) =>
    dashes.filter(([c]) => (c ?? '').includes(part)).map(([, d]) => d);
  expect(byStyle('lineTaken').every((d) => d === 'none')).toBe(true);
  expect(byStyle('lineNotTaken').every((d) => d === '4px, 4px')).toBe(true);
  expect(byStyle('lineException')).toEqual(['2px, 3px']);
  expect(byStyle('lineTaken')).toHaveLength(6);
  await expect(canvas.getByText('예', { exact: true })).toBeVisible();
  await expect(canvas.getByText('아니오 · 그대로', { exact: true })).toBeVisible();
  for (const t of ['이번에 지난 길', '안 지난 갈래', '예외 갈래'])
    await expect(page.getByText(t)).toBeVisible();
  // The lines meet the cards: the 시작 → 종목 line ends at the 종목 card's left edge.
  const stock = await canvas.locator('[data-node="stock"]').boundingBox();
  const start = await canvas.locator('[data-node="start"]').boundingBox();
  const first = await edges.first().locator('polyline').boundingBox();
  if (!isMobile(info)) {
    expect(Math.abs((first?.x ?? 0) + (first?.width ?? 0) - (stock?.x ?? 0))).toBeLessThan(1.5);
  } else {
    expect((first?.y ?? 0) + (first?.height ?? 0)).toBeLessThanOrEqual((stock?.y ?? 0) + 1);
    expect(first?.y ?? 0).toBeGreaterThan((start?.y ?? 0) + (start?.height ?? 0) - 10);
  }
  await axe(page);
  await shoot(page, info, 'rules.momentum');
  expect(problems).toEqual([]);
});

test('완료 조건: one rule at a time — 390 chips / 1440 list cards, id in the address', async ({
  page,
}, info) => {
  await page.goto('/rules?fixture=rules.index-half');
  await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
  if (isMobile(info)) {
    await page.getByRole('button', { name: /\[예시\] 종목 모멘텀 18\.3%/ }).click();
  } else {
    await page.getByRole('link', { name: /\[예시\] 종목 모멘텀/ }).click();
  }
  await expect(page).toHaveURL(/\/rules\/momentum/);
  await expect(page.getByRole('heading', { level: 1, name: '[예시] 종목 모멘텀' })).toBeVisible();
  await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
});

test('완료 조건: 과거 1년 수익 ⌄ opens the source, period and definitions in place', async ({
  page,
}) => {
  await page.goto('/rules?fixture=rules.index-half');
  const toggle = page.getByRole('button', { name: '출처' });
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  await expect(page.getByText('T09')).toBeVisible();
  await expect(page.getByText('나쁜 해')).toBeVisible();
});

test('rules.first-day (1:61661): no selector, same six tiles; axe; screenshot', async ({
  page,
}, info) => {
  await page.goto('/rules?fixture=rules.first-day');
  await expect(page.getByRole('heading', { level: 1, name: '지수 반반' })).toBeVisible();
  await expect(page.getByText('99.6%')).toBeVisible();
  await expect(page.getByRole('group', { name: '규칙' })).toHaveCount(0);
  await expect(page.getByText('다음 확인 7/2 08:30')).toBeVisible();
  await axe(page);
  await shoot(page, info, 'rules.first-day');
});

for (const lane of ['daily', 'quarterly', 'earnings', 'monthly'] as const) {
  test(`rules.discovery-${lane}: 흐름 chips and the lane's cards; axe; screenshot`, async ({
    page,
  }, info) => {
    await page.goto(`/rules/discovery_3y?fixture=rules.discovery-${lane}`);
    await expect(page.getByRole('heading', { level: 1, name: '3년 발굴' })).toBeVisible();
    const lanes = page.getByRole('group', { name: '흐름', exact: true });
    await expect(lanes.getByRole('button')).toHaveCount(4);
    await expect(lanes.getByRole('button', { pressed: true })).toHaveCount(1);
    await axe(page);
    await shoot(page, info, `rules.discovery-${lane}`);
  });
}

test('lane chips switch the lane in place (?lane=)', async ({ page }) => {
  await page.goto('/rules/discovery_3y?fixture=rules.discovery-daily');
  await page
    .getByRole('group', { name: '흐름', exact: true })
    .getByRole('button', { name: '실적 공시' })
    .click();
  await expect(page).toHaveURL(/lane=earnings/);
  await expect(page.getByText('실적 지표 뽑기', { exact: true })).toBeVisible();
});

for (const [state, check] of [
  ['rules.stale', '미국 시세 10/2 기준 · 2거래일째 갱신 없음'],
  ['rules.error', '규칙을 못 불러왔어요'],
] as const) {
  test(`${state}: renders, axe, screenshot`, async ({ page }, info) => {
    await page.goto(`/rules?fixture=${state}`);
    await expect(page.getByText(check)).toBeVisible();
    await axe(page);
    await shoot(page, info, state);
  });
}

test('rules.loading: frames as skeletons', async ({ page }, info) => {
  await page.goto('/rules?fixture=rules.loading');
  await expect(page.locator('[aria-busy="true"]').first()).toBeVisible();
  await shoot(page, info, 'rules.loading');
});

test('rules.permission: no session → PIN, then the same rule', async ({ page }) => {
  await page.goto('/rules/momentum?fixture=rules.permission');
  await expect(page).toHaveURL(/\/pin\?next=/);
  expect(new URL(page.url()).searchParams.get('next')).toBe(
    '/rules/momentum?fixture=rules.permission',
  );
});
