// 한국 계좌 · 미국 계좌 of the 예시-값표 worlds (CONTRACT.md HomeResponse.accounts), the way the
// engine splits a ledger (autotrade/api/views/accounts.py):
// - 한국 = won holdings + won cash (BTC is bought in won, so it is here), 미국 = dollar holdings +
//   dollar cash, each valued in its own money;
// - money in: the start amount into 한국; each conversion moves its won out of 한국 and its dollars
//   into 미국 (값표 §1.4: 7/1 4,768,000원 → $3,425.28 · 8/21 175,000원 → $125.93 · 10/7 173,000원 →
//   $125.30, each at 09:10, so in that day's 16:00 value);
// - 전체 손익 = 한국 + 미국 in won (× 1,382.4, rounded) + 환율 효과 (the remainder);
// - an account's % is its P&L over the money it held on average (`dietzPct`, the server's
//   modified Dietz return): the start at 7/1 08:30 and each conversion at 09:10 weighted by the
//   share of the time they were in the account.
// The table has no per-account daily values: the dollar line is the table's holdings at prices that
// run from the buys ($66.00 · $172.00) to the 10/6 closes ($62.40 · $176.40), the rate from 1,392.0
// (7/1) through 1,389.6 (8/21) to 1,382.4 (10/7); 한국 is the day's total minus 미국 in won. The
// 10/7 numbers are the table's exactly.
import type {
  Breakdown,
  CompRow,
  Composition,
  HomeAccount,
  HomeAccounts,
  HomePeriod,
  Trend,
} from '../../api/types';
import type { LinePoint } from '../../charts/geometry/lineChart';
import { paperDaily3m, paperDailySinceStart } from '../charts';
import { BTC, INDEX_HALF, KOSPI200, MOMENTUM, NVDA, SAMSUNG, SP500, START_CAPITAL } from '../world';

/** Percent shares to 0.1 that add up to 100.0 (largest remainder, as the server's allocate_pct1). */
export function allocatePct1(values: readonly number[]): number[] {
  const total = values.reduce((s, v) => s + v, 0);
  if (total <= 0) return values.map(() => 0);
  const raw = values.map((v) => (v * 1000) / total);
  const floors = raw.map((r) => Math.floor(r));
  const short = 1000 - floors.reduce((s, f) => s + f, 0);
  const order = raw
    .map((r, i) => ({ i, rest: r - (floors[i] ?? 0), v: values[i] ?? 0 }))
    .sort((a, b) => b.rest - a.rest || b.v - a.v);
  for (const { i } of order.slice(0, Math.max(short, 0))) floors[i] = (floors[i] ?? 0) + 1;
  return floors.map((f) => f / 10);
}

const won = (cents: number, rateTenths: number) => Math.round((cents * rateTenths) / 1000);
const dollars = (cents: number) => Math.round(cents) / 100;

// ── 모의투자 world (값표 §1, 10/7 16:10) ──────────────────────────────────────────────────

/** Conversions (09:10): won out of 한국, dollars into 미국. */
const CONVERSIONS = [
  { date: '2026-07-01', krw: 4_768_000, cents: 342_528 },
  { date: '2026-08-21', krw: 175_000, cents: 12_593 },
  { date: '2026-10-07', krw: 173_000, cents: 12_530 },
] as const;

const LAST = '2026-10-07';
const DAYS = paperDailySinceStart.map((p) => p.date);

/** Minutes from the start (7/1 08:30 KST) to a moment of a day. */
const minutes = (date: string, hhmm: string) =>
  (Date.parse(`${date}T${hhmm}:00+09:00`) - Date.parse('2026-07-01T08:30:00+09:00')) / 60_000;
/** 16:00 (the day's value) and now (10/7 16:10). */
const VALUED = '16:00';
const NOW = minutes(LAST, '16:10');

