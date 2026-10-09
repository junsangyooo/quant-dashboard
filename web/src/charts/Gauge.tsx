// Semicircle gauge: needle = the most deviated holding (%p), band = ±threshold.
import clsx from 'clsx';
import { MINUS } from '../lib/format';
import { GAUGE, gaugeGeometry } from './geometry/gauge';
import styles from './charts.module.css';

/** '−2' · '0' · '+2' (U+2212 minus). */
export function signedTick(v: number): string {
  if (v > 0) return `+${String(v)}`;
  if (v < 0) return `${MINUS}${String(Math.abs(v))}`;
  return '0';
}

export interface GaugeProps {
  /** Deviation in %p; null hides the needle and leaves a hollow hub (시세 대기, 첫 확인 전). */
  value: number | null;
  /** Accessible summary, e.g. 'KOSPI200 ETF +0.2%p · 리밸런싱까지 1.8%p'. */
  label: string;
  className?: string | undefined;
}

export function Gauge({ value, label, className }: GaugeProps) {
  const g = gaugeGeometry(value);
  return (
    <svg
      className={clsx(styles.svg, className)}
      width={GAUGE.width}
      height={GAUGE.height}
      viewBox={`0 0 ${String(GAUGE.width)} ${String(GAUGE.height)}`}
      role="img"
      aria-label={label}
    >
      <path className={styles.track} d={g.track} />
      <path className={styles.band} d={g.band} />
      <path className={styles.bandEdge} d={g.bandEdge} strokeWidth={1} />
      {g.labels.map((l) => (
        <text
          key={l.value}
          className={clsx(styles.tick, styles.caption)}
          x={l.x}
          y={l.y}
          textAnchor="middle"
          dominantBaseline="central"
          aria-hidden
        >
          {signedTick(l.value)}
        </text>
      ))}
      {g.needle ? (
        <>
          <line
            className={styles.needle}
            x1={g.needle.x1}
            y1={g.needle.y1}
            x2={g.needle.x2}
            y2={g.needle.y2}
            strokeWidth={GAUGE.needleWidth}
            strokeLinecap="round"
          />
          <circle className={styles.hub} cx={g.hub.cx} cy={g.hub.cy} r={g.hub.r} />
        </>
      ) : (
        <circle
          className={styles.hubEmpty}
          cx={g.hub.cx}
          cy={g.hub.cy}
          r={g.hub.r - 1}
          strokeWidth={2}
        />
      )}
    </svg>
  );
}
