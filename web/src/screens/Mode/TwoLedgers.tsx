// 두 장부 (Figma 1:64317 · 1:64799): legend chips that switch each line, 금액 | 수익률, one chart
// (실전 solid black · 모의투자 dashed purple · 손대지 않았을 때 dashed grey), the 차이 분해 stacked bar with
// its rows, and links to each ledger's 기록.
import clsx from 'clsx';
import { useId, useState } from 'react';
import { modeCopy as t } from '../../copy/mode';
import { copy } from '../../copy';
import type { ModeResponse } from '../../api/types';
import { CollapseButton, ExpandButton, LinkButton } from '../../components/Buttons';
import { PeriodChip } from '../../components/Chips';
import { CompositionBar } from '../../charts/CompositionBar';
import { ChartTable } from '../../charts/ChartTable';
import { useElementWidth } from '../../charts/useElementWidth';
import {
  anchoredDateTicks,
  lineGeometry,
  niceYAxis,
  placeDateLabels,
  type LineLayout,
  type YAxis,
} from '../../charts/geometry/lineChart';
import {
  formatDateTime,
  formatKrw,
  formatManAxis,
  formatMonthDay,
  formatPercentSigned,
  formatPp,
  pnlDirection,
} from '../../lib/format';
import { signedPct } from './text';
import styles from './Mode.module.css';

type TwoLedgers = NonNullable<ModeResponse['twoLedgers']>;
type LineKey = 'live' | 'paper' | 'baseline';
type Unit = 'amount' | 'ret';

/** 390 frame: 170 tall plot, 52 right gutter, labels 10 after the plot. */
const LAYOUT: LineLayout = { plotHeight: 170, gutter: 52, labelAlign: 'start', labelGap: 10 };

const NICE = [0.25, 0.5, 1, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10, 15, 20, 25, 30, 40, 50, 75, 100];

/**
 * Return axis of the drawing: a 0% line and one nice tick under the top value (+1.5% for a 1.75%
 * top), with room above and below (domain −0.8…2.6 for the 9/1–10/7 lines).
 */
export function retAxis(values: readonly number[]): YAxis {
  const finite = values.filter((v) => Number.isFinite(v));
  if (finite.length === 0) return { domain: [-1, 1], ticks: [0] };
  const min = Math.min(0, ...finite);
  const max = Math.max(0, ...finite);
  const range = max - min || 1;
  const top = max > 0 ? [...NICE].reverse().find((n) => n <= max) : undefined;
  const bottom =
    max <= 0 && min < 0 ? -([...NICE].reverse().find((n) => n <= -min) ?? 0) : undefined;
  const ticks = [0, ...(top !== undefined ? [top] : []), ...(bottom ? [bottom] : [])];
  return { domain: [min - 0.28 * range, max + 0.43 * range], ticks };
}

function tickLabel(unit: Unit, v: number): string {
  if (unit === 'amount') return formatManAxis(v);
  if (v === 0) return '0%';
  return formatPercentSigned(v, Number.isInteger(v) ? 0 : 1);
}

const LINE_CLASS: Record<LineKey, string | undefined> = {
  live: styles.lineLive,
  paper: styles.linePaper,
  baseline: styles.lineBaseline,
};

