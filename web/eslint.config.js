import js from '@eslint/js';
import { defineConfig } from 'eslint/config';
import tseslint from 'typescript-eslint';
import reactHooks from 'eslint-plugin-react-hooks';
import jsxA11y from 'eslint-plugin-jsx-a11y';
import globals from 'globals';

export default defineConfig(
  {
    ignores: [
      'dist',
      'dist-e2e',
      'dist-e2e-*',
      'node_modules',
      'coverage',
      'playwright-report',
      'test-results',
      'public',
      // A Figma plugin job body (top-level return/await), not a module.
      'scripts/figma/dump.js',
    ],
  },
  js.configs.recommended,
  tseslint.configs.strictTypeChecked,
  tseslint.configs.stylisticTypeChecked,
  {
    languageOptions: {
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
      globals: { ...globals.browser },
    },
    rules: {
      // SVG path strings and copy templates interpolate numbers constantly.
      '@typescript-eslint/restrict-template-expressions': ['error', { allowNumber: true }],
    },
  },
  {
    files: ['src/**/*.{ts,tsx}', 'tests/**/*.{ts,tsx}'],
    ...reactHooks.configs.flat['recommended-latest'],
  },
  {
    files: ['src/**/*.tsx'],
    ...jsxA11y.flatConfigs.strict,
  },
  {
    files: ['scripts/**', 'e2e/**', 'tests/**', '*.config.{js,ts}'],
    languageOptions: { globals: { ...globals.node } },
  },
  {
    files: ['**/*.{js,mjs}'],
    ...tseslint.configs.disableTypeChecked,
  },
);
