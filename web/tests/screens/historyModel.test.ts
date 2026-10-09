// 기록 helpers: the chip counts the server sends equal the rows they leave (완료 조건), month
// changes add up, URL state, tiles. Run over every history.* bundle that answers /api/history.
import { describe, expect, it } from 'vitest';
import type { HistoryResponse } from '../../src/api/types';
import { bundleIds, loadBundle } from '../../src/fixtures/registry';
import {
  countRows,
  kindOf,
  readParams,
  rebalanceCells,
  rebalanceFees,
  rowTitle,
  stageNote,
  visibleMonths,
  withParam,
} from '../../src/screens/History/historyModel';
import { historyPaper } from '../../src/fixtures/parts/history';

function firstAnswer(script: unknown): HistoryResponse | null {
  const step: unknown = Array.isArray(script) ? script[0] : script;
  if (typeof step !== 'object' || step === null) return null;
  if ('$status' in step || '$pending' in step || '$network' in step) return null;
  return step as HistoryResponse;
}

const historyBundles = bundleIds().filter(
  (id) => id.startsWith('history.') || id.startsWith('day.'),
);

describe.each(historyBundles)('bundle %s', (id) => {
  it('chip counts equal the rows they leave; month changes add up to the 손익', async () => {
    const bundle = await loadBundle(id);
    const responses = (bundle?.responses ?? {}) as Record<string, unknown>;
    const answers = Object.entries(responses)
      .filter(([key]) => key.startsWith('/api/history'))
      .map(([, v]) => firstAnswer(v))
      .filter((v): v is HistoryResponse => v !== null);
    for (const h of answers) {
      expect(countRows(h, 'all', null)).toBe(h.filters.total);
      for (const { rule, count } of h.filters.rules)
        expect(countRows(h, rule.id, null)).toBe(count);
      for (const { kind, count } of h.filters.kinds) expect(countRows(h, 'all', kind)).toBe(count);
      const sum = h.months.reduce((s, m) => s + m.change, 0);
      expect(sum).toBe(h.trend.pnl?.amount ?? 0);
      const last = h.trend.series.at(-1);
      if (last) expect(last.value).toBe(h.trend.total);
      // Tiles count what the list shows.
      const rebalances = h.months
        .flatMap((m) => m.events)
        .filter((e) => kindOf(e.kind) === 'rebalance');
      expect(rebalances).toHaveLength(h.tiles.rebalances.count);
      expect(rebalances.filter((e) => e.kind === 'partial-failed')).toHaveLength(
        h.tiles.rebalances.partialFailed,
      );
      expect(rebalances.filter((e) => e.kind === 'in-progress')).toHaveLength(
        h.tiles.rebalances.inProgress,
      );
      const fees = h.months.flatMap((m) => m.events).reduce((s, e) => s + (e.fees ?? 0), 0);
      expect(fees).toBe(h.tiles.fees.krw);
    }
  });
});

describe('history helpers', () => {
  const h = historyPaper();

  it('시작 counts in 전체 only, not as 입금 (값표 §1.4)', () => {
    expect(kindOf('start')).toBeNull();
    expect(countRows(h, 'all', 'deposit')).toBe(0);
    expect(countRows(h, 'all', null)).toBe(6);
  });

  it('partial failures count as 리밸런싱, not as 실패 (D-basis)', () => {
    expect(kindOf('partial-failed')).toBe('rebalance');
    expect(countRows(h, 'all', 'failed')).toBe(1);
  });

  it('months newest first; filters drop empty months', () => {
    expect(visibleMonths(h, 'all', null).map((m) => m.month)).toEqual([
      '2026-10',
      '2026-09',
      '2026-08',
      '2026-07',
    ]);
    expect(visibleMonths(h, 'momentum', null).map((m) => m.month)).toEqual(['2026-09']);
  });

  it('row words', () => {
    const [e1007] = h.months[0]?.events ?? [];
    const e0821 = h.months[2]?.events[0];
    if (!e1007 || !e0821) throw new Error('fixture');
    expect(rowTitle(e1007)).toBe('리밸런싱 중');
    expect(stageNote(e1007)).toBe('매수 22:30');
    expect(rowTitle(e0821)).toBe('리밸런싱 · 2.3%p 벗어남');
    expect(stageNote(e0821)).toBe('수수료 206원');
  });

  it('tiles: mini cells oldest first, fee bars per rebalance', () => {
    expect(rebalanceCells(h.tiles.rebalances)).toEqual([
      'rebalance',
      'partialFail',
      'rebalanceInProgress',
    ]);
    expect(rebalanceFees(h)).toEqual([206, 35, 27]);
  });

  it('URL state keeps ledger, year, rule and kind', () => {
    const p = readParams(
      new URLSearchParams('ledger=paper&year=2025&rule=index_half&kind=rebalance'),
    );
    expect(p).toEqual({ ledger: 'paper', year: 2025, rule: 'index_half', kind: 'rebalance' });
    expect(readParams(new URLSearchParams('kind=nope'))).toMatchObject({ rule: 'all', kind: null });
    expect(withParam(new URLSearchParams('ledger=paper'), 'ledger', null).toString()).toBe('');
  });
});
