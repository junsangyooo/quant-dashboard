// SCR-HISTORY 기록 on the e2e build (production code + fixtures, production CSP), at 390 and 1440.
// Every state: numbers from 예시-값표 §1.4, axe, a screenshot; plus the 완료 조건 that need a real
// browser (scroll, layout, keyboard, the 1440 panel, the PIN round trip).
import { expect, test } from '@playwright/test';
import { axe, isMobile, settle, shoot, watch } from './hdr-helpers';

const PAPER = '/history?fixture=history.paper';

test.describe('history.paper (1:58215 · 1:59344)', () => {
  test('numbers, tiles, months, axe and screenshot', async ({ page }, info) => {
    const problems = await watch(page);
    await page.goto(PAPER);
    await expect(page.getByText('10,243,800원', { exact: true }).first()).toBeVisible();
    await expect(
      page.getByRole('heading', { level: 1, name: '모의투자 기록 · 2026' }),
    ).toBeVisible();
    await expect(page.getByText('▲ +243,800원 · +2.44%')).toBeVisible();
    for (const t of ['3회', '5,935원', '71회', '일부 실패 1', '세금 미포함', '실패 1']) {
      await expect(page.getByText(t, { exact: true }).first()).toBeVisible();
    }
    const list = page.getByRole('region', { name: '사건 목록' });
    await expect(list.getByRole('heading', { level: 3 })).toHaveText([
      /10월\s*\+70,300원/,
      /9월\s*\+58,700원/,
      /8월\s*\+162,200원/,
      /7월\s*−47,400원/,
    ]);
    await axe(page);
    await shoot(page, info, 'history.paper');
    expect(problems).toEqual([]);
  });

  test('filter chips: counts equal rows, both rows apply together, kept in the address', async ({
    page,
  }) => {
    await page.goto(PAPER);
    const rows = page.getByRole('region', { name: '사건 목록' }).getByRole('link');
    await expect(rows).toHaveCount(6);
    await page.getByRole('button', { name: '지수 반반 3' }).click();
    await expect(rows).toHaveCount(3);
    await page.getByRole('button', { name: '리밸런싱 3' }).click();
    await expect(rows).toHaveCount(2);
    await expect(page).toHaveURL(/rule=index_half/);
    await expect(page).toHaveURL(/kind=rebalance/);
    await page.getByRole('button', { name: '전체 6' }).click();
    await expect(rows).toHaveCount(3);
    await page.getByRole('button', { name: '리밸런싱 3' }).click();
    await expect(rows).toHaveCount(6);
    for (const [name, n] of [
      ['배당 1', 1],
      ['실패 1', 1],
      ['입금 0', 0],
    ] as const) {
      await page.getByRole('button', { name }).click();
      await expect(rows).toHaveCount(n);
      await page.getByRole('button', { name }).click();
    }
  });

  test('calendar: Mon–Fri only, newest weeks in view at 390 with the swipe hint; arrow keys', async ({
    page,
  }, info) => {
    await page.goto(PAPER);
    const grid = page.getByRole('group', { name: '매일 확인' });
    await expect(grid.getByRole('link')).toHaveCount(71);
    await expect(grid.getByRole('link', { name: '9/9(수) 실패' })).toBeVisible();
    if (isMobile(info)) {
      await expect(page.getByText('가로로 밀면 7/1~7/10')).toBeVisible();
      const scroll = grid.locator('xpath=..');
      expect(await scroll.evaluate((el) => el.scrollLeft)).toBeGreaterThan(0);
      await expect(grid.getByRole('link', { name: '10/7(수) 리밸런싱 중' })).toBeInViewport();
      // 월–금 stay at the left over the scrolled weeks, with '7월' over the first visible week.
      const pin = page.locator('div[aria-hidden="true"][class*="calendarPin"]');
      for (const w of ['월', '화', '수', '목', '금'])
        await expect(pin.getByText(w, { exact: true })).toBeVisible();
      await expect(pin.getByText('7월')).toBeVisible();
      // A week reached with the arrow keys scrolls clear of the pinned labels, ring included.
      await grid.getByRole('link', { name: '10/7(수) 리밸런싱 중' }).focus();
      for (let i = 0; i < 12; i++) await page.keyboard.press('ArrowLeft');
      const july15 = grid.getByRole('link', { name: /^7\/15\(수\)/ });
      await expect(july15).toBeFocused();
      const cell = await july15.boundingBox();
      const pinBox = await pin.boundingBox();
      expect((cell?.x ?? 0) - ((pinBox?.x ?? 0) + (pinBox?.width ?? 0))).toBeGreaterThanOrEqual(4);
      // At the very start the grid's own labels are in place: no pin.
      await scroll.evaluate((el) => {
        el.scrollLeft = 0;
      });
      await expect(pin).toHaveCount(0);
    } else {
      await expect(page.getByText(/가로로 밀면/)).toHaveCount(0);
      await expect(page.locator('div[aria-hidden="true"][class*="calendarPin"]')).toHaveCount(0);
    }
    // One Tab stop; ← moves a week back.
    const today = grid.getByRole('link', { name: '10/7(수) 리밸런싱 중' });
    await today.focus();
    await page.keyboard.press('ArrowLeft');
    await expect(grid.getByRole('link', { name: '9/30(수) 정상 실행' })).toBeFocused();
    await page.keyboard.press('ArrowDown');
    await expect(grid.getByRole('link', { name: '10/1(목) 정상 실행' })).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/day\/2026-10-01/);
  });

  test('chart markers move with ←/→ and open 그날', async ({ page }) => {
    await page.goto(PAPER);
    const chart = page.getByRole('region', { name: '자산 변동 · 7/1부터' });
    await chart.getByRole('link', { name: '7/1(수) 시작' }).focus();
    await page.keyboard.press('ArrowRight');
    const rebalance = chart.getByRole('link', { name: '8/21(금) 리밸런싱' });
    await expect(rebalance).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/day\/2026-08-21\?fixture=history\.paper$/);
  });

  test('완료 조건 1440: a row opens the right panel; chart line on that day; row highlighted', async ({
    page,
  }, info) => {
    test.skip(isMobile(info), '1440 only');
    await page.goto(PAPER);
    await page
      .getByRole('region', { name: '사건 목록' })
      .getByRole('link', { name: /^8\/21\(금\)/ })
      .click();
    const panel = page.getByRole('complementary', { name: '8/21(금)' });
    await expect(panel).toBeVisible();
    const box = await panel.boundingBox();
    expect(box?.width).toBe(480);
    expect((box?.x ?? 0) + (box?.width ?? 0)).toBe(1440);
    // The vertical line stands on 8/21: same x as the 8/21 marker's centre.
    const chart = page.getByRole('region', { name: '자산 변동 · 7/1부터' });
    const marker = await chart.getByRole('link', { name: '8/21(금) 리밸런싱' }).boundingBox();
    const line = await chart.locator('line[class*="cursor"]').boundingBox();
    expect(Math.abs((line?.x ?? 0) - ((marker?.x ?? 0) + 12))).toBeLessThan(1.5);
    await expect(
      page.getByRole('region', { name: '사건 목록' }).getByRole('link', { name: /^8\/21\(금\)/ }),
    ).toHaveAttribute('aria-current', 'page');
    // The right column (타일 · 달력) is under the panel; the left column stays clear of it.
    const list = await page.getByRole('region', { name: '사건 목록' }).boundingBox();
    expect((list?.x ?? 0) + (list?.width ?? 0)).toBeLessThanOrEqual(912.5);
    await shoot(page, info, 'history.paper-panel');
    await page.keyboard.press('Escape');
    await expect(page).toHaveURL(/\/history\?fixture=history\.paper$/);
  });
});

