// 자산 변동 (Figma '자산 변동'): 기간 손익 › (변동 분해 시트) · 금액|수익률 / 기간 칩 (30거래일부터) /
// 선 그래프 (내 자산 · 손대지 않았을 때) / 사건 띠 (표식 → 그날, '[n]' → 사건 목록, ⓘ → 범례) /
// 범례 · 표로 보기. A card on 1440; plain on 390. One account (한국 ₩ · 미국 $) draws its own line in
// its own money; its dashed line is 원금 (money in by that day), not 손대지 않았을 때 (that
// comparison is the whole ledger's): a conversion moves both lines, the gap is the P&L.
import clsx from 'clsx';
import { useId, useState } from 'react';
import { ChevronRight, ChevronUp } from 'lucide-react';
import { markerKind } from '../../api/adapters';
import { useBreakdown } from '../../api/queries';
import type {
  AccountId,
  Breakdown,
  Currency,
  EventKind,
  HomePeriod,
  HomeResponse,
  Trend,
} from '../../api/types';
import { ChartTable } from '../../charts/ChartTable';
import { LineChart } from '../../charts/LineChart';
import {
  LINE_HOME_1440,
  LINE_HOME_390,
  MARKER,
  niceStep,
  niceYAxis,
  type ChartEvent,
  type YAxis,
} from '../../charts/geometry/lineChart';
import { Waterfall } from '../../charts/Waterfall';
import type { WaterfallStep } from '../../charts/geometry/waterfall';
import { PeriodChip } from '../../components/Chips';
import { ErrorBlock, SkeletonBlock } from '../../components/State';
import { copy } from '../../copy';
import { homeCopy } from '../../copy/home';
import { eventLabel } from '../../lib/labels';
import { formatMonthDay, formatPercentSigned } from '../../lib/format';
import { EventListSheet, LegendSheet } from './EventListSheet';
import { formatMoney, formatMoneySigned, moneyDirection, moneyTick } from './money';
import { Sheet } from './Sheet';
import styles from './Home.module.css';

type Mode = 'amount' | 'rate';

/**
 * What the 사건 띠 shows (기획 §5 SCR-HOME 자산 변동 and its ⓘ legend): 시작 · 리밸런싱 · 일부
 * 실패 · 진행 중 · 배당 · 입금 · 출금 · 실전 켬/끔. A failed check is not one of them (기록 and 작동
 * show it), so a day that only had one draws no marker.
 */
const BAND_KINDS: ReadonlySet<EventKind> = new Set([
  'start',
  'rebalance',
  'partial-failed',
  'in-progress',
  'dividend',
  'deposit',
  'withdrawal',
  'live-on',
  'live-off',
]);

/**
 * Trend events as band markers. A day's `kinds` lists every event of that day (CONTRACT Trend):
 * two or more become a grouped '[n]' marker whose list names each one.
 */
export function trendEvents(events: HomeResponse['trend']['events']): ChartEvent[] {
  return events.flatMap((e) => {
    const kinds = e.kinds.length > 0 ? e.kinds : [e.kind];
    return kinds.flatMap((k) => {
      const kind = BAND_KINDS.has(k) ? markerKind(k) : null;
      return kind === null ? [] : [{ date: e.date, kind, label: eventLabel(e.date, kind) }];
    });
  });
}

/**
 * One point (or none): the point on the lowest line (Figma 1:55613) — 10만 steps in won, about
 * 2% steps in dollars ($50 at $3,568).
 */
export function singlePointAxis(value: number, mode: Mode, currency: Currency = 'KRW'): YAxis {
  if (mode === 'rate') return niceYAxis([value - 1, value + 1]);
  const step = currency === 'USD' ? niceStep(Math.max(Math.abs(value) * 0.02, 1)) : 100_000;
  const base = Math.floor(value / step) * step;
  return { domain: [base - step, base + 2.75 * step], ticks: [base, base + step, base + 2 * step] };
}

