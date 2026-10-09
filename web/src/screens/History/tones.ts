// Colors of a rule's instruments (logo rings, before/after bars, donut): chart/cat-n by position.
// The Figma frames use cat-1 · cat-2 for 지수 반반 (전후 비중 1:59915, 도넛 1:61916) and cat-3 · cat-1 ·
// cat-5 for the AI rules ([예시] 종목 모멘텀 1:62197, 3년 발굴 17:6432: 삼 · NV · B, HD · 한 · AV).
import type { LogoTone } from '../../components/Badges';

const PALETTES: readonly (readonly (1 | 2 | 3 | 4 | 5)[])[] = [
  [1, 2, 3, 4, 5],
  [3, 1, 5, 2, 4],
];

/** chart/cat-n of the `index`-th instrument of a rule with `colorIndex`. */
export function logoTone(colorIndex: number, index: number): Exclude<LogoTone, 'cash'> {
  const palette = PALETTES[colorIndex % PALETTES.length] ?? PALETTES[0] ?? [1];
  return palette[index % palette.length] ?? 1;
}
