// Figma: 노드/D 지금 값 카드 (종류 = 시작 | 종목 | 데이터 | AI 판단 | 비중 | 조건 | 행동 | 예외 | 결과).
// Variants A/B/C on the 탐색 page are explorations and are not implemented.
import clsx from 'clsx';
import type { ReactNode } from 'react';
import {
  ChartCandlestick,
  ChartLine,
  ChartPie,
  CirclePause,
  Clock,
  Flag as FlagIcon,
  Send,
  Sparkles,
  Split,
  type LucideIcon,
} from 'lucide-react';
import { copy } from '../copy';
import styles from './NodeCard.module.css';

export type NodeKind = keyof typeof copy.nodeKind;

const NODE_ICON: Record<NodeKind, LucideIcon> = {
  start: Clock,
  asset: ChartCandlestick,
  data: ChartLine,
  ai: Sparkles,
  weight: ChartPie,
  condition: Split,
  action: Send,
  exception: CirclePause,
  result: FlagIcon,
};

export interface NodeCardProps {
  kind: NodeKind;
  /** Main line (type/body-strong). */
  title: ReactNode;
  /** Rows under the title (subtitle, logos, chips…). */
  children?: ReactNode;
  /** Text after '지금', e.g. '· 마지막 판단 10/07 08:30'. */
  nowSuffix?: ReactNode;
  /** Value rows inside the '지금' box. */
  now: ReactNode;
  /** Heading level for the kind label inside a flow. */
  className?: string | undefined;
}

export function NodeCard({ kind, title, children, nowSuffix, now, className }: NodeCardProps) {
  const Icon = NODE_ICON[kind];
  return (
    <article
      className={clsx(
        styles.card,
        styles[`k-${kind}`],
        kind === 'ai' && styles['card-ai'],
        className,
      )}
    >
      {kind === 'ai' ? (
        <svg className={styles.aiEdge} aria-hidden>
          <rect width="100%" height="100%" rx="10" strokeWidth="3" strokeDasharray="4 3" />
        </svg>
      ) : null}
      <span className={styles.stripe} aria-hidden />
      <div className={styles.body}>
        <p className={styles.head}>
          <Icon size={16} aria-hidden />
          <span className="t-label">{copy.nodeKind[kind]}</span>
        </p>
        <div className={styles.content}>
          <p className="t-body-strong">{title}</p>
          {children}
        </div>
        <div className={styles.now}>
          <p className={styles.nowHead}>
            <span className="t-label">{copy.now}</span>
            {nowSuffix !== undefined ? <span className="t-caption">{nowSuffix}</span> : null}
          </p>
          {now}
        </div>
      </div>
    </article>
  );
}

/** A row inside a node card (8px gap). `tight` uses the 4px gap of logo/flag rows. */
export function NodeRow({ children, tight }: { children: ReactNode; tight?: boolean | undefined }) {
  return <div className={tight ? styles.rowTight : styles.row}>{children}</div>;
}

/** Fixed 40px label column of the AI 판단 rows (입력 · AI · 출력). */
export function NodeRowLabel({ children }: { children: ReactNode }) {
  return <span className={clsx('t-caption', styles.rowLabel)}>{children}</span>;
}

/** Icon tinted with the card's kind color (행동 rows). */
export function NodeIcon({ icon: Icon }: { icon: LucideIcon }) {
  return <Icon size={16} className={styles.icon} aria-hidden />;
}
