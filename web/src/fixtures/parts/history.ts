// SCR-HISTORY responses of each 예시-값표 world (history.* and day.* bundles share them).
// Numbers are 값표 §1.4 (모의투자) and §2 (실전); where the table is silent the value is derived
// from it and the assumption is written next to it.
import type { CalendarState, HistoryEvent, HistoryResponse } from '../../api/types';
import { paperDailySinceStart } from '../charts';
import { INDEX_HALF, KOSPI200, MOMENTUM, START_CAPITAL, kst } from '../world';
import { BASIS_1007 } from './common';
import { liveDaily } from './series';

// ── weekday calendar ────────────────────────────────────────────────────────

const DAY_MS = 86_400_000;

function dayNumber(date: string): number {
  return Date.parse(`${date}T00:00:00Z`) / DAY_MS;
}

function dateOf(n: number): string {
  return new Date(n * DAY_MS).toISOString().slice(0, 10);
}

/** Weekdays from `from` to `to` (inclusive) with their state; `today` and later are 'future'. */
export function weekdayCalendar(
  from: string,
  to: string,
  today: string,
  special: Readonly<Record<string, CalendarState>>,
): HistoryResponse['calendar'] {
  const out: HistoryResponse['calendar'] = [];
  for (let n = dayNumber(from); n <= dayNumber(to); n++) {
    const date = dateOf(n);
    const dow = new Date(n * DAY_MS).getUTCDay();
    if (dow === 0 || dow === 6) continue;
    const state: CalendarState = date > today ? 'future' : (special[date] ?? 'normal');
    out.push({ date, state });
  }
  return out;
}

// ── 모의투자 (값표 §1.4) ──────────────────────────────────────────────────────

/** 휴장 (값표 §0): one market each, so the check ran (반쪽 점). */
const PAPER_HOLIDAYS: Record<string, CalendarState> = {
  '2026-07-03': 'holiday-one',
  '2026-08-17': 'holiday-one',
  '2026-09-07': 'holiday-one',
  '2026-09-24': 'holiday-one',
  '2026-09-25': 'holiday-one',
  '2026-10-05': 'holiday-one',
};

export const PAPER_CALENDAR = weekdayCalendar('2026-07-01', '2026-10-09', '2026-10-07', {
  ...PAPER_HOLIDAYS,
  '2026-08-21': 'rebalance',
  '2026-09-09': 'failed',
  '2026-09-14': 'partial-failed',
  '2026-10-07': 'in-progress',
});

/** 10/7 리밸런싱 중: 매도·환전 체결, 매수 22:30 대기 (값표 §1.4). Fees so far 27원. */
export const EVENT_1007: HistoryEvent = {
  date: '2026-10-07',
  kind: 'in-progress',
  rule: INDEX_HALF,
  stagesMini: ['done', 'done', 'pending'],
  fill: 'paper',
  fees: 27,
  pending: { side: 'buy', at: kst('2026-10-07', '22:30') },
  dayChange: 24_400,
  dayTotal: 10_243_800,
};

export const EVENT_0930: HistoryEvent = {
  date: '2026-09-30',
  kind: 'dividend',
  rule: INDEX_HALF,
  amount: 16_243,
  instrument: KOSPI200,
  treatment: 'income',
  dayChange: 7_500,
  dayTotal: 10_173_500,
};

/** 9/14 일부 실패 → 9/15 다시 · 체결. Fees 8원 (9/14) + 27원 (9/15) = 35원. */
export const EVENT_0914: HistoryEvent = {
  date: '2026-09-14',
  kind: 'partial-failed',
  rule: MOMENTUM,
  stagesMini: ['done', 'failed'],
  fill: 'paper',
  fees: 35,
  retry: { date: '2026-09-15', filled: true },
  dayChange: -19_000,
  dayTotal: 10_090_600,
};

export const EVENT_0909: HistoryEvent = {
  date: '2026-09-09',
  kind: 'check-failed',
  failureReason: 'no-quote',
  recoveredOn: '2026-09-10',
  dayChange: -9_800,
  dayTotal: 10_100_300,
};

