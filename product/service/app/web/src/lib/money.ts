// MVP number words: shares, counts, signed returns. Built on lib/format (U+2212 minus, KST dates).
import { copy } from '../copy';
import { formatNumber, formatPercentSigned, pnlDirection, type PnlDirection } from './format';

export const shares = (n: number) => `${formatNumber(n)}${copy.units.shares}`;
export const times = (n: number) => `${formatNumber(n)}${copy.units.times}`;

/** Ratio (0.0412) → `+4.12%`. */
export const pct = (ratio: number, digits = 2) => formatPercentSigned(ratio * 100, digits);

export function tone(value: number, digits = 0): PnlDirection {
  return pnlDirection(value, digits);
}

export const toneClass: Record<PnlDirection, string> = {
  gain: 'c-gain',
  loss: 'c-loss',
  flat: 'c-flat',
};

/**
 * Asset axis: below 1억 in 만 with grouping (`10500000` → `1,050만`); from 1억 in 억 with up to
 * three decimals (`5000000000` → `50억`, `120000000` → `1.2억`, `302500000` → `3.025억`).
 */
export function manTick(value: number, inEok = Math.abs(value) >= 1e8): string {
  if (inEok) {
    const eok = Number((value / 1e8).toFixed(3));
    return `${formatNumber(eok, eok % 1 === 0 ? 0 : (String(eok).split('.')[1]?.length ?? 0))}${copy.units.eok}`;
  }
  return `${formatNumber(Math.round(value / 1e4))}${copy.units.man}`;
}

/** One unit for a whole axis: if its top reaches 1억, every tick is in 억 (0 → '0억'). */
export function axisTick(domainMax: number): (value: number) => string {
  const inEok = Math.abs(domainMax) >= 1e8;
  return (value: number) => manTick(value, inEok);
}
