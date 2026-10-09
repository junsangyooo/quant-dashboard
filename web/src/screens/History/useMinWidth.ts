import { useSyncExternalStore } from 'react';

/**
 * True from `px` up (`@media (min-width: …)`), following resizes. Environments without
 * matchMedia (jsdom) read as the narrow layout, the mobile-first default.
 */
export function useMinWidth(px: 600 | 900 | 1100): boolean {
  const query = `(min-width: ${String(px)}px)`;
  return useSyncExternalStore(
    (listener) => {
      if (typeof window.matchMedia !== 'function') return () => undefined;
      const mql = window.matchMedia(query);
      mql.addEventListener('change', listener);
      return () => {
        mql.removeEventListener('change', listener);
      };
    },
    () => typeof window.matchMedia === 'function' && window.matchMedia(query).matches,
    () => false,
  );
}
