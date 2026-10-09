// Figma: 칩/헤더 상태, 칩/리밸런싱 상태, 칩/기간, 칩/범례, 칩/신호, 칩/예외, 칩/정보,
// 칩/AI 개입, 칩/규칙 선택.
import clsx from 'clsx';
import type { MouseEventHandler, ReactNode } from 'react';
import { Link } from 'react-router';
import {
  BanknoteArrowDown,
  CalendarX,
  ClockAlert,
  Coins,
  ListChecks,
  Sparkles,
  type LucideIcon,
} from 'lucide-react';
import { copy } from '../copy';
import styles from './Chips.module.css';

interface Base {
  className?: string | undefined;
}

// ── 칩/헤더 상태 (상태 = 정상 | 점검 | 오류 | 확인 불가) ─────────────────────
export type HeaderStatus = 'ok' | 'check' | 'error' | 'unknown';

export interface HeaderStatusChipProps extends Base {
  status: HeaderStatus;
  children: ReactNode;
  /** Navigates to 작동 when given. */
  to?: string | undefined;
}

export function HeaderStatusChip({ status, children, to, className }: HeaderStatusChipProps) {
  const cls = clsx(styles.chip, styles.header, styles[`header-${status}`], className);
  const body = (
    <>
      <span className={clsx(styles.dot, status === 'unknown' && styles.ring)} aria-hidden />
      <span className="t-caption">{children}</span>
    </>
  );
  return to ? (
    <Link to={to} className={cls}>
      {body}
    </Link>
  ) : (
    <span className={cls}>{body}</span>
  );
}

// ── 칩/리밸런싱 상태 (7 states) ──────────────────────────────────────────────
export type RebalanceState = keyof typeof copy.rebalance;

const RING_STATES: ReadonlySet<RebalanceState> = new Set(['scheduled', 'holiday']);

export interface RebalanceChipProps extends Base {
  state: RebalanceState;
  /** Overrides the default label (copy.rebalance[state]). */
  children?: ReactNode;
}

export function RebalanceChip({ state, children, className }: RebalanceChipProps) {
  return (
    <span
      className={clsx(
        styles.chip,
        styles.outlined,
        styles.rebalance,
        styles[`rb-${state}`],
        className,
      )}
    >
      <span className={clsx(styles.dot, RING_STATES.has(state) && styles.ring)} aria-hidden />
      <span className="t-label">{children ?? copy.rebalance[state]}</span>
    </span>
  );
}

// ── 칩/기간 (선택 = 예 | 아니오) ───────────────────────────────────────────────
export interface PeriodChipProps extends Base {
  selected: boolean;
  children: ReactNode;
  onClick?: MouseEventHandler<HTMLButtonElement> | undefined;
}

export function PeriodChip({ selected, children, onClick, className }: PeriodChipProps) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onClick}
      className={clsx(styles.chip, styles.period, 't-label', className)}
    >
      {children}
    </button>
  );
}

// ── 칩/범례 (켜짐 = 예 | 아니오) ───────────────────────────────────────────────
export interface LegendChipProps extends Base {
  on: boolean;
  children: ReactNode;
  onClick?: MouseEventHandler<HTMLButtonElement> | undefined;
}

export function LegendChip({ on, children, onClick, className }: LegendChipProps) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={clsx(styles.chip, styles.legend, className)}
    >
      <svg className={styles.legendSwatch} viewBox="0 0 16 8" aria-hidden>
        <line
          x1="0"
          y1="4"
          x2="16"
          y2="4"
          strokeWidth="2"
          strokeDasharray="2 3"
          strokeLinecap="round"
        />
      </svg>
      <span className="t-caption">{children}</span>
    </button>
  );
}

// ── 칩/신호 (종류 = 정상 | 주의 | 오류 | 확인 불가) ──────────────────────────
export type SignalKind = 'ok' | 'warn' | 'error' | 'unknown';

export interface SignalChipProps extends Base {
  kind: SignalKind;
  children: ReactNode;
}

export function SignalChip({ kind, children, className }: SignalChipProps) {
  return (
    <span
      className={clsx(styles.chip, styles.pill, styles.signal, styles[`sig-${kind}`], className)}
    >
      <span className={styles.dot} aria-hidden />
      <span className="t-label">{children}</span>
    </span>
  );
}

// ── 칩/예외 (종류 = 휴장 | 시세 대기 | 출금 대기 | 새 현금) ─────────────────
export type ExceptionKind = keyof typeof copy.exception;

const EXCEPTION_ICON: Record<ExceptionKind, LucideIcon> = {
  holiday: CalendarX,
  awaitingQuote: ClockAlert,
  withdrawPending: BanknoteArrowDown,
  newCash: Coins,
};

export interface ExceptionChipProps extends Base {
  kind: ExceptionKind;
  children?: ReactNode;
}

export function ExceptionChip({ kind, children, className }: ExceptionChipProps) {
  const Icon = EXCEPTION_ICON[kind];
  return (
    <span className={clsx(styles.chip, styles.pill, styles.outlined, styles.exception, className)}>
      <Icon size={14} aria-hidden />
      <span className="t-caption">{children ?? copy.exception[kind]}</span>
    </span>
  );
}

// ── 칩/정보 ───────────────────────────────────────────────────────────────────
export interface InfoChipProps extends Base {
  children: ReactNode;
  onClick?: MouseEventHandler<HTMLButtonElement> | undefined;
}

export function InfoChip({ children, onClick, className }: InfoChipProps) {
  const cls = clsx(styles.chip, styles.outlined, styles.info, 't-caption', className);
  return onClick ? (
    <button type="button" className={cls} onClick={onClick}>
      {children}
    </button>
  ) : (
    <span className={cls}>{children}</span>
  );
}

// ── 칩/AI 개입 (개입 = AI 없음 | AI 판단 포함) ───────────────────────────────
export interface AiChipProps extends Base {
  included: boolean;
}

export function AiChip({ included, className }: AiChipProps) {
  const Icon = included ? Sparkles : ListChecks;
  return (
    <span
      className={clsx(
        styles.chip,
        styles.pill,
        styles.ai,
        included ? styles['ai-included'] : styles['ai-none'],
        className,
      )}
    >
      <Icon size={14} className={styles.aiIcon} aria-hidden />
      <span className="t-caption">{included ? copy.ai.included : copy.ai.none}</span>
    </span>
  );
}

// ── 칩/규칙 선택 (선택 = 예 | 아니오, AI = boolean) ──────────────────────────
export interface RuleSelectChipProps extends Base {
  selected: boolean;
  name: ReactNode;
  /** Share or count after the name; omit it for name-only chips (규칙 '흐름' 칩). */
  weight?: ReactNode;
  ai?: boolean | undefined;
  onClick?: MouseEventHandler<HTMLButtonElement> | undefined;
}

export function RuleSelectChip({
  selected,
  name,
  weight,
  ai,
  onClick,
  className,
}: RuleSelectChipProps) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onClick}
      className={clsx(styles.chip, styles.pill, styles.ruleSelect, className)}
    >
      {ai ? (
        <>
          <Sparkles size={14} className={styles.ruleAi} aria-hidden />
          <span className="sr-only">{copy.ai.included}</span>{' '}
        </>
      ) : null}
      <span className="t-label">{name}</span>
      {/* The spaces keep the accessible name '지수 반반 81.1%' (flex drops them visually). */}
      {weight !== undefined && weight !== null ? (
        <>
          {' '}
          <span className={clsx('t-caption', styles.ruleWeight)}>{weight}</span>
        </>
      ) : null}
    </button>
  );
}
