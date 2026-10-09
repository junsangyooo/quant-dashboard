// Figma: 헤더/390 and 헤더/1440 (현재 = 자산 | 계획 | 기록 | 규칙).
// Badge → 모의투자·실전, status chip → 작동, gear → 설정 (기획 §5 SCR-HOME header row).
import clsx from 'clsx';
import { Settings } from 'lucide-react';
import { copy } from '../copy';
import { ModeBadge, type Mode } from './Badges';
import { IconButton } from './Buttons';
import { HeaderStatusChip, type HeaderStatus } from './Chips';
import { NavItem, TABS, type CurrentKind, type TabKey } from './Nav';
import styles from './Header.module.css';

export interface HeaderProps {
  mode: Mode;
  status: HeaderStatus;
  statusLabel: string;
  current: TabKey | null;
  currentKind?: CurrentKind | undefined;
  /** `auto` switches 390 → 1440 at 900px; the others force one (gallery). */
  layout?: 'auto' | '390' | '1440' | undefined;
}

export function Header({
  mode,
  status,
  statusLabel,
  current,
  currentKind,
  layout = 'auto',
}: HeaderProps) {
  return (
    <header
      className={clsx(
        styles.header,
        layout === 'auto' && styles.auto,
        layout === '1440' && styles.desktop,
      )}
    >
      <div className={styles.inner}>
        <div className={styles.left}>
          <span className="t-heading-1">{copy.wordmark}</span>
          <ModeBadge mode={mode} to="/mode" />
          <HeaderStatusChip status={status} to="/health">
            {statusLabel}
          </HeaderStatusChip>
        </div>
        <nav className={styles.tabs}>
          <ul className={styles.tabList}>
            {TABS.map(({ key, to }) => (
              <li key={key}>
                <NavItem to={to} current={key === current} currentKind={currentKind}>
                  {copy.nav[key]}
                </NavItem>
              </li>
            ))}
          </ul>
        </nav>
        <div className={styles.right}>
          <IconButton icon={Settings} label={copy.settings} to="/account" />
        </div>
      </div>
    </header>
  );
}
