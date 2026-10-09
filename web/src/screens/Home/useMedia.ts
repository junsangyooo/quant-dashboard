import { useSyncExternalStore } from 'react';

/**
 * The 1440 layout of 자산 and 계획 (two columns, composition second lines always open, a drift
 * chart inside each rule card) starts at 1100px; below it the 390 layout grows wider.
 */
export const WIDE = '(min-width: 1100px)';

function media(query: string): MediaQueryList | null {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia(query)
    : null;
}

/** Whether a media query matches, following changes. False where matchMedia is missing (tests). */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const m = media(query);
      if (!m) return () => undefined;
      m.addEventListener('change', onChange);
      return () => {
        m.removeEventListener('change', onChange);
      };
    },
    () => media(query)?.matches ?? false,
    () => false,
  );
}
