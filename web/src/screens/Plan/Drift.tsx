// 벗어남 흐름 (390: one chart under the timeline; 1440: one per rule card) and the AI rule's
// '지수 대비' line (Figma 탐색 17:7108), plus their table alternatives.
import clsx from 'clsx';
import { DriftChart, type DriftSeries } from '../../charts/DriftChart';
import { ChartTable } from '../../charts/ChartTable';
import { EventBand } from '../../charts/EventBand';
import { signedTick } from '../../charts/Gauge';
import { DRIFT_1440, DRIFT_390, driftGeometry } from '../../charts/geometry/drift';
import {
  MARKER,
  monthStartTicks,
  placeDateLabels,
  type ChartEvent,
} from '../../charts/geometry/lineChart';
import { daysBetween } from '../../charts/geometry/scale';
import { useElementWidth } from '../../charts/useElementWidth';
import chartStyles from '../../charts/charts.module.css';
import { markerKind } from '../../api/adapters';
import type { PlanResponse, RuleRef } from '../../api/types';
import { copy } from '../../copy';
import { planCopy } from '../../copy/plan';
import { eventLabel } from '../../lib/labels';
import { formatMonthDay, formatPpMagnitude } from '../../lib/format';
import { ruleName } from './words';

type Drift = PlanResponse['drift'];
/** One point of a line chart (drift lines, 지수 대비); null breaks the line. */
type DriftPoint = Drift['lines'][number]['points'][number];

const dayHref = (date: string) => `/day/${date}`;

/** Lines in rule order: the first rule is dark purple, the others light purple. */
export function driftSeries(drift: Drift, rules: readonly RuleRef[], only?: string): DriftSeries[] {
  return drift.lines
    .filter((l) => only === undefined || l.ruleId === only)
    .map((l) => {
      const rule = rules.find((r) => r.id === l.ruleId);
      return { key: l.ruleId, tone: rule?.colorIndex === 0 ? 1 : 2, points: l.points };
    });
}

/** Markers of one rule (plus the ledger's own), or of every rule with duplicates merged. */
export function driftEvents(drift: Drift, only?: string): ChartEvent[] {
  const seen = new Set<string>();
  const out: ChartEvent[] = [];
  for (const e of drift.events) {
    // A ledger-wide event (시작 · 실전 켬·끔: ruleId null) belongs on every rule's chart.
    if (only !== undefined && e.ruleId !== null && e.ruleId !== only) continue;
    const kind = markerKind(e.kind);
    const key = `${e.date}-${e.kind}`;
    if (kind === null || seen.has(key)) continue;
    seen.add(key);
    out.push({ date: e.date, kind, label: eventLabel(e.date, kind) });
  }
  return out;
}

/** Last date drawn on any line (10/7), or the start. */
export function driftEnd(drift: Drift): string {
  const dates = drift.lines.flatMap((l) => l.points.map((p) => p.date)).sort();
  return dates.at(-1) ?? drift.since;
}

/** '벗어남 흐름 · 3개월' / '벗어남 흐름 · 9/1부터'. */
export function driftHeading(drift: Drift): string {
  return planCopy.drift.withPeriod(
    drift.periods === null
      ? planCopy.drift.since(formatMonthDay(drift.since))
      : planCopy.drift.periods[drift.period],
  );
}

/** The same values as a table, for assistive tech (the drawing has no visible table). */
function DriftTable({
  caption,
  columns,
  lines,
}: {
  caption: string;
  columns: readonly string[];
  lines: readonly (readonly DriftPoint[])[];
}) {
  const dates = [...new Set(lines.flatMap((l) => l.map((p) => p.date)))].sort();
  return (
    <div className="sr-only">
      <ChartTable
        caption={caption}
        columns={[copy.chart.dateColumn, ...columns]}
        rows={dates.map((d) => [
          formatMonthDay(d),
          ...lines.map((l) => {
            const v = l.find((p) => p.date === d)?.value;
            return v === undefined || v === null ? planCopy.row.dash : formatPpMagnitude(v);
          }),
        ])}
      />
    </div>
  );
}

export interface DriftPlotProps {
  drift: Drift;
  rules: readonly RuleRef[];
  /** One rule (1440 card) or all rules (390). */
  only?: string | undefined;
  size: '390' | '1440';
  onGroup?: ((events: ChartEvent[]) => void) | undefined;
}

