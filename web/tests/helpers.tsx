// Test helpers: render with a fresh QueryClient and the API answering from a fixture bundle.
import { QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import type { ReactNode } from 'react';
import { createMemoryRouter, RouterProvider, type RouteObject } from 'react-router';
import { configureClient } from '../src/api/client';
import { createQueryClient } from '../src/api/queries';
import { fixtureFetch } from '../src/fixtures/runtime';
import type { FixtureBundle } from '../src/fixtures/types';

/** Every /api/* call in this test answers from `bundle` (as `?fixture=` does in the browser). */
export function answerFrom(bundle: FixtureBundle): void {
  configureClient({
    fetch: fixtureFetch(bundle),
    ...(bundle.shellPollMs !== undefined ? { shellPollMs: bundle.shellPollMs } : {}),
  });
}

/** Routes in a memory router under a fresh QueryClient (no retry back-off). */
export function renderRoutes(routes: RouteObject[], path = '/') {
  const client = createQueryClient({ retryDelayMs: 0 });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const result = render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { ...result, client, router };
}

/** One element at any path. */
export function renderWithData(ui: ReactNode, path = '/') {
  return renderRoutes([{ path: '*', element: ui }], path);
}
