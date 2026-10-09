// Shapes the real engine API sends that the fixture worlds did not (found by npm run e2e:full).
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type {
  DayResponse,
  FlowDisplay,
  HistoryResponse,
  HomeResponse,
  Instrument,
} from '../../src/api/types';
import { CheckCard } from '../../src/screens/Day/CheckCard';
import { recordWeeks } from '../../src/screens/History/historyModel';
import { trendEvents } from '../../src/screens/Home/TrendCard';
import { NowRows } from '../../src/screens/Rules/FlowCards';

type FlowNode = FlowDisplay['nodes'][number];

type Calendar = HistoryResponse['calendar'];

/** Weekdays of 2026 from `from` to `to`, all with one state. */
function weekdays(from: string, to: string, state: Calendar[number]['state']): Calendar {
  const out: Calendar = [];
  for (let d = new Date(`${from}T00:00:00Z`); d <= new Date(`${to}T00:00:00Z`);) {
    const dow = d.getUTCDay();
    if (dow !== 0 && dow !== 6) out.push({ date: d.toISOString().slice(0, 10), state });
    d = new Date(d.getTime() + 86_400_000);
  }
  return out;
}

describe('매일 확인 달력: the API sends the whole year', () => {
  it('draws from the record start to the end of the current week', () => {
    const year: Calendar = [
      ...weekdays('2026-01-01', '2026-06-30', 'before-record'),
      ...weekdays('2026-07-01', '2026-10-07', 'normal'),
      ...weekdays('2026-10-08', '2026-12-31', 'future'),
    ];
    const shown = recordWeeks(year);
    expect(shown[0]).toEqual({ date: '2026-07-01', state: 'normal' });
    expect(shown.at(-1)).toEqual({ date: '2026-10-09', state: 'future' });
  });

  it('keeps the first week before the first check', () => {
    const year: Calendar = [
      ...weekdays('2026-01-01', '2026-06-30', 'before-record'),
      ...weekdays('2026-07-01', '2026-12-31', 'future'),
    ];
    expect(recordWeeks(year).map((c) => c.date)).toEqual([
      '2026-07-01',
      '2026-07-02',
      '2026-07-03',
    ]);
  });

  it('leaves a calendar that is all record alone', () => {
    const fixtureLike = weekdays('2026-07-01', '2026-10-09', 'normal');
    expect(recordWeeks(fixtureLike)).toEqual(fixtureLike);
  });
});

describe('사건 띠 on 자산', () => {
  it('draws the legend kinds only: a failed check has no marker there', () => {
    const events: HomeResponse['trend']['events'] = [
      { date: '2026-08-21', kind: 'rebalance', kinds: ['rebalance'] },
      { date: '2026-09-09', kind: 'check-failed', kinds: ['check-failed'] },
      { date: '2026-09-30', kind: 'dividend', kinds: ['dividend', 'check-failed'], count: 2 },
    ];
    expect(trendEvents(events).map((e) => `${e.date} ${e.kind}`)).toEqual([
      '2026-08-21 rebalance',
      '2026-09-30 dividend',
    ]);
  });
});

describe('3년 발굴 지금 boxes with real data', () => {
  const pick = (name: string, initials: string): Instrument => ({
    id: `KR:${initials}`,
    name,
    kind: 'stock',
    market: 'KR',
    currency: 'KRW',
    initials,
  });
  const node = (type: FlowNode['type'], rows: FlowNode['now']['rows']): FlowNode => ({
    id: type,
    type,
    col: 0,
    row: 0,
    title: type,
    now: { headKey: 'now', rows },
  });
  const draw = (n: FlowNode) =>
    render(<NowRows node={n} lane="quarterly" colorIndex={1} ai nowIso={null} stale={false} />)
      .container.textContent;

  it('names a held pick that is not bought yet (no weight) on the stock card', () => {
    const text = draw(
      node('stock', [
        { kind: 'instrument', instrument: pick('한화에어로스페이스', '한') },
        { kind: 'instrument', instrument: pick('한화오션', '한'), weight: 5.9 },
      ]),
    );
    expect(text).toContain('한화에어로스페이스—');
    expect(text).toContain('한화오션5.9%');
  });

  it("says '—' in a box with nothing yet (no discovery, no candidate)", () => {
    expect(draw(node('condition', []))).toBe('—');
  });
});

describe('그날 확인 after a new-cash rebalance', () => {
  it("prints no '0.0%p 넘음' line when the band was not crossed (over 0)", () => {
    const check: DayResponse['check'] = {
      at: '2026-10-06T08:30:00+09:00',
      result: 'rebalance',
      band: { threshold: 2, before: 1.9, after: 1.5 },
      ruleId: 'index_half',
      weight: 51.9,
      toThreshold: 0.1,
      over: 0,
    };
    const text = render(<CheckCard check={check} ruleName="지수 반반" />).container.textContent;
    expect(text).toContain('1.9%p 벗어남');
    expect(text).not.toContain('넘음');
  });
});
