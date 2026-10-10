// SCR-PIN 입장 in the browser: the 완료 조건, keyboard entry, axe, and screenshots of every state
// (390 drawn: 1:51276 · 1:51328 · 1:51378; 1440 has no drawing — the same column, keyboard only).
import { expect, test, type Page } from '@playwright/test';
import { axe, pinClock, shoot, watch } from './ops-helpers';

const PROMPT = 'PIN 6자리';

async function keypad(page: Page, digits: string) {
  const pad = page.getByRole('group', { name: '숫자 키패드' });
  for (const d of digits) await pad.getByRole('button', { name: d, exact: true }).click();
}

/** 390 taps the keypad; 1440 (no keypad) types on the keyboard. */
async function enter(page: Page, digits: string, isMobile: boolean) {
  if (isMobile) await keypad(page, digits);
  else {
    await page.getByLabel(PROMPT).focus();
    await page.keyboard.type(digits);
  }
}

test.describe('SCR-PIN', () => {
  test('pin.entering: only the wordmark, PIN 6자리, six cells, keypad and 잊었을 때 — no request', async ({
    page,
    isMobile,
  }, info) => {
    const problems = await watch(page);
    const api: string[] = [];
    page.on('request', (r) => {
      if (new URL(r.url()).pathname.startsWith('/api/')) api.push(r.url());
    });
    await page.goto('/pin?fixture=pin.entering');
    await expect(page.getByRole('heading', { level: 1, name: 'quant' })).toBeVisible();
    await expect(page.getByText(PROMPT, { exact: true })).toBeVisible();
    await expect(page.locator('[class*="pinCell"]')).toHaveCount(6);
    await expect(page.getByRole('button', { name: '잊었을 때' })).toBeVisible();
    if (isMobile) {
      await expect(
        page.getByRole('group', { name: '숫자 키패드' }).getByRole('button'),
      ).toHaveCount(11);
      await expect(page.getByLabel(PROMPT)).toHaveAttribute('inputmode', 'none');
    } else {
      await expect(page.getByRole('group', { name: '숫자 키패드' })).toHaveCount(0);
      await expect(page.getByLabel(PROMPT)).toHaveAttribute('inputmode', 'numeric');
      // The column is 360 wide and centred.
      const box = await page.locator('main').boundingBox();
      expect(Math.round(box?.width ?? 0)).toBe(360);
    }
    expect(await page.locator('main').textContent()).not.toMatch(/원|%|\$/);
    await enter(page, '123', isMobile);
    await expect(page.getByLabel(PROMPT)).toHaveValue('123');
    await page.getByRole('button', { name: '잊었을 때' }).click();
    await expect(
      page.getByText('PIN을 잊었다면 서버에서 다시 정해요 · Claude에게 요청'),
    ).toBeVisible();
    await shoot(page, info, 'pin.entering');
    expect(await axe(page)).toEqual([]);
    expect(api).toEqual([]);
    expect(problems).toEqual([]);
  });

  test('keyboard entry: the sixth digit submits and the page returns to next', async ({ page }) => {
    const next = '/day/2026-08-21?ledger=paper';
    await page.goto(`/pin?fixture=pin.entering&next=${encodeURIComponent(next)}`);
    await expect(page.getByLabel(PROMPT)).toBeFocused();
    await page.keyboard.type('12x3456');
    await expect(page).toHaveURL(/\/day\/2026-08-21\?ledger=paper$/);
  });

  test('a link to the day panel opens the same panel after the PIN (알림 링크)', async ({
    page,
    isMobile,
  }) => {
    await page.goto(
      `/pin?fixture=pin.entering&next=${encodeURIComponent('/day/2026-08-21?ledger=paper')}`,
    );
    await enter(page, '482915', isMobile);
    await expect(page).toHaveURL(/\/day\/2026-08-21\?ledger=paper$/);
  });

  test('pin.error: red empty cells and the tries left; the keypad keeps working', async ({
    page,
    isMobile,
  }, info) => {
    await page.goto('/pin?fixture=pin.error');
    await enter(page, '000000', isMobile);
    await expect(page.getByText('PIN이 맞지 않아요 · 남은 시도 2회')).toBeVisible();
    await expect(page.getByLabel(PROMPT)).toHaveValue('');
    await expect(page.locator('[class*="pin-error"]')).toHaveCount(6);
    if (isMobile) await expect(page.getByRole('button', { name: '1', exact: true })).toBeEnabled();
    await page.getByRole('button', { name: '잊었을 때' }).click();
    await shoot(page, info, 'pin.error');
    expect(await axe(page)).toEqual([]);
  });

  test('pin.locked: locked here until 16:40, the note, and a keypad that cannot be pressed', async ({
    page,
    isMobile,
  }, info) => {
    await pinClock(page);
    await page.goto('/pin?fixture=pin.locked');
    await enter(page, '123456', isMobile);
    await expect(page.getByText('16:40까지 잠김 · 이 접속 위치')).toBeVisible();
    await expect(
      page.getByText('이미 열린 기기는 그대로 써요 · 실전 끄기도 그 기기에서 돼요'),
    ).toBeVisible();
    await expect(page.getByLabel(PROMPT)).toBeDisabled();
    if (isMobile) {
      for (const key of await page
        .getByRole('group', { name: '숫자 키패드' })
        .getByRole('button')
        .all()) {
        await expect(key).toBeDisabled();
      }
    }
    await page.getByRole('button', { name: '잊었을 때' }).click();
    await shoot(page, info, 'pin.locked');
    expect(await axe(page)).toEqual([]);
  });

  test('pin.global-lock: the clock icon line and minutes left', async ({
    page,
    isMobile,
  }, info) => {
    await pinClock(page);
    await page.goto('/pin?fixture=pin.global-lock');
    await enter(page, '123456', isMobile);
    await expect(page.getByText('시도가 많아요 · 42분 뒤 다시')).toBeVisible();
    await expect(page.getByLabel(PROMPT)).toBeDisabled();
    await shoot(page, info, 'pin.global-lock');
    expect(await axe(page)).toEqual([]);
  });

  test('pin.hold: closed until the server unlocks it — the command, no time', async ({
    page,
    isMobile,
  }, info) => {
    await pinClock(page);
    await page.goto('/pin?fixture=pin.hold');
    await enter(page, '123456', isMobile);
    await expect(page.getByText('새 로그인이 닫혔어요 · 서버에서 열어야 해요')).toBeVisible();
    await expect(page.getByText('python -m autotrade.jobs unlock')).toBeVisible();
    await expect(
      page.getByText('이미 열린 기기는 그대로 써요 · 실전 끄기도 그 기기에서 돼요'),
    ).toBeVisible();
    await expect(page.getByLabel(PROMPT)).toBeDisabled();
    await shoot(page, info, 'pin.hold');
    expect(await axe(page)).toEqual([]);
  });

  test('pin.no-pin: the server-CLI guidance, nothing to type', async ({ page, isMobile }, info) => {
    await page.goto('/pin?fixture=pin.no-pin');
    await enter(page, '123456', isMobile);
    await expect(page.getByText('PIN이 아직 없어요 · 서버에서 먼저 정해요')).toBeVisible();
    await expect(page.getByText('python -m autotrade.jobs set-pin')).toBeVisible();
    await expect(page.getByLabel(PROMPT)).toBeDisabled();
    await shoot(page, info, 'pin.no-pin');
    expect(await axe(page)).toEqual([]);
  });

  test('pin.loading: six dots kept, a small spinner, closed keypad', async ({
    page,
    isMobile,
  }, info) => {
    await page.goto('/pin?fixture=pin.loading');
    await enter(page, '123456', isMobile);
    await expect(page.getByText('확인 중')).toBeAttached();
    await expect(page.locator('[class*="pinDot"]')).toHaveCount(6);
    await expect(page.getByLabel(PROMPT)).toBeDisabled();
    await shoot(page, info, 'pin.loading');
  });
});
