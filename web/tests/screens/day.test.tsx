// SCR-DAY 그날 — 기획 §5 완료 조건 (one block per bullet), numbers from 예시-값표 §1.4 · §3.
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import day0821 from '../../src/fixtures/bundles/day.0821';
import day0925 from '../../src/fixtures/bundles/day.0925';
import day1007 from '../../src/fixtures/bundles/day.1007';
import dayAi from '../../src/fixtures/bundles/day.ai';
import dayError from '../../src/fixtures/bundles/day.error';
import dayLoading from '../../src/fixtures/bundles/day.loading';
import dayPartial from '../../src/fixtures/bundles/day.partial';
import dayWeekend from '../../src/fixtures/bundles/day.weekend';
import type { FixtureBundle } from '../../src/fixtures/types';
import { findText, findTotal, renderState, textOf, viewport } from './hdr.routes';

afterEach(() => {
  vi.unstubAllGlobals();
});

async function openSheet(bundle: FixtureBundle = day0821, path = '/day/2026-08-21') {
  const r = renderState(bundle, path);
  const sheet = await screen.findByRole('dialog');
  return { ...r, sheet };
}

function orders(scope: HTMLElement) {
  return within(scope)
    .getAllByRole('listitem')
    .filter((li) => li.querySelector('svg'));
}

describe('SCR-DAY · 8/21 리밸런싱 (1:59915)', () => {
  it('date line: ‹ 8/21(금) › with 이전 7/1 · 다음 9/9, 예시 and ×', async () => {
    const { sheet } = await openSheet();
    expect(within(sheet).getByRole('heading', { level: 1, name: '8/21(금)' })).toBeInTheDocument();
    expect(await within(sheet).findByText('이전 7/1 · 다음 9/9')).toBeInTheDocument();
    expect(within(sheet).getByRole('link', { name: '이전 사건 7/1' })).toHaveAttribute(
      'href',
      '/day/2026-07-01',
    );
    expect(within(sheet).getByRole('link', { name: '다음 사건 9/9' })).toHaveAttribute(
      'href',
      '/day/2026-09-09',
    );
    expect(within(sheet).getByText('예시')).toBeInTheDocument();
    expect(within(sheet).getByRole('link', { name: '닫기' })).toHaveAttribute('href', '/history');
  });

  it('완료 조건: 그날 자산 10,084,600원 · ▲ +12,300원 · +0.12% and 수수료 합계 206원 equal the 기록 row', async () => {
    const { sheet } = await openSheet();
    await findTotal('10,084,600원');
    expect(within(sheet).getByText('그날 자산 · 모의투자')).toBeInTheDocument();
    expect(within(sheet).getByText('▲ +12,300원 · +0.12%')).toBeInTheDocument();
    expect(within(sheet).getByText('전날 대비')).toBeInTheDocument();
    expect(within(sheet).getByText('수수료 합계 206원')).toBeInTheDocument();
    expect(within(sheet).getByText('수수료 반영 · 세금 미포함')).toBeInTheDocument();
  });

  it('완료 조건: each stage card has market · time · instrument · qty · price · amount · fee (환전: rate) · 모의 체결', async () => {
    const { sheet } = await openSheet();
    await findTotal('10,084,600원');
    const cards = orders(within(sheet).getByRole('region', { name: '리밸런싱' }));
    expect(cards.map((c) => textOf(c))).toEqual([
      '체결 매도 · 한국09:05KOSPI200 ETF 5주 · 33,800원169,000원 · 수수료 25원모의 체결',
      '체결 환전 · 원→달러09:10175,000원 → $125.93환율 1,389.6원모의 체결',
      '체결 매수 · 미국22:31S&P 500 ETF 2주 · $63.00$126.00 · 수수료 $0.13모의 체결',
    ]);
  });

  it('완료 조건: 전후 비중 (전 52.3 | 47.7 → 후 50.2 | 49.8, 목표 50% · ±2%p) match the 그날 확인 band points', async () => {
    const { sheet } = await openSheet();
    await findTotal('10,084,600원');
    expect(
      within(sheet).getByRole('img', { name: '전 KOSPI200 ETF 52.3% · S&P 500 ETF 47.7%' }),
    ).toBeInTheDocument();
    expect(
      within(sheet).getByRole('img', { name: '후 KOSPI200 ETF 50.2% · S&P 500 ETF 49.8%' }),
    ).toBeInTheDocument();
    expect(within(sheet).getByText('목표 50% · ±2%p')).toBeInTheDocument();
    expect(
      within(sheet).getByRole('img', { name: '전 52.3 → 후 50.2 · 목표 ±2%p' }),
    ).toBeInTheDocument();
  });

  it('완료 조건: result chip and the line say the same (리밸런싱 · 2.3%p 벗어남 · 0.3%p 넘음 → 리밸런싱)', async () => {
    const { sheet } = await openSheet();
    await findTotal('10,084,600원');
    const check = within(sheet).getByRole('region', { name: '그날 확인 · 08:30' });
    expect(within(check).getByText('리밸런싱')).toBeInTheDocument();
    expect(within(check).getByText('2.3%p 벗어남')).toBeInTheDocument();
    expect(within(check).getByText('0.3%p 넘음 → 리밸런싱')).toBeInTheDocument();
  });

  it('완료 조건: the basis line has 한국 · 미국(ET) closes and the FX rate and time', async () => {
    const { sheet } = await openSheet();
    expect(
      await within(sheet).findByText(
        '기준 한국 8/20 종가 · 미국 8/20 종가(ET) · 환율 1,389.6원 08:30',
      ),
    ).toBeInTheDocument();
  });

  it('‹ › move to the neighbouring event in place; × on a direct visit lands on 기록', async () => {
    const { sheet, router } = await openSheet();
    await findTotal('10,084,600원');
    fireEvent.click(within(sheet).getByRole('link', { name: '다음 사건 9/9' }));
    await findTotal('10,100,300원');
    expect(router.state.location.pathname).toBe('/day/2026-09-09');
    expect(router.state.historyAction).toBe('REPLACE');
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('link', { name: '닫기' }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/history');
    });
  });

  it('the sheet is modal (focus starts on the date) and Escape closes it', async () => {
    const { sheet, router } = await openSheet();
    await findTotal('10,084,600원');
    expect(sheet).toHaveAttribute('open');
    expect(document.activeElement).toBe(within(sheet).getByRole('heading', { level: 1 }));
    fireEvent(sheet, new Event('cancel', { cancelable: true }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/history');
    });
  });
});