/** '+2%' style ticks for the 수익률 line. */
function rateTick(v: number): string {
  return formatPercentSigned(v, Number.isInteger(v) ? 0 : 1);
}

function BreakdownSheet({
  period,
  account,
  onClose,
}: {
  period: HomePeriod;
  account?: AccountId | undefined;
  onClose: () => void;
}) {
  const q = useBreakdown({ period, account });
  const b = q.data;
  return (
    <Sheet
      title={`${homeCopy.breakdown.title} · ${homeCopy.trend.periods[period]}`}
      onClose={onClose}
    >
      {b ? (
        <BreakdownBody breakdown={b} />
      ) : q.isError ? (
        <ErrorBlock
          message={homeCopy.errors.load}
          onRetry={() => void q.refetch()}
          retrying={q.isFetching}
        />
      ) : (
        <SkeletonBlock height={224} />
      )}
    </Sheet>
  );
}

/**
 * Waterfall steps: 기간 시작 → 입금 → 출금 → 시세·환율 → 배당 → 수수료 → 지금. One account
 * (`currency` set) adds 환전 (money the conversions moved in or out) and its market move is 시세
 * only; 미국 계좌 has no deposits or withdrawals, so those rows are left out.
 */
export function breakdownSteps(b: Breakdown): WaterfallStep[] {
  const w = copy.waterfall;
  const account = b.currency !== undefined;
  const flows: WaterfallStep[] =
    b.currency === 'USD'
      ? []
      : [
          { key: 'deposit', label: w.deposit, kind: 'cashflow', value: b.deposit },
          { key: 'withdraw', label: w.withdraw, kind: 'cashflow', value: b.withdrawal },
        ];
  return [
    { key: 'start', label: w.start, kind: 'anchor', value: b.start },
    ...flows,
    ...(account
      ? [
          {
            key: 'transfer',
            label: homeCopy.breakdown.transfer,
            kind: 'cashflow' as const,
            value: b.transfer ?? 0,
          },
        ]
      : []),
    {
      key: 'market',
      label: account ? homeCopy.breakdown.market : w.market,
      kind: 'change',
      value: b.market,
    },
    { key: 'dividend', label: w.dividend, kind: 'change', value: b.dividend },
    { key: 'fee', label: w.fee, kind: 'change', value: b.fees },
    { key: 'end', label: w.end, kind: 'anchor', value: b.end },
  ];
}

export function BreakdownBody({ breakdown: b }: { breakdown: Breakdown }) {
  const steps = breakdownSteps(b);
  const currency = b.currency ?? 'KRW';
  const value = (s: WaterfallStep) =>
    s.kind === 'anchor' ? formatMoney(s.value, currency) : formatMoneySigned(s.value, currency);
  const range = homeCopy.breakdown.range(formatMonthDay(b.from), formatMonthDay(b.to));
  return (
    <>
      <p className={clsx('t-caption', styles.muted)}>{range}</p>
      <Waterfall
        steps={steps}
        formatValue={value}
        label={steps.map((s) => `${s.label} ${value(s)}`).join(' · ')}
      />
      <div className="sr-only">
        <ChartTable
          caption={`${homeCopy.breakdown.title} ${range}`}
          columns={[homeCopy.breakdown.title, copy.chart.myAssets]}
          rows={steps.map((s) => [s.label, value(s)])}
        />
      </div>
    </>
  );
}

export interface TrendCardProps {
  home: HomeResponse;
  wide: boolean;
  onPeriod: (period: HomePeriod) => void;
  /** One account's line in its own money (한국 ₩ · 미국 $); the whole ledger when absent. */
  account?: { id: AccountId; currency: Currency; trend: Trend; total: number } | undefined;
}

