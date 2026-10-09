// 자산 변동(시작부터): head + 기준 chip → total → ▲ change · % + note → history chart with event
// stems (Figma 1:59344 '자산 변동', 1:58215) → '표로 보기'.
import clsx from 'clsx';
import { useId, useState } from 'react';
import { eventName, markerKind } from '../../api/adapters';
import type { HistoryResponse } from '../../api/types';
import { ChartTable } from '../../charts/ChartTable';
import { HistoryChart } from '../../charts/HistoryChart';
import {
  LINE_HISTORY_1440,
  LINE_HISTORY_390,
  niceYAxis,
  type ChartEvent,
} from '../../charts/geometry/lineChart';
import { CollapseButton, ExpandButton } from '../../components/Buttons';
import { InfoChip } from '../../components/Chips';
import { OfflineChip } from '../../components/State';
import { copy } from '../../copy';
import { historyCopy as hc } from '../../copy/history';
import {
  formatDateTime,
  formatKrw,
  formatKrwSigned,
  formatMonthDay,
  formatMonthDayWeekday,
  formatPercentSigned,
  pnlDirection,
} from '../../lib/format';
import { useMinWidth } from './useMinWidth';
import styles from './History.module.css';

/** Chart markers for the history events (AI events have no marker yet and are skipped). */
export function historyChartEvents(events: HistoryResponse['trend']['events']): ChartEvent[] {
  return events.flatMap((e) => {
    const kind = markerKind(e.kind);
    return kind
      ? [{ date: e.date, kind, label: `${formatMonthDayWeekday(e.date)} ${eventName(e.kind)}` }]
      : [];
  });
}

export function ChangeLine({
  amount,
  pct,
  digits = 2,
}: {
  amount: number;
  pct: number | null;
  digits?: number;
}) {
  const dir = pnlDirection(amount);
  const arrow = dir === 'gain' ? '▲ ' : dir === 'loss' ? '▼ ' : '';
  const text =
    pct === null
      ? `${arrow}${formatKrwSigned(amount)}`
      : `${arrow}${formatKrwSigned(amount)} · ${formatPercentSigned(pct, digits)}`;
  return <span className={clsx('t-label', styles[`pnl-${dir}`])}>{text}</span>;
}

export interface AssetCardProps {
  trend: HistoryResponse['trend'];
  hrefFor: (date: string) => string;
  /** Date of the open day panel (1440): vertical line on the chart. */
  selected?: string | undefined;
}

export function AssetCard({ trend, hrefFor, selected }: AssetCardProps) {
  const roomy = useMinWidth(600);
  const [table, setTable] = useState(false);
  const tableId = useId();
  const series = trend.series;
  const first = series[0];
  const last = series.at(-1);
  const events = historyChartEvents(trend.events);
  const axis = niceYAxis(series.map((p) => p.value));

  return (
    <section className={clsx(styles.assetCard, styles.asset)} aria-labelledby={`${tableId}-h`}>
      <div className={styles.assetHead}>
        <h2 id={`${tableId}-h`} className={clsx('t-caption', styles.muted)}>
          {hc.asset.since(formatMonthDay(trend.since))}
        </h2>
        <span className={styles.headChips}>
          <OfflineChip />
          <InfoChip>{hc.asset.basis(formatDateTime(trend.basis.valuedAt))}</InfoChip>
        </span>
      </div>
      <p className="t-title">{formatKrw(trend.total)}</p>
      <p className={styles.pnlRow}>
        {trend.pnl ? (
          <ChangeLine amount={trend.pnl.amount} pct={trend.pnl.pct} />
        ) : (
          <span className={clsx('t-label', styles.muted)}>{hc.asset.noPnl}</span>
        )}
        <span className={clsx('t-caption', styles.muted)}>{hc.asset.note}</span>
      </p>
      {series.length === 0 || !first || !last ? (
        <p className={clsx('t-caption', styles.muted, styles.chartEmpty)}>{hc.asset.empty}</p>
      ) : (
        <>
          <HistoryChart
            layout={roomy ? LINE_HISTORY_1440 : LINE_HISTORY_390}
            start={first.date}
            end={last.date}
            axis={axis}
            mine={{ key: 'mine', points: series }}
            events={events}
            hrefFor={hrefFor}
            selected={selected}
            label={hc.asset.chartLabel(
              formatMonthDay(first.date),
              formatKrw(first.value),
              formatMonthDay(last.date),
              formatKrw(last.value),
            )}
          />
          <div className={styles.tableToggle}>
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
          <div id={tableId} hidden={!table}>
            {table ? (
              <ChartTable
                caption={copy.chart.tableView}
                columns={[copy.chart.dateColumn, copy.chart.myAssets, hc.asset.eventColumn]}
                rows={series.map((p) => [
                  formatMonthDayWeekday(p.date),
                  formatKrw(p.value),
                  trend.events
                    .filter((e) => e.date === p.date)
                    .map((e) => eventName(e.kind))
                    .join(' · '),
                ])}
              />
            ) : null}
          </div>
        </>
      )}
    </section>
  );
}