/** Money into an account and when: the start into 한국, each conversion out of 한국 into 미국. */
function flowsOf(id: 'kr' | 'us'): { at: number; amount: number }[] {
  const moved = CONVERSIONS.map((c) => ({
    at: minutes(c.date, '09:10'),
    amount: id === 'kr' ? -c.krw : dollars(c.cents),
  }));
  return id === 'kr' ? [{ at: 0, amount: START_CAPITAL }, ...moved] : moved;
}

/**
 * The account's % from `start` (its value then, or nothing before its first money) to `end`: the
 * gain over the money held on average (autotrade/api/views/accounts.py `dietz`). null when it held
 * nothing on average.
 */
function dietzPct(
  id: 'kr' | 'us',
  end: { at: number; value: number },
  start: { at: number; value: number } | null,
): number | null {
  const all = flowsOf(id);
  const from = start?.at ?? all[0]?.at ?? 0;
  const flows = all.filter((f) => f.at <= end.at && (start === null || f.at > start.at));
  const span = end.at - from;
  const moved = flows.reduce((s, f) => s + f.amount, 0);
  const held =
    (start?.value ?? 0) +
    flows.reduce(
      (s, f) => s + f.amount * (span > 0 ? Math.min(Math.max((end.at - f.at) / span, 0), 1) : 1),
      0,
    );
  if (held <= 0) return null;
  return Math.round(((end.value - (start?.value ?? 0) - moved) / held) * 10_000) / 100;
}

/** 미국 계좌 holdings in a day's 16:00 value (the US buys come at 22:30, after it). */
function usHoldings(date: string): { spym: number; nvda: number; cash: number } {
  if (date === '2026-07-01') return { spym: 0, nvda: 0, cash: 342_528 };
  if (date < '2026-08-21') return { spym: 44, nvda: 3, cash: 186 };
  if (date === '2026-08-21') return { spym: 44, nvda: 3, cash: 186 + 12_593 };
  if (date < LAST) return { spym: 46, nvda: 3, cash: 166 };
  return { spym: 46, nvda: 3, cash: 166 + 12_530 };
}

/** A path from `from` to `to` over the record, with a wobble that is 0 on the last day. */
function path(date: string, from: number, to: number, wobble: (n: number) => number): number {
  const n = DAYS.indexOf(date);
  const f = n / (DAYS.length - 1);
  return Math.round(from + (to - from) * f + wobble(n) * (1 - f));
}

const spymCents = (d: string) =>
  path(d, 6600, 6240, (n) => 70 * Math.sin(n * 0.45) + 25 * Math.sin(n * 1.7));
const nvdaCents = (d: string) =>
  path(d, 17_200, 17_640, (n) => 320 * Math.sin(n * 0.33) + 110 * Math.sin(n * 1.3));

/** KRW per USD in tenths: 1,392.0 (7/1) → 1,389.6 (8/21) → 1,382.4 (10/7 16:00). */
function rateTenths(date: string): number {
  const i = DAYS.indexOf(date);
  const a = DAYS.indexOf('2026-08-21');
  const z = DAYS.length - 1;
  if (i <= 0) return 13_920;
  if (i === a) return 13_896;
  if (i === z) return 13_824;
  const base =
    i < a ? 13_920 + ((13_896 - 13_920) * i) / a : 13_896 + ((13_824 - 13_896) * (i - a)) / (z - a);
  return Math.round(base + 9 * Math.sin(i * 0.8));
}

function netIn(date: string): { krw: number; cents: number } {
  const done = CONVERSIONS.filter((c) => c.date <= date);
  return {
    krw: START_CAPITAL - done.reduce((s, c) => s + c.krw, 0),
    cents: done.reduce((s, c) => s + c.cents, 0),
  };
}

