// Figma: 상태 줄 (정상 | 경고 | 오류 | 대기), 줄/점검 (통과 | 막힘 | 경고),
// 주문 행 (체결 | 대기 | 실패), 행/펼침 (접힘 | 펼침).
import clsx from 'clsx';
import { useId, type ReactNode } from 'react';
import { Link } from 'react-router';
import {
  ChevronDown,
  ChevronRight,
  ChevronUp,
  CircleCheck,
  CircleX,
  Clock,
  Hourglass,
  TriangleAlert,
  type LucideIcon,
} from 'lucide-react';
import styles from './Rows.module.css';

// ── 상태 줄 ──────────────────────────────────────────────────────────────────
export type StatusTone = 'ok' | 'warn' | 'error' | 'wait';

const STATUS_ICON: Record<StatusTone, LucideIcon> = {
  ok: CircleCheck,
  warn: TriangleAlert,
  error: CircleX,
  wait: Clock,
};

export interface StatusLineProps {
  tone: StatusTone;
  children: ReactNode;
  className?: string | undefined;
}

export function StatusLine({ tone, children, className }: StatusLineProps) {
  const Icon = STATUS_ICON[tone];
  return (
    <div className={clsx(styles.statusLine, className)}>
      <span className={clsx(styles.statusIcon, styles[`tone-${tone}`])}>
        <Icon size={18} aria-hidden />
      </span>
      <p className={clsx('t-body', styles.grow)}>{children}</p>
    </div>
  );
}

// ── 줄/점검 ──────────────────────────────────────────────────────────────────
export type CheckState = 'pass' | 'blocked' | 'warn';

const CHECK_ICON: Record<CheckState, { icon: LucideIcon; tone: StatusTone }> = {
  pass: { icon: CircleCheck, tone: 'ok' },
  blocked: { icon: CircleX, tone: 'error' },
  warn: { icon: TriangleAlert, tone: 'warn' },
};

export interface CheckRowProps {
  state: CheckState;
  name: ReactNode;
  description?: ReactNode;
  /** 막힘·경고 rows link to the cause (shows the chevron). */
  to?: string | undefined;
  className?: string | undefined;
}

export function CheckRow({ state, name, description, to, className }: CheckRowProps) {
  const { icon: Icon, tone } = CHECK_ICON[state];
  const body = (
    <>
      <Icon size={20} className={styles[`tone-${tone}`]} aria-hidden />
      <span className={styles.checkText}>
        <span className={clsx('t-body-strong', styles.checkName)}>{name}</span>
        {description !== undefined ? (
          <span className={clsx('t-caption', styles.muted)}>{description}</span>
        ) : null}
      </span>
      {state !== 'pass' ? <ChevronRight size={16} className={styles.muted} aria-hidden /> : null}
    </>
  );
  return to ? (
    <Link to={to} className={clsx(styles.checkRow, className)}>
      {body}
    </Link>
  ) : (
    <div className={clsx(styles.checkRow, className)}>{body}</div>
  );
}

// ── 주문 행 ──────────────────────────────────────────────────────────────────
export type OrderState = 'filled' | 'pending' | 'failed';

const ORDER_ICON: Record<OrderState, { icon: LucideIcon; tone: StatusTone }> = {
  filled: { icon: CircleCheck, tone: 'ok' },
  pending: { icon: Hourglass, tone: 'wait' },
  failed: { icon: CircleX, tone: 'error' },
};

export interface OrderRowProps {
  state: OrderState;
  /** Screen-reader word for the state icon (체결 · 대기 · 실패). */
  stateLabel: string;
  children: ReactNode;
  time: ReactNode;
  className?: string | undefined;
}

export function OrderRow({ state, stateLabel, children, time, className }: OrderRowProps) {
  const { icon: Icon, tone } = ORDER_ICON[state];
  return (
    <span className={clsx(styles.orderRow, className)}>
      <Icon size={14} className={styles[`tone-${tone}`]} aria-hidden />
      <span className="sr-only">{stateLabel}</span>
      <span className="t-caption">{children}</span>
      <span className={clsx('t-caption', styles.muted)}>{time}</span>
    </span>
  );
}

// ── 행/펼침 ──────────────────────────────────────────────────────────────────
export interface ExpandRowProps {
  title: ReactNode;
  subtitle?: ReactNode;
  expanded: boolean;
  onToggle?: (() => void) | undefined;
  /** Shown under the row while expanded. */
  children?: ReactNode;
  className?: string | undefined;
}

export function ExpandRow({
  title,
  subtitle,
  expanded,
  onToggle,
  children,
  className,
}: ExpandRowProps) {
  const panelId = useId();
  const Chevron = expanded ? ChevronUp : ChevronDown;
  return (
    <div className={className}>
      <button
        type="button"
        className={styles.expandRow}
        aria-expanded={expanded}
        aria-controls={children !== undefined ? panelId : undefined}
        onClick={onToggle}
      >
        <span className={styles.expandText}>
          <span className="t-body-strong">{title}</span>
          {subtitle !== undefined ? (
            <span className={clsx('t-caption', styles.muted)}>{subtitle}</span>
          ) : null}
        </span>
        <Chevron size={20} className={styles.muted} aria-hidden />
      </button>
      {children !== undefined ? (
        <div id={panelId} hidden={!expanded}>
          {children}
        </div>
      ) : null}
    </div>
  );
}
