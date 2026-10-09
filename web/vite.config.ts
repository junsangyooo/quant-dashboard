/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The production server sends the same policy. `vite preview` sends it too so the
// Playwright smoke test catches any inline <script>/<style> or external request.
// React's `style` prop goes through the CSSOM, which style-src does not govern.
export const CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self'",
  "img-src 'self'",
  "font-src 'self'",
  "connect-src 'self'",
  "manifest-src 'self'",
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join('; ');

export default defineConfig({
  plugins: [react()],
  build: {
    target: 'es2023',
    // No data: URIs — every asset is a same-origin file so CSP needs no `data:`.
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
