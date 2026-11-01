// Figma: 칩/기간 (선택 = 예 | 아니오), 칩/정보.
import clsx from 'clsx';
import type { MouseEventHandler, ReactNode } from 'react';
import styles from './Chips.module.css';

interface Base {
  className?: string | undefined;
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
