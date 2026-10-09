// SCR-HISTORY 기록 — 기획 §5 완료 조건, one assertion block per bullet; numbers are 예시-값표 §1.4.
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { HistoryResponse } from '../../src/api/types';
import historyEmpty from '../../src/fixtures/bundles/history.empty';
import historyError from '../../src/fixtures/bundles/history.error';
import historyLoading from '../../src/fixtures/bundles/history.loading';
import historyOff from '../../src/fixtures/bundles/history.off-period';
import historyPaper from '../../src/fixtures/bundles/history.paper';
import historyLedger from '../../src/fixtures/bundles/history.paper-ledger';
import historyStale from '../../src/fixtures/bundles/history.stale';
import modePaper from '../../src/fixtures/bundles/mode.paper';
import { historyPaper as paperResponse } from '../../src/fixtures/parts/history';
import type { FixtureBundle } from '../../src/fixtures/types';
import { findText, findTotal, renderState, textOf, viewport } from './hdr.routes';

afterEach(() => {
  vi.unstubAllGlobals();
});

function list() {
  return screen.getByRole('region', { name: '사건 목록' });
}

function active(): HTMLElement {
  const el = document.activeElement;
  if (!(el instanceof HTMLElement)) throw new Error('nothing focused');
  return el;
}

function rows() {
  return within(list()).queryAllByRole('link');
}

async function ready(bundle: FixtureBundle = historyPaper, path = '/history') {
  const r = renderState(bundle, path);
  await findTotal('10,243,800원');
  return r;
}

function tile(label: string) {
  const head = screen.getByText(label, { selector: '.t-label' });
  const box = head.closest('p')?.parentElement;
  if (!box) throw new Error(`no tile ${label}`);
  return box;
}

