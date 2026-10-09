// 구성 막대 / 전후 비중: segments with 2px gaps, hatched pending segment, dashed target
// outlines (empty state), optional target marker and target band.
import clsx from 'clsx';
import {
  COMPOSITION,
  compositionGeometry,
  hatchLines,
  segmentLabelAnchor,
  targetGeometry,
} from './geometry/composition';
import { useElementWidth } from './useElementWidth';
import styles from './charts.module.css';

export type SegmentTone =
  'strategy-1' | 'strategy-2' | 'cash' | 'cat-1' | 'cat-2' | 'cat-3' | 'cat-4' | 'cat-5';

export interface CompositionSegment {
  key: string;
  value: number;
  tone: SegmentTone;
  /** 출금 대기: hatched, outlined. */
  pending?: boolean | undefined;
  /** 목표 비중 only (첫 확인 전): dashed outline in the tone color, no fill. */
  outline?: boolean | undefined;
  /** Text inside the segment (전후 비중 '52.3%'). */
  label?: string | undefined;
  /** inverse on dark fills, primary on light ones. */
  labelTone?: 'inverse' | 'primary' | undefined;
}

export interface CompositionBarProps {
  segments: readonly CompositionSegment[];
  label: string;
  /** Bar thickness: 12 (구성 막대) or 24 (전후 비중). */
  barHeight?: number | undefined;
  /** Target weight 0…1 and band, drawn over the full frame height (전후 비중). */
  target?: { at: number; band?: readonly [number, number] | undefined } | undefined;
  /** Frame height when a target overhangs the bar (전후 비중: 32). */
  height?: number | undefined;
  width?: number | undefined;
  className?: string | undefined;
}

export function CompositionBar({
  segments,
  label,
  barHeight = 12,
  target,
  height,
  width: fixed,
  className,
}: CompositionBarProps) {
  const [ref, width] = useElementWidth(310, fixed);
  const frameH = height ?? barHeight;
  const top = (frameH - barHeight) / 2;
  const boxes = compositionGeometry(width, segments, COMPOSITION.gap, COMPOSITION.minWidth);
  const byKey = new Map(segments.map((s) => [s.key, s]));
  const t = target ? targetGeometry(width, target.at, target.band) : null;

  return (
    <div ref={ref} className={clsx(styles.frame, className)}>
      <svg className={styles.svg} width={width} height={frameH} role="img" aria-label={label}>
        {t?.band ? (
          <>
            <rect
              className={styles.band}
              x={t.band.x}
              y={0}
              width={t.band.w}
              height={frameH}
              rx={2}
            />
            <rect
              className={styles.bandEdge}
              x={t.band.x + 0.5}
              y={0.5}
              width={t.band.w - 1}
              height={frameH - 1}
              rx={1.5}
              strokeWidth={1}
            />
          </>
        ) : null}
        {boxes.map((box) => {
          const seg = byKey.get(box.key);
          if (!seg) return null;
          if (seg.pending) {
            return (
              <g key={box.key}>
                <g transform={`translate(0 ${String(top)})`}>
                  <path
                    className={styles.pending}
                    d={hatchLines(box, barHeight)}
                    strokeWidth={1}
                    strokeLinecap="round"
                  />
                </g>
                <rect
                  className={styles.pending}
                  x={box.x + 0.5}
                  y={top + 0.5}
                  width={box.w - 1}
                  height={barHeight - 1}
                  strokeWidth={1}
                />
              </g>
            );
          }
          if (seg.outline) {
            return (
              <rect
                key={box.key}
                className={styles[`outline-${seg.tone}`]}
                x={box.x + 0.75}
                y={top + 0.75}
                width={box.w - 1.5}
                height={barHeight - 1.5}
                strokeWidth={1.5}
                strokeDasharray="4 3"
              />
            );
          }
          return (
            <rect
              key={box.key}
              className={styles[`seg-${seg.tone}`]}
              x={box.x}
              y={top}
              width={box.w}
              height={barHeight}
            />
          );
        })}
        {t ? (
          <rect className={styles.target} x={t.marker.x} y={0} width={t.marker.w} height={frameH} />
        ) : null}
        {boxes.map((box, i) => {
          const seg = byKey.get(box.key);
          const at = segmentLabelAnchor(boxes, i);
          if (!seg?.label || !at) return null;
          return (
            <text
              key={`${box.key}-label`}
              className={clsx(
                styles.segLabel,
                seg.labelTone === 'inverse' ? styles.segLabelInverse : styles.segLabelPrimary,
              )}
              x={at.x}
              y={frameH / 2}
              textAnchor={at.anchor}
              dominantBaseline="central"
              aria-hidden
            >
              {seg.label}
            </text>
          );
        })}
      </svg>
    </div>
  );
}
