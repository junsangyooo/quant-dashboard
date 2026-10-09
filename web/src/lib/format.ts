// Number and date formatting for every figure on screen. Unit words come from copy.ts.
// Rules (ops notes, 예시-값표.md): minus is U+2212, %p is signed, KST everywhere,
// ratios round half away from zero.

import { copy } from '../copy';

/** U+2212 MINUS SIGN, never the ASCII hyphen. */
export const MINUS = '\u2212';
const { won: WON, eok: EOK, man: MAN, pp: PP } = copy.units;

const formatters = new Map<number, Intl.NumberFormat>();

function grouped(digits: number): Intl.NumberFormat {
  let f = formatters.get(digits);
  if (!f) {
    f = new Intl.NumberFormat('en-US', {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
      useGrouping: true,
    });
    formatters.set(digits, f);
  }
  return f;
}

/** Round half away from zero, robust to binary artefacts (1.005 → 1.01). */
export function roundTo(value: number, digits: number): number {
  const factor = 10 ** digits;
  const scaled = Math.round(Math.abs(value) * factor * (1 + Number.EPSILON));
  const rounded = scaled / factor;
  return value < 0 && rounded !== 0 ? -rounded : rounded;
}

type SignMode = 'negative' | 'always';

function signed(value: number, digits: number, body: (abs: string) => string, mode: SignMode) {
  const rounded = roundTo(value, digits);
  const abs = body(grouped(digits).format(Math.abs(rounded)));
  if (rounded < 0) return `${MINUS}${abs}`;
  if (rounded > 0 && mode === 'always') return `+${abs}`;
  return abs;
}

/** `10243800` → `10,243,800` */
export function formatNumber(value: number, digits = 0): string {
  return signed(value, digits, (abs) => abs, 'negative');
}

/** `10243800` → `10,243,800원` */
export function formatKrw(value: number): string {
  return signed(value, 0, (abs) => `${abs}${WON}`, 'negative');
}

/** `243800` → `+243,800원`, `-47400` → `−47,400원`, `0` → `0원` */
export function formatKrwSigned(value: number): string {
  return signed(value, 0, (abs) => `${abs}${WON}`, 'always');
}

/** Amounts of 1억 and more: `154930000` → `1억 5,493만원`; below that, plain won. */
export function formatKrwEok(value: number): string {
  const abs = Math.abs(value);
  if (abs < 1e8) return formatKrw(value);
  const eok = Math.floor(abs / 1e8);
  const man = Math.round((abs - eok * 1e8) / 1e4);
  const sign = value < 0 ? MINUS : '';
  return man === 0
    ? `${sign}${grouped(0).format(eok)}${EOK}${WON}`
    : `${sign}${grouped(0).format(eok)}${EOK} ${grouped(0).format(man)}${MAN}${WON}`;
}

/** Chart axis in 만 units: `10200000` → `1020만`, `120000000` → `1억 2000만`. */
export function formatManAxis(value: number): string {
  const sign = value < 0 ? MINUS : '';
  const abs = Math.abs(value);
  const eok = Math.floor(abs / 1e8);
  const man = Math.round((abs - eok * 1e8) / 1e4);
  if (eok === 0) return `${sign}${String(man)}${MAN}`;
  return man === 0
    ? `${sign}${String(eok)}${EOK}`
    : `${sign}${String(eok)}${EOK} ${String(man)}${MAN}`;
}

/** `3568.24` → `$3,568.24`, `62.4` → `$62.40` */
export function formatUsd(value: number): string {
  return signed(value, 2, (abs) => `$${abs}`, 'negative');
}

/** `126.96` → `+$126.96` */
export function formatUsdSigned(value: number): string {
  return signed(value, 2, (abs) => `$${abs}`, 'always');
}

/** KRW per USD, always one decimal: `1392` → `1,392.0원` */
export function formatFxRate(value: number): string {
  return signed(value, 1, (abs) => `${abs}${WON}`, 'negative');
}

/** Share or weight: `40.7` → `40.7%`, `-6` → `−6.0%` */
export function formatPercent(value: number, digits = 1): string {
  return signed(value, digits, (abs) => `${abs}%`, 'negative');
}

