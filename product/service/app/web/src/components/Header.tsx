// Figma: v2 머리(SPEC 2-1) — wordmark(실전 운용이 있을 때만 상태 칩 · T-64), then (signed in) the tabs in
// the middle on 1440 and the gear on the right. 모의투자 배지 · '실전 주문을 내지 않아요' 글은 없앴어요(SPEC 8-1).
import { Settings } from 'lucide-react';
import { copy } from '../copy';
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
