// Figma: 표식/사건 (종류 = 리밸런싱 | 리밸런싱 중 | 일부 실패 | 입금 | 출금 | 배당 | 실전 켬 | 시작),
// 표식/실행 실패, 칸/실행 달력 (11 states).
import clsx from 'clsx';
import type { CSSProperties, MouseEventHandler, Ref } from 'react';
import { Link } from 'react-router';
import {
  ArrowDownToLine,
  ArrowLeftRight,
  ArrowUpFromLine,
  Coins,
  Flag as FlagIcon,
  Hourglass,
  Power,
  X,
  type LucideIcon,
} from 'lucide-react';
import styles from './Markers.module.css';

// ── 표식/사건 · 표식/실행 실패 (24×24, 1.5px edge, 14px icon) ────────────────
export type EventKind =
  | 'rebalance'
  | 'rebalanceInProgress'
  | 'partialFail'
  | 'deposit'
  | 'withdraw'
  | 'dividend'
  | 'liveOn'
  | 'start'
  | 'runFail';

const EVENT_ICON: Record<EventKind, LucideIcon> = {
  rebalance: ArrowLeftRight,
  rebalanceInProgress: ArrowLeftRight,
  partialFail: ArrowLeftRight,
  deposit: ArrowDownToLine,
  withdraw: ArrowUpFromLine,
  dividend: Coins,
  liveOn: Power,
  start: FlagIcon,
  runFail: X,
};

const EVENT_TONE: Record<EventKind, 'accent' | 'error' | 'primary'> = {
  rebalance: 'accent',
  rebalanceInProgress: 'accent',
  partialFail: 'error',
  deposit: 'primary',
  withdraw: 'primary',
  dividend: 'primary',
  liveOn: 'primary',
  start: 'primary',
  runFail: 'error',
};

// Bottom half of the 24×24 / r10 box, for 일부 실패 (chart/band "half done").
const HALF_PATH = 'M0 12H24V14A10 10 0 0 1 14 24H10A10 10 0 0 1 0 14Z';

function MarkerArt({ kind, count }: { kind: EventKind; count?: number | undefined }) {
  const Icon = EVENT_ICON[kind];
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden>
      <rect className={styles.surface} width="24" height="24" rx="10" />
      {kind === 'partialFail' ? <path className={styles.half} d={HALF_PATH} /> : null}
      <rect
        className={styles.edge}
        x="0.75"
        y="0.75"
        width="22.5"
        height="22.5"
        rx="9.25"
        strokeWidth="1.5"
        strokeDasharray={kind === 'rebalanceInProgress' ? '3 2' : undefined}
      />
      {count === undefined ? (
        <Icon x={5} y={5} size={14} />
      ) : (
        <text
          className={styles.groupCount}
          x="12"
          y="12"
          textAnchor="middle"
          dominantBaseline="central"
        >
          {count}
        </text>
      )}
    </svg>
  );
}

export interface EventMarkerProps {
  kind: EventKind;
  /** Accessible name, e.g. '8/21(금) 리밸런싱'. */
  label: string;
  /** Opens the day panel. */
  to?: string | undefined;
  onClick?: MouseEventHandler<HTMLButtonElement> | undefined;
  /** Static drawing (gallery, legend): not focusable. */
  inert?: boolean | undefined;
  /** Grouped marker: shows the count instead of the icon. */
  count?: number | undefined;
  style?: CSSProperties | undefined;
  className?: string | undefined;
  tabIndex?: number | undefined;
  ref?: Ref<HTMLElement> | undefined;
}

export function EventMarker({
  kind,
  label,
  to,
  onClick,
  inert,
  count,
  style,
  className,
  tabIndex,
  ref,
}: EventMarkerProps) {
  const cls = clsx(styles.marker, styles[`m-${EVENT_TONE[kind]}`], className);
  const art = <MarkerArt kind={kind} count={count} />;
  if (inert) {
    return (
      <span className={cls} style={style} role="img" aria-label={label}>
        {art}
      </span>
    );
  }
  if (to) {
    return (
      <Link
        to={to}
        className={cls}
        style={style}
        aria-label={label}
        tabIndex={tabIndex}
        ref={ref as Ref<HTMLAnchorElement> | undefined}
      >
        {art}
      </Link>
    );
  }
  return (
    <button
      type="button"
      className={cls}
      style={style}
      aria-label={label}
      onClick={onClick}
      tabIndex={tabIndex}
      ref={ref as Ref<HTMLButtonElement> | undefined}
    >
      {art}
    </button>
  );
}