export const EVENT_0821: HistoryEvent = {
  date: '2026-08-21',
  kind: 'rebalance',
  rule: INDEX_HALF,
  stagesMini: ['done', 'done', 'done'],
  weightsMini: { before: [52.3, 47.7], after: [50.2, 49.8], target: [50, 50] },
  fill: 'paper',
  deviation: 2.3,
  fees: 206,
  dayChange: 12_300,
  dayTotal: 10_084_600,
};

/**
 * 7/1 시작 · 10,000,000원 · 손익 제외. The first buys are fills too (환전 · 매수, 6 모의 체결,
 * 수수료 5,667원), so the row carries 체결 라벨 (완료 조건 '체결이 있는 모든 행').
 */
export const EVENT_0701: HistoryEvent = {
  date: '2026-07-01',
  kind: 'start',
  amount: START_CAPITAL,
  treatment: 'pnl-excluded',
  stagesMini: ['done', 'done'],
  fill: 'paper',
  fees: 5_667,
  dayChange: null,
  dayTotal: START_CAPITAL,
};

const PAPER_TREND_EVENTS: HistoryResponse['trend']['events'] = [
  { date: '2026-07-01', kind: 'start' },
  { date: '2026-08-21', kind: 'rebalance' },
  { date: '2026-09-09', kind: 'check-failed' },
  { date: '2026-09-14', kind: 'partial-failed' },
  { date: '2026-09-30', kind: 'dividend' },
  { date: '2026-10-07', kind: 'in-progress' },
];

export function historyPaper(): HistoryResponse {
  return {
    ledger: 'paper',
    example: true,
    year: 2026,
    years: [2026],
    trend: {
      since: '2026-07-01',
      basis: BASIS_1007,
      total: 10_243_800,
      pnl: { amount: 243_800, pct: 2.44 },
      series: paperDailySinceStart.flatMap((p) =>
        p.value === null ? [] : [{ date: p.date, value: p.value }],
      ),
      events: PAPER_TREND_EVENTS,
    },
    tiles: {
      rebalances: { count: 3, partialFailed: 1, inProgress: 1 },
      fees: { krw: 5_935 },
      checks: { count: 71, failed: 1 },
    },
    calendar: PAPER_CALENDAR,
    filters: {
      total: 6,
      rules: [
        { rule: INDEX_HALF, count: 3 },
        { rule: MOMENTUM, count: 1 },
      ],
      kinds: [
        { kind: 'rebalance', count: 3 },
        { kind: 'deposit', count: 0 },
        { kind: 'withdrawal', count: 0 },
        { kind: 'dividend', count: 1 },
        { kind: 'failed', count: 1 },
      ],
    },
    months: [
      { month: '2026-10', change: 70_300, events: [EVENT_1007] },
      { month: '2026-09', change: 58_700, events: [EVENT_0930, EVENT_0914, EVENT_0909] },
      { month: '2026-08', change: 162_200, events: [EVENT_0821] },
      { month: '2026-07', change: -47_400, events: [EVENT_0701] },
    ],
    offPeriods: [],
  };
}

/**
 * 일부 실패 세계 (값표 §3, 10/8 08:40): the 10/7 buy failed (no quote) and goes again 10/8 22:30.
 * Totals are 1.1's (the table assumes the same closes).
 */
export function historyPartial(): HistoryResponse {
  const base = historyPaper();
  const event1007: HistoryEvent = {
    ...EVENT_1007,
    kind: 'partial-failed',
    stagesMini: ['done', 'done', 'failed'],
    retry: { date: '2026-10-08', filled: false },
  };
  return {
    ...base,
    trend: {
      ...base.trend,
      events: base.trend.events.map((e) =>
        e.date === '2026-10-07' ? { ...e, kind: 'partial-failed' } : e,
      ),
    },
    tiles: { ...base.tiles, rebalances: { count: 3, partialFailed: 2, inProgress: 0 } },
    calendar: base.calendar.map((c) =>
      c.date === '2026-10-07'
        ? { ...c, state: 'partial-failed' }
        : c.date === '2026-10-08'
          ? { ...c, state: 'future' }
          : c,
    ),
    months: base.months.map((m) => (m.month === '2026-10' ? { ...m, events: [event1007] } : m)),
  };
}

