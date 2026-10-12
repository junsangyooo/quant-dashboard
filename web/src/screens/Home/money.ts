// Figures of one account in its own currency: won (whole won) or dollars (cents).
import type { Currency } from '../../api/types';
import { homeCopy } from '../../copy/home';
import {
  formatKrw,
  formatKrwEok,
  formatKrwSigned,
  formatManAxis,
  formatNumber,
  formatPercentSigned,
  formatUsd,
  formatUsdSigned,
  pnlDirection,
  roundTo,
  type PnlDirection,
} from '../../lib/format';

/** '▲ +243,800원 · +2.44%', '▼ −$149.95 · −4.08%' (pct hidden when its base is 0 or less). */
export function pnlText(
  pnl: { amount: number; pct: number | null },
  currency: Currency = 'KRW',
): string {
  const dir = moneyDirection(pnl.amount, currency);
  const arrow = dir === 'gain' ? homeCopy.hero.up : dir === 'loss' ? homeCopy.hero.down : '';
  const body = homeCopy.hero.pnl(
    formatMoneySigned(pnl.amount, currency),
    pnl.pct === null ? null : formatPercentSigned(pnl.pct, 2),
  );
  return arrow ? `${arrow} ${body}` : body;
}

export function formatMoney(value: number, currency: Currency): string {
  return currency === 'USD' ? formatUsd(value) : formatKrw(value);
}

/** '+484,683원', '−$149.95'. */
export function formatMoneySigned(value: number, currency: Currency): string {
  return currency === 'USD' ? formatUsdSigned(value) : formatKrwSigned(value);
}

/** Average cost: 1억 and up in 억·만 for won ('1억 5,493만원'), cents for dollars. */
export function formatAvg(value: number, currency: Currency): string {
  return currency === 'USD' ? formatUsd(value) : formatKrwEok(value);
}

/** Direction after rounding to what is shown: whole won, or cents. */
export function moneyDirection(value: number, currency: Currency): PnlDirection {
  return pnlDirection(value, currency === 'USD' ? 2 : 0);
}

/** Axis ticks: won in 만 ('520만'), dollars without cents unless the step needs them. */
export function moneyTick(currency: Currency): (v: number) => string {
  if (currency === 'KRW') return formatManAxis;
  return (v) => {
    const cents = roundTo(v, 2);
    return `$${formatNumber(cents, Number.isInteger(cents) ? 0 : 2)}`;
  };
}
