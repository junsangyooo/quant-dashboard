import { useCallback, useState } from 'react';

/**
 * Width of an element, following resizes. Geometry is computed in px from this width, so
 * strokes and text stay crisp (no viewBox scaling). `fixed` skips measuring (tests, gallery).
 */
export function useElementWidth(fallback: number, fixed?: number) {
  const [measured, setMeasured] = useState(fallback);
  const ref = useCallback(
    (el: HTMLElement | null) => {
      if (!el || fixed !== undefined) return;
      const read = () => {
        const w = el.getBoundingClientRect().width;
        if (w > 0) setMeasured(w);
      };
      read();
      if (typeof ResizeObserver === 'undefined') return;
      const ro = new ResizeObserver(read);
      ro.observe(el);
      return () => {
        ro.disconnect();
      };
    },
    [fixed],
  );
  return [ref, fixed ?? measured] as const;
}