/** One day of both accounts: 미국 in cents and in won, 한국 = the day's total − 미국 in won. */
function day(date: string, total: number) {
  const h = usHoldings(date);
  const rate = rateTenths(date);
  const spym = h.spym * spymCents(date);
  const nvda = h.nvda * nvdaCents(date);
  const usCents = spym + nvda + h.cash;
  const usWon = won(spym, rate) + won(nvda, rate) + won(h.cash, rate);
  return { date, kr: total - usWon, usCents, rate };
}

const SINCE: Record<HomePeriod, string> = {
  '1m': '2026-09-07',
  '3m': '2026-07-07',
  '1y': '2026-07-01',
  all: '2026-07-01',
};

function lineOf(period: HomePeriod): readonly LinePoint[] {
  // The same days the 전체 line of that period draws (home.ts paperTrend).
  return period === '1m' || period === '3m' ? paperDaily3m : paperDailySinceStart;
}

function days(period: HomePeriod) {
  return lineOf(period).flatMap((p) =>
    p.value === null || p.date < SINCE[period] ? [] : [day(p.date, p.value)],
  );
}

type Markers = Trend['events'];

const KR_MARKERS: Markers = [
  { date: '2026-07-01', kind: 'start', kinds: ['start'] },
  { date: '2026-08-21', kind: 'rebalance', kinds: ['rebalance'] },
  // 9/14 sold 삼성전자 and bought BTC, both in won: only 한국 계좌 moved.
  { date: '2026-09-14', kind: 'partial-failed', kinds: ['partial-failed'] },
  { date: '2026-09-30', kind: 'dividend', kinds: ['dividend'] },
  { date: '2026-10-07', kind: 'in-progress', kinds: ['in-progress'] },
];
const US_MARKERS: Markers = KR_MARKERS.filter(
  (m) => m.kind !== 'partial-failed' && m.kind !== 'dividend',
);

function trendOf(id: 'kr' | 'us', period: HomePeriod): Trend {
  const points = days(period);
  const value = (p: (typeof points)[number]) => (id === 'kr' ? p.kr : dollars(p.usCents));
  const base = (date: string) => (id === 'kr' ? netIn(date).krw : dollars(netIn(date).cents));
  const first = points[0];
  const last = day(LAST, 10_243_800);
  let periodPnl: Trend['periodPnl'] = null;
  if (period !== 'all' && first) {
    const startIn = netIn(first.date);
    const endIn = netIn(LAST);
    const amount =
      id === 'kr'
        ? last.kr - first.kr - (endIn.krw - startIn.krw)
        : dollars(last.usCents - first.usCents - (endIn.cents - startIn.cents));
    // pct: the account's return from the period start (its value at that day's 16:00) to now
    const pct = dietzPct(
      id,
      { at: NOW, value: value(last) },
      { at: minutes(first.date, VALUED), value: value(first) },
    );
    periodPnl = pct === null ? null : { amount, pct };
  }
  const markers = id === 'kr' ? KR_MARKERS : US_MARKERS;
  return {
    periods: ['1m', '3m', '1y', 'all'],
    period,
    periodPnl,
    series: points.map((p) => ({
      date: p.date,
      value: value(p),
      ret: dietzPct(id, { at: minutes(p.date, VALUED), value: value(p) }, null) ?? 0,
      baseline: null,
      baselineRet: null,
      netIn: base(p.date),
    })),
    events: markers.filter((m) => m.date >= (first?.date ?? SINCE[period])),
    empty: null,
  };
}

function withPct(rows: CompRow[], amounts: readonly number[]): CompRow[] {
  const pcts = allocatePct1(amounts);
  return rows.map((r, i) => ({ ...r, pct: pcts[i] ?? 0 }));
}