export function DriftPlot({ drift, rules, only, size, onGroup }: DriftPlotProps) {
  const series = driftSeries(drift, rules, only);
  const names = series.map((s) => {
    const rule = rules.find((r) => r.id === s.key);
    return rule ? ruleName(rule) : s.key;
  });
  const heading = driftHeading(drift);
  return (
    <>
      <DriftChart
        layout={size === '390' ? DRIFT_390 : DRIFT_1440}
        bandHeight={size === '390' ? 26 : 28}
        start={drift.since}
        end={driftEnd(drift)}
        series={series}
        events={driftEvents(drift, only)}
        hrefFor={dayHref}
        onGroup={onGroup}
        groupBelow={MARKER}
        label={`${heading} · ${names.join(' · ')}`}
      />
      <DriftTable caption={heading} columns={names} lines={series.map((s) => s.points)} />
    </>
  );
}

/** '지수 대비' axis step: 지수 · +5 · +10 (Figma 17:7108). */
const VS_STEP = 5;

/**
 * '지수 대비 · 7/1부터 (%p)' (AI rule): the drift frame of 1440 (130 tall, 0 at y 101.67) with
 * the axis 지수 · +5 · +10, a start flag on the pick date and no band.
 */
export function VsIndexChart({
  since,
  points,
  label,
}: {
  since: string;
  points: readonly DriftPoint[];
  label: string;
}) {
  const [ref, width] = useElementWidth(384);
  const layout = DRIFT_1440;
  const end = points.at(-1)?.date ?? since;
  const g = driftGeometry({
    width,
    layout,
    start: since,
    end,
    series: [{ key: 'vs', points }],
    threshold: VS_STEP,
  });
  const d = g.paths[0]?.d ?? '';
  const last = g.ends[0];
  // The start, the month starts and the last day, as Figma 17:7108 labels it (7/1 · 8/1 · 9/1 ·
  // 10/7). Real picks start mid-month (10/6): the start keeps its label, and a month start within
  // 10 days of either end gives way.
  const middle = monthStartTicks(since, end).filter(
    (d) => daysBetween(since, d) > 10 && daysBetween(d, end) > 10,
  );
  const ticks = since === end ? [end] : [since, ...middle, end];
  const dates = placeDateLabels(ticks, g.x, g.plotW);
  const events: ChartEvent[] = [{ date: since, kind: 'start', label: eventLabel(since, 'start') }];
  return (
    <div ref={ref} className={chartStyles.stack}>
      <svg
        className={chartStyles.svg}
        width={width}
        height={layout.height}
        role="img"
        aria-label={label}
      >
        <line
          className={chartStyles.grid}
          x1={0}
          x2={g.plotW}
          y1={g.zeroY}
          y2={g.zeroY}
          strokeWidth={1}
          strokeLinecap="round"
        />
        {g.ticks.map((t) => (
          <text
            key={t.value}
            className={clsx(chartStyles.tick, chartStyles.caption)}
            x={t.labelX}
            y={t.y}
            textAnchor={t.anchor}
            dominantBaseline="central"
            aria-hidden
          >
            {t.value === 0 ? planCopy.drift.index : signedTick(t.value)}
          </text>
        ))}
        <path className={chartStyles.strategy2} d={d} strokeWidth={2} />
        {last ? (
          <>
            <circle className={chartStyles.halo} cx={last.cx} cy={last.cy} r={5} strokeWidth={2} />
            <circle className={chartStyles.dotStrategy2} cx={last.cx} cy={last.cy} r={4} />
          </>
        ) : null}
      </svg>
      <EventBand
        width={width}
        plotW={g.plotW}
        x={g.x}
        events={events}
        hrefFor={dayHref}
        groupBelow={MARKER}
      />
      <div className={clsx(chartStyles.dates, 't-caption')} style={{ width }} aria-hidden>
        {dates.map((dl) => (
          <span
            key={dl.date}
            className={clsx(chartStyles.dateText, chartStyles[`anchor-${dl.anchor}`])}
            style={{ left: dl.x }}
          >
            {formatMonthDay(dl.date)}
          </span>
        ))}
      </div>
      <DriftTable caption={label} columns={[planCopy.drift.index]} lines={[points]} />
    </div>
  );
}
