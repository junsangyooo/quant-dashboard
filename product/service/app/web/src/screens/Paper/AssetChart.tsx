// 자산 추이 카드: 제목 + 1개월 · 3개월 · 전체 칩, 총자산 선 + 원금(점선), 끝점 값, 범례. 첫 확인 전에는 빈 그래프와 안내.
import { useState } from 'react';
import { LineChart } from '../../charts/LineChart';
import { LINE_HOME_1440, LINE_HOME_390 } from '../../charts/geometry/lineChart';
import { edgeAxis } from '../../charts/geometry/mvpAxis';
import { addDays } from '../../charts/geometry/scale';
import { Card } from '../../components/Card';
import { PeriodChip } from '../../components/Chips';
import { copy } from '../../copy';
import { homeCopy as t } from '../../copy/paper';
import { useMediaQuery } from '../../lib/useMedia';
import { axisTick } from '../../lib/money';
import styles from './Paper.module.css';

type Range = 'm1' | 'm3' | 'all';
const DAYS: Record<Exclude<Range, 'all'>, number> = { m1: 30, m3: 91 };

/** '1,041만'. */
export function manLabel(v: number): string {
  return `${Math.round(v / 1e4).toLocaleString('en-US')}${copy.units.man}`;
}

export function AssetChart({
  curve,
  cash0,
  title,
  periods = true,
  emptyText,
}: {
  curve: readonly [string, number][];
  cash0: number;
  title: string;
  periods?: boolean;
  /** 첫 확인 전: 선 대신 이 글. */
  emptyText?: string | undefined;
}) {
  const [range, setRange] = useState<Range>('m1');
  const wide = useMediaQuery('(min-width: 900px)');
  const last = curve.at(-1)?.[0] ?? '';
  const from =
    !periods || range === 'all' || !last ? (curve[0]?.[0] ?? '') : addDays(last, -DAYS[range]);
  const shown = curve.filter(([d]) => d >= from);
  const points = shown.length > 0 ? shown : curve.slice(-1);
  const start = points[0]?.[0] ?? last;
  const values = [...points.map(([, v]) => v), cash0];
  const spread = Math.max(...values) - Math.min(...values);
  const axis = edgeAxis(spread > 0 ? values : [cash0 * 0.99, cash0 * 1.05]);
  const end = points.at(-1)?.[1];
  const empty = emptyText !== undefined;
  const endDay = empty ? addDays(start, 30) : last;
  return (
    <Card>
      <div className={styles.cardHead}>
        <h2 className="t-heading-1">{title}</h2>
        {periods ? (
          <div className={styles.chips} role="group" aria-label={title}>
            {(['m1', 'm3', 'all'] as const).map((r) => (
              <PeriodChip
                key={r}
                selected={range === r}
                onClick={() => {
                  setRange(r);
                }}
              >
                {t.ranges[r]}
              </PeriodChip>
            ))}
          </div>
        ) : null}
      </div>
      <LineChart
        layout={wide ? LINE_HOME_1440 : LINE_HOME_390}
        start={start}
        end={endDay}
        dateTicks={empty ? [start] : undefined}
        axis={axis}
        mine={{
          key: 'mine',
          points: empty ? [] : points.map(([date, value]) => ({ date, value })),
        }}
        baseline={{
          key: 'principal',
          points: [
            { date: start, value: cash0 },
            { date: endDay, value: cash0 },
          ],
        }}
        label={t.chartLabel}
        formatTick={axisTick(axis.domain[1])}
        emptyText={emptyText}
        endLabel={!empty && end !== undefined && points.length > 1 ? manLabel(end) : undefined}
      />
      <div className={`t-caption ${styles.legend}`} aria-hidden>
        <span className={styles.legendItem}>
          <span className={styles.swatch} />
          {t.legendMine}
        </span>
        <span className={styles.legendItem}>
          <span className={styles.swatchDashed} />
          {t.legendPrincipal}
        </span>
      </div>
    </Card>
  );
}
