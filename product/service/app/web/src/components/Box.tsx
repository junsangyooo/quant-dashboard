// MVP notice boxes (Figma MVP section): a tinted box with an icon, a strong first line and
// muted lines under it. Tones: 경고(노랑) · 오류(빨강) · 확인(초록) · 정보(회색).
import clsx from 'clsx';
import type { ReactNode } from 'react';
import {
  CircleCheck,
  CircleX,
  Clock,
  Flag,
  Hourglass,
  Info,
  Lock,
  RefreshCw,
  TriangleAlert,
  type LucideIcon,
} from 'lucide-react';
import styles from './Box.module.css';

export type BoxTone = 'warn' | 'error' | 'success' | 'info';
export type BoxIcon =
  'warn' | 'error' | 'success' | 'info' | 'lock' | 'wait' | 'clock' | 'refresh' | 'flag' | 'none';

const ICONS: Record<Exclude<BoxIcon, 'none'>, LucideIcon> = {
  warn: TriangleAlert,
  error: CircleX,
  success: CircleCheck,
  info: Info,
  lock: Lock,
  wait: Hourglass,
  clock: Clock,
  refresh: RefreshCw,
  flag: Flag,
};

export interface BoxProps {
  tone: BoxTone;
  icon?: BoxIcon | undefined;
  title?: ReactNode;
  children?: ReactNode;
  /** The title in the tone color (오류 · 잠금 boxes). */
  strongTitle?: boolean | undefined;
  role?: 'status' | 'alert' | undefined;
  className?: string | undefined;
}

export function Box({ tone, icon, title, children, strongTitle, role, className }: BoxProps) {
  const which = icon ?? tone;
  const Icon = which === 'none' ? null : ICONS[which];
  return (
    <div className={clsx(styles.box, styles[tone], className)} role={role}>
      {Icon ? <Icon size={18} className={styles.icon} aria-hidden /> : null}
      <div className={styles.text}>
        {title !== undefined ? (
          <p className={clsx('t-body-strong', strongTitle && styles.strong)}>{title}</p>
        ) : null}
        {children !== undefined ? (
          <div className={clsx('t-caption', styles.lines)}>{children}</div>
        ) : null}
      </div>
    </div>
  );
}
