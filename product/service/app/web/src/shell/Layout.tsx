// Page frames of the MVP screens.
// 390: one column with a 20px gutter (16 on 설정). 1440 (from 900px):
// - narrow: the 390 column, at most 560 wide, centred (rule for screens without a 1440 frame)
// - login: 400 wide, centred (로그인 1440 frames)
// - wide: the 1200 column (기록 · 전략 목록 · 전략 편집)
// - split: 776 main + 400 side (자산 · 계획 · 전략 상세 · 연결 · 백테스트)
import clsx from 'clsx';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { ChevronLeft } from 'lucide-react';
import styles from './Layout.module.css';

export type PageWidth = 'narrow' | 'login' | 'wide' | 'split' | 'backtest';

export function Page({
  width,
  gutter = 'section',
  children,
  className,
}: {
  width: PageWidth;
  gutter?: 'section' | 'block';
  children: ReactNode;
  className?: string | undefined;
}) {
  return (
    <div
      className={clsx(
        styles.page,
        styles[`w-${width}`],
        gutter === 'block' && styles.gutterBlock,
        className,
      )}
    >
      {children}
    </div>
  );
}

/** Two columns on 1440; on 390 the side follows the main (or comes first with `sideFirst`). */
export function Split({
  main,
  side,
  sideFirstOnNarrow,
}: {
  main: ReactNode;
  side: ReactNode;
  sideFirstOnNarrow?: boolean | undefined;
}) {
  return (
    <div className={clsx(styles.split, sideFirstOnNarrow && styles.sideFirst)}>
      <div className={styles.main}>{main}</div>
      <div className={styles.side}>{side}</div>
    </div>
  );
}

export function BackLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link to={to} className={clsx(styles.back, 't-caption')}>
      <ChevronLeft size={16} aria-hidden />
      {children}
    </Link>
  );
}

export function Stack({
  gap = 'block',
  children,
  className,
}: {
  gap?: 'tight' | 'inline' | 'row' | 'block' | 'section' | 'grid';
  children: ReactNode;
  className?: string | undefined;
}) {
  return <div className={clsx(styles.stack, styles[`gap-${gap}`], className)}>{children}</div>;
}
