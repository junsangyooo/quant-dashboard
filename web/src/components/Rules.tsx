// Figma: 규칙/블록 (종류 = 시간 | AI | 조건 | 그대로 | 매도 | 환전 | 매수), 규칙/목표 칸,
// 규칙 카드/머리.
import clsx from 'clsx';
import type { ReactNode } from 'react';
import {
  ArrowLeftRight,
  CircleMinus,
  CirclePlus,
  Clock8,
  Sparkles,
  type LucideIcon,
} from 'lucide-react';
import { Flag, InitialLogo, type Country, type LogoTone } from './Badges';
import { AiChip, InfoChip, RebalanceChip, type RebalanceState } from './Chips';
import styles from './Rules.module.css';

// ── 규칙/블록 ────────────────────────────────────────────────────────────────
export type RuleBlockKind = 'time' | 'ai' | 'condition' | 'hold' | 'sell' | 'exchange' | 'buy';

const BLOCK_ICON: Partial<Record<RuleBlockKind, LucideIcon>> = {
  time: Clock8,
  ai: Sparkles,
  sell: CircleMinus,
  exchange: ArrowLeftRight,
  buy: CirclePlus,
};

export interface RuleBlockProps {
  kind: RuleBlockKind;
  children: ReactNode;
  className?: string | undefined;
}

export function RuleBlock({ kind, children, className }: RuleBlockProps) {
  const Icon = BLOCK_ICON[kind];
  return (
    <span className={clsx(styles.block, styles[`b-${kind}`], className)}>
      {Icon ? <Icon size={16} className={styles.blockIcon} aria-hidden /> : null}
      <span className="t-label">{children}</span>
    </span>
  );
}

// ── 규칙/목표 칸 ─────────────────────────────────────────────────────────────
export interface RuleTargetCellProps {
  initials: string;
  tone?: LogoTone | undefined;
  country: Country;
  /** Target weight, e.g. '50%'. */
  children: ReactNode;
  className?: string | undefined;
}

export function RuleTargetCell({
  initials,
  tone,
  country,
  children,
  className,
}: RuleTargetCellProps) {
  return (
    <span className={clsx(styles.target, className)}>
      <InitialLogo initials={initials} size={20} tone={tone} />
      <Flag country={country} />
      <span className="t-label">{children}</span>
    </span>
  );
}

// ── 규칙 카드/머리 ───────────────────────────────────────────────────────────
export interface RuleCardHeadProps {
  name: ReactNode;
  /** e.g. '80%' next to '자산의'. */
  share: ReactNode;
  shareLabel?: ReactNode;
  /** Fill of the weight bar, 0…1. */
  fraction: number;
  strategy?: 1 | 2 | undefined;
  status: RebalanceState;
  ai: boolean;
  /** '예시' chip (hidden in Figma by default). */
  example?: ReactNode;
  /** Heading level for the rule name. */
  as?: 'h2' | 'h3' | undefined;
  className?: string | undefined;
}

export function RuleCardHead({
  name,
  share,
  shareLabel,
  fraction,
  strategy = 1,
  status,
  ai,
  example,
  as: Heading = 'h3',
  className,
}: RuleCardHeadProps) {
  const pct = `${String(Math.max(0, Math.min(1, fraction)) * 100)}%`;
  return (
    <div className={clsx(styles.head, className)}>
      <div className={styles.nameRow}>
        <Heading className="t-heading-1">{name}</Heading>
        <span className={styles.share}>
          {shareLabel !== undefined ? (
            <span className={clsx('t-caption', styles.muted)}>{shareLabel}</span>
          ) : null}
          <span className="t-heading-1">{share}</span>
        </span>
      </div>
      <div className={styles.bar} aria-hidden>
        <span
          className={clsx(styles.barFill, styles[`strategy-${String(strategy)}`])}
          style={{ width: pct }}
        />
      </div>
      <div className={styles.chips}>
        <RebalanceChip state={status} />
        <AiChip included={ai} />
        {example !== undefined ? <InfoChip>{example}</InfoChip> : null}
      </div>
    </div>
  );
}
