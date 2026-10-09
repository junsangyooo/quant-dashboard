/// <reference types="vitest/config" />
import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';

// Same policy as the production server (autotrade/CONTRACT.md §세션과 보안). `vite preview`
// sends it too, so Playwright catches any inline <script>/<style> or external request.
// React's `style` prop goes through the CSSOM, which style-src does not govern.
export const CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self'",
  "img-src 'self' data:",
  "connect-src 'self'",
  "font-src 'self'",
  "frame-ancestors 'none'",
  "base-uri 'none'",
  "form-action 'self'",
].join('; ');

/**
 * Build-time guard: a production build fails if any module under src/fixtures/ made it into
 * the output. Fixtures load only behind `import.meta.env.MODE !== 'production'` (main.tsx),
 * which the bundler removes; this catches an accidental static import.
 */
export function noFixturesInProduction(): Plugin {
  let mode = 'production';
  return {
    name: 'quant:no-fixtures-in-production',
    apply: 'build',
    configResolved(config) {
      mode = config.mode;
    },
    generateBundle(_options, bundle) {
      if (mode !== 'production') return;
      const leaked = Object.values(bundle).flatMap((output) =>
        output.type === 'chunk'
          ? output.moduleIds.filter((id) => id.includes('/src/fixtures/'))
          : [],
      );
      if (leaked.length > 0) {
        this.error(`fixtures must not ship in the production build:\n${leaked.join('\n')}`);
      }
    },
  };
}

export default defineConfig({
  plugins: [react(), noFixturesInProduction()],
  build: {
    target: 'es2023',
    // No data: URIs — every asset is a same-origin file.
    assetsInlineLimit: 0,
  },
  preview: {
    headers: { 'Content-Security-Policy': CONTENT_SECURITY_POLICY },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
    include: ['tests/**/*.test.{ts,tsx}'],
    css: { modules: { classNameStrategy: 'non-scoped' } },
  },
});
