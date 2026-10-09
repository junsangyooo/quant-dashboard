import { defineConfig } from '@playwright/test';

// The smoke test runs against the e2e build (production code plus fixtures, `--mode e2e`)
// served by `vite preview`, which sends the production Content-Security-Policy. Pages pick a
// state with `?fixture=<state id>` and never reach a server.
const PORT = 4173;

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
    command: `npm run build:e2e && npx vite preview --outDir dist-e2e --host 127.0.0.1 --port ${String(PORT)} --strictPort`,
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
