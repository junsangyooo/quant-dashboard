// 변동 분해: horizontal waterfall from 기간 시작 to 지금. No Figma frame exists for this
// sheet; geometry follows the spec text (see geometry/waterfall.ts).
import clsx from 'clsx';
import { WATERFALL, waterfallGeometry, type WaterfallStep } from './geometry/waterfall';
import { useElementWidth } from './useElementWidth';
import styles from './charts.module.css';

export interface WaterfallProps {
  steps: readonly WaterfallStep[];
  /** Value text per row: anchors as totals, deltas signed. */
  formatValue: (step: WaterfallStep) => string;
  label: string;
  width?: number | undefined;
  className?: string | undefined;
}

export function Waterfall({ steps, formatValue, label, width: fixed, className }: WaterfallProps) {
  const [ref, width] = useElementWidth(350, fixed);
  const g = waterfallGeometry({ width, steps });
  const { rowHeight, barHeight, tickWidth, tickHeight } = WATERFALL;
  const mid = rowHeight / 2;

  return (
    <div ref={ref} className={clsx(styles.frame, className)}>
      <svg className={styles.svg} width={width} height={g.height} role="img" aria-label={label}>
        {g.rows.map((row, i) => {
          const next = g.rows[i + 1];
          return (
            <g key={row.key}>
              <text
                className={clsx(styles.wfLabel, styles.caption)}
                x={0}
                y={row.y + mid}
                dominantBaseline="central"
              >
                {row.label}
              </text>
              {row.bar ? (
                <rect
                  className={styles[`wf-${row.tone}`]}
                  x={row.bar.x}
                  y={row.y + mid - barHeight / 2}
                  width={row.bar.w}
                  height={barHeight}
                />
              ) : null}
              {row.tick ? (
                <rect
                  className={styles['wf-anchor']}
                  x={row.tick.x - tickWidth / 2}
                  y={row.y + mid - tickHeight / 2}
                  width={tickWidth}
                  height={tickHeight}
                />
              ) : null}
              {next ? (
                <line
                  className={styles.stem}
                  x1={row.edge}
                  x2={row.edge}
                  y1={row.y + mid + (row.tick ? tickHeight : barHeight) / 2}
                  y2={next.y + mid - (next.tick ? tickHeight : barHeight) / 2}
                  strokeWidth={1}
                  strokeDasharray="2 2"
                />
              ) : null}
              <text
                className={clsx(
                  row.kind === 'cashflow' ? styles.wfValueMuted : styles.wfValue,
                  styles.caption,
                )}
                x={width}
                y={row.y + mid}
                textAnchor="end"
                dominantBaseline="central"
              >
                {formatValue(row)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
