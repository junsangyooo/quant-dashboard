// SCR-PLAN in the browser (e2e build + production CSP): 완료 조건 that need layout or navigation,
// axe on every state, and a screenshot of every state at 390×844 and 1440×900.
import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page, type TestInfo } from '@playwright/test';

const STATES = [
  'plan.paper',
  'plan.live',
  'plan.live-mix',
  'plan.stale',
  'plan.partial',
  'plan.live-todo',
  'plan.first-day',
  'plan.empty',
  'plan.withdraw',
  'plan.holiday',
  'plan.loading',
  'plan.offline',
  'plan.discovery',
] as const;

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

const wide = (info: TestInfo) => info.project.name === 'desktop-1440';

test.describe('SCR-PLAN states', () => {
  for (const id of STATES) {
    test(`${id}: renders, no axe violations, screenshot`, async ({ page }, info) => {
      const problems = await watch(page);
      await page.goto(`/plan?fixture=${id}`);
      await expect(
        page.getByRole('banner').getByRole('link', { name: /모의투자|실전/ }),
      ).toBeVisible();
      if (id === 'plan.loading') {
        await expect(page.getByRole('heading', { level: 2, name: '예정' })).toBeVisible();
      } else {
        await expect(page.getByRole('article').first()).toBeVisible();
      }
      if (id === 'plan.offline') {
        await expect(page.getByText('16:10 불러온 값 · 연결 안 됨')).toBeVisible({
          timeout: 15_000,
        });
      }
      expect(await axe(page)).toEqual([]);
      await shoot(page, info, id);
      expect(problems.filter((p) => !p.includes('network down'))).toEqual([]);
    });
  }
});

test('모의투자 기본: both rule cards with their numbers (1440: a drift chart in each)', async ({
  page,
}, info) => {
  await page.goto('/plan?fixture=plan.paper');
  const index = page.getByRole('article', { name: '지수 반반' });
  await expect(index).toContainText('자산의81.1%· 목표 80%');
  await expect(index).toContainText('리밸런싱 중');
  await expect(index).toContainText('오늘 22:30 미국 매수 2주');
  await expect(
    index.getByRole('img', { name: 'KOSPI200 ETF +0.2%p · 리밸런싱까지 1.8%p' }),
  ).toBeVisible();
  await expect(index).toContainText('50.2% · 목표 50%');
  await expect(index).toContainText('49.8% · 목표 50%');
  const momentum = page.getByRole('article', { name: '[예시] 종목 모멘텀' });
  await expect(momentum).toContainText('목표 범위 안');
  await expect(
    momentum.getByRole('img', { name: 'NVDA −1.0%p · 리밸런싱까지 1.0%p' }),
  ).toBeVisible();
  if (wide(info)) {
    await expect(index.locator('p', { hasText: '벗어남 흐름 · 3개월' })).toBeVisible();
    await expect(momentum.locator('p', { hasText: '벗어남 흐름 · 3개월' })).toBeVisible();
    await expect(page.getByRole('region', { name: '예정' })).toBeInViewport();
  } else {
    await expect(page.getByRole('region', { name: '벗어남 흐름' })).toBeVisible();
  }
});

test('next action and share segments scroll to their targets', async ({ page }) => {
  await page.goto('/plan?fixture=plan.paper');
  await page.getByRole('button', { name: '오늘 22:30 미국 매수 2주' }).click();
  await expect(page.locator('#plan-now')).toBeFocused();
  await expect(page.locator('#plan-now')).toBeInViewport();
  await page.getByRole('button', { name: '[예시] 종목 모멘텀 18.3%' }).click();
  await expect(page.getByRole('article', { name: '[예시] 종목 모멘텀' })).toBeFocused();
});

test('a stage card opens its day; 규칙 그림 보기 goes to 규칙', async ({ page }) => {
  await page.goto('/plan?fixture=plan.paper');
  await page.locator('#plan-now').getByRole('link', { name: /매도/ }).click();
  await expect(page).toHaveURL(/\/day\/2026-10-07/);
  await page.goto('/plan?fixture=plan.paper');
  await page.getByRole('link', { name: '규칙 그림 보기' }).click();
  await expect(page).toHaveURL(/\/rules/);
});

test('실전 직접 할 일: the red card links to 작동', async ({ page }) => {
  await page.goto('/plan?fixture=plan.live-todo');
  await expect(page.getByRole('banner')).toContainText('직접 할 일 1');
  await expect(page.getByText('지금 · 일부 실패 · 직접 할 일')).toBeVisible();
  await page.locator('#plan-now').getByRole('link', { name: '직접 할 일' }).click();
  await expect(page).toHaveURL(/\/health/);
});

test("시세 대기: hollow gauges and lines broken from 10/5 ('10/5부터 시세 대기')", async ({
  page,
}) => {
  await page.goto('/plan?fixture=plan.stale');
  // .all() does not wait: wait for both cards first, or a slow render reads zero (flaky under load).
  await expect(page.getByRole('article')).toHaveCount(2);
  const cards = await page.getByRole('article').all();
  for (const card of cards) {
    await expect(card.locator('circle[class*="hubEmpty"]')).toHaveCount(1);
    await expect(card.locator('line[class*="needle"]')).toHaveCount(0);
    await expect(card.getByText('규칙 안 비중 · 미국 시세 10/2 기준이라 계산 안 함')).toBeVisible();
  }
  await expect(page.getByText('10/5부터 시세 대기').first()).toBeVisible();
  await expect(page.getByText('목표 범위 안')).toHaveCount(0);
});

test('AI 규칙 card (17:7108): 0–100 gauge and 지수 대비 line', async ({ page }, info) => {
  await page.goto('/plan?fixture=plan.discovery');
  const ai = page.getByRole('article', { name: '3년 발굴' });
  await expect(
    ai.getByRole('img', { name: 'HD현대일렉트릭 54% · 팔 조건까지 이익률 2.3%p' }),
  ).toBeVisible();
  await expect(ai.locator('p', { hasText: '지수 대비 · 7/1부터 (%p)' })).toBeVisible();
  await expect(ai).toContainText('다음 확인 10/8 08:30 · 점검 11/1');
  if (wide(info)) {
    const box = await ai.boundingBox();
    expect(box?.width).toBeGreaterThan(700);
  }
});

test('no session: the PIN page, with the way back', async ({ page }) => {
  await page.goto('/plan?fixture=plan.permission');
  await expect(page).toHaveURL(/\/pin\?next=/);
});

test('실전 · 넣은 돈 그대로: 환전 제안 and the money of today (D47·D48)', async ({ page }) => {
  await page.goto('/plan?fixture=plan.live-mix');
  const card = page.getByRole('article', { name: '지수 반반' });
  await expect(card.getByText('환전 제안')).toBeVisible();
  await expect(card.getByText('약 1,500,000원을 달러로 바꾸면 50:50')).toBeVisible();
  await expect(
    page.getByText('새로 들어온 돈 3,000,000원 · 다음 거래일 08:30부터 써요'),
  ).toBeVisible();
  await expect(page.getByRole('banner')).not.toContainText('직접 할 일');
});