describe('SCR-DAY · 거래 없음 9/25 (1:60076)', () => {
  it('완료 조건: no event card, chip 한국 휴장 · 거래 없음 and 주문 0건; position and basis lines', async () => {
    const { sheet } = await openSheet(day0925, '/day/2026-09-25');
    await findTotal('10,152,400원');
    expect(within(sheet).getByText('▲ +3,400원 · +0.03%')).toBeInTheDocument();
    expect(within(sheet).getByText('이전 9/14 · 다음 9/30')).toBeInTheDocument();
    expect(
      within(sheet).queryByRole('region', { name: /리밸런싱|입금|출금|배당|시작/ }),
    ).toBeNull();
    const check = within(sheet).getByRole('region', { name: '그날 확인 · 08:30' });
    expect(within(check).getByText('한국 휴장 · 거래 없음')).toBeInTheDocument();
    expect(within(check).getByText('미국만 열린 날 · 확인은 돌았고 주문 0건')).toBeInTheDocument();
    expect(
      within(check).getByText('지수 반반 KOSPI200 ETF 51.1% · 리밸런싱까지 0.9%p'),
    ).toBeInTheDocument();
    expect(
      within(sheet).getByText('기준 한국 9/23 종가 · 미국 9/24 종가(ET) · 환율 1,384.0원 08:30'),
    ).toBeInTheDocument();
  });
});