export function TrendCard({ home, wide, onPeriod, account }: TrendCardProps) {
  const [mode, setMode] = useState<Mode>('amount');
  const [table, setTable] = useState(false);
  const [sheet, setSheet] = useState<'breakdown' | 'legend' | ChartEvent[] | null>(null);
  const tableId = useId();
  const t = account ? account.trend : home.trend;
  const total = account ? account.total : home.total;
  const currency = account?.currency ?? 'KRW';
  const lineName = account ? homeCopy.accounts.name[account.id] : copy.chart.myAssets;
  const h = homeCopy.trend;

  const start = t.series[0]?.date ?? home.startDate;
  const end = t.series.at(-1)?.date ?? start;
  const pick = (p: (typeof t.series)[number]) => (mode === 'amount' ? p.value : p.ret);
  // The dashed line: 손대지 않았을 때 for the whole ledger; for one account its 원금 (money in by
  // that day), so a conversion that moves the value moves this line too and the gap stays the
  // P&L. In 수익률 an account's line is already net of what came in: no second line.
  const pickBase = (p: (typeof t.series)[number]) =>
    account
      ? mode === 'amount'
        ? (p.netIn ?? null)
        : null
      : mode === 'amount'
        ? p.baseline
        : p.baselineRet;
  const baseName = account ? homeCopy.accounts.netIn : copy.chart.untouched;
  const mine = { key: 'mine', points: t.series.map((p) => ({ date: p.date, value: pick(p) })) };
  const basePoints = t.series.map((p) => ({ date: p.date, value: pickBase(p) }));
  const hasBaseline = t.series.length >= 2 && basePoints.some((p) => p.value !== null);
  const values = [
    ...mine.points.map((p) => p.value),
    ...(hasBaseline ? basePoints.flatMap((p) => (p.value === null ? [] : [p.value])) : []),
  ];
  const axis =
    t.series.length >= 2
      ? niceYAxis(values)
      : singlePointAxis(t.series[0] ? pick(t.series[0]) : total, mode, currency);
  const formatTick =
    t.empty === 'before-first-check'
      ? () => ''
      : mode === 'amount'
        ? moneyTick(currency)
        : rateTick;
  const emptyText =
    t.empty === 'before-first-check'
      ? h.emptyBeforeCheck
      : t.empty === 'before-first-fill'
        ? h.emptyBeforeFill
        : t.empty === 'first-day'
          ? h.emptyFirstDay
          : undefined;
  const fmt = (v: number | null) =>
    v === null ? '—' : mode === 'amount' ? formatMoney(v, currency) : formatPercentSigned(v, 2);
  const label =
    mine.points.length > 0
      ? `${lineName} ${formatMonthDay(start)} ${fmt(mine.points[0]?.value ?? null)} → ${formatMonthDay(end)} ${fmt(mine.points.at(-1)?.value ?? null)}`
      : `${lineName} · ${emptyText ?? ''}`;

  const pnl = t.periodPnl;
  const dir = pnl ? moneyDirection(pnl.amount, currency) : 'flat';
  const arrow = dir === 'gain' ? homeCopy.hero.up : dir === 'loss' ? homeCopy.hero.down : '';

  const modeChips = (
    <div className={styles.chips} role="group" aria-label={h.modeGroup}>
      {(['amount', 'rate'] as const).map((m) => (
        <PeriodChip
          key={m}
          selected={mode === m}
          onClick={() => {
            setMode(m);
          }}
        >
          {m === 'amount' ? h.amount : h.rate}
        </PeriodChip>
      ))}
    </div>
  );

  return (
    <section className={clsx(styles.trend, wide && styles.card)} aria-label={h.title}>
      {pnl || t.empty !== 'before-first-check' ? (
        <div className={clsx(styles.trendTop, !pnl && styles.trendTopStart)}>
          {pnl ? (
            <button
              type="button"
              className={styles.periodPnl}
              onClick={() => {
                setSheet('breakdown');
              }}
            >
              <span className={clsx('t-label', styles.muted)}>{h.periods[t.period]}</span>
              <span className={clsx('t-label', styles[dir])}>
                {`${arrow ? `${arrow} ` : ''}${formatMoneySigned(pnl.amount, currency)} (${formatPercentSigned(pnl.pct, 2)})`}
              </span>
              <ChevronRight size={14} className={styles.muted} aria-hidden />
            </button>
          ) : null}
          {t.empty !== 'before-first-check' ? modeChips : null}
        </div>
      ) : null}

      {t.periods ? (
        <div className={styles.chips} role="group" aria-label={h.periodGroup}>
          {t.periods.map((p) => (
            <PeriodChip
              key={p}
              selected={p === t.period}
              onClick={() => {
                onPeriod(p);
              }}
            >
              {h.periods[p]}
            </PeriodChip>
          ))}
        </div>
      ) : null}

      <LineChart
        layout={wide ? LINE_HOME_1440 : LINE_HOME_390}
        start={start}
        end={end}
        axis={axis}
        mine={mine}
        baseline={hasBaseline ? { key: 'base', points: basePoints } : undefined}
        events={trendEvents(t.events)}
        hrefFor={(date) => `/day/${date}`}
        onLegend={() => {
          setSheet('legend');
        }}
        onGroup={(events) => {
          setSheet(events);
        }}
        // Overlapping markers merge into '[n]' (기획 '겹치면 묶음', WCAG 2.5.8 target size).
        groupBelow={MARKER}
        label={label}
        formatTick={formatTick}
        emptyText={emptyText}
      />

      {t.empty !== 'before-first-check' ? (
        <div className={styles.legendRow}>
          <ul className={styles.legend}>
            <li className={styles.legendItem}>
              <svg className={styles.swatch} viewBox="0 0 16 8" aria-hidden>
                <line className={styles.swatchMine} x1="0" y1="4" x2="16" y2="4" strokeWidth="2" />
              </svg>
              <span className={clsx('t-caption', styles.muted)}>{lineName}</span>
            </li>
            {hasBaseline ? (
              <li className={styles.legendItem}>
                <svg className={styles.swatch} viewBox="0 0 16 8" aria-hidden>
                  <line
                    className={styles.swatchBase}
                    x1="0"
                    y1="4"
                    x2="16"
                    y2="4"
                    strokeWidth="1.5"
                    strokeDasharray="5 4"
                  />
                </svg>
                <span className={clsx('t-caption', styles.muted)}>{baseName}</span>
              </li>
            ) : null}
          </ul>
          <button
            type="button"
            className={styles.textButton}
            aria-expanded={table}
            aria-controls={tableId}
            onClick={() => {
              setTable(!table);
            }}
          >
            <span className="t-label">{table ? copy.collapse : copy.chart.tableView}</span>
            {table ? <ChevronUp size={16} aria-hidden /> : <ChevronRight size={16} aria-hidden />}
          </button>
        </div>
      ) : null}

      {table ? (
        <div id={tableId} className={styles.tableWrap}>
          <ChartTable
            caption={copy.chart.tableView}
            columns={[copy.chart.dateColumn, lineName, ...(hasBaseline ? [baseName] : [])]}
            rows={t.series.map((p) => [
              formatMonthDay(p.date),
              fmt(pick(p)),
              ...(hasBaseline ? [fmt(pickBase(p))] : []),
            ])}
          />
        </div>
      ) : null}

      {sheet === 'breakdown' ? (
        <BreakdownSheet
          period={t.period}
          account={account?.id}
          onClose={() => {
            setSheet(null);
          }}
        />
      ) : null}
      {sheet === 'legend' ? (
        <LegendSheet
          onClose={() => {
            setSheet(null);
          }}
        />
      ) : null}
      {Array.isArray(sheet) ? (
        <EventListSheet
          events={sheet}
          onClose={() => {
            setSheet(null);
          }}
        />
      ) : null}
    </section>
  );
}