describe('SCR-HISTORY 모의투자 기본 (1:58215 · 1:59344)', () => {
  it('title, 예시 and 자산 변동 since 7/1: 10,243,800원 · ▲ +243,800원 · +2.44%', async () => {
    await ready();
    expect(screen.getByRole('heading', { level: 1, name: '모의투자 기록 · 2026' })).toBeVisible();
    expect(screen.getAllByText('예시').length).toBeGreaterThan(0);
    expect(screen.getByText('자산 변동 · 7/1부터')).toBeInTheDocument();
    expect(screen.getByText('10/7 16:00 기준')).toBeInTheDocument();
    expect(screen.getByText('▲ +243,800원 · +2.44%')).toBeInTheDocument();
    expect(screen.getByText('입금 제외 · 수수료 반영')).toBeInTheDocument();
  });

  it('완료 조건: tiles 리밸런싱 3회 (일부 실패 1) · 수수료 5,935원 (세금 미포함) · 확인 71회 (실패 1)', async () => {
    await ready();
    expect(textOf(tile('리밸런싱'))).toBe('리밸런싱3회일부 실패 1');
    expect(textOf(tile('수수료'))).toBe('수수료5,935원세금 미포함');
    expect(textOf(tile('확인'))).toBe('확인71회실패 1');
  });

  it('완료 조건: the tiles equal the 모드 화면 성적 numbers (확인 71 · 리밸런싱 3 · 실패 1)', () => {
    const mode: unknown = modePaper.responses['/api/mode'];
    const perf =
      typeof mode === 'object' && mode !== null && 'performance' in mode
        ? (mode as { performance: { checks: number; rebalances: number; failures: number } })
            .performance
        : null;
    const tiles = paperResponse().tiles;
    expect(perf).not.toBeNull();
    expect(tiles.checks.count).toBe(perf?.checks);
    expect(tiles.rebalances.count).toBe(perf?.rebalances);
    expect(tiles.checks.failed).toBe(perf?.failures);
  });

  it('완료 조건: 7/1 is 시작 · 10,000,000원 · 손익 제외 with the flag marker, and not counted as 입금 (입금 0)', async () => {
    await ready();
    const start = within(list()).getByRole('link', { name: /^7\/1\(수\) · 시작 · 10,000,000원/ });
    expect(start).toHaveTextContent('손익 제외');
    const chart = screen.getByRole('region', { name: '자산 변동 · 7/1부터' });
    expect(within(chart).getByRole('link', { name: '7/1(수) 시작' })).toHaveAttribute(
      'href',
      '/day/2026-07-01',
    );
    expect(screen.getByRole('button', { name: '입금 0' })).toBeInTheDocument();
  });

  it('완료 조건: every row with fills carries 모의 체결 (7/1 · 8/21 · 9/14 · 10/7)', async () => {
    await ready();
    const filled = rows().filter((r) =>
      ['start', 'rebalance', 'partial-failed', 'in-progress'].includes(
        r.getAttribute('data-kind') ?? '',
      ),
    );
    expect(filled).toHaveLength(4);
    for (const row of filled) expect(row).toHaveTextContent('모의 체결');
    expect(within(list()).queryAllByText('실제 체결')).toHaveLength(0);
  });

  it('완료 조건: filter chip numbers equal the rows they leave (전체 6 · 지수 반반 3 · 모멘텀 1 · 리밸런싱 3 · 배당 1 · 실패 1)', async () => {
    await ready();
    const cases: [string, number][] = [
      ['전체 6', 6],
      ['지수 반반 3', 3],
      ['AI 판단 포함 [예시] 종목 모멘텀 1', 1],
    ];
    for (const [name, n] of cases) {
      fireEvent.click(screen.getByRole('button', { name }));
      await waitFor(() => {
        expect(rows()).toHaveLength(n);
      });
    }
    fireEvent.click(screen.getByRole('button', { name: '전체 6' }));
    for (const [name, n] of [
      ['리밸런싱 3', 3],
      ['입금 0', 0],
      ['출금 0', 0],
      ['배당 1', 1],
      ['실패 1', 1],
    ] as const) {
      const chip = screen.getByRole('button', { name });
      fireEvent.click(chip);
      await waitFor(() => {
        expect(chip).toHaveAttribute('aria-pressed', 'true');
        expect(rows()).toHaveLength(n);
      });
      fireEvent.click(chip);
    }
  });

  it('완료 조건: both chip rows apply together (지수 반반 + 리밸런싱 → 8/21 and 10/7)', async () => {
    await ready();
    fireEvent.click(screen.getByRole('button', { name: '지수 반반 3' }));
    fireEvent.click(screen.getByRole('button', { name: '리밸런싱 3' }));
    await waitFor(() => {
      expect(rows().map((r) => r.getAttribute('href'))).toEqual([
        '/day/2026-10-07?rule=index_half&kind=rebalance',
        '/day/2026-08-21?rule=index_half&kind=rebalance',
      ]);
    });
  });

  it('완료 조건: month heads add up to the PnL (−47,400 + 162,200 + 58,700 + 70,300 = +243,800원)', async () => {
    await ready();
    const heads = within(list())
      .getAllByRole('heading', { level: 3 })
      .map((h) => textOf(h));
    expect(heads).toEqual(['10월+70,300원', '9월+58,700원', '8월+162,200원', '7월−47,400원']);
    const sum = paperResponse().months.reduce((s, m) => s + m.change, 0);
    expect(sum).toBe(243_800);
    expect(paperResponse().trend.pnl?.amount).toBe(sum);
  });

  it('rows read like the spec: 리밸런싱 중 · 매수 22:30, 배당 16,243원 · 수익, 9/15 다시 · 체결, 시세 응답 없음 · 9/10 정상, 2.3%p 벗어남 · 수수료 206원', async () => {
    await ready();
    const byDate = (d: string) =>
      rows().find((r) => r.getAttribute('href')?.startsWith(`/day/${d}`)) ?? null;
    expect(textOf(byDate('2026-10-07'))).toContain('리밸런싱 중매수 22:30모의 체결지수 반반');
    expect(textOf(byDate('2026-10-07'))).toContain('+24,400원10,243,800원');
    expect(textOf(byDate('2026-09-30'))).toContain('배당 16,243원수익KOSPI200 ETF지수 반반');
    expect(textOf(byDate('2026-09-14'))).toContain('리밸런싱 · 일부 실패9/15 다시 · 체결모의 체결');
    expect(textOf(byDate('2026-09-09'))).toContain('확인 실패시세 응답 없음9/10 정상');
    expect(textOf(byDate('2026-08-21'))).toContain('리밸런싱 · 2.3%p 벗어남');
    expect(textOf(byDate('2026-08-21'))).toContain('수수료 206원모의 체결지수 반반');
    expect(textOf(byDate('2026-08-21'))).toContain('+12,300원10,084,600원');
  });

  it('완료 조건: calendar — 9/9 ✕, 9/14 일부 실패, 10/7 점선, 한쪽 휴장 반쪽 점, no weekend cells; not by colour alone', async () => {
    await ready();
    const grid = screen.getByRole('group', { name: '매일 확인' });
    const cell = (label: string) => within(grid).getByRole('link', { name: label });
    // ✕ icon, ⇄ icon, dashed edge, half dot: each state has its own drawing besides colour.
    expect(cell('9/9(수) 실패').querySelector('.lucide-x')).not.toBeNull();
    expect(cell('9/14(월) 일부 실패').querySelector('.lucide-arrow-left-right')).not.toBeNull();
    expect(cell('10/7(수) 리밸런싱 중').querySelector('rect[stroke-dasharray]')).not.toBeNull();
    expect(cell('9/25(금) 한쪽 휴장').querySelector('path')).not.toBeNull();
    expect(cell('8/21(금) 리밸런싱').querySelector('.lucide-arrow-left-right')).not.toBeNull();
    const labels = within(grid)
      .getAllByRole('link')
      .map((a) => a.getAttribute('aria-label') ?? '');
    expect(labels.some((l) => /\((토|일)\)/.test(l))).toBe(false);
    expect(labels).toHaveLength(71);
    expect(screen.getByText('확인 71회 중 실패 1')).toBeInTheDocument();
    for (const word of [
      '정상 실행',
      '리밸런싱',
      '리밸런싱 중',
      '일부 실패',
      '실패',
      '실행 없음',
      '한쪽 휴장',
      '두 시장 휴장',
    ]) {
      expect(
        within(screen.getByRole('list', { name: '범례' })).getByText(word),
      ).toBeInTheDocument();
    }
  });

  it('calendar keyboard: one Tab stop, ←/→ move a week, ↑/↓ a weekday', async () => {
    await ready();
    const grid = screen.getByRole('group', { name: '매일 확인' });
    const links = within(grid).getAllByRole('link');
    expect(links.filter((a) => a.tabIndex === 0)).toHaveLength(1);
    const today = within(grid).getByRole('link', { name: '10/7(수) 리밸런싱 중' });
    expect(today.tabIndex).toBe(0);
    today.focus();
    fireEvent.keyDown(today, { key: 'ArrowLeft' });
    expect(document.activeElement).toBe(
      within(grid).getByRole('link', { name: '9/30(수) 정상 실행' }),
    );
    fireEvent.keyDown(active(), { key: 'ArrowUp' });
    expect(document.activeElement).toBe(
      within(grid).getByRole('link', { name: '9/29(화) 정상 실행' }),
    );
    fireEvent.keyDown(active(), { key: 'ArrowRight' });
    expect(document.activeElement).toBe(
      within(grid).getByRole('link', { name: '10/6(화) 정상 실행' }),
    );
    expect(active().tabIndex).toBe(0);
  });

  it('chart markers: real links to 그날, ←/→ move between them', async () => {
    await ready();
    const chart = screen.getByRole('region', { name: '자산 변동 · 7/1부터' });
    const first = within(chart).getByRole('link', { name: '7/1(수) 시작' });
    expect(first).toHaveAttribute('href', '/day/2026-07-01');
    first.focus();
    fireEvent.keyDown(first, { key: 'ArrowRight' });
    expect(document.activeElement).toBe(
      within(chart).getByRole('link', { name: '8/21(금) 리밸런싱' }),
    );
    fireEvent.keyDown(active(), { key: 'ArrowRight' });
    expect(document.activeElement).toBe(
      within(chart).getByRole('link', { name: '9/9(수) 확인 실패' }),
    );
    fireEvent.keyDown(active(), { key: 'ArrowLeft' });
    expect(document.activeElement).toBe(
      within(chart).getByRole('link', { name: '8/21(금) 리밸런싱' }),
    );
  });

  it('rows open 그날 (390: the full-height sheet)', async () => {
    const { router } = await ready();
    fireEvent.click(within(list()).getByRole('link', { name: /^8\/21\(금\)/ }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/day/2026-08-21');
    });
    const sheet = await screen.findByRole('dialog', { name: '8/21(금)' });
    expect(await within(sheet).findByText('10,084,600원')).toBeInTheDocument();
  });
});

