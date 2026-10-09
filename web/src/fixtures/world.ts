// The 예시-값표 world shared by every fixture bundle: instruments, rules and time helpers.
// Values are the table's; keep bundles importing from here so 39 states stay consistent.
// `initials` follow the contract rule, which matches Figma's logo circles: K2, SP, 삼, NV, B.
import type { Instrument, RuleRef, Trend } from '../api/types';
import { paperDaily3m, untouchedDaily3m } from './charts';

/** KST ISO timestamp: kst('2026-10-07', '08:30') → '2026-10-07T08:30:00+09:00'. */
export function kst(date: string, time: string): string {
  return `${date}T${time}:00+09:00`;
}

/** Return in % with two decimals (contract `ret2`). */
export function ret2(value: number, base: number): number {
  return Math.round(((value - base) / base) * 10000) / 100;
}

export const START_CAPITAL = 10_000_000;

export const KOSPI200: Instrument = {
  id: 'KR:069500',
  name: 'KOSPI200 ETF',
  kind: 'etf',
  market: 'KR',
  currency: 'KRW',
  initials: 'K2',
};

/** US-listed S&P 500 ETF; the engine's default ticker is SPYM (formerly SPLG). */
export const SP500: Instrument = {
  id: 'US:SPYM',
  name: 'S&P 500 ETF',
  kind: 'etf',
  market: 'US',
  currency: 'USD',
  initials: 'SP',
};

export const SAMSUNG: Instrument = {
  id: 'KR:005930',
  name: '삼성전자',
  kind: 'stock',
  market: 'KR',
  currency: 'KRW',
  initials: '삼',
};

export const NVDA: Instrument = {
  id: 'US:NVDA',
  name: 'NVDA',
  kind: 'stock',
  market: 'US',
  currency: 'USD',
  initials: 'NV',
};

/** Bought in KRW outside Toss (예시 값표 2장 가정). */
export const BTC: Instrument = {
  id: 'COIN:BTC',
  name: 'BTC',
  kind: 'coin',
  market: 'COIN',
  currency: 'KRW',
  initials: 'B',
  outsideToss: true,
};

export const INDEX_HALF: RuleRef = {
  id: 'index_half',
  name: '지수 반반',
  ai: false,
  colorIndex: 0,
};

/** '[예시] 종목 모멘텀' (AI 판단 포함); the screen prints the '[예시]' prefix from `example`. */
export const MOMENTUM: RuleRef = {
  id: 'momentum',
  name: '종목 모멘텀',
  ai: true,
  colorIndex: 1,
  example: true,
};

/** 3개월 series of the paper ledger (7/7–10/7), daily values read off the Figma lines. */
export function paperTrendSeries3m(): Trend['series'] {
  const baseline = new Map(untouchedDaily3m.map((p) => [p.date, p.value]));
  return paperDaily3m.flatMap((p) => {
    if (p.value === null) return [];
    const b = baseline.get(p.date) ?? null;
    return [
      {
        date: p.date,
        value: p.value,
        ret: ret2(p.value, START_CAPITAL),
        baseline: b,
        baselineRet: b === null ? null : ret2(b, START_CAPITAL),
      },
    ];
  });
}
