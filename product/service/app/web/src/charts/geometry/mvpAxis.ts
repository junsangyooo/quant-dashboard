// MVP chart axis: three ticks, the lowest on the bottom line and the highest on the top line
// (Figma MVP 자산 · 백테스트: 990만 · 1,020만 · 1,050만), always covering the data.
import { niceStep, type YAxis } from './lineChart';

export function edgeAxis(values: readonly number[]): YAxis {
  const finite = values.filter((v) => Number.isFinite(v));
  if (finite.length === 0) return { domain: [0, 1], ticks: [] };
  const min = Math.min(...finite);
  const max = Math.max(...finite);
  let step = niceStep((max - min || Math.max(Math.abs(max) * 0.01, 1)) / 2);
  for (let i = 0; i < 20; i++) {
    const lo = Math.floor(min / step) * step;
    if (lo + 2 * step >= max) {
      const ticks = [lo, lo + step, lo + 2 * step];
      return { domain: [lo, lo + 2 * step], ticks };
    }
    step = niceStep(step * 1.6);
  }
  return { domain: [min, max], ticks: [min, max] };
}