describe('SCR-HISTORY.paper-ledger (1:58777)', () => {
  it('완료 조건: 실전 mode with ?ledger=paper shows the 장부 칩; × goes back to the 실전 record with no 모의 체결 rows', async () => {
    const { router } = renderState(historyLedger, '/history?ledger=paper');
    await findTotal('10,243,800원');
    expect(screen.getByText('모의투자 장부')).toBeInTheDocument();
    expect(screen.getByText('· 실전 중에 보는 중')).toBeInTheDocument();
    expect(
      within(screen.getByRole('banner')).getByRole('link', { name: '실전' }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '닫기 · 실전 기록으로' }));
    await findTotal('10,112,670원');
    expect(router.state.location.search).toBe('');
    expect(screen.queryByText('모의투자 장부')).toBeNull();
    expect(screen.getByRole('heading', { level: 1, name: '실전 기록 · 2026' })).toBeVisible();
    expect(within(list()).queryAllByText('모의 체결')).toHaveLength(0);
    expect(within(list()).getAllByText('실제 체결').length).toBeGreaterThan(0);
  });

  it('완료 조건: the default 실전 record has no chip', async () => {
    renderState(historyLedger, '/history');
    await findTotal('10,112,670원');
    expect(screen.queryByText('모의투자 장부')).toBeNull();
  });
});

