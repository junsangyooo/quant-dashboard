// Figma: MVP/머리 390 and MVP/머리 1440 — wordmark · 모의투자 badge · '이 앱은 실전 주문을 내지 않아요'
// chip, then (signed in) the tabs in the middle on 1440 and the gear on the right.
import clsx from 'clsx';
import { Settings } from 'lucide-react';
import { copy } from '../copy';
import { ModeBadge } from './Badges';
import { IconButton } from './Buttons';
import { NavItem, TABS, type TabKey } from './Nav';
import styles from './Header.module.css';

export interface HeaderProps {
  /** Signed in: tabs (1440) and the gear. */
  signedIn: boolean;
  current: TabKey | null;
}

export function Header({ signedIn, current }: HeaderProps) {
  return (
    <header className={styles.header}>
      <div className={styles.inner}>
        <div className={styles.left}>
          <span className="t-heading-1">{copy.wordmark}</span>
          <ModeBadge />
          <span className={clsx(styles.noLive, 't-caption')}>{copy.noLiveOrders}</span>
        </div>
        {signedIn ? (
          <nav className={styles.tabs}>
            <ul className={styles.tabList}>
              {TABS.map(({ key, to }) => (
                <li key={key}>
                  <NavItem to={to} current={key === current}>
                    {copy.nav[key]}
                  </NavItem>
                </li>
              ))}
            </ul>
          </nav>
        ) : (
          <span />
        )}
        <div className={styles.right}>
          {signedIn ? <IconButton icon={Settings} label={copy.settings} to="/settings" /> : null}
        </div>
      </div>
    </header>
  );
}