function grouped(
  rows: CompRow[],
  groups: { key: string; take: number; rule?: typeof INDEX_HALF; label?: 'cash' }[],
  groupBy: Composition['groupBy'],
): Composition {
  let at = 0;
  return {
    groupBy,
    groups: groups.map((g) => {
      const members = rows.slice(at, at + g.take);
      at += g.take;
      const pct = Math.round(members.reduce((s, r) => s + r.pct, 0) * 10) / 10;
      return {
        key: g.key,
        ...(g.rule ? { rule: g.rule } : {}),
        ...(g.label ? { label: g.label } : {}),
        pct,
        target: null,
        rows: members,
      };
    }),
    pendingBar: null,
    outsideRules: null,
  };
}

/** 한국 계좌 at 10/7 16:00 (값표 §1.1 rows in won). */
const KR_ROWS: CompRow[] = [
  {
    kind: 'holding',
    instrument: KOSPI200,
    pct: 0,
    krw: 4_168_750,
    pnlPct: 13.3,
    qty: 115,
    avgCost: { amount: 32_005, currency: 'KRW' },
  },
  {
    kind: 'holding',
    instrument: SAMSUNG,
    pct: 0,
    krw: 788_200,
    pnlPct: 1.4,
    qty: 14,
    avgCost: { amount: 55_508, currency: 'KRW' },
  },
  {
    kind: 'holding',
    instrument: BTC,
    pct: 0,
    krw: 355_185,
    pnlPct: -15.1,
    qty: 0.0027,
    avgCost: { amount: 154_930_000, currency: 'KRW' },
  },
  {
    kind: 'cash',
    cash: { currency: 'KRW', country: 'KR' },
    pct: 0,
    krw: 56_548,
    chip: { kind: 'sub-share' },
  },
];

/** 미국 계좌 at 10/7 16:00 in dollars; the % of each holding is in dollars (no rate in it). */
const US_ROWS: CompRow[] = [
  {
    kind: 'holding',
    instrument: SP500,
    pct: 0,
    krw: 3_968_041,
    usd: 2_870.4,
    // ($2,870.40 − $3,033.03) ÷ $3,033.03 (fees in the cost): in won, with the rate, −6.0%.
    pnlPct: -5.4,
    qty: 46,
    avgCost: { amount: 65.94, currency: 'USD' },
  },
  {
    kind: 'cash',
    cash: { currency: 'USD', country: 'US' },
    pct: 0,
    krw: 175_510,
    usd: 126.96,
    chip: { kind: 'buy-wait', instrumentName: 'S&P 500 ETF', qty: 2 },
  },
  {
    kind: 'holding',
    instrument: NVDA,
    pct: 0,
    krw: 731_566,
    usd: 529.2,
    pnlPct: 2.5, // ($529.20 − $516.52) ÷ $516.52
    qty: 3,
    avgCost: { amount: 172.17, currency: 'USD' },
  },
];

export const PAPER_KR_COMPOSITION: Composition = grouped(
  withPct(
    KR_ROWS,
    KR_ROWS.map((r) => r.krw),
  ),
  [
    { key: INDEX_HALF.id, take: 1, rule: INDEX_HALF },
    { key: MOMENTUM.id, take: 2, rule: MOMENTUM },
    { key: 'cash', take: 1, label: 'cash' },
  ],
  ['instrument', 'kind', 'country', 'rule'],
);

export const PAPER_US_COMPOSITION: Composition = grouped(
  withPct(
    US_ROWS,
    US_ROWS.map((r) => (r.usd ?? 0) * 100),
  ),
  [
    { key: INDEX_HALF.id, take: 2, rule: INDEX_HALF },
    { key: MOMENTUM.id, take: 1, rule: MOMENTUM },
  ],
  ['instrument', 'kind', 'rule'],
);