/**
 * 시세 대기 (값표 §3): US quotes stuck at 10/2, the 10/6 and 10/7 checks waited (주문 0건), so
 * there is no 10/7 rebalance. Total 10,217,664 (+217,664 · +2.18%); 10월 = 10,217,664 − 9/30's
 * 10,173,500 = +44,164. Fees lose 10/7's 27원; rebalances 2 (8/21, 9/14).
 */
export function historyStale(): HistoryResponse {
  const base = historyPaper();
  const series = base.trend.series.map((p) =>
    p.date === '2026-10-07' ? { ...p, value: 10_217_664 } : p,
  );
  return {
    ...base,
    trend: {
      ...base.trend,
      basis: { ...BASIS_1007, usClose: '2026-10-02' },
      total: 10_217_664,
      pnl: { amount: 217_664, pct: 2.18 },
      series,
      events: base.trend.events.filter((e) => e.date !== '2026-10-07'),
    },
    tiles: {
      rebalances: { count: 2, partialFailed: 1, inProgress: 0 },
      fees: { krw: 5_908 },
      checks: { count: 71, failed: 1 },
    },
    calendar: base.calendar.map((c) =>
      c.date === '2026-10-06' || c.date === '2026-10-07' ? { ...c, state: 'quote-wait' } : c,
    ),
    filters: {
      total: 5,
      rules: [
        { rule: INDEX_HALF, count: 2 },
        { rule: MOMENTUM, count: 1 },
      ],
      kinds: [
        { kind: 'rebalance', count: 2 },
        { kind: 'deposit', count: 0 },
        { kind: 'withdrawal', count: 0 },
        { kind: 'dividend', count: 1 },
        { kind: 'failed', count: 1 },
      ],
    },
    months: [
      { month: '2026-10', change: 44_164, events: [] },
      ...base.months.filter((m) => m.month !== '2026-10'),
    ],
  };
}

/** 첫 확인 전 (6/30 18:00): the start amount only, no graph, empty calendar (기획 §5 empty). */
export function historyEmpty(): HistoryResponse {
  return {
    ledger: 'paper',
    example: true,
    year: 2026,
    years: [2026],
    trend: {
      since: '2026-07-01',
      basis: {
        valuedAt: kst('2026-06-30', '16:00'),
        krClose: null,
        usClose: null,
        fxRate: null,
        fxAt: null,
      },
      total: START_CAPITAL,
      pnl: null,
      series: [],
      events: [],
    },
    tiles: {
      rebalances: { count: 0, partialFailed: 0, inProgress: 0 },
      fees: { krw: 0 },
      checks: { count: 0, failed: 0 },
    },
    calendar: weekdayCalendar('2026-07-01', '2026-07-03', '2026-06-30', {}),
    filters: {
      total: 1,
      rules: [
        { rule: INDEX_HALF, count: 0 },
        { rule: MOMENTUM, count: 0 },
      ],
      kinds: [
        { kind: 'rebalance', count: 0 },
        { kind: 'deposit', count: 0 },
        { kind: 'withdrawal', count: 0 },
        { kind: 'dividend', count: 0 },
        { kind: 'failed', count: 0 },
      ],
    },
    months: [
      {
        month: '2026-07',
        change: 0,
        events: [
          {
            date: '2026-07-01',
            kind: 'start',
            amount: START_CAPITAL,
            treatment: 'pnl-excluded',
            dayChange: null,
            dayTotal: START_CAPITAL,
          },
        ],
      },
    ],
    offPeriods: [],
  };
}

// ── 실전 (값표 §2: 켬 8/31 21:10, 첫 확인 9/1, 시작 10,000,000원) ────────────────

