import { defineConfig } from '@playwright/test';

// The smoke test runs against the e2e build (production code plus fixtures, `--mode e2e`)
// served by `vite preview`, which sends the production Content-Security-Policy. Pages pick a
// state with `?fixture=<state id>` and never reach a server.
// Several e2e runs may share one working tree at once: each picks its own port and build
// folder (E2E_PORT, E2E_OUT) so builds and preview servers never collide.
const PORT = Number(process.env.E2E_PORT ?? '4173');
const OUT = process.env.E2E_OUT ?? 'dist-e2e';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: `http://127.0.0.1:${String(PORT)}`,
    trace: 'retain-on-failure',
  },
  webServer: {
    command: `npm run gen:tokens && npx tsc -b && npx vite build --mode e2e --outDir ${OUT} && npx vite preview --outDir ${OUT} --host 127.0.0.1 --port ${String(PORT)} --strictPort`,
    url: `http://127.0.0.1:${String(PORT)}`,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
  projects: [
    {
      name: 'mobile-390',
      use: {
        browserName: 'chromium',
        viewport: { width: 390, height: 844 },
        deviceScaleFactor: 3,
        isMobile: true,
        hasTouch: true,
      },
    },
    {
      name: 'desktop-1440',
      use: { browserName: 'chromium', viewport: { width: 1440, height: 900 } },
    },
  ],
});
