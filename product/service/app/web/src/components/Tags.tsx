// MVP tags: 상태 칩(모의투자 중 · 백테스트 가능 · 문제 n개 · 버전 n · 매매 방식), 매수/매도 칩, 단계 번호.
import clsx from 'clsx';
import type { ReactNode } from 'react';
import {
  CircleCheck,
  CirclePlay,
  GitCommitHorizontal,
  Pencil,
  type LucideIcon,
} from 'lucide-react';
import { copy } from '../copy';
import styles from './Tags.module.css';

export type StatusKind = 'paper' | 'ready' | 'blanks' | 'version' | 'plain' | 'edit';

const ICON: Partial<Record<StatusKind, LucideIcon>> = {
  paper: CirclePlay,
  ready: CircleCheck,
  blanks: Pencil,
  version: GitCommitHorizontal,
  edit: Pencil,
};

export function StatusTag({
  kind,
  children,
  className,
}: {
  kind: StatusKind;
  children: ReactNode;
  className?: string | undefined;
}) {
  const Icon = ICON[kind];
  return (
    <span
      className={clsx(
        styles.tag,
        styles[kind],
        kind === 'plain' ? 't-caption' : 't-label',
        className,
      )}
    >
      {Icon ? <Icon size={14} className={styles.icon} aria-hidden /> : null}
      {children}
    </span>
  );
}

/** The tag a version shows: 모의투자 중 · 백테스트 가능 · 문제 n개. */
export function VersionTag({ paper, problems }: { paper: boolean; problems: number }) {
  if (paper) return <StatusTag kind="paper">{copy.common.paperRunning}</StatusTag>;
  if (problems === 0) return <StatusTag kind="ready">{copy.common.backtestReady}</StatusTag>;
  return <StatusTag kind="blanks">{copy.common.problems(problems)}</StatusTag>;
}

export function SideTag({ side }: { side: 'buy' | 'sell' }) {
  return (
    <span className={clsx(styles.side, styles[side], 't-label')}>
      {side === 'buy' ? copy.common.buy : copy.common.sell}
    </span>
  );
}

export function StepNo({ n }: { n: number }) {
  return (
    <span className={clsx(styles.stepNo, 't-label')} aria-hidden>
      {n}
    </span>
  );
}
