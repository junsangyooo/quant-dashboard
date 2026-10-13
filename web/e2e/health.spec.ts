// SCR-HEALTH 작동 in the browser: 완료 조건, axe, screenshots of every state at 390×844 (and the
// drawn 1440×900 할 일 1, 1:63806).
import { expect, test } from '@playwright/test';
import { axe, pinClock, shoot, watch } from './ops-helpers';

const SIX = ['한국 시세', '미국 시세', '환율', '토스 연결', '토스 잔고 대조', '알림 기기'];

test.describe('SCR-HEALTH', () => {
  test('health.todo: 정상 · 할 일 1 without a banner, six sources, 14 days, device list', async ({
    page,
    isMobile,
  }, info) => {
    const problems = await watch(page);
    await page.goto('/health?fixture=health.todo');
    await expect(page.getByRole('heading', { level: 2, name: '정상' })).toBeVisible();
    await expect(page.getByRole('banner').getByText('정상 · 08:30 확인')).toBeVisible();
    await expect(page.getByText('자료 6개 중 할 일 1')).toBeVisible();
    await expect(page.getByText('할 일 1', { exact: true })).toBeVisible();
    await expect(page.getByRole('article', { name: '토스 연결 만료 예정 · 10/19' })).toBeVisible();
    const names = page.getByRole('region', { name: '자료별' }).locator('[class*="rowName"]');
    await expect(names).toHaveText(SIX);
    await expect(page.getByText('10/7 08:30 확인 · 리밸런싱 시작 · 42초')).toBeVisible();
    await expect(
      page.getByRole('group', { name: '최근 14일 확인 달력' }).getByRole('button'),
    ).toHaveCount(10);

    if (!isMobile) {
      // 1440: 종합 · 할 일 · 14일 in the left 4 of 12 columns, 자료별 in the right 8.
      const sources = await page.getByRole('region', { name: '자료별' }).boundingBox();
      const recent = await page.getByRole('region', { name: '최근 14일 확인' }).boundingBox();
      expect(Math.round(sources?.width ?? 0)).toBe(792);
      expect(Math.round(sources?.x ?? 0)).toBe(120 + 384 + 24);
      expect(Math.round(recent?.width ?? 0)).toBe(384);
      expect(Math.round(recent?.x ?? 0)).toBe(120);
    }
    await shoot(page, info, 'health.todo');
    expect(await axe(page)).toEqual([]);

    // The push row opens the device list (no drawing).
    await page.getByRole('button', { name: /알림 기기/ }).click();
    await expect(page.getByText('iPhone · 홈 화면 앱')).toBeVisible();
    await expect(page.getByText('마지막 전달 10/6 16:01')).toBeVisible();
    await expect(page.getByRole('link', { name: '알림 설정' })).toHaveAttribute(
      'href',
      '/account#notifications',
    );
    // A cell shows its line under the grid.
    await page.getByRole('button', { name: '9/30(수) 정상 실행' }).click();
    await expect(page.getByText('9/30 08:30 확인 · 목표 범위 안 · 10초')).toBeVisible();
    await shoot(page, info, 'health.todo-open');
    expect(await axe(page)).toEqual([]);
    expect(problems).toEqual([]);
  });

  test('health.stale: 점검 1 by cause, red card with its retry time, stale bar', async ({
    page,
  }, info) => {
    await page.goto('/health?fixture=health.stale');
    await expect(page.getByRole('heading', { level: 2, name: '점검 1' })).toBeVisible();
    await expect(page.getByRole('banner').getByText('점검 1')).toBeVisible();
    await expect(page.getByText('미국 시세 10/2 기준 · 2거래일째 갱신 없음')).toBeVisible();
    await expect(page.getByText('점검 1 · 할 일 1')).toBeVisible();
    const card = page.getByRole('article', { name: '미국 시세 10/2 기준 · 2거래일째' });
    await expect(card.getByText('10/8 06:20 자동 재시도')).toBeVisible();
    await expect(card).toContainText('그동안 주문 0건 · 실전 켜기 막힘');
    await expect(page.getByText('14일 중 실패 0 · 시세 대기 2')).toBeVisible();
    await expect(page.getByText('10/7 08:30 확인 · 시세 대기 · 주문 0건')).toBeVisible();
    await shoot(page, info, 'health.stale');
    expect(await axe(page)).toEqual([]);
  });

  test('health.unknown: grey 확인 불가, 상태 모름, reload, values —, header 확인 불가', async ({
    page,
  }, info) => {
    await pinClock(page);
    await page.goto('/health?fixture=health.unknown');
    await expect(page.getByRole('heading', { level: 2, name: '확인 불가' })).toBeVisible();
    await expect(page.getByText('상태를 못 불러왔어요 · 16:10 시도')).toBeVisible();
    await expect(page.getByText('마지막으로 받은 상태 10/7 08:30')).toBeVisible();
    await expect(page.getByText('상태 모름')).toBeVisible();
    await expect(page.getByRole('button', { name: '다시 불러오기' })).toBeVisible();
    await expect(page.getByRole('banner').getByText('확인 불가')).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('정상', { exact: true })).toHaveCount(0);
    await shoot(page, info, 'health.unknown');
    expect(await axe(page)).toEqual([]);
  });

  test('health.failed: 09:30 자동 재시도, 주문은 나가지 않았어요, 실패 1', async ({
    page,
  }, info) => {
    await page.goto('/health?fixture=health.failed');
    await expect(page.getByRole('heading', { level: 2, name: '확인 실패' })).toBeVisible();
    await expect(page.getByRole('banner').getByText('확인 실패')).toBeVisible();
    await expect(page.getByText('09:30 자동 재시도', { exact: true })).toBeVisible();
    await expect(page.getByText(/주문은 나가지 않았어요/)).toBeVisible();
    await expect(page.getByText('14일 중 실패 1')).toBeVisible();
    await expect(page.getByText('10/7 08:30 확인 실패 · 시세 응답 없음 · 12초')).toBeVisible();
    await shoot(page, info, 'health.failed');
    expect(await axe(page)).toEqual([]);
  });

  test('health.empty: 첫 확인 전, grey bars, empty cells', async ({ page }, info) => {
    await page.goto('/health?fixture=health.empty');
    await expect(page.getByRole('heading', { level: 2, name: '첫 확인 전' })).toBeVisible();
    await expect(page.getByText('첫 확인 7/1(수) 08:30 예정')).toBeVisible();
    await expect(page.locator('[class*="ageFill"]')).toHaveCount(0);
    await shoot(page, info, 'health.empty');
    expect(await axe(page)).toEqual([]);
  });

  test('health.loading: skeleton frame, no 정상', async ({ page }, info) => {
    await page.goto('/health?fixture=health.loading');
    await expect(page.locator('main [aria-busy="true"]')).toBeVisible();
    await expect(page.getByText('정상', { exact: true })).toHaveCount(0);
    await shoot(page, info, 'health.loading');
  });

  test('health.live: the live to-dos and the Toss rows say what is wrong and what to do', async ({
    page,
  }, info) => {
    await page.goto('/health?fixture=health.live');
    const mismatch = page.getByRole('article', { name: '토스 잔고와 장부가 달라요' });
    await expect(mismatch.getByText(/KOSPI200 ETF 장부 156주 · 토스 160주/)).toBeVisible();
    await expect(mismatch).toContainText('그동안 주문 0건 · 실전 켜기 막힘');
    const link = page.getByRole('article', { name: '토스 연결 · 다른 프로그램과 키 겹침' });
    await expect(link).toContainText('Claude에게 옛 quant cron 줄 삭제 요청');
    // No conversion to-do (D47): the 원화 · 달러 card sits beside the to-dos, not among them.
    await expect(page.getByRole('article')).toHaveCount(2);
    const money = page.getByRole('region', { name: '원화 · 달러' });
    await expect(money).toContainText('약 1,500,000원을 달러로 바꾸면 50:50');
    await expect(money).toContainText('새로 들어온 돈 3,000,000원 · 다음 거래일 08:30부터 써요');
    await expect(
      page.getByText('다른 프로그램과 키 겹침 · 마지막 성공 15:50 · 확인마다'),
    ).toBeVisible();
    await expect(page.getByText('15:50 불일치 · 확인마다')).toBeVisible();
    await shoot(page, info, 'health.live');
    expect(await axe(page)).toEqual([]);
  });

  test('health.phase2: 공시 · AI 호출 · 지표 표 rows when listed', async ({ page }, info) => {
    await page.goto('/health?fixture=health.phase2');
    const names = page.getByRole('region', { name: '자료별' }).locator('[class*="rowName"]');
    await expect(names).toHaveText([...SIX, '공시', 'AI 호출', '지표 표']);
    await expect(page.getByText('한국 공시 감시 멈춤', { exact: false })).toBeVisible();
    await shoot(page, info, 'health.phase2');
    expect(await axe(page)).toEqual([]);
  });

  test('health.permission: no session → 입장 → back to 작동', async ({ page, isMobile }) => {
    await page.goto('/health?fixture=health.permission');
    await expect(page).toHaveURL(/\/pin\?next=/);
    if (isMobile) {
      for (const d of '123456') {
        await page
          .getByRole('group', { name: '숫자 키패드' })
          .getByRole('button', { name: d, exact: true })
          .click();
      }
    } else {
      await page.keyboard.type('123456');
    }
    await expect(page).toHaveURL(/\/health/);
    await expect(page.getByRole('heading', { level: 2, name: '정상' })).toBeVisible();
  });
});