function Chart({ data, unit, on }: { data: TwoLedgers; unit: Unit; on: Record<LineKey, boolean> }) {
  const [ref, width] = useElementWidth(310);
  const first = data.series[0];
  const last = data.series.at(-1);
  if (!first || !last) return null;
  const value = (p: TwoLedgers['series'][number], key: LineKey) =>
    unit === 'ret'
      ? key === 'live'
        ? p.liveRet
        : key === 'paper'
          ? p.paperRet
          : p.baselineRet
      : p[key];
  const keys: LineKey[] = ['baseline', 'paper', 'live'];
  const all = data.series.flatMap((p) => keys.map((k) => value(p, k)));
  const axis = unit === 'ret' ? retAxis(all) : niceYAxis(all);
  const series = keys
    .filter((k) => on[k])
    .map((k) => ({
      key: k,
      points: data.series.map((p) => ({ date: p.date, value: value(p, k) })),
    }));
  const g = lineGeometry({
    width,
    layout: LAYOUT,
    start: first.date,
    end: last.date,
    domain: axis.domain,
    ticks: axis.ticks,
    series,
  });
  const dates = placeDateLabels(anchoredDateTicks(first.date, last.date), g.x, g.plotW);
  const end = (key: LineKey) => g.ends.find((e) => e.key === key);
  const label = t.twoLedgers.chart(
    signedPct(data.endRet.live),
    signedPct(data.endRet.paper),
    signedPct(data.endRet.baseline),
  );

  return (
    <div ref={ref} className={styles.chart}>
      <svg
        width={width}
        height={LAYOUT.plotHeight}
        className={styles.svg}
        role="img"
        aria-label={label}
      >
        {g.ticks.map((tick) => (
          <g key={tick.value}>
            <line
              className={styles.grid}
              x1={0}
              x2={g.plotW}
              y1={tick.y}
              y2={tick.y}
              strokeWidth={1}
            />
            <text
              className={styles.tick}
              x={tick.labelX}
              y={tick.y}
              textAnchor="start"
              dominantBaseline="central"
              aria-hidden
            >
              {tickLabel(unit, tick.value)}
            </text>
          </g>
        ))}
        {g.paths.map((p) => (
          <path
            key={p.key}
            d={p.d}
            className={LINE_CLASS[p.key as LineKey]}
            strokeWidth={p.key === 'baseline' ? 1.5 : 2}
            strokeDasharray={p.key === 'baseline' ? '4 3' : p.key === 'paper' ? '5 4' : undefined}
            fill="none"
          />
        ))}
        {(['paper', 'live'] as const).map((key) => {
          const e = end(key);
          return e ? (
            <g key={key}>
              <circle className={styles.halo} cx={e.cx} cy={e.cy} r={6} />
              <circle
                className={key === 'live' ? styles.dotLive : styles.dotPaper}
                cx={e.cx}
                cy={e.cy}
                r={4}
              />
            </g>
          ) : null;
        })}
      </svg>
      <div className={clsx('t-caption', styles.dates)} style={{ width }} aria-hidden>
        {dates.map((d) => (
          <span
            key={d.date}
            className={clsx(styles.dateText, styles[`anchor-${d.anchor}`])}
            style={{ left: d.x }}
          >
            {formatMonthDay(d.date)}
          </span>
        ))}
      </div>
    </div>
  );
}

function Swatch({ line }: { line: LineKey }) {
  return (
    <svg className={styles.swatch} viewBox="0 0 16 8" aria-hidden>
      <line
        x1="0"
        y1="4"
        x2="16"
        y2="4"
        className={LINE_CLASS[line]}
        strokeWidth="2"
        strokeLinecap="round"
        strokeDasharray={line === 'live' ? undefined : '4 3'}
      />
    </svg>
  );
}