/** 10/7: 한국 5,368,683원 (+484,683원 on 4,884,000원 in) · 미국 $3,526.56 (−$149.95 on $3,676.51). */
export function paperAccounts(period: HomePeriod = '3m'): HomeAccounts {
  const kr: HomeAccount = {
    id: 'kr',
    currency: 'KRW',
    total: 5_368_683,
    pnl: { amount: 484_683, pct: dietzPct('kr', { at: NOW, value: 5_368_683 }, null) },
    stale: false,
    trend: trendOf('kr', period),
    composition: PAPER_KR_COMPOSITION,
  };
  const us: HomeAccount = {
    id: 'us',
    currency: 'USD',
    total: 3_526.56,
    pnl: { amount: -149.95, pct: dietzPct('us', { at: NOW, value: 3_526.56 }, null) },
    stale: false,
    trend: trendOf('us', period),
    composition: PAPER_US_COMPOSITION,
  };
  // +243,800 = +484,683 + round(−$149.95 × 1,382.4) (−207,291) + 환율 효과 (−33,592): the
  // dollars bought at 1,392.0 · 1,389.6 · 1,380.6 are worth 1,382.4 now.
  return { list: [kr, us], split: { kr: 484_683, us: -207_291, fx: -33_592 } };
}

/**
 * 변동 분해 of one account (sum of the bars = end − start). Fees per account (값표 §1.2 수수료
 * 누계 5,935원 split by currency): 한국 7/1 906 · 8/21 25 · 9/14 8 · 9/15 27 · 10/7 27, 미국 7/1
 * $3.42 (22:30, after that day's value) · 8/21 $0.13.
 */
export function paperAccountBreakdown(id: 'kr' | 'us', period: HomePeriod): Breakdown {
  const all = period === 'all';
  const first = days(period)[0] ?? day('2026-07-01', START_CAPITAL);
  const from = all ? '2026-07-01' : first.date;
  const moved = CONVERSIONS.filter((c) => (all ? true : c.date > from));
  const end = day(LAST, 10_243_800);
  if (id === 'kr') {
    const start = all ? START_CAPITAL : first.kr;
    const transfer = -moved.reduce((s, c) => s + c.krw, 0);
    const dividend = from < '2026-09-30' ? 16_243 : 0;
    const fees = all ? -993 : from < '2026-08-21' ? -87 : from < '2026-09-14' ? -62 : -27;
    const market = end.kr - start - transfer - dividend - fees;
    return {
      from,
      to: LAST,
      currency: 'KRW',
      start,
      deposit: 0,
      withdrawal: 0,
      transfer,
      market,
      dividend,
      fees,
      end: end.kr,
    };
  }
  const start = all ? 0 : first.usCents;
  const transfer = moved.reduce((s, c) => s + c.cents, 0);
  const fees = all || from === '2026-07-01' ? -355 : from < '2026-08-21' ? -13 : 0;
  const market = end.usCents - start - transfer - fees;
  return {
    from,
    to: LAST,
    currency: 'USD',
    start: dollars(start),
    deposit: 0,
    withdrawal: 0,
    transfer: dollars(transfer),
    market: dollars(market),
    dividend: 0,
    fees: dollars(fees),
    end: dollars(end.usCents),
  };
}

// ── 출시 첫날 (값표 §4, 7/1 16:10): 미국 계좌 holds only the dollars waiting for 22:30 ──────────