describe('SCR-DAY states', () => {
  it('partial: red ✕ card with 시세 응답 없음 · 다시 10/8 22:30, head ✓✓✕, chip 일부 실패, 진행 중 단계 보기', async () => {
    const { sheet } = await openSheet(dayPartial, '/day/2026-10-07');
    await findTotal('10,243,800원');
    const event = within(sheet).getByRole('region', { name: '일부 실패' });
    expect(within(event).getByText('리밸런싱 · 일부 실패')).toBeInTheDocument();
    const failed = orders(event).at(-1);
    expect(textOf(failed ?? null)).toContain('실패 매수 · 미국22:30S&P 500 ETF 2주 · 약 $62.40');
    expect(textOf(failed ?? null)).toContain('시세 응답 없음다시 10/8 22:30');
    expect(failed?.className).toMatch(/orderFailed/);
    const head = event.querySelector('h3')?.parentElement?.parentElement;
    expect(head?.querySelectorAll('.lucide-circle-check')).toHaveLength(2);
    expect(head?.querySelectorAll('.lucide-circle-x')).toHaveLength(1);
    expect(within(sheet).getByRole('region', { name: '그날 확인 · 08:30' })).toHaveTextContent(
      '일부 실패',
    );
    expect(within(event).getByRole('link', { name: '진행 중 단계 보기' })).toHaveAttribute(
      'href',
      '/plan#now',
    );
  });

  it('partial retried later: the failed card carries 9/15 다시 · 체결 (9/14)', async () => {
    const { sheet } = await openSheet(dayPartial, '/day/2026-09-14');
    await findTotal('10,090,600원');
    expect(within(sheet).getByText('9/15 다시 · 체결')).toBeInTheDocument();
    expect(within(sheet).queryByRole('link', { name: '진행 중 단계 보기' })).toBeNull();
  });

  it('10/7 리밸런싱 중: the waiting buy has no fill label (인계 명세 정정)', async () => {
    const { sheet } = await openSheet(day1007, '/day/2026-10-07');
    await findTotal('10,243,800원');
    const cards = orders(within(sheet).getByRole('region', { name: '리밸런싱 중' }));
    expect(cards.map((c) => c.textContent.includes('모의 체결'))).toEqual([true, true, false]);
    expect(textOf(cards[2] ?? null)).toContain(
      '대기 매수 · 미국22:30S&P 500 ETF 2주 · 약 $62.40약 $124.80 · 수수료 약 $0.12',
    );
  });

  it('AI 판단 card (no drawing): trigger, input, model · tokens, output, verdict, votes and action', async () => {
    const { sheet } = await openSheet(dayAi, '/day/2026-10-02');
    await findTotal('10,226,200원');
    const card = within(sheet).getByRole('region', { name: 'AI 확인' });
    expect(within(card).getByText('AI 확인 · 셀트리온')).toBeInTheDocument();
    expect(within(card).getByText('급락')).toBeInTheDocument();
    // The contract now sends the 입력 · 출력 lines as JudgmentItem data (2026-10-09 '서버 문구
    // 걷어냄'), not the drawn sentences: the screen words the instrument, the day's drop against
    // the index and the filings count; 출력 is the news the web search found.
    expect(
      within(card).getByText('셀트리온 · 10/2 지수 대비 −8.1% · 최근 공시 2건'),
    ).toBeInTheDocument();
    expect(within(card).getByText('Sonnet · 약 2만 토큰')).toBeInTheDocument();
    expect(within(card).getByText('뉴스 3건')).toBeInTheDocument();
    expect(within(card).getByText('판단')).toBeInTheDocument();
    expect(within(card).getByText('유지')).toBeInTheDocument();
    expect(within(card).getByText("두 번 다 '유지'")).toBeInTheDocument();
    expect(within(card).getByText('주문 0건')).toBeInTheDocument();
  });

  it('weekend: 주말 · 확인 없음', async () => {
    const { sheet } = await openSheet(dayWeekend, '/day/2026-10-04');
    expect(await within(sheet).findByText('주말 · 확인 없음')).toBeInTheDocument();
  });

  it('loading keeps the date line; error shows 그날 기록을 못 불러왔어요 + 다시 불러오기', async () => {
    const loading = await openSheet(dayLoading, '/day/2026-08-21');
    expect(
      within(loading.sheet).getByRole('heading', { level: 1, name: '8/21(금)' }),
    ).toBeInTheDocument();
    expect(loading.sheet).toHaveAttribute('aria-busy', 'true');
    loading.unmount();
    const failed = await openSheet(dayError, '/day/2026-08-21');
    expect(await within(failed.sheet).findByText('그날 기록을 못 불러왔어요')).toBeInTheDocument();
    expect(within(failed.sheet).getByRole('button', { name: '다시 불러오기' })).toBeEnabled();
  });
});

describe('1440: right panel over 기록 (1:60239)', () => {
  it('opens as a complementary panel next to the page, which keeps the chart line and row highlight', async () => {
    viewport(1440);
    renderState(day0821, '/day/2026-08-21');
    const panel = await screen.findByRole('complementary', { name: '8/21(금)' });
    expect(await within(panel).findByText('10,084,600원')).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(await findText('모의투자 기록 · 2026')).toBeInTheDocument();
    const row = within(screen.getByRole('region', { name: '사건 목록' })).getByRole('link', {
      current: 'page',
    });
    expect(row).toHaveAttribute('href', '/day/2026-08-21');
    // The same 그날 numbers as the row and the chart marker (완료 조건).
    expect(row).toHaveTextContent('+12,300원');
    expect(row).toHaveTextContent('10,084,600원');
    fireEvent.keyDown(panel, { key: 'Escape' });
    await waitFor(() => {
      expect(screen.queryByRole('complementary', { name: '8/21(금)' })).toBeNull();
    });
  });
});
