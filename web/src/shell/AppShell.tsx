// Frame for every signed-in page: skip link → header → main → bottom tabs (tab pages, 390).
import clsx from 'clsx';
import { useEffect, useRef } from 'react';
import { Outlet, ScrollRestoration, useLocation, useMatches } from 'react-router';
import { copy } from '../copy';
import { Header } from '../components/Header';
import { BottomTabs } from '../components/Nav';
import { shellFixture } from '../fixtures/shell';
import { isPageHandle, type PageHandle } from './page';
import styles from './AppShell.module.css';

const FALLBACK: PageHandle = { page: 'home', kind: 'tab', tab: 'home' };

export function useCurrentPage(): PageHandle {
  const matches = useMatches();
  for (let i = matches.length - 1; i >= 0; i--) {
    const handle = matches[i]?.handle;
    if (isPageHandle(handle)) return handle;
  }
  return FALLBACK;
}

export function AppShell() {
  const page = useCurrentPage();
  const { pathname } = useLocation();
  const main = useRef<HTMLElement>(null);
  const firstRender = useRef(true);

  // Move focus to the new page's content after client-side navigation.
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    main.current?.focus({ preventScroll: true });
  }, [pathname]);

  // Sub-pages sit under 자산 in the sitemap; Figma keeps 자산 underlined there (1:63806).
  const current = page.tab ?? (page.kind === 'sub' ? 'home' : null);
  const state = shellFixture;

  return (
    <div className={styles.shell}>
      <a className={clsx(styles.skip, 't-label')} href="#main">
        {copy.skipLink}
      </a>
      <Header
        mode={state.mode}
        status={state.status}
        statusLabel={state.statusLabel}
        current={current}
        currentKind={page.kind === 'tab' ? 'page' : 'true'}
      />
      <main
        id="main"
        ref={main}
        tabIndex={-1}
        className={clsx(styles.main, page.kind !== 'tab' && styles.sub)}
      >
        <Outlet />
      </main>
      {page.kind === 'tab' ? <BottomTabs current={page.tab ?? null} /> : null}
      <ScrollRestoration />
    </div>
  );
}
