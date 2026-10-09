// SCR-DAY 그날 on the e2e build at 390 (full-height sheet over the header) and 1440 (right panel
// over 기록). Numbers from 예시-값표 §1.4 · §3; every state gets axe and a screenshot.
import { expect, test } from '@playwright/test';
import { axe, isMobile, shoot, watch } from './hdr-helpers';

function surface(page: import('@playwright/test').Page, mobile: boolean, name: string) {
  return mobile ? page.getByRole('dialog', { name }) : page.getByRole('complementary', { name });
}

test('day.0821 (1:59915 · 1:60239): numbers, stage cards, band, basis; axe; screenshot', async ({
  page,
}, info) => {
  const problems = await watch(page);
  await page.goto('/day/2026-08-21?fixture=day.0821');
  const day = surface(page, isMobile(info), '8/21(금)');
  await expect(day.getByText('10,084,600원', { exact: true })).toBeVisible();
  await expect(day.getByText('▲ +12,300원 · +0.12%')).toBeVisible();
  await expect(day.getByText('이전 7/1 · 다음 9/9')).toBeVisible();
  await expect(day.getByText('KOSPI200 ETF 5주 · 33,800원')).toBeVisible();
  await expect(day.getByText('169,000원 · 수수료 25원')).toBeVisible();
  await expect(day.getByText('175,000원 → $125.93')).toBeVisible();
  await expect(day.getByText('환율 1,389.6원', { exact: true })).toBeVisible();
  await expect(day.getByText('S&P 500 ETF 2주 · $63.00')).toBeVisible();
  await expect(day.getByText('$126.00 · 수수료 $0.13')).toBeVisible();
  await expect(day.getByText('모의 체결')).toHaveCount(3);
  await expect(day.getByText('수수료 합계 206원')).toBeVisible();
  await expect(day.getByRole('img', { name: '전 52.3 → 후 50.2 · 목표 ±2%p' })).toBeVisible();
  await expect(day.getByText('2.3%p 벗어남')).toBeVisible();
  await expect(day.getByText('0.3%p 넘음 → 리밸런싱')).toBeVisible();
  await expect(
    day.getByText('기준 한국 8/20 종가 · 미국 8/20 종가(ET) · 환율 1,389.6원 08:30'),
  ).toBeVisible();
  await axe(page);
  await shoot(page, info, 'day.0821');
  expect(problems).toEqual([]);
});

test('390: the sheet covers the header, focus starts on the date, ‹ › move in place', async ({
  page,
}, info) => {
  test.skip(!isMobile(info), '390 only');
  await page.goto('/day/2026-08-21?fixture=day.0821');
  const sheet = page.getByRole('dialog', { name: '8/21(금)' });
  await expect(sheet).toBeVisible();
  const box = await sheet.boundingBox();
  expect(box).toMatchObject({ x: 0, y: 0, width: 390, height: 844 });
  await expect(sheet.getByRole('heading', { level: 1, name: '8/21(금)' })).toBeFocused();
  // The page behind is inert: Tab stays in the sheet.
  for (let i = 0; i < 6; i++) await page.keyboard.press('Tab');
  expect(await page.evaluate(() => Boolean(document.activeElement?.closest('dialog')))).toBe(true);
  await sheet.getByRole('link', { name: '다음 사건 9/9' }).click();
  await expect(page).toHaveURL(/\/day\/2026-09-09\?fixture=day\.0821$/);
  const next = page.getByRole('dialog', { name: '9/9(수)' });
  await expect(next.getByText('10,100,300원', { exact: true })).toBeVisible();
  await expect(next.getByText('시세 응답 없음')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page).toHaveURL(/\/history\?fixture=day\.0821$/);
});

test('1440: a 480 panel over the right column, the 기록 page stays (line + row)', async ({
  page,
}, info) => {
  test.skip(isMobile(info), '1440 only');
  await page.goto('/day/2026-08-21?fixture=day.0821');
  const panel = page.getByRole('complementary', { name: '8/21(금)' });
  await expect(panel).toBeVisible();
  expect(await panel.boundingBox()).toMatchObject({ x: 960, y: 64, width: 480 });
  await expect(page.getByRole('heading', { level: 1, name: '모의투자 기록 · 2026' })).toBeVisible();
  await expect(
    page.getByRole('region', { name: '사건 목록' }).getByRole('link', { name: /^8\/21\(금\)/ }),
  ).toHaveAttribute('aria-current', 'page');
  await panel.getByRole('link', { name: '이전 사건 7/1' }).click();
  await expect(page.getByRole('complementary', { name: '7/1(수)' })).toBeVisible();
  await expect(
    page.getByRole('region', { name: '사건 목록' }).getByRole('link', { name: /^7\/1\(수\)/ }),
  ).toHaveAttribute('aria-current', 'page');
  await page
    .getByRole('complementary', { name: '7/1(수)' })
    .getByRole('link', { name: '닫기' })
    .click();
  await expect(page).toHaveURL(/\/history\?fixture=day\.0821$/);
  await expect(page.getByRole('complementary')).toHaveCount(0);
});

for (const [state, path, name, checks] of [
  [
    'day.0925',
    '/day/2026-09-25',
    '9/25(금)',
    ['10,152,400원', '한국 휴장 · 거래 없음', '미국만 열린 날 · 확인은 돌았고 주문 0건'],
  ],
  [
    'day.partial',
    '/day/2026-10-07',
    '10/7(수)',
    ['리밸런싱 · 일부 실패', '다시 10/8 22:30', '시세 응답 없음'],
  ],
  [
    'day.1007',
    '/day/2026-10-07',
    '10/7(수)',
    ['리밸런싱 중', '진행 중 단계 보기', '약 $124.80 · 수수료 약 $0.12'],
  ],
  [
    'day.ai',
    '/day/2026-10-02',
    '10/2(금)',
    ['AI 확인 · 셀트리온', 'Sonnet · 약 2만 토큰', "두 번 다 '유지'"],
  ],
  ['day.weekend', '/day/2026-10-04', '10/4(일)', ['주말 · 확인 없음']],
  ['day.error', '/day/2026-08-21', '8/21(금)', ['그날 기록을 못 불러왔어요']],
] as const) {
  test(`${state}: renders, axe, screenshot`, async ({ page }, info) => {
    await page.goto(`${path}?fixture=${state}`);
    const day = surface(page, isMobile(info), name);
    for (const text of checks)
      await expect(day.getByText(text, { exact: true }).first()).toBeVisible();
    await axe(page);
    await shoot(page, info, state);
  });
}

test('day.loading: the date line stays, skeleton body', async ({ page }, info) => {
  await page.goto('/day/2026-08-21?fixture=day.loading');
  const day = surface(page, isMobile(info), '8/21(금)');
  await expect(day).toHaveAttribute('aria-busy', 'true');
  await expect(day.getByRole('heading', { name: '8/21(금)' })).toBeVisible();
  await shoot(page, info, 'day.loading');
});

test('완료 조건 day.permission: an alert link with no session goes to PIN and back to the same day', async ({
  page,
}) => {
  await page.goto('/day/2026-08-21?ledger=paper&fixture=day.permission');
  await expect(page).toHaveURL(/\/pin\?next=/);
  expect(new URL(page.url()).searchParams.get('next')).toBe(
    '/day/2026-08-21?ledger=paper&fixture=day.permission',
  );
});