describe('SCR-HISTORY states', () => {
  it('완료 조건 off-period: a 끈 기간 9/21–9/25 row and hatched (실행 없음) cells, ⏻ markers on the graph', async () => {
    renderState(historyOff, '/history');
    await findTotal('10,112,670원');
    expect(
      within(list()).getByRole('link', { name: '9/21(월) · 끈 기간 9/21–9/25' }),
    ).toBeInTheDocument();
    const grid = screen.getByRole('group', { name: '매일 확인' });
    for (const d of ['9/21(월)', '9/22(화)', '9/23(수)', '9/24(목)', '9/25(금)']) {
      expect(
        within(grid).getByRole('link', { name: `${d} 실행 없음 · 끈 기간` }),
      ).toBeInTheDocument();
    }
    expect(screen.getByRole('link', { name: '9/18(금) 실전 끔' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '9/28(월) 실전 켬' })).toBeInTheDocument();
  });

  it('empty: no graph yet, tiles 0회 · 0원 · 0회, empty calendar, one 시작 row', async () => {
    renderState(historyEmpty, '/history');
    await findText('첫 확인 뒤 그래프가 그려져요');
    expect(textOf(tile('리밸런싱'))).toBe('리밸런싱0회일부 실패 0');
    expect(textOf(tile('수수료'))).toBe('수수료0원세금 미포함');
    expect(textOf(tile('확인'))).toBe('확인0회실패 0');
    expect(
      within(screen.getByRole('group', { name: '매일 확인' })).queryAllByRole('link'),
    ).toHaveLength(0);
    expect(rows()).toHaveLength(1);
    expect(rows()[0]).toHaveTextContent('시작 · 10,000,000원');
  });

  it('loading: card frames with skeletons', async () => {
    const { container } = renderState(historyLoading, '/history');
    await waitFor(() => {
      expect(container.querySelector('[aria-busy="true"]')).not.toBeNull();
    });
    expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument();
  });

  it('error: 기록을 못 불러왔어요 + 다시 불러오기', async () => {
    renderState(historyError, '/history');
    expect(await findText('기록을 못 불러왔어요')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '다시 불러오기' })).toBeEnabled();
  });

  it('stale: the shell banner and today in 시세 대기 (+ legend)', async () => {
    renderState(historyStale, '/history');
    await findTotal('10,217,664원');
    expect(screen.getByText('미국 시세 10/2 기준 · 2거래일째 갱신 없음')).toBeInTheDocument();
    const grid = screen.getByRole('group', { name: '매일 확인' });
    expect(within(grid).getByRole('link', { name: '10/7(수) 시세 대기' })).toBeInTheDocument();
    expect(
      within(screen.getByRole('list', { name: '범례' })).getByText('시세 대기'),
    ).toBeInTheDocument();
  });

  it('연도 전환: two years switch title, tiles, calendar and list', async () => {
    const base = paperResponse();
    const y2025: HistoryResponse = {
      ...base,
      year: 2025,
      years: [2025, 2026],
      tiles: { ...base.tiles, checks: { count: 12, failed: 0 } },
      months: [{ month: '2025-12', change: 0, events: [] }],
    };
    const bundle: FixtureBundle = {
      ...historyPaper,
      responses: {
        ...historyPaper.responses,
        '/api/history': { ...base, years: [2025, 2026] },
        '/api/history?ledger=paper&year=2025': y2025,
      },
    };
    const { router } = renderState(bundle, '/history');
    await findTotal('10,243,800원');
    fireEvent.click(screen.getByRole('button', { name: '2025' }));
    await findText('확인 12회 중 실패 0');
    expect(router.state.location.search).toBe('?year=2025');
    expect(screen.getByRole('heading', { level: 1, name: '모의투자 기록 · 2025' })).toBeVisible();
  });
});

describe('1440 with the 그날 panel (1:60239)', () => {
  it('완료 조건: a row opens the right panel, the row is highlighted and the chart draws its line', async () => {
    viewport(1440);
    const { router, container } = renderState(historyPaper, '/history');
    await findTotal('10,243,800원');
    fireEvent.click(within(list()).getByRole('link', { name: /^8\/21\(금\)/ }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/day/2026-08-21');
    });
    const panel = await screen.findByRole('complementary', { name: '8/21(금)' });
    expect(await within(panel).findByText('수수료 합계 206원')).toBeInTheDocument();
    expect(within(list()).getByRole('link', { current: 'page' })).toHaveAttribute(
      'href',
      '/day/2026-08-21',
    );
    expect(container.querySelector('line[class*="cursor"]')).not.toBeNull();
    // The page stays: another row swaps the day in place (no new history entry).
    fireEvent.click(within(list()).getByRole('link', { name: /^9\/30\(수\)/ }));
    expect(await screen.findByRole('complementary', { name: '9/30(수)' })).toBeInTheDocument();
  });
});
