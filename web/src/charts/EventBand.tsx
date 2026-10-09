// Event band under a time chart (사건 띠): a baseline, one marker per event (real links,
// Tab or ←/→ to move between them), grouped '[n]' when they collide, and an ⓘ legend button.
import clsx from 'clsx';
import { useRef, type KeyboardEvent } from 'react';
import { Info } from 'lucide-react';
import { copy } from '../copy';
import { EventMarker } from '../components/Markers';
import { bandMarkers, MARKER, type ChartEvent } from './geometry/lineChart';
import styles from './charts.module.css';

export interface EventBandProps {
  width: number;
  plotW: number;
  x: (date: string) => number;
  events: readonly ChartEvent[];
  /** Day panel link for an event date. */
  hrefFor?: ((date: string) => string) | undefined;
  /** ⓘ: opens the marker legend sheet. Hidden when absent. */
  onLegend?: (() => void) | undefined;
  /** A grouped '[n]' marker: opens the list of its events (기획 §5 사건 띠). */
  onGroup?: ((events: ChartEvent[]) => void) | undefined;
  /** Markers closer than this (px) merge into '[n]'. 24 = never overlap (WCAG 2.5.8). Default 20. */
  groupBelow?: number | undefined;
  /** Band height: 28 (자산 변동, 1440 흐름) or 26 (390 흐름). */
  height?: number | undefined;
}

export function EventBand({
  width,
  plotW,
  x,
  events,
  hrefFor,
  onLegend,
  onGroup,
  groupBelow,
  height = 28,
}: EventBandProps) {
  const markers = bandMarkers(events, x, groupBelow);
  const refs = useRef<(HTMLElement | null)[]>([]);
  const mid = height / 2;

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    const i = refs.current.findIndex((el) => el === document.activeElement);
    if (i === -1) return;
    e.preventDefault();
    const next = e.key === 'ArrowRight' ? Math.min(i + 1, markers.length - 1) : Math.max(i - 1, 0);
    refs.current[next]?.focus();
  };

  return (
    // Arrow keys only move focus between the band's own links; the links stay in Tab order.
    // eslint-disable-next-line jsx-a11y/no-static-element-interactions
    <div className={styles.eventBand} style={{ width, height }} onKeyDown={onKeyDown}>
      <svg className={styles.svg} width={width} height={height} aria-hidden>
        <line
          className={styles.grid}
          x1={0}
          x2={plotW}
          y1={mid}
          y2={mid}
          strokeWidth={1}
          strokeLinecap="round"
        />
      </svg>
      {markers.map((m, i) => {
        const first = m.events[0];
        if (!first) return null;
        const grouped = m.events.length > 1;
        return (
          <EventMarker
            key={first.date}
            ref={(el: HTMLElement | null) => {
              refs.current[i] = el;
            }}
            className={styles.marker}
            style={{ left: m.x - MARKER / 2, top: mid - MARKER / 2 }}
            kind={first.kind}
            count={grouped ? m.events.length : undefined}
            label={m.events.map((e) => e.label).join(' · ')}
            to={grouped ? undefined : hrefFor?.(first.date)}
            onClick={
              grouped && onGroup
                ? () => {
                    onGroup(m.events);
                  }
                : undefined
            }
          />
        );
      })}
      {onLegend ? (
        <button
          type="button"
          className={clsx(styles.info)}
          style={{ left: width - MARKER, top: mid - MARKER / 2 }}
          aria-label={copy.chart.markerLegend}
          onClick={onLegend}
        >
          <Info size={18} aria-hidden />
        </button>
      ) : null}
    </div>
  );
}
