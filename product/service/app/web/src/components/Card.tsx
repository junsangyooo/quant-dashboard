// MVP cards: subtle (회색 바탕) or outline (흰 바탕 + 테두리, 'API 키 받는 법').
import clsx from 'clsx';
import type { ReactNode } from 'react';
import styles from './Card.module.css';

export function Card({
  children,
  tone = 'subtle',
  as: Tag = 'section',
  className,
  labelledBy,
}: {
  children: ReactNode;
  tone?: 'subtle' | 'outline' | 'white';
  as?: 'section' | 'div';
  className?: string | undefined;
  labelledBy?: string | undefined;
}) {
  return (
    <Tag className={clsx(styles.card, styles[tone], className)} aria-labelledby={labelledBy}>
      {children}
    </Tag>
  );
}

/** Label · value row (시작 · 시작 금액 · Client ID …). */
export function KeyValue({
  label,
  children,
  strong = true,
  className,
}: {
  label: ReactNode;
  children: ReactNode;
  strong?: boolean;
  className?: string | undefined;
}) {
  return (
    <div className={clsx(styles.kv, className)}>
      <span className={clsx('t-caption', styles.kvLabel)}>{label}</span>
      <span className={strong ? 't-body-strong' : 't-body'}>{children}</span>
    </div>
  );
}

export function Row({
  children,
  className,
  align = 'center',
}: {
  children: ReactNode;
  className?: string | undefined;
  align?: 'center' | 'start' | 'baseline';
}) {
  return <div className={clsx(styles.row, styles[`align-${align}`], className)}>{children}</div>;
}