/** 한국 5,040,052원 (+7,052원 on 5,033,000원 in) · 미국 $3,568.24 (no gain, no loss yet). */
export function firstDayAccounts(): HomeAccounts {
  const start: Markers = [{ date: '2026-07-01', kind: 'start', kinds: ['start'] }];
  const single = (value: number, ret: number, netIn: number): Trend => ({
    periods: null,
    period: 'all',
    periodPnl: null,
    series: [{ date: '2026-07-01', value, ret, baseline: null, baselineRet: null, netIn }],
    events: start,
    empty: 'first-day',
  });
  return {
    list: [
      {
        id: 'kr',
        currency: 'KRW',
        total: 5_040_052,
        // 7,052 over 10,000,000 from 08:30 less 4,967,000 from 09:10 (16:10: 5,464,870): 0.13%.
        pnl: { amount: 7_052, pct: 0.13 },
        stale: false,
        trend: single(5_040_052, 0.13, 5_033_000), // at 16:00: 5,474,583 held, 0.13%
        composition: {
          groupBy: [],
          groups: [
            {
              key: INDEX_HALF.id,
              rule: INDEX_HALF,
              pct: 99.2,
              target: null,
              rows: [
                {
                  kind: 'holding',
                  instrument: KOSPI200,
                  pct: 99.2,
                  krw: 4_999_800,
                  pnlPct: 0.1,
                  qty: 156,
                  avgCost: { amount: 32_000, currency: 'KRW' },
                },
              ],
            },
            {
              key: 'cash',
              label: 'cash',
              pct: 0.8,
              target: null,
              rows: [
                {
                  kind: 'cash',
                  cash: { currency: 'KRW', country: 'KR' },
                  pct: 0.8,
                  krw: 40_252,
                  chip: { kind: 'sub-share' },
                },
              ],
            },
          ],
          pendingBar: null,
          outsideRules: null,
        },
      },
      {
        id: 'us',
        currency: 'USD',
        total: 3_568.24,
        pnl: { amount: 0, pct: 0 },
        stale: false,
        trend: single(3_568.24, 0, 3_568.24),
        composition: {
          groupBy: [],
          groups: [
            {
              key: INDEX_HALF.id,
              rule: INDEX_HALF,
              pct: 100,
              target: null,
              rows: [
                {
                  kind: 'cash',
                  cash: { currency: 'USD', country: 'US' },
                  pct: 100,
                  krw: 4_965_206,
                  usd: 3_568.24,
                  chip: { kind: 'buy-wait', instrumentName: 'S&P 500 ETF', qty: 54 },
                },
              ],
            },
          ],
          pendingBar: null,
          outsideRules: null,
        },
      },
    ],
    // +5,258 = +7,052 + 0 + (−1,794): $3,568.24 bought at 1,392.0 is 4,965,206원 at 1,391.5.
    split: { kr: 7_052, us: 0, fx: -1_794 },
  };
}

/** 7/1 09:07 (값표 §4 world): KOSPI200 ETF bought at 09:05; the 09:10 conversion not yet run. */
export function usEmptyAccounts(): HomeAccounts {
  return {
    list: [
      {
        id: 'kr',
        currency: 'KRW',
        total: 9_999_252,
        pnl: { amount: -748, pct: -0.01 },
        stale: false,
        trend: {
          periods: null,
          period: 'all',
          periodPnl: null,
          series: [],
          events: [{ date: '2026-07-01', kind: 'start', kinds: ['start'] }],
          empty: 'first-day',
        },
        composition: {
          groupBy: [],
          groups: [
            {
              key: INDEX_HALF.id,
              rule: INDEX_HALF,
              pct: 100,
              target: null,
              rows: [
                {
                  kind: 'holding',
                  instrument: KOSPI200,
                  pct: 49.9,
                  krw: 4_992_000,
                  pnlPct: 0,
                  qty: 156,
                  avgCost: { amount: 32_005, currency: 'KRW' },
                },
                {
                  kind: 'cash',
                  cash: { currency: 'KRW', country: 'KR' },
                  pct: 50.1,
                  krw: 5_007_252,
                  chip: { kind: 'buy-wait', instrumentName: 'S&P 500 ETF', qty: 54 },
                },
              ],
            },
          ],
          pendingBar: null,
          outsideRules: null,
        },
      },
      {
        id: 'us',
        currency: 'USD',
        total: 0,
        pnl: null,
        stale: false,
        trend: {
          periods: null,
          period: 'all',
          periodPnl: null,
          series: [],
          events: [{ date: '2026-07-01', kind: 'start', kinds: ['start'] }],
          empty: null,
        },
        composition: { groupBy: [], groups: [], pendingBar: null, outsideRules: null },
      },
    ],
    split: { kr: -748, us: 0, fx: 0 },
  };
}
