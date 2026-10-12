// SCR-MODE 모의투자·실전 in the browser: 완료 조건, the off modal's focus trap, axe, and screenshots of
// every state at 390×844 (and the drawn 1440×900 모의투자, 1:65140).
import { expect, test, type Page } from '@playwright/test';
import { axe, expectFocusTrapped, shoot, watch } from './ops-helpers';

async function open(page: Page, fixture: string) {
  await page.goto(`/mode?fixture=${fixture}`);
  await expect(page.getByRole('radiogroup', { name: '지금 모드' })).toBeVisible();
}

function card(page: Page, name: string) {
  return page.getByRole('region', { name });
}

async function fillTurnOn(page: Page, pin = '123456') {
  const turnOn = card(page, '실전으로 켜기');
  await turnOn.getByRole('checkbox', { name: '내용을 확인했고 실전으로 켤게요' }).check();
  await turnOn.getByLabel('PIN 6자리').fill(pin);
  return turnOn;
}

test.describe('SCR-MODE', () => {
  test('mode.paper: preview stage by stage, basis chips, outside-Toss line; ready with check + PIN', async ({
    page,
    isMobile,
  }, info) => {
    const problems = await watch(page);
    await open(page, 'mode.paper');
    const preview = card(page, '첫 주문 미리보기');
    await expect(preview.getByText('지금 · 원화 현금 10,000,000원')).toBeVisible();
    await expect(preview.getByText('환전 · 원→달러')).toBeVisible();
    await expect(preview.getByText('10/8 09:10 예상')).toBeVisible();
    await expect(preview.getByText('→ 약 $3,403')).toBeVisible();
    await expect(preview.getByText('매수 · 4건')).toBeVisible();
    await expect(preview.getByText('약 4,775,700원 · 약 $3,400')).toBeVisible();
    await expect(preview.getByText(/^매도 ·/)).toHaveCount(0);
    for (const chip of ['잔고 08:30', '현재가 16:00', '환율 1,382.4원 16:00']) {
      await expect(preview.getByText(chip, { exact: true })).toBeVisible();
    }
    await expect(
      preview.getByText('BTC 0.0027 · 약 355,000원 · 토스 밖 계좌라 이 미리보기에 없어요'),
    ).toBeVisible();
    const perf = card(page, '모의투자 성적');
    await expect(perf.getByRole('listitem')).toHaveText([
      '71회확인',
      '3회리밸런싱',
      '1회실패',
      '13건모의 체결',
    ]);
    await expect(perf.getByText('+2.44%')).toBeVisible();

    const button = card(page, '실전으로 켜기').getByRole('button', { name: '실전 켜기' });
    await expect(button).toBeDisabled();
    await fillTurnOn(page);
    await expect(button).toBeEnabled();

    if (!isMobile) {
      // 1440: left 7 of 12 (690), right 5 (486).
      const left = await perf.boundingBox();
      const right = await preview.boundingBox();
      expect(Math.round(left?.width ?? 0)).toBe(690);
      expect(Math.round(right?.width ?? 0)).toBe(486);
      await expect(perf.getByRole('listitem').first()).toBeVisible();
    }
    await shoot(page, info, 'mode.paper');
    expect(await axe(page)).toEqual([]);
    expect(problems).toEqual([]);
  });

  test('mode.paper: the 1단계 server refuses (409 live-not-available) with a line under the button', async ({
    page,
  }) => {
    await open(page, 'mode.paper');
    const turnOn = await fillTurnOn(page);
    await turnOn.getByRole('button', { name: '실전 켜기' }).click();
    await expect(turnOn.getByText('켜지 않았어요 · 토스 주문 연결 전')).toBeVisible();
    await expect(page.getByRole('radio', { name: '모의투자' })).toHaveAttribute(
      'aria-checked',
      'true',
    );
  });

  test('mode.turning-on: 바꾸는 중, the note, check kept and PIN cleared', async ({
    page,
  }, info) => {
    await open(page, 'mode.turning-on');
    const turnOn = await fillTurnOn(page);
    await turnOn.getByRole('button', { name: '실전 켜기' }).click();
    await expect(turnOn.getByRole('button', { name: '바꾸는 중' })).toBeDisabled();
    await expect(turnOn.getByText('실계좌 잔고 확인 중 · 다시 누를 수 없어요')).toBeVisible();
    await expect(turnOn.getByRole('checkbox')).toBeChecked();
    await expect(turnOn.getByLabel('PIN 6자리')).toHaveValue('');
    await shoot(page, info, 'mode.turning-on');
    expect(await axe(page)).toEqual([]);
  });

  test('mode.live: period chip, two ledgers, breakdown that adds up, 성적, 실전 끄기', async ({
    page,
  }, info) => {
    await open(page, 'mode.live');
    await expect(page.getByRole('radio', { name: '실전' })).toHaveAttribute('aria-checked', 'true');
    await expect(page.getByText('실전 9/1부터 · 27일째')).toBeVisible();
    const two = card(page, '두 장부');
    for (const [label, value] of [
      ['체결가', '−0.02%p'],
      ['실제 수수료', '−0.06%p'],
      ['기타 · 1주 단위·시작 시점', '−0.07%p'],
      ['합', '−0.15%p'],
    ] as const) {
      await expect(
        two.locator('div', { has: page.getByText(label, { exact: true }) }).last(),
      ).toContainText(value);
    }
    await expect(two.getByRole('link', { name: '실전 기록' })).toHaveAttribute(
      'href',
      '/history?ledger=live',
    );
    await expect(page.getByRole('button', { name: '실전 끄기' })).toBeVisible();
    await expect(card(page, '실전으로 켜기')).toHaveCount(0);
    await shoot(page, info, 'mode.live');
    expect(await axe(page)).toEqual([]);
  });

  test('mode.off-confirm: centred modal, focus trapped, no PIN; 끄기 returns to paper', async ({
    page,
  }, info) => {
    await open(page, 'mode.off-confirm');
    const opener = page.getByRole('button', { name: '실전 끄기' });
    await opener.click();
    const dialog = page.getByRole('dialog', { name: '실전을 끌까요?' });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText('매수 · 미국 · 22:30 대기')).toBeVisible();
    await expect(dialog.getByText('S&P 500 ETF 2주 · 약 $124.80')).toBeVisible();
    await expect(dialog.getByText('달러 현금 $125.67은 계좌에 남아요')).toBeVisible();
    await expect(dialog.getByLabel(/PIN/)).toHaveCount(0);
    await expect(dialog.getByRole('button', { name: '취소' })).toBeFocused();
    await expectFocusTrapped(page, dialog);
    await shoot(page, info, 'mode.off-confirm', { fullPage: false });
    expect(await axe(page)).toEqual([]);
    // Escape cancels and focus returns to the opener.
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(opener).toBeFocused();
    await opener.click();
    await dialog.getByRole('button', { name: '끄기' }).click();
    await expect(page.getByText('모의투자 · 실계좌 주문은 멈췄어요')).toBeVisible();
    await expect(page.getByText('실전 9/1~10/7 · 16:12에 끔')).toBeVisible();
    await expect(page.getByRole('radio', { name: '모의투자' })).toHaveAttribute(
      'aria-checked',
      'true',
    );
    // 실전 기록 › opens the live ledger's 기록.
    await page.getByRole('link', { name: '실전 기록' }).click();
    await expect(page).toHaveURL(/\/history\?ledger=live$/);
  });

  test('mode.off-failed: 취소 안 됨 1, banner, 모의투자 segment, red card; retry clears it', async ({
    page,
  }, info) => {
    await open(page, 'mode.off-failed');
    await expect(page.getByRole('banner').getByText('취소 안 됨 1')).toBeVisible();
    await expect(page.getByText('모의투자로 바뀜 · 미국 매수 주문 취소 안 됨')).toBeVisible();
    await expect(page.getByRole('radio', { name: '모의투자' })).toHaveAttribute(
      'aria-checked',
      'true',
    );
    const red = card(page, '취소 안 된 주문 · 토스 앱에서 확인');
    await expect(red.getByText('매수·미국 S&P 500 ETF 2주 · 약 $124.80')).toBeVisible();
    await expect(red.getByText('그대로 두면 22:30에 체결될 수 있어요')).toBeVisible();
    await shoot(page, info, 'mode.off-failed');
    expect(await axe(page)).toEqual([]);
    await red.getByRole('button', { name: '취소 다시 시도' }).click();
    await expect(red).toHaveCount(0);
    await expect(page.getByRole('banner').getByText('취소 안 됨 1')).toHaveCount(0);
  });

  test('mode.cancel-pending: the cancel Toss still has to carry out, and 켜기 closed until it ends', async ({
    page,
  }, info) => {
    await open(page, 'mode.cancel-pending');
    const pending = card(page, '취소 요청한 주문');
    await expect(pending.getByText('매수·미국 S&P 500 ETF 2주 · 약 $124.80')).toBeVisible();
    await expect(pending.getByText('다음 확인 때 토스에서 취소해요 · 5분 안')).toBeVisible();
    await expect(card(page, '취소 안 된 주문 · 토스 앱에서 확인')).toHaveCount(0);
    const turnOn = card(page, '실전으로 켜기');
    await expect(turnOn.getByText('지난 실전 주문의 취소가 끝나면 켤 수 있어요')).toBeVisible();
    await expect(turnOn.getByRole('button', { name: '실전 켜기' })).toBeDisabled();
    await shoot(page, info, 'mode.cancel-pending');
    expect(await axe(page)).toEqual([]);
  });

  test('mode.blocked: ✕ checks link to 작동, one cause, preview not computable, closed 켜기', async ({
    page,
  }, info) => {
    await open(page, 'mode.blocked');
    const checks = card(page, '켜기 전 점검');
    await expect(checks.getByRole('link', { name: /작동/ })).toHaveAttribute('href', '/health');
    await expect(checks.getByText('점검 1 · 미국 시세 낡음')).toBeVisible();
    await expect(page.getByText('첫 주문 계산 안 됨 · 10/7 16:00 조회')).toBeVisible();
    const turnOn = card(page, '실전으로 켜기');
    await expect(turnOn.getByRole('checkbox')).toBeDisabled();
    await expect(turnOn.getByRole('button', { name: '실전 켜기' })).toBeDisabled();
    await expect(turnOn.getByText('점검 1개(미국 시세) 해결 뒤 켤 수 있어요')).toBeVisible();
    await shoot(page, info, 'mode.blocked');
    expect(await axe(page)).toEqual([]);
  });

  for (const [id, text] of [
    ['mode.short', '기간 짧음 · 30거래일부터 수익률'],
    ['mode.empty', '아직 모의투자 기록 없음 · 첫 확인 7/1(수) 08:30'],
    ['mode.live-not-available', '토스 주문 연결 뒤 켤 수 있어요'],
    ['mode.live-stale', '미국 시세 10/2 기준 · 2거래일째 갱신 없음'],
    // 3단계: the link's cause and what to do; the old picture counts as the same cause.
    ['mode.link-off', '주문 열쇠 꺼짐 · Claude에게 서버 cron 줄 수정 요청'],
  ] as const) {
    test(`${id}: ${text}`, async ({ page }, info) => {
      await open(page, id);
      await expect(page.getByText(text)).toBeVisible();
      await shoot(page, info, id);
      expect(await axe(page)).toEqual([]);
    });
  }

  test('mode.preview-changed: new numbers, the recompute chip, unchecked', async ({
    page,
  }, info) => {
    await open(page, 'mode.preview-changed');
    const turnOn = await fillTurnOn(page);
    await turnOn.getByRole('button', { name: '실전 켜기' }).click();
    await expect(page.getByText('16:10 다시 계산 · 금액 바뀜')).toBeVisible();
    await expect(page.getByText('→ 약 $3,341')).toBeVisible();
    await expect(turnOn.getByRole('checkbox')).not.toBeChecked();
    await shoot(page, info, 'mode.preview-changed');
    expect(await axe(page)).toEqual([]);
  });

  test('mode.loading: skeletons', async ({ page }, info) => {
    await page.goto('/mode?fixture=mode.loading');
    await expect(page.locator('main [aria-busy="true"]')).toBeVisible();
    await shoot(page, info, 'mode.loading');
  });

  test('mode.permission: no session → 입장 → back to 모의투자·실전', async ({ page }) => {
    await page.goto('/mode?fixture=mode.permission');
    await expect(page).toHaveURL(/\/pin\?next=/);
    await page.getByLabel('PIN 6자리').fill('123456');
    await expect(page).toHaveURL(/\/mode/);
    await expect(page.getByRole('radiogroup', { name: '지금 모드' })).toBeVisible();
  });
});
