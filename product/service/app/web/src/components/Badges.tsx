// Figma: 배지/모드 (모드 = 모의투자). The MVP has no live mode, so the badge is always 모의투자.
import clsx from 'clsx';
import { copy } from '../copy';
import styles from './Badges.module.css';

export function ModeBadge({ className }: { className?: string | undefined }) {
  return (
    <span className={clsx(styles.mode, styles['mode-paper'], 't-label', className)}>
      {copy.mode.paper}
    </span>
  );
}