// ── 칸/실행 달력 (16×16) ─────────────────────────────────────────────────────
export type CalendarState =
  | 'ok'
  | 'rebalance'
  | 'rebalanceInProgress'
  | 'partialFail'
  | 'fail'
  | 'noRun'
  | 'holiday'
  | 'future'
  | 'beforeRecord'
  | 'oneMarketHoliday'
  | 'awaitingQuote';

/** 1px inside stroke on the 16px / r2 cell. */
function Edge({ className }: { className: string | undefined }) {
  return (
    <rect className={className} x="0.5" y="0.5" width="15" height="15" rx="1.5" strokeWidth="1" />
  );
}

function Fill({ className }: { className: string | undefined }) {
  return <rect className={className} width="16" height="16" rx="2" />;
}

function CellIcon({ icon: Icon, className }: { icon: LucideIcon; className: string | undefined }) {
  return <Icon x={3} y={3} size={10} className={className} />;
}

function CalendarArt({ state }: { state: CalendarState }) {
  switch (state) {
    case 'ok':
      return (
        <>
          <Fill className={styles['c-fill-ok']} />
          <Edge className={styles['c-edge-ok']} />
        </>
      );
    case 'rebalance':
      return (
        <>
          <Fill className={styles['c-fill-rebalance']} />
          <CellIcon icon={ArrowLeftRight} className={styles['c-icon-inverse']} />
        </>
      );
    case 'rebalanceInProgress':
      return (
        <>
          <Fill className={styles['c-fill-default']} />
          <rect
            className={styles['c-edge-rebalance']}
            x="0.75"
            y="0.75"
            width="14.5"
            height="14.5"
            rx="1.25"
            strokeWidth="1.5"
            strokeDasharray="2 2"
          />
          <CellIcon icon={ArrowLeftRight} className={styles['c-icon-rebalance']} />
        </>
      );
    case 'partialFail':
      return (
        <>
          <Fill className={styles['c-fill-failTint']} />
          <Edge className={styles['c-edge-fail']} />
          <CellIcon icon={ArrowLeftRight} className={styles['c-icon-fail']} />
        </>
      );
    case 'fail':
      return (
        <>
          <Fill className={styles['c-fill-default']} />
          <rect
            className={styles['c-edge-fail']}
            x="0.75"
            y="0.75"
            width="14.5"
            height="14.5"
            rx="1.25"
            strokeWidth="1.5"
          />
          <CellIcon icon={X} className={styles['c-icon-fail']} />
        </>
      );
    case 'noRun':
      // Three 45° hatch lines starting at x = −8, 0, 8 on the bottom edge, clipped to the cell.
      return (
        <>
          <Fill className={styles['c-fill-default']} />
          <path
            className={styles['c-edge-mark']}
            d="M0 8L8 0M0 16L16 0M8 16L16 8"
            strokeWidth="1"
          />
          <Edge className={styles['c-edge-mark']} />
        </>
      );
    case 'holiday':
      return (
        <>
          <Fill className={styles['c-fill-default']} />
          <Edge className={styles['c-edge-empty']} />
          <circle className={styles['c-fill-mark']} cx="8" cy="8" r="2" />
        </>
      );
    case 'future':
      return <Edge className={styles['c-edge-empty']} />;
    case 'beforeRecord':
      return null;
    case 'oneMarketHoliday':
      // Left half filled + full ring: "one of two markets closed".
      return (
        <>
          <Fill className={styles['c-fill-ok']} />
          <Edge className={styles['c-edge-ok']} />
          <path className={styles['c-fill-mark']} d="M8 11A3 3 0 0 1 8 5Z" />
          <circle className={styles['c-edge-mark']} cx="8" cy="8" r="2.5" strokeWidth="1" />
        </>
      );
    case 'awaitingQuote':
      return (
        <>
          <Fill className={styles['c-fill-warnTint']} />
          <Edge className={styles['c-edge-warn']} />
          <CellIcon icon={Hourglass} className={styles['c-icon-warn']} />
        </>
      );
  }
}

export interface CalendarCellProps {
  state: CalendarState;
  /** Accessible name, e.g. '9/9(수) 실패'. Omit for decorative legend swatches. */
  label?: string | undefined;
  to?: string | undefined;
  className?: string | undefined;
  style?: CSSProperties | undefined;
}

export function CalendarCell({ state, label, to, className, style }: CalendarCellProps) {
  const art = (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden>
      <CalendarArt state={state} />
    </svg>
  );
  const cls = clsx(styles.cell, className);
  if (to && label) {
    return (
      <Link to={to} className={cls} style={style} aria-label={label}>
        {art}
      </Link>
    );
  }
  return label ? (
    <span className={cls} style={style} role="img" aria-label={label}>
      {art}
    </span>
  ) : (
    <span className={cls} style={style} aria-hidden>
      {art}
    </span>
  );
}