const LIVE_CALENDAR = weekdayCalendar('2026-09-01', '2026-10-09', '2026-10-07', {
  '2026-09-07': 'holiday-one',
  '2026-09-09': 'failed',
  '2026-09-24': 'holiday-one',
  '2026-09-25': 'holiday-one',
  '2026-10-05': 'holiday-one',
  '2026-10-07': 'in-progress',
});

/**
 * 실전 9/1–10/7 (27 checks; the 9/9 check failed for both ledgers), 지수 반반 alone (D47). The
 * owner converted about half before turning on, so the first plan bought both ETFs in one buy stage
 * (한국 09:05, 미국 22:30): fees ≈ 5,590원. 10/7 buys S&P 500 ETF at 22:30 with dollars he
 * converted on 10/6 (no fee yet). Month changes from the 실전 line: 9/30 10,060,000 → 9월 +60,000,
 * 10월 +52,670.
 */
export function historyLive(): HistoryResponse {
  const live1007: HistoryEvent = {
    ...EVENT_1007,
    stagesMini: ['pending'],
    fill: 'live',
    fees: 0,
    dayChange: 14_670,
    dayTotal: 10_112_670,
  };
  return {
    ledger: 'live',
    example: true,
    year: 2026,
    years: [2026],
    trend: {
      since: '2026-09-01',
      basis: BASIS_1007,
      total: 10_112_670,
      pnl: { amount: 112_670, pct: 1.13 },
      series: liveDaily.flatMap((p) =>
        p.value === null ? [] : [{ date: p.date, value: p.value }],
      ),
      events: [
        { date: '2026-09-01', kind: 'start' },
        { date: '2026-09-09', kind: 'check-failed' },
        { date: '2026-10-07', kind: 'in-progress' },
      ],
    },
    tiles: {
      rebalances: { count: 1, partialFailed: 0, inProgress: 1 },
      fees: { krw: 5_590 },
      checks: { count: 27, failed: 1 },
    },
    calendar: LIVE_CALENDAR,
    filters: {
      total: 3,
      rules: [{ rule: INDEX_HALF, count: 1 }],
      kinds: [
        { kind: 'rebalance', count: 1 },
        { kind: 'deposit', count: 0 },
        { kind: 'withdrawal', count: 0 },
        { kind: 'dividend', count: 0 },
        { kind: 'failed', count: 1 },
      ],
    },
    months: [
      { month: '2026-10', change: 52_670, events: [live1007] },
      {
        month: '2026-09',
        change: 60_000,
        events: [
          {
            date: '2026-09-09',
            kind: 'check-failed',
            failureReason: 'no-quote',
            recoveredOn: '2026-09-10',
            dayChange: -2_700,
            dayTotal: 9_985_000,
          },
          {
            date: '2026-09-01',
            kind: 'start',
            amount: START_CAPITAL,
            treatment: 'pnl-excluded',
            stagesMini: ['done'],
            fill: 'live',
            fees: 5_590,
            dayChange: null,
            dayTotal: 9_994_400,
          },
        ],
      },
    ],
    offPeriods: [],
  };
}

/**
 * 끈 기간 (spec only, SCR-HISTORY.off-period): the 실전 ledger was turned off 9/18 16:12 and on
 * again for 9/28, so 9/21–9/25 have no 실전 check (빗금). Checks 27 − 5 = 22.
 */
export function historyOffPeriod(): HistoryResponse {
  const base = historyLive();
  return {
    ...base,
    trend: {
      ...base.trend,
      events: [
        ...base.trend.events.slice(0, 2),
        { date: '2026-09-18', kind: 'live-off' },
        { date: '2026-09-28', kind: 'live-on' },
        ...base.trend.events.slice(2),
      ],
    },
    tiles: { ...base.tiles, checks: { count: 22, failed: 1 } },
    calendar: base.calendar.map((c) =>
      c.date >= '2026-09-21' && c.date <= '2026-09-25' ? { ...c, state: 'no-run' } : c,
    ),
    offPeriods: [{ from: '2026-09-21', to: '2026-09-25' }],
  };
}
