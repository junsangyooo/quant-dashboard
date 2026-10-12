// SCR-ACCOUNT 설정 in the browser: 완료 조건, the logout-others modal's focus trap, the PIN change by
// keyboard, axe, and screenshots of every state at 390×844 (drawn: 1:65384 · 1:65568; 1440 has no
// drawing — the same order in one 640 column).
import { expect, test, type Page } from '@playwright/test';
import { axe, expectFocusTrapped, shoot, watch } from './ops-helpers';

async function open(page: Page, fixture: string) {
  await page.goto(`/account?fixture=${fixture}`);
  await expect(notifications(page)).toBeVisible();
}

function notifications(page: Page) {
  return page.getByRole('region', { name: '알림' });
}

function eventSwitch(page: Page, name: string) {
  return notifications(page).getByRole('switch', { name, exact: true });
}

/**
 * The person's answer to the browser's permission prompt. Headless Chromium has no prompt and
 * reports 'denied' even after grantPermissions, so the page's Notification answers instead and
 * counts how often it was asked.
 */
async function answerPermission(page: Page, answer: 'granted' | 'denied') {
  await page.addInitScript((reply) => {
    let permission: NotificationPermission = 'default';
    const box = window as unknown as { __permissionAsked: number };
    box.__permissionAsked = 0;
    Object.defineProperty(Notification, 'permission', {
      configurable: true,
      get: () => permission,
    });
    Notification.requestPermission = () => {
      box.__permissionAsked += 1;
      permission = reply;
      return Promise.resolve(permission);
    };
  }, answer);
}

function asked(page: Page): Promise<number> {
  return page.evaluate(
    () => (window as unknown as { __permissionAsked: number }).__permissionAsked,
  );
}