test('history.paper-ledger (1:58777): chip + × back to the 실전 record', async ({ page }, info) => {
  await page.goto('/history?ledger=paper&fixture=history.paper-ledger');
  await expect(page.getByText('모의투자 장부')).toBeVisible();
  await expect(page.getByText('· 실전 중에 보는 중')).toBeVisible();
  await expect(page.getByRole('banner').getByRole('link', { name: '실전' })).toBeVisible();
  await axe(page);
  await shoot(page, info, 'history.paper-ledger');
  await page.getByRole('button', { name: '닫기 · 실전 기록으로' }).click();
  await expect(page).toHaveURL(/\/history\?fixture=history\.paper-ledger$/);
  await expect(page.getByRole('heading', { level: 1, name: '실전 기록 · 2026' })).toBeVisible();
  await expect(page.getByText('모의 체결')).toHaveCount(0);
  await expect(page.getByText('실제 체결').first()).toBeVisible();
});

for (const [state, check] of [
  ['history.off-period', '끈 기간 9/21–9/25'],
  ['history.empty', '첫 확인 뒤 그래프가 그려져요'],
  ['history.error', '기록을 못 불러왔어요'],
  ['history.stale', '미국 시세 10/2 기준 · 2거래일째 갱신 없음'],
] as const) {
  test(`${state}: renders, axe, screenshot`, async ({ page }, info) => {
    const problems = await watch(page);
    await page.goto(`/history?fixture=${state}`);
    await expect(page.getByText(check)).toBeVisible();
    await axe(page);
    await shoot(page, info, state);
    // The error state's 500 is the scripted answer, not a problem of the page.
    expect(problems.filter((p) => !p.includes('500'))).toEqual([]);
  });
}

test('history.loading: card frames with skeletons', async ({ page }, info) => {
  await page.goto('/history?fixture=history.loading');
  await expect(page.locator('[aria-busy="true"]')).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  await shoot(page, info, 'history.loading');
});

test('history.offline: the numbers stay with "16:10 불러온 값 · 연결 안 됨"', async ({
  page,
}, info) => {
  await page.goto('/history?fixture=history.offline');
  await expect(page.getByText('16:10 불러온 값 · 연결 안 됨')).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText('10,243,800원', { exact: true }).first()).toBeVisible();
  await shoot(page, info, 'history.offline');
});

test('history.permission: no session → PIN with ledger and filters kept in next', async ({
  page,
}) => {
  await page.goto(
    '/history?ledger=paper&rule=index_half&kind=rebalance&fixture=history.permission',
  );
  await expect(page).toHaveURL(/\/pin\?next=/);
  const next = new URL(page.url()).searchParams.get('next');
  expect(next).toBe(
    '/history?ledger=paper&rule=index_half&kind=rebalance&fixture=history.permission',
  );
});

test('390 sheet from a row, × back to the same filtered 기록', async ({ page }, info) => {
  test.skip(!isMobile(info), '390 only');
  await page.goto('/history?rule=index_half&fixture=history.paper');
  await page
    .getByRole('region', { name: '사건 목록' })
    .getByRole('link', { name: /^9\/30\(수\)/ })
    .click();
  const sheet = page.getByRole('dialog', { name: '9/30(수)' });
  await expect(sheet).toBeVisible();
  await settle(page);
  await sheet.getByRole('link', { name: '닫기' }).click();
  await expect(page).toHaveURL(/\/history\?rule=index_half&fixture=history.paper$/);
  await expect(page.getByRole('region', { name: '사건 목록' }).getByRole('link')).toHaveCount(3);
});