/** Return or change: `13.3` → `+13.3%`, `2.44` (digits 2) → `+2.44%` */
export function formatPercentSigned(value: number, digits = 1): string {
  return signed(value, digits, (abs) => `${abs}%`, 'always');
}

/** Deviation in percentage points, signed: `0.2` → `+0.2%p`, `-0.2` → `−0.2%p`, `0` → `0.0%p` */
export function formatPp(value: number, digits = 1): string {
  return signed(value, digits, (abs) => `${abs}${PP}`, 'always');
}

/** Distance in percentage points, no sign: `1.8` → `1.8%p` (리밸런싱까지 1.8%p) */
export function formatPpMagnitude(value: number, digits = 1): string {
  return signed(Math.abs(value), digits, (abs) => `${abs}${PP}`, 'negative');
}

export type PnlDirection = 'gain' | 'loss' | 'flat';

/** Direction after rounding to what is shown, so `+0.0%` is flat, not gain. */
export function pnlDirection(value: number, digits = 0): PnlDirection {
  const rounded = roundTo(value, digits);
  if (rounded > 0) return 'gain';
  if (rounded < 0) return 'loss';
  return 'flat';
}

// ── Dates (KST) ────────────────────────────────────────────────────────────

const KST_OFFSET_MS = 9 * 60 * 60 * 1000;
const WEEKDAYS = copy.weekdaysShort;
const DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/;

export interface KstParts {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
  weekday: (typeof WEEKDAYS)[number];
}

/**
 * Calendar parts in Asia/Seoul. A bare `YYYY-MM-DD` is already a KST calendar date;
 * anything else is an instant and is shifted by +9h (KST has no DST).
 */
export function kstParts(input: string | Date): KstParts {
  let utc: Date;
  if (typeof input === 'string') {
    const m = DATE_ONLY.exec(input);
    if (m) {
      utc = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
    } else {
      const t = Date.parse(input);
      if (Number.isNaN(t)) throw new RangeError(`Invalid date: ${input}`);
      utc = new Date(t + KST_OFFSET_MS);
    }
  } else {
    utc = new Date(input.getTime() + KST_OFFSET_MS);
  }
  const weekday = WEEKDAYS[utc.getUTCDay()];
  if (weekday === undefined) throw new RangeError('weekday out of range');
  return {
    year: utc.getUTCFullYear(),
    month: utc.getUTCMonth() + 1,
    day: utc.getUTCDate(),
    hour: utc.getUTCHours(),
    minute: utc.getUTCMinutes(),
    weekday,
  };
}

const pad2 = (n: number) => String(n).padStart(2, '0');

export interface MonthDayOptions {
  /** Zero-pad the day: `10/07` instead of `10/7`. */
  padDay?: boolean;
}

/** `2026-10-07` → `10/7` (or `10/07` with padDay) */
export function formatMonthDay(input: string | Date, options: MonthDayOptions = {}): string {
  const p = kstParts(input);
  return `${String(p.month)}/${options.padDay ? pad2(p.day) : String(p.day)}`;
}

/** `2026-10-07` → `10/07(수)` with padDay, `2026-07-01` → `7/1(수)` */
export function formatMonthDayWeekday(input: string | Date, options: MonthDayOptions = {}): string {
  return `${formatMonthDay(input, options)}(${kstParts(input).weekday})`;
}

/** `2026-10-06T23:30:00Z` → `08:30` */
export function formatTime(input: string | Date): string {
  const p = kstParts(input);
  return `${pad2(p.hour)}:${pad2(p.minute)}`;
}

/** `10/07 08:30` */
export function formatDateTime(input: string | Date, options: MonthDayOptions = {}): string {
  return `${formatMonthDay(input, options)} ${formatTime(input)}`;
}

/** KST calendar date key `YYYY-MM-DD` for an instant or a date key. */
export function kstDateKey(input: string | Date): string {
  const p = kstParts(input);
  return `${String(p.year)}-${pad2(p.month)}-${pad2(p.day)}`;
}
