// Figma: 배지/모드 (모드 = 모의투자 | 실전), 배지/종류, 국기 (나라 = KR | US | 코인),
// 로고/이니셜 (크기 = 32 | 20).
import clsx from 'clsx';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { Bitcoin } from 'lucide-react';
import { copy } from '../copy';
import styles from './Badges.module.css';

export type Mode = 'paper' | 'live';

export interface ModeBadgeProps {
  mode: Mode;
  /** Navigates to 모의투자·실전 when given. */
  to?: string | undefined;
  className?: string | undefined;
}

export function ModeBadge({ mode, to, className }: ModeBadgeProps) {
  const cls = clsx(styles.mode, styles[`mode-${mode}`], 't-label', className);
  const label = copy.mode[mode];
  return to ? (
    <Link to={to} className={cls}>
      {label}
    </Link>
  ) : (
    <span className={cls}>{label}</span>
  );
}

export interface KindBadgeProps {
  children: ReactNode;
  className?: string | undefined;
}

/** 배지/종류: ETF · 주식 · 코인. */
export function KindBadge({ children, className }: KindBadgeProps) {
  return <span className={clsx(styles.kind, 't-caption', className)}>{children}</span>;
}

export type Country = 'kr' | 'us' | 'coin';

export interface FlagProps {
  country: Country;
  /** Hide from assistive tech when the market is already written next to it. */
  decorative?: boolean | undefined;
  className?: string | undefined;
}

/** 국기: self-hosted flag-icons (4×3); 코인 is Lucide bitcoin. */
export function Flag({ country, decorative, className }: FlagProps) {
  const label = copy.country[country];
  if (country === 'coin') {
    return (
      <span
        className={clsx(styles.flag, className)}
        role={decorative ? undefined : 'img'}
        aria-label={decorative ? undefined : label}
        aria-hidden={decorative ? true : undefined}
      >
        <Bitcoin size={15} className={styles.coin} aria-hidden />
      </span>
    );
  }
  return (
    <span className={clsx(styles.flag, styles.flagFramed, className)}>
      <img
        className={styles.flagImage}
        src={`/flags/${country}.svg`}
        width={20}
        height={15}
        alt={decorative ? '' : label}
      />
    </span>
  );
}

export type LogoTone = 1 | 2 | 3 | 4 | 5;

export interface InitialLogoProps {
  initials: string;
  size?: 32 | 20 | undefined;
  /** chart/cat-n ring color. */
  tone?: LogoTone | undefined;
  className?: string | undefined;
}

/** 로고/이니셜: stock logos are initials in a ring (no third-party logos). */
export function InitialLogo({ initials, size = 32, tone = 1, className }: InitialLogoProps) {
  return (
    <span
      className={clsx(
        styles.logo,
        styles[`logo-${String(size)}`],
        styles[`tone-${String(tone)}`],
        size === 32 ? 't-label' : 't-micro',
        className,
      )}
      aria-hidden
    >
      {initials}
    </span>
  );
}