test.describe('SCR-ACCOUNT', () => {
  test('account.default: PIN · 기기 · 알림, six events on, 확인 실패 locked, saves at once, a row per device', async ({
    page,
    isMobile,
  }, info) => {
    const problems = await watch(page);
    await open(page, 'account.default');
    await expect(page.getByRole('heading', { level: 1, name: '설정' })).toBeVisible();
    const pin = await page.getByRole('region', { name: 'PIN 바꾸기' }).boundingBox();
    const devices = await page.getByRole('region', { name: '기기' }).boundingBox();
    const notes = await notifications(page).boundingBox();
    expect((pin?.y ?? 0) < (devices?.y ?? 0) && (devices?.y ?? 0) < (notes?.y ?? 0)).toBe(true);
    if (!isMobile) expect(Math.round(notes?.width ?? 0)).toBe(640);

    const card = page.getByRole('region', { name: '기기' });
    await expect(card.getByText('iPhone · 홈 화면 앱')).toBeVisible();
    await expect(card.getByText('들어온 시각 10/1 08:12')).toBeVisible();
    await expect(card.getByText('이 기기', { exact: true })).toBeVisible();

    await expect(
      notifications(page).getByRole('switch', { name: '이 기기에서 알림 받기' }),
    ).toBeChecked();
    await expect(notifications(page).getByText('받을 사건 · 처음부터 6개 켜짐')).toBeVisible();
    for (const name of [
      '확인 실패',
      '자료 낡음',
      '주간 정상 요약',
      '실전 체결',
      'PIN 실패 급증',
      '토스 연결 만료 예정',
    ]) {
      await expect(eventSwitch(page, name)).toBeChecked();
    }
    for (const name of ['확인 누락', '리밸런싱 예고', '입출금·직접 매매']) {
      await expect(eventSwitch(page, name)).not.toBeChecked();
    }
    await expect(eventSwitch(page, '확인 실패')).toBeDisabled();
    await expect(notifications(page).getByText('일부 실패 포함 · 끌 수 없어요')).toBeVisible();
    await expect(notifications(page).getByText('끄면 서버가 멈춰도 알 수 없게 돼요')).toBeVisible();
    await expect(
      notifications(page).getByRole('switch', { name: '알림에 금액 숨기기' }),
    ).not.toBeChecked();
    await expect(notifications(page).getByText('10/7 15:38 저장됨')).toBeVisible();
    await expect(notifications(page).getByText(/받음$/)).toHaveText([
      '10/7 15:40 받음',
      '10/7 15:40 받음',
    ]);
    await shoot(page, info, 'account.default');
    expect(await axe(page)).toEqual([]);

    // A switch saves at once; the test push answers per device.
    await eventSwitch(page, '리밸런싱 예고').click();
    await expect(eventSwitch(page, '리밸런싱 예고')).toBeChecked();
    await expect(notifications(page).getByText('10/7 16:10 저장됨')).toBeVisible();
    await notifications(page).getByRole('button', { name: '시험 알림 보내기' }).click();
    await expect(notifications(page).getByText(/받음$/)).toHaveText([
      '10/7 16:10 받음',
      '10/7 16:10 받음',
    ]);
    expect(problems).toEqual([]);
  });

  test('logout-others: confirm modal holds the focus; Escape cancels; 로그아웃 logs the others out', async ({
    page,
  }, info) => {
    await open(page, 'account.default');
    const opener = page.getByRole('button', { name: '다른 기기 모두 로그아웃' });
    await opener.click();
    const dialog = page.getByRole('dialog', { name: '다른 기기를 모두 로그아웃할까요?' });
    await expect(dialog).toBeVisible();
    await expect(
      dialog.getByText('이 기기만 남고 다른 기기는 PIN을 다시 넣어야 해요'),
    ).toBeVisible();
    await expect(dialog.getByRole('button', { name: '취소' })).toBeFocused();
    await expectFocusTrapped(page, dialog);
    await shoot(page, info, 'account.logout-others', { fullPage: false });
    expect(await axe(page)).toEqual([]);
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(opener).toBeFocused();
    await opener.click();
    await dialog.getByRole('button', { name: '로그아웃', exact: true }).click();
    await expect(page.getByText('다른 기기 로그아웃됨')).toBeVisible();
  });

  test('이 기기 로그아웃 ends this session and goes to 입장', async ({ page }) => {
    await open(page, 'account.default');
    const card = page.getByRole('region', { name: '기기' });
    // Each button says what it does in one line above it.
    await expect(card.getByText('이 기기에서만 나가요')).toBeVisible();
    await expect(card.getByText('휴대폰을 잃어버렸을 때 · 이 기기만 남겨요')).toBeVisible();
    await card.getByRole('button', { name: '이 기기 로그아웃', exact: true }).click();
    await expect(page).toHaveURL(/\/pin$/);
  });

  test('PIN change by keyboard: three fields, Tab between them, Enter sends', async ({
    page,
  }, info) => {
    await open(page, 'account.default');
    const card = page.getByRole('region', { name: 'PIN 바꾸기' });
    const toggle = card.getByRole('button', { name: 'PIN 바꾸기' });
    await toggle.focus();
    await page.keyboard.press('Enter');
    await expect(toggle).toHaveAttribute('aria-expanded', 'true');
    await expect(card.getByLabel('현재 PIN')).toBeFocused();
    // Different new PINs: nothing is sent and the second field clears.
    await page.keyboard.type('111111');
    await page.keyboard.press('Tab');
    await page.keyboard.type('222222');
    await page.keyboard.press('Tab');
    await page.keyboard.type('333333');
    await page.keyboard.press('Enter');
    await expect(card.getByText('두 PIN이 달라요')).toBeVisible();
    await expect(card.getByLabel('새 PIN 다시')).toHaveValue('');
    await shoot(page, info, 'account.pin-mismatch');
    expect(await axe(page)).toEqual([]);
    await card.getByLabel('새 PIN 다시').focus();
    await page.keyboard.type('222222');
    await page.keyboard.press('Enter');
    await expect(card.getByText('바꿨어요 · 다른 기기 로그아웃됨')).toBeVisible();
    for (const label of ['현재 PIN', '새 PIN', '새 PIN 다시']) {
      await expect(card.getByLabel(label, { exact: true })).toHaveValue('');
    }
  });

  test('account.pin-error: 현재 PIN이 맞지 않아요 and that field clears', async ({
    page,
  }, info) => {
    await open(page, 'account.pin-error');
    const card = page.getByRole('region', { name: 'PIN 바꾸기' });
    await card.getByRole('button', { name: 'PIN 바꾸기' }).click();
    await card.getByLabel('현재 PIN').fill('999999');
    await card.getByLabel('새 PIN', { exact: true }).fill('222222');
    await card.getByLabel('새 PIN 다시').fill('222222');
    await card.getByRole('button', { name: '바꾸기', exact: true }).click();
    await expect(card.getByText('현재 PIN이 맞지 않아요')).toBeVisible();
    await expect(card.getByLabel('현재 PIN')).toHaveValue('');
    await expect(card.getByLabel('새 PIN', { exact: true })).toHaveValue('222222');
    await shoot(page, info, 'account.pin-error');
    expect(await axe(page)).toEqual([]);
  });

  test('account.no-push: an iPhone Safari tab cannot receive, with the fix; events and the test stay', async ({
    page,
  }, info) => {
    await open(page, 'account.no-push');
    const card = notifications(page);
    await expect(card.getByText('이 기기는 알림을 못 받아요 · Safari 탭')).toBeVisible();
    await expect(card.getByText('공유 → 홈 화면에 추가 → 앱에서 다시 켜기')).toBeVisible();
    await expect(card.getByRole('switch', { name: '이 기기에서 알림 받기' })).not.toBeChecked();
    await expect(eventSwitch(page, '자료 낡음')).toBeEnabled();
    await expect(card.getByRole('button', { name: '시험 알림 보내기' })).toBeEnabled();
    await shoot(page, info, 'account.no-push');
    expect(await axe(page)).toEqual([]);
  });

  test('account.empty: the start line, no test push; the switch asks the browser, 501 reads 준비 중', async ({
    page,
  }, info) => {
    await answerPermission(page, 'granted');
    await open(page, 'account.empty');
    const card = notifications(page);
    await expect(card.getByText('이 기기에서 알림 받기를 눌러 시작해요')).toBeVisible();
    await expect(card.getByRole('button', { name: '시험 알림 보내기' })).toBeDisabled();
    await expect(card.getByText(/받음$/)).toHaveCount(0);
    expect(await asked(page)).toBe(0);
    await shoot(page, info, 'account.empty');
    expect(await axe(page)).toEqual([]);
    await card.getByRole('switch', { name: '이 기기에서 알림 받기' }).click();
    await expect(card.getByText('알림은 준비 중이에요 · 다음 단계에서 켤 수 있어요')).toBeVisible();
    await expect(card.getByText('켜지 못했어요 · 다시 시도')).toHaveCount(0);
    expect(await asked(page)).toBe(1);
  });

  test('a denied permission says this device cannot receive and how to allow it', async ({
    page,
  }) => {
    await answerPermission(page, 'denied');
    await open(page, 'account.empty');
    const card = notifications(page);
    await card.getByRole('switch', { name: '이 기기에서 알림 받기' }).click();
    await expect(card.getByText('이 기기는 알림을 못 받아요 · 알림 차단됨')).toBeVisible();
    await expect(card.getByText('브라우저 설정 → 알림 허용 → 다시 켜기')).toBeVisible();
    await expect(card.getByRole('switch', { name: '이 기기에서 알림 받기' })).not.toBeChecked();
  });

  test('account.push-not-ready: the 1·2단계 server folds 알림 into one disabled row', async ({
    page,
  }, info) => {
    await open(page, 'account.push-not-ready');
    const card = notifications(page);
    await expect(card.getByText('3단계에서 켤 수 있어요')).toBeVisible();
    await expect(card.getByRole('switch')).toHaveCount(1);
    await expect(card.getByRole('switch', { name: '알림' })).toBeDisabled();
    await expect(card.getByRole('switch', { name: '알림' })).not.toBeChecked();
    await expect(card.getByText(/받을 사건/)).toHaveCount(0);
    await expect(card.getByRole('button', { name: '시험 알림 보내기' })).toHaveCount(0);
    // The PIN card says what it does before it opens.
    await expect(page.getByText('들어올 때 넣는 6자리를 바꿔요')).toBeVisible();
    await shoot(page, info, 'account.push-not-ready');
    expect(await axe(page)).toEqual([]);
  });

  test('account.loading: skeletons', async ({ page }, info) => {
    await page.goto('/account?fixture=account.loading');
    await expect(page.locator('main [aria-busy="true"]')).toBeVisible();
    await shoot(page, info, 'account.loading');
  });

  test('account.error: 설정을 못 불러왔어요 → 다시 불러오기 loads', async ({ page }, info) => {
    await page.goto('/account?fixture=account.error');
    await expect(page.getByText('설정을 못 불러왔어요')).toBeVisible();
    await shoot(page, info, 'account.error');
    expect(await axe(page)).toEqual([]);
    await page.getByRole('button', { name: '다시 불러오기' }).click();
    await expect(notifications(page)).toBeVisible();
  });

  test('account.permission: no session → 입장 → back to 설정', async ({ page }) => {
    await page.goto('/account?fixture=account.permission');
    await expect(page).toHaveURL(/\/pin\?next=/);
    await page.getByLabel('PIN 6자리').fill('123456');
    await expect(page).toHaveURL(/\/account/);
    await expect(notifications(page)).toBeVisible();
  });
});
