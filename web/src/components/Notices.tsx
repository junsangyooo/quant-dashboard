// Figma: 배너/이상, 띠/모드 (모드 = 모의 | Live), 표시/낡음.
import clsx from 'clsx';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { ChevronRight, Clock, TriangleAlert } from 'lucide-react';
import { copy } from '../copy';
import type { Mode } from './Badges';
import styles from './Notices.module.css';

export interface AlertBannerProps {
  /** The fact, e.g. '미국 시세 10/02 기준 · 2거래일째 갱신 없음'. */
  children: ReactNode;
  /** Optional move link (버튼/링크), e.g. '작동 보기 ›'. */
  action?: ReactNode;
  className?: string | undefined;
}

/** 배너/이상: warning band under the header, one line + one link. */
export function AlertBanner({ children, action, className }: AlertBannerProps) {
  return (
    <div className={clsx(styles.banner, className)} role="status">
      <TriangleAlert size={20} className={styles.bannerIcon} aria-hidden />
      <div className={styles.bannerBody}>
        <p className="t-label">{children}</p>
        {action}
      </div>
    </div>
  );
}

export interface ModeStripProps {
  mode: Mode;
  children: ReactNode;
  to?: string | undefined;
  className?: string | undefined;
}

/** 띠/모드: full-width mode band with a chevron. */
export function ModeStrip({ mode, children, to, className }: ModeStripProps) {
  const cls = clsx(styles.strip, styles[`strip-${mode}`], className);
  const body = (
    <>
      <span className="t-label">{children}</span>
      <ChevronRight size={16} aria-hidden />
    </>
  );
  return to ? (
    <Link to={to} className={cls}>
      {body}
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}

/** 표시/낡음: one per section whose data is older than expected. */
export function StaleTag({ className }: { className?: string | undefined }) {
  return (
    <span className={clsx(styles.stale, className)}>
      <Clock size={14} aria-hidden />
      <span className="t-label">{copy.stale}</span>
    </span>
  );
}
