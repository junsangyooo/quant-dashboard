// Figma: 내비/항목 (1440 header tab) and MVP/하단 탭 (390: 자산 | 계획 | 기록 | 전략).
import clsx from 'clsx';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { FlaskConical, History, Target, Wallet, Workflow, type LucideIcon } from 'lucide-react';
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
  { key: 'strategies', to: '/strategies', icon: Workflow },
  { key: 'paper', to: '/paper', icon: FlaskConical },
];

export interface NavItemProps {
  to: string;
  current: boolean;
  children: ReactNode;
}

export function NavItem({ to, current, children }: NavItemProps) {
  return (
    <Link
      to={to}
      className={clsx(styles.navItem, current ? 't-body-strong' : 't-body')}
      aria-current={current ? 'page' : undefined}
    >
      <span>{children}</span>
      <span className={styles.underline} aria-hidden />
    </Link>
  );
}

export function BottomTabs({ current }: { current: TabKey | null }) {
  return (
    <nav className={styles.tabbar}>
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