export function TwoLedgersCard({ data }: { data: TwoLedgers }) {
  const [unit, setUnit] = useState<Unit>('ret');
  const [on, setOn] = useState<Record<LineKey, boolean>>({
    live: true,
    paper: true,
    baseline: true,
  });
  const [table, setTable] = useState(false);
  const tableId = useId();
  const titleId = useId();
  const b = data.breakdown;
  const parts = [
    { key: 'fills', label: t.twoLedgers.fills, value: b.fills, tone: 'cat-3' as const },
    { key: 'fees', label: t.twoLedgers.fees, value: b.fees, tone: 'cat-4' as const },
    { key: 'other', label: t.twoLedgers.other, value: b.other, tone: 'cat-5' as const },
  ];
  const legend: { key: LineKey; text: string }[] = [
    { key: 'live', text: t.twoLedgers.live(signedPct(data.endRet.live)) },
    { key: 'paper', text: t.twoLedgers.paper(signedPct(data.endRet.paper)) },
    { key: 'baseline', text: t.twoLedgers.baseline(signedPct(data.endRet.baseline)) },
  ];
  const cell = (v: number) => (unit === 'ret' ? formatPercentSigned(v, 2) : formatKrw(v));

  return (
    <section className={clsx(styles.card, styles.subtle)} aria-labelledby={titleId}>
      <div className={styles.cardHead}>
        <h2 id={titleId} className="t-heading-1">
          {t.twoLedgers.title}
        </h2>
        <span className={clsx('t-caption', styles.muted)}>
          {t.twoLedgers.since(formatMonthDay(data.since))}
        </span>
      </div>

      <div className={styles.legendChips}>
        {legend.map((item) => (
          <button
            key={item.key}
            type="button"
            aria-pressed={on[item.key]}
            className={styles.ledgerChip}
            onClick={() => {
              setOn((o) => ({ ...o, [item.key]: !o[item.key] }));
            }}
          >
            <Swatch line={item.key} />
            <span className="t-caption">{item.text}</span>
          </button>
        ))}
      </div>

      <div className={styles.unitRow}>
        <div role="group" aria-label={t.twoLedgers.unit} className={styles.unitChips}>
          <PeriodChip
            selected={unit === 'amount'}
            onClick={() => {
              setUnit('amount');
            }}
          >
            {t.twoLedgers.amount}
          </PeriodChip>
          <PeriodChip
            selected={unit === 'ret'}
            onClick={() => {
              setUnit('ret');
            }}
          >
            {t.twoLedgers.ret}
          </PeriodChip>
        </div>
        {table ? (
          <CollapseButton
            controls={tableId}
            onClick={() => {
              setTable(false);
            }}
          />
        ) : (
          <ExpandButton
            controls={tableId}
            onClick={() => {
              setTable(true);
            }}
          >
            {copy.chart.tableView}
          </ExpandButton>
        )}
      </div>

      <Chart data={data} unit={unit} on={on} />

      {table ? (
        <ChartTable
          id={tableId}
          caption={t.twoLedgers.title}
          columns={[
            copy.chart.dateColumn,
            t.twoLedgers.columns.live,
            t.twoLedgers.columns.paper,
            t.twoLedgers.columns.baseline,
          ]}
          rows={data.series.map((p) => [
            formatMonthDay(p.date),
            cell(unit === 'ret' ? p.liveRet : p.live),
            cell(unit === 'ret' ? p.paperRet : p.paper),
            cell(unit === 'ret' ? p.baselineRet : p.baseline),
          ])}
        />
      ) : null}

      <p className={clsx('t-label', styles.muted)}>
        {t.twoLedgers.breakdown(formatMonthDay(data.since), formatDateTime(b.valuedAt))}
      </p>
      <CompositionBar
        label={parts.map((p) => `${p.label} ${formatPp(p.value, 2)}`).join(' · ')}
        segments={parts.map((p) => ({ key: p.key, value: Math.abs(p.value), tone: p.tone }))}
      />
      <dl className={styles.breakdown}>
        {parts.map((p) => (
          <div key={p.key} className={styles.breakdownRow}>
            <dt className={styles.breakdownLabel}>
              <span className={clsx(styles.legendDot, styles[`fill-${p.tone}`])} aria-hidden />
              <span className="t-caption">{p.label}</span>
            </dt>
            <dd className={clsx('t-figure', styles[`pnl-${pnlDirection(p.value, 2)}`])}>
              {formatPp(p.value, 2)}
            </dd>
          </div>
        ))}
        <div className={styles.breakdownRow}>
          <dt className={clsx('t-label', styles.muted)}>{t.twoLedgers.total}</dt>
          <dd className={clsx('t-figure', styles[`pnl-${pnlDirection(b.total, 2)}`])}>
            {formatPp(b.total, 2)}
          </dd>
        </div>
      </dl>

      <div className={styles.links}>
        <LinkButton to="/history?ledger=live">{t.twoLedgers.liveHistory}</LinkButton>
        <LinkButton to="/history?ledger=paper">{t.twoLedgers.paperHistory}</LinkButton>
      </div>
    </section>
  );
}
