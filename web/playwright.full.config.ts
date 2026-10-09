import { defineConfig } from '@playwright/test';

// The full run (npm run e2e:full): the site against the real engine API, no fixtures. Each
// dev-seed world gets a fresh database and its own uvicorn (e2e/full/serve.ts), which serves the
// production build in web/dist (npm run build) on the same origin with the production CSP.
// Ports 4271–4273 and the dist folder keep it apart from the fixture run (playwright.config.ts).
const WORLDS = [
  { world: 'first-day', port: 4271 },
  { world: 'paper', port: 4272 },
  { world: 'discovery', port: 4273 },
] as const;

const WIDTHS = [
  {
    name: '390',
    use: {
      viewport: { width: 390, height: 844 },
      deviceScaleFactor: 3,
      isMobile: true,
      hasTouch: true,
    },
  },
  { name: '1440', use: { viewport: { width: 1440, height: 900 } } },
] as const;

export default defineConfig({
  testDir: './e2e/full',
  outputDir: 'test-results/full',
  fullyParallel: false,
  workers: 3,
  forbidOnly: Boolean(process.env.CI),
  reporter: process.env.CI ? 'github' : 'list',
  use: { browserName: 'chromium', trace: 'retain-on-failure' },
  webServer: WORLDS.map(({ world, port }) => ({
    command: `node e2e/full/serve.ts ${world} ${String(port)}`,
    url: `http://127.0.0.1:${String(port)}/api/healthz`,
    // Always a fresh seed: never reuse a server that may hold yesterday's database.
    reuseExistingServer: false,
    timeout: 180_000,
    stdout: 'ignore' as const,
    stderr: 'pipe' as const,
  })),
  projects: WORLDS.flatMap(({ world, port }) =>
    WIDTHS.map((width) => ({
      name: `${world}-${width.name}`,
      metadata: { world },
      use: { ...width.use, baseURL: `http://127.0.0.1:${String(port)}` },
    })),
  ),
});
