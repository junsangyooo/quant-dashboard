// SCR-HEALTH 작동 — 기획 §5 완료 조건 (lines 719–727) and the spec's states.
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { copy } from '../../src/copy';
import { healthCopy } from '../../src/copy/health';
import healthEmpty from '../../src/fixtures/bundles/health.empty';
import healthFailed from '../../src/fixtures/bundles/health.failed';
import healthLoading from '../../src/fixtures/bundles/health.loading';
import healthPhase2 from '../../src/fixtures/bundles/health.phase2';
import healthStale from '../../src/fixtures/bundles/health.stale';
import healthTodo from '../../src/fixtures/bundles/health.todo';
import healthUnknown from '../../src/fixtures/bundles/health.unknown';
import homePaper from '../../src/fixtures/bundles/home.paper';
import { renderApp, serve } from './ops';

const SIX = ['한국 시세', '미국 시세', '환율', '토스 연결', '토스 잔고 대조', '알림 기기'];

function sourcesCard() {
  return screen.getByRole('region', { name: healthCopy.sources.title });
}

function sourceRows() {
  return within(sourcesCard())
    .getAllByRole('listitem')
    .filter((li) => li.querySelector('[class*="ageBar"]'));
}

function recentCard() {
  return screen.getByRole('region', { name: healthCopy.recent.title });
}

afterEach(() => {
  vi.useRealTimers();
});

