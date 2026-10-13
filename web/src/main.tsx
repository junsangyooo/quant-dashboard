import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClientProvider } from '@tanstack/react-query';
import { createBrowserRouter } from 'react-router';
import { RouterProvider } from 'react-router/dom';
import { configureClient, pinPath } from './api/client';
import { createQueryClient } from './api/queries';
import { createRoutes, loadScreens, prefetchScreens, screenOf } from './routes';
import './styles/pretendard.css';
import './styles/tokens.css';
import './styles/global.css';

// The screen this address opens loads before the first render, alongside the fixture below: the
// shell and the screen then paint together, as with one bundle (routes.tsx). A chunk that cannot
// load leaves the screen lazy; its route then shows the router's error like any failed load.
const first = screenOf(window.location.pathname);
const firstScreen = first ? loadScreens([first]).catch(() => ({})) : Promise.resolve({});

// `?fixture=<state id>` answers every /api/* call from src/fixtures/bundles/<id>.ts with no
// network. MODE is 'development' (vite dev), 'e2e' (Playwright build) or 'test' (vitest); in
// 'production' this block is removed at build time and the fixtures never ship.
if (import.meta.env.MODE !== 'production') {
  const fixture = new URLSearchParams(window.location.search).get('fixture');
  if (fixture) {
    const { installFixture, applyFixtureSearch } = await import('./fixtures/runtime');
    applyFixtureSearch(await installFixture(fixture));
  }
}

const container = document.getElementById('root');
if (!container) throw new Error('#root is missing from index.html');

const router = createBrowserRouter(createRoutes(await firstScreen));
const queryClient = createQueryClient();

// No session (403 pin|locked|auth) → the PIN page, then back to where the user was.
configureClient({
  onAuthRequired: (next) => {
    if (window.location.pathname !== '/pin') void router.navigate(pinPath(next));
  },
});

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);

// The other screens' chunks load a second after the page has loaded, so they never compete
// with the first screen and its data; a tab then opens without waiting for its chunk.
function prefetchLater(): void {
  const start = () => window.setTimeout(() => void prefetchScreens().catch(() => undefined), 1000);
  if (document.readyState === 'complete') start();
  else window.addEventListener('load', start, { once: true });
}
prefetchLater();
