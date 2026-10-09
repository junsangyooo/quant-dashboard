// Figma: 내비/항목 (상태 = 현재 | 기본), 내비/하단 탭 (현재 = 자산 | 계획 | 기록 | 규칙).
import clsx from 'clsx';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { History, Target, Wallet, Workflow, type LucideIcon } from 'lucide-react';
import { copy } from '../copy';
import styles from './Nav.module.css';

export type TabKey = keyof typeof copy.nav;

export interface TabDef {
  key: TabKey;
  to: string;
  icon: LucideIcon;
}

export const TABS: readonly TabDef[] = [
  { key: 'home', to: '/', icon: Wallet },
  { key: 'plan', to: '/plan', icon: Target },
  { key: 'history', to: '/history', icon: History },
  { key: 'rules', to: '/rules', icon: Workflow },
];

/**
 * How the current tab is announced: `page` on the tab's own page, `true` on a sub-page
 * that sits under that tab (작동·모드·설정 keep 자산 underlined, as in Figma).
 */
export type CurrentKind = 'page' | 'true';

export interface NavItemProps {
  to: string;
  current: boolean;
  currentKind?: CurrentKind | undefined;
  children: ReactNode;
}

export function NavItem({ to, current, currentKind = 'page', children }: NavItemProps) {
  return (
    <Link
      to={to}
      className={clsx(styles.navItem, current ? 't-body-strong' : 't-body')}
      aria-current={current ? currentKind : undefined}
    >
      <span>{children}</span>
      <span className={styles.underline} aria-hidden />
    </Link>
  );
}

export interface BottomTabsProps {
  current: TabKey | null;
  /** `auto` hides the bar from 900px up; `390` always shows it (gallery). */
  layout?: 'auto' | '390' | undefined;
}

export function BottomTabs({ current, layout = 'auto' }: BottomTabsProps) {
  return (
    <nav className={clsx(styles.tabbar, layout === 'auto' && styles.auto)}>
      <ul className={styles.tabList}>
        {TABS.map(({ key, to, icon: Icon }) => {
          const isCurrent = key === current;
          return (
            <li key={key} className={styles.tabItem}>
              <Link to={to} className={styles.tab} aria-current={isCurrent ? 'page' : undefined}>
                <Icon size={22} aria-hidden />
                <span className={isCurrent ? 't-label' : 't-caption'}>{copy.nav[key]}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