describe('작동 (SCR-HEALTH)', () => {
  it('has the ‹ 작동 title and no bottom tabs', async () => {
    serve(healthTodo);
    renderApp('/health');
    expect(screen.getByRole('heading', { level: 1, name: copy.pages.health })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: copy.back })).toHaveAttribute('href', '/');
    await screen.findByRole('heading', { level: 2, name: '정상' });
    expect(screen.getAllByRole('navigation')).toHaveLength(1);
  });

  it('shows each of the six sources with basis · received · cadence, an age bar and a chip', async () => {
    serve(healthTodo);
    renderApp('/health');
    await screen.findByRole('heading', { level: 2, name: '정상' });
    const rows = sourceRows();
    expect(rows.map((r) => r.querySelector('[class*="rowName"]')?.textContent)).toEqual(SIX);
    const lines = rows.map((r) => r.querySelector('[class*="rowLine"]')?.textContent);
    expect(lines).toEqual([
      '10/7 종가 · 16:00 받음 · 매일',
      '10/6 종가(ET) · 06:20 받음 · 매일',
      '1,382.4원 · 16:00 받음 · 매일',
      '만료 10/19 · 12일 남음 · 90일마다 갱신',
      '08:30 일치 · 확인마다',
      '2대 · 마지막 전달 10/7 08:31',
    ]);
    const chips = rows.map(
      (r) => within(r).getAllByText(/제때|늦음|낡음|만료 \d+일 전/)[0]?.textContent,
    );
    expect(chips).toEqual(['제때', '제때', '제때', '만료 12일 전', '제때', '제때']);
    for (const row of rows) {
      const bar = row.querySelector('[class*="ageBar"]');
      expect(bar?.querySelectorAll('[class*="zone"]').length).toBeGreaterThanOrEqual(3);
      expect(bar?.querySelector('[class*="ageFill"]')).not.toBeNull();
    }
    // Legend and the bar note.
    expect(within(sourcesCard()).getByText(healthCopy.sources.barNote)).toBeInTheDocument();
    for (const w of ['제때', '늦음', '낡음']) {
      expect(within(sourcesCard()).getAllByText(w).length).toBeGreaterThan(0);
    }
  });

  it('places each age on a 0–2 cadence bar (fresh zone to 1, late to 1.5)', async () => {
    serve(healthTodo);
    renderApp('/health');
    await screen.findByRole('heading', { level: 2, name: '정상' });
    const widths = sourceRows().map(
      (r) => r.querySelector<HTMLElement>('[class*="ageFill"]')?.style.width,
    );
    // 토스 연결: the contract's age is days since connecting ÷ 90 (0.87 on 10/7, 12 days left);
    // the bar puts the expiry at the late/stale edge, so it ends at 65.25% (the drawing's 62%
    // came from the old cadence-relative 1.24).
    expect(widths).toEqual(['8%', '20%', '8%', '65.25%', '12%', '5%']);
  });

  it('shows 토스 연결 만료 예정 only as 할 일 1 and a yellow card; the header stays 정상 · 08:30 확인', async () => {
    serve(healthTodo);
    renderApp('/health');
    await screen.findByRole('heading', { level: 2, name: '정상' });
    expect(screen.getByText('자료 6개 중 할 일 1')).toBeInTheDocument();
    expect(screen.getByText('마지막 확인 10/7 08:30 · 다음 10/8 08:30')).toBeInTheDocument();
    expect(screen.getByText('할 일 1')).toBeInTheDocument();
    const card = screen.getByRole('article', { name: '토스 연결 만료 예정 · 10/19' });
    expect(card.className).toContain('todo-warn');
    expect(within(card).getByText('직접 할 일')).toBeInTheDocument();
    expect(card).toHaveTextContent('12일 뒤 토스 연결이 끝나요그 전에 Claude에게 재연결 요청');
    expect(within(card).getByText('끝나면 실전 주문과 잔고 대조가 멈춰요')).toBeInTheDocument();
    const header = screen.getByRole('banner');
    expect(within(header).getByText('정상 · 08:30 확인')).toBeInTheDocument();
    // No 이상 배너.
    expect(document.querySelector('[class*="bannerSlot"]')?.textContent).toBe('');
  });

  it('counts by cause: one stale US quote is 점검 1', async () => {
    serve(healthStale);
    renderApp('/health');
    expect(await screen.findByRole('heading', { level: 2, name: '점검 1' })).toBeInTheDocument();
    expect(screen.getByText('자료 6개 중 낡음 1 · 할 일 1')).toBeInTheDocument();
    expect(screen.getByText('점검 1 · 할 일 1')).toBeInTheDocument();
    expect(within(screen.getByRole('banner')).getByText('점검 1')).toBeInTheDocument();
    const card = screen.getByRole('article', { name: '미국 시세 10/2 기준 · 2거래일째' });
    expect(card.className).toContain('todo-error');
    expect(card).toHaveTextContent('10/5·10/6 미국 종가를 못 받았어요다음 시도 10/8 06:20');
    expect(within(card).getByText('그동안 주문 0건 · 실전 켜기 막힘')).toBeInTheDocument();
    const us = sourceRows()[1];
    expect(us).toBeDefined();
    if (!us) return;
    expect(within(us).getByText('낡음')).toBeInTheDocument();
    expect(us).toHaveTextContent('10/2 종가(ET) · 10/3 06:20 받음 · 매일');
    expect(within(recentCard()).getByText('14일 중 실패 0 · 시세 대기 2')).toBeInTheDocument();
    expect(
      within(recentCard()).getByText('10/7 08:30 확인 · 시세 대기 · 주문 0건'),
    ).toBeInTheDocument();
  });

  it('gives every 할 일 card a 자동 재시도 chip with its time or 직접 할 일', async () => {
    for (const bundle of [healthTodo, healthStale, healthFailed, healthPhase2]) {
      serve(bundle);
      const { unmount } = renderApp('/health');
      await screen.findByRole('heading', { level: 1, name: copy.pages.health });
      const cards = await screen.findAllByRole('article');
      for (const card of cards) {
        const chip = card.querySelector('[class*="signal"]');
        expect(chip?.textContent).toMatch(
          /^(\d{1,2}\/\d{1,2} )?\d{2}:\d{2} 자동 재시도$|^직접 할 일$/,
        );
      }
      unmount();
    }
  });

  it('shows the failed check: 09:30 자동 재시도, 주문은 나가지 않았어요 and 실패 1 over 14 days', async () => {
    serve(healthFailed);
    renderApp('/health');
    expect(await screen.findByRole('heading', { level: 2, name: '확인 실패' })).toBeInTheDocument();
    expect(screen.getByText('10/7 08:30 · 시세 응답 없음')).toBeInTheDocument();
    expect(screen.getByText('마지막 성공 10/6 08:30 · 다시 09:30')).toBeInTheDocument();
    expect(screen.getByText('실패 1')).toBeInTheDocument();
    const card = screen.getByRole('article', { name: '10/7 08:30 확인 실패' });
    expect(within(card).getByText('09:30 자동 재시도')).toBeInTheDocument();
    expect(card).toHaveTextContent('주문은 나가지 않았어요');
    expect(card).toHaveTextContent('09:30에도 실패하면 알림이 가요');
    expect(within(card).getByText('두 번 실패하면 직접 할 일 · 작동에서 확인')).toBeInTheDocument();
    expect(within(recentCard()).getByText('14일 중 실패 1')).toBeInTheDocument();
    expect(
      within(recentCard()).getByText('10/7 08:30 확인 실패 · 시세 응답 없음 · 12초'),
    ).toBeInTheDocument();
    expect(sourceRows()[0]).toHaveTextContent('10/6 종가 · 10/6 16:00 받음 · 매일');
  });

  it('draws the 14 days as weekday cells only: half-dot holidays, 10/7 rebalancing and the last line', async () => {
    serve(healthTodo);
    renderApp('/health');
    await screen.findByRole('heading', { level: 2, name: '정상' });
    const grid = within(recentCard()).getByRole('group', { name: healthCopy.recent.grid });
    const cells = within(grid).getAllByRole('button');
    expect(cells).toHaveLength(10);
    const names = cells.map((c) => c.getAttribute('aria-label'));
    expect(names[0]).toBe('9/24(목) 한쪽 휴장');
    expect(names[1]).toBe('9/25(금) 한쪽 휴장');
    expect(names[7]).toBe('10/5(월) 한쪽 휴장');
    expect(names[9]).toBe('10/7(수) 리밸런싱 중');
    // No cell for a weekend: every cell is a weekday.
    expect(names.every((n) => /\((월|화|수|목|금)\)/.test(n ?? ''))).toBe(true);
    expect(within(recentCard()).getByText('9/24~10/7 · 주말은 빈칸')).toBeInTheDocument();
    expect(
      within(recentCard()).getByText('10/7 08:30 확인 · 리밸런싱 시작 · 42초'),
    ).toBeInTheDocument();
    for (const w of [
      '정상 실행',
      '리밸런싱',
      '리밸런싱 중',
      '실패',
      '실행 없음',
      '한쪽 휴장',
      '두 시장 휴장',
      '시세 대기',
    ]) {
      expect(within(recentCard()).getAllByText(w).length).toBeGreaterThan(0);
    }
  });

  it('shows a chosen cell’s line under the grid', async () => {
    serve(healthTodo);
    renderApp('/health');
    await screen.findByRole('heading', { level: 2, name: '정상' });
    const cell = within(recentCard()).getByRole('button', { name: '9/30(수) 정상 실행' });
    await userEvent.click(cell);
    expect(cell).toHaveAttribute('aria-pressed', 'true');
    expect(
      within(recentCard()).getByText('9/30 08:30 확인 · 목표 범위 안 · 10초'),
    ).toBeInTheDocument();
    await userEvent.click(cell);
    expect(within(recentCard()).queryByText('9/30 08:30 확인 · 목표 범위 안 · 10초')).toBeNull();
  });

  it('opens the push row into the device list with last deliveries and a settings link', async () => {
    serve(healthTodo);
    renderApp('/health');
    await screen.findByRole('heading', { level: 2, name: '정상' });
    const row = screen.getByRole('button', { name: /알림 기기/ });
    expect(row).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(row);
    expect(row).toHaveAttribute('aria-expanded', 'true');
    expect(await screen.findByText('iPhone · 홈 화면 앱')).toBeInTheDocument();
    expect(screen.getByText('MacBook · Chrome')).toBeInTheDocument();
    expect(screen.getByText('마지막 전달 10/6 16:01')).toBeInTheDocument();
    expect(screen.getAllByText(healthCopy.devices.ok)).toHaveLength(2);
    expect(screen.getByRole('link', { name: healthCopy.devices.settings })).toHaveAttribute(
      'href',
      '/account#notifications',
    );
  });

  it('never draws 정상 when the status cannot be loaded: grey 확인 불가, 상태 모름, reload, header 확인 불가', async () => {
    vi.useFakeTimers({ toFake: ['Date'], shouldAdvanceTime: true });
    vi.setSystemTime(new Date('2026-10-07T16:10:00+09:00'));
    serve(healthUnknown);
    renderApp('/health');
    expect(await screen.findByRole('heading', { level: 2, name: '확인 불가' })).toBeInTheDocument();
    expect(screen.getByText('상태를 못 불러왔어요 · 16:10 시도')).toBeInTheDocument();
    expect(screen.getByText('마지막으로 받은 상태 10/7 08:30')).toBeInTheDocument();
    expect(screen.getByText('상태 모름')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: copy.state.retry })).toBeInTheDocument();
    expect(screen.queryByText('정상')).toBeNull();
    // Values below are '—', not normal-looking numbers.
    const rows = sourceRows();
    expect(rows.length).toBeGreaterThan(0);
    for (const r of rows) expect(r.querySelector('[class*="rowLine"]')?.textContent).toBe('—');
    await waitFor(
      () => {
        expect(within(screen.getByRole('banner')).getByText('확인 불가')).toBeInTheDocument();
      },
      { timeout: 4000 },
    );
  });

  it('keeps the frame as skeletons while loading, without pre-drawing 정상', () => {
    serve(healthLoading);
    renderApp('/health');
    expect(document.querySelector('[aria-busy="true"]')).not.toBeNull();
    expect(screen.queryByText('정상')).toBeNull();
    expect(screen.queryByRole('heading', { level: 2 })).toBeNull();
  });

  it('shows 첫 확인 전 with the first check time before anything ran: grey bars, empty cells', async () => {
    serve(healthEmpty);
    renderApp('/health');
    expect(
      await screen.findByRole('heading', { level: 2, name: '첫 확인 전' }),
    ).toBeInTheDocument();
    expect(screen.getByText('첫 확인 7/1(수) 08:30 예정')).toBeInTheDocument();
    expect(screen.queryByText('정상')).toBeNull();
    const rows = sourceRows();
    expect(rows).toHaveLength(3);
    for (const r of rows) expect(r.querySelector('[class*="ageFill"]')).toBeNull();
    const cells = within(recentCard()).getAllByRole('button');
    expect(cells.every((c) => c.getAttribute('aria-label')?.endsWith('앞으로'))).toBe(true);
  });

  it('adds the 2단계 rows (공시 · AI 호출 · 지표 표) only when the response lists them', async () => {
    serve(healthTodo);
    const first = renderApp('/health');
    await screen.findByRole('heading', { level: 2, name: '정상' });
    expect(within(sourcesCard()).queryByText('공시')).toBeNull();
    expect(within(sourcesCard()).queryByText('AI 호출')).toBeNull();
    first.unmount();

    serve(healthPhase2);
    renderApp('/health');
    // The final contract makes the paused filing watch a red card and counts its 'maintenance'
    // source as stale, so the summary reads '점검 1'; 할 일 2 = 토스 연결 + the AI budget card.
    await screen.findByRole('heading', { level: 2, name: '점검 1' });
    expect(screen.getByText('자료 9개 중 낡음 1 · 할 일 2')).toBeInTheDocument();
    const names = sourceRows().map((r) => r.querySelector('[class*="rowName"]')?.textContent);
    expect(names).toEqual([...SIX, '공시', 'AI 호출', '지표 표']);
    const filings = sourceRows()[6];
    expect(filings).toHaveTextContent('점검 중');
    expect(filings).toHaveTextContent('한국 공시 감시 멈춤');
    expect(screen.getByRole('article', { name: '한국 공시 수집 점검 중' })).toHaveTextContent(
      '마지막으로 받음 10/6 18:00',
    );
    // ai-cli yellow (over-budget) has no time: no '…부터' in its title.
    expect(screen.getByRole('article', { name: 'AI 토큰 예산 넘음' })).toHaveTextContent(
      '이번 달 324만 토큰 · 예산 300만 토큰',
    );
  });

  it('asks again from the error state (다시 불러오기)', async () => {
    serve(homePaper); // no /api/health in this bundle → a 404 answer
    renderApp('/health');
    const retry = await screen.findByRole('button', { name: copy.state.retry });
    expect(screen.getByRole('heading', { level: 2, name: '확인 불가' })).toBeInTheDocument();
    await userEvent.click(retry);
    expect(screen.getByRole('heading', { level: 2, name: '확인 불가' })).toBeInTheDocument();
  });
});
