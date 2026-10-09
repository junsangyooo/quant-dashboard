// Helpers for the 작동 · 모의투자·실전 · 설정 · 입장 screen tests: every /api call answers from a
// fixture bundle and is logged (method, path, body); a 403 session sends the memory router to
// /pin?next= the way main.tsx does in the browser.
import { configureClient, pinPath } from '../../src/api/client';
import { fixtureFetch } from '../../src/fixtures/runtime';
import type { FixtureBundle } from '../../src/fixtures/types';
import { routes } from '../../src/routes';
import { renderRoutes } from '../helpers';

export interface Call {
  method: string;
  path: string;
  body: unknown;
}

/** Answer from `bundle` and record every request. */
export function serve(bundle: FixtureBundle): Call[] {
  const calls: Call[] = [];
  const play = fixtureFetch(bundle);
  configureClient({
    fetch: (input, init) => {
      const raw = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      const url = new URL(raw, 'http://test.invalid');
      calls.push({
        method: (init?.method ?? 'GET').toUpperCase(),
        path: `${url.pathname}${url.search}`,
        body: typeof init?.body === 'string' ? (JSON.parse(init.body) as unknown) : undefined,
      });
      return play(input, init);
    },
    ...(bundle.shellPollMs !== undefined ? { shellPollMs: bundle.shellPollMs } : {}),
  });
  return calls;
}

/**
 * The app's routes at `path`; 403 session redirects inside the memory router. The client reads
 * the return path from window.location, which a memory router does not move, so the router's
 * own location is used (main.tsx does the same with the browser's).
 */
export function renderApp(path: string) {
  const result = renderRoutes(routes, path);
  configureClient({
    onAuthRequired: () => {
      const { pathname, search, hash } = result.router.state.location;
      if (pathname !== '/pin') void result.router.navigate(pinPath(`${pathname}${search}${hash}`));
    },
  });
  return result;
}

export function writes(calls: readonly Call[]): Call[] {
  return calls.filter((c) => c.method !== 'GET');
}
