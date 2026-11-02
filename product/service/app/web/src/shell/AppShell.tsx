// Frame for every page: skip link → header → main → bottom tabs (tab pages, 390).
// It also keeps the door: no account yet → 비밀번호 만들기; no session → 로그인.
import clsx from 'clsx';
import { useEffect, useRef } from 'react';
import { Navigate, Outlet, ScrollRestoration, useLocation, useMatches } from 'react-router';
import { useAppState } from '../api/mvp';
import { copy } from '../copy';
import { Header } from '../components/Header';
import { BottomTabs } from '../components/Nav';
import { Box } from '../components/Box';
import { ConfirmHost } from '../components/ConfirmHost';
import { isPageHandle, type PageHandle } from './page';
import styles from './AppShell.module.css';

const FALLBACK: PageHandle = { page: 'notFound', kind: 'sub' };

export function useCurrentPage(): PageHandle {
  const matches = useMatches();
  for (let i = matches.length - 1; i >= 0; i--) {
    const handle = matches[i]?.handle;
    if (isPageHandle(handle)) return handle;
  }
  return FALLBACK;
}

const AUTH_PATHS = new Set(['/setup', '/login', '/recover']);

export function AppShell() {
  const page = useCurrentPage();
  const { pathname } = useLocation();
  const main = useRef<HTMLElement>(null);
  const firstRender = useRef(true);
  const state = useAppState();

  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    main.current?.focus({ preventScroll: true });
  }, [pathname]);

  const s = state.data;
  if (s) {
    if (!s.setup && pathname !== '/setup') return <Navigate to="/setup" replace />;
    if (s.setup && !s.logged_in && !AUTH_PATHS.has(pathname))
      return <Navigate to="/login" replace />;
    if (s.setup && pathname === '/setup' && !s.logged_in) return <Navigate to="/login" replace />;
    if (s.logged_in && pathname === '/login') return <Navigate to="/" replace />;
  }
  const signedIn = Boolean(s?.logged_in) && page.kind !== 'auth';

  return (
    <div className={styles.shell}>
      <a className={clsx(styles.skip, 't-label')} href="#main">
        {copy.skipLink}
      </a>
      <Header signedIn={signedIn} current={page.tab ?? null} />
      <main id="main" ref={main} tabIndex={-1} className={styles.main}>
        {state.isError ? (
          <div className={styles.offline}>
            <Box tone="error" title={copy.common.noConnection} />
          </div>
        ) : s ? (
          <Outlet />
        ) : null}
      </main>
      {signedIn && page.kind === 'tab' ? <BottomTabs current={page.tab ?? null} /> : null}
      {signedIn ? <ConfirmHost /> : null}
      <ScrollRestoration />
    </div>
  );
}
