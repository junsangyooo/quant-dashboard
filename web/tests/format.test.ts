// Expected strings are literals from 예시-값표.md.
import { describe, expect, it } from 'vitest';
import {
  MINUS,
  formatDateTime,
  formatFxRate,
  formatKrw,
  formatKrwEok,
  formatKrwSigned,
  formatManAxis,
  formatMonthDay,
  formatMonthDayWeekday,
  formatNumber,
  formatPercent,
  formatPercentSigned,
  formatPp,
  formatPpMagnitude,
  formatTime,
  formatUsd,
  formatUsdSigned,
  kstDateKey,
  pnlDirection,
  roundTo,
} from '../src/lib/format';

describe('KRW', () => {
  it('formats totals and evaluations', () => {
    expect(formatKrw(10_243_800)).toBe('10,243,800원');
    expect(formatKrw(4_168_750)).toBe('4,168,750원');
    expect(formatKrw(56_548)).toBe('56,548원');
    expect(formatKrw(131_550_000)).toBe('131,550,000원');
  });

  it('signs PnL with + and U+2212', () => {
    expect(formatKrwSigned(243_800)).toBe('+243,800원');
    expect(formatKrwSigned(-47_400)).toBe('−47,400원');
    expect(formatKrwSigned(-47_400).startsWith(MINUS)).toBe(true);
    expect(formatKrwSigned(0)).toBe('0원');
  });

  it('writes amounts of 1억 and more in 억·만 units', () => {
    expect(formatKrwEok(154_930_000)).toBe('1억 5,493만원');
    expect(formatKrwEok(132_660_000)).toBe('1억 3,266만원');
    expect(formatKrwEok(100_000_000)).toBe('1억원');
    expect(formatKrwEok(4_999_800)).toBe('4,999,800원');
  });

  it('labels chart axes in 만', () => {
    expect(formatManAxis(10_000_000)).toBe('1000만');
    expect(formatManAxis(10_200_000)).toBe('1020만');
    expect(formatManAxis(10_400_000)).toBe('1040만');
    expect(formatManAxis(120_000_000)).toBe('1억 2000만');
  });
});

describe('USD and FX', () => {
  it('formats dollars with two decimals', () => {
    expect(formatUsd(3_568.24)).toBe('$3,568.24');
    expect(formatUsd(62.4)).toBe('$62.40');
    expect(formatUsd(126.96)).toBe('$126.96');
    expect(formatUsd(0.13)).toBe('$0.13');
    expect(formatUsd(-0.13)).toBe('−$0.13');
    expect(formatUsdSigned(124.8)).toBe('+$124.80');
  });

  it('formats the KRW/USD rate with one decimal', () => {
    expect(formatFxRate(1_382.4)).toBe('1,382.4원');
    expect(formatFxRate(1_392)).toBe('1,392.0원');
    expect(formatFxRate(1_389.6)).toBe('1,389.6원');
  });
});

describe('percent and percentage points', () => {
  it('formats shares with one decimal', () => {
    expect(formatPercent(40.7)).toBe('40.7%');
    expect(formatPercent(100)).toBe('100.0%');
    expect(formatPercent(0.6)).toBe('0.6%');
  });

  it('signs returns; digits follow the 값표 (+2.44% total, +13.3% per row)', () => {
    expect(formatPercentSigned(2.44, 2)).toBe('+2.44%');
    expect(formatPercentSigned(2.22, 2)).toBe('+2.22%');
    expect(formatPercentSigned(13.3)).toBe('+13.3%');
    expect(formatPercentSigned(-6)).toBe('−6.0%');
    expect(formatPercentSigned(-15.1)).toBe('−15.1%');
    expect(formatPercentSigned(3.59, 2)).toBe('+3.59%');
  });

  it('always signs deviations in %p, U+2212 for minus', () => {
    expect(formatPp(0.2)).toBe('+0.2%p');
    expect(formatPp(-0.2)).toBe('−0.2%p');
    expect(formatPp(-1)).toBe('−1.0%p');
    expect(formatPp(2.4)).toBe('+2.4%p');
    expect(formatPp(0)).toBe('0.0%p');
    expect(formatPp(-4, 0)).toBe('−4%p');
    expect(formatPp(4, 0)).toBe('+4%p');
  });

  it('writes distances in %p without a sign', () => {
    expect(formatPpMagnitude(1.8)).toBe('1.8%p');
    expect(formatPpMagnitude(-0.4)).toBe('0.4%p');
  });

  it('rounds half away from zero, even for binary artefacts', () => {
    expect(roundTo(1.005, 2)).toBe(1.01);
    expect(roundTo(-0.05, 1)).toBe(-0.1);
    expect(formatPercent(0.05)).toBe('0.1%');
    expect(formatPp(-0.04)).toBe('0.0%p');
    expect(formatNumber(-1234.5, 1)).toBe('−1,234.5');
  });

  it('reads direction from what is shown', () => {
    expect(pnlDirection(243_800)).toBe('gain');
    expect(pnlDirection(-0.4)).toBe('flat');
    expect(pnlDirection(-0.6)).toBe('loss');
  });
});

describe('dates and times (KST)', () => {
  it('formats month/day with a weekday', () => {
    expect(formatMonthDayWeekday('2026-10-07', { padDay: true })).toBe('10/07(수)');
    expect(formatMonthDayWeekday('2026-10-08', { padDay: true })).toBe('10/08(목)');
    expect(formatMonthDayWeekday('2026-07-01')).toBe('7/1(수)');
    expect(formatMonthDayWeekday('2026-08-21')).toBe('8/21(금)');
    expect(formatMonthDayWeekday('2026-09-25')).toBe('9/25(금)');
    expect(formatMonthDayWeekday('2026-09-14')).toBe('9/14(월)');
  });

  it('formats axis dates and times', () => {
    expect(formatMonthDay('2026-10-07')).toBe('10/7');
    expect(formatMonthDay('2026-07-07')).toBe('7/7');
    expect(formatTime('2026-10-07T08:30:00+09:00')).toBe('08:30');
    expect(formatDateTime('2026-10-07T08:30:00+09:00', { padDay: true })).toBe('10/07 08:30');
  });

  it('converts instants to KST, across the date line', () => {
    expect(formatTime('2026-10-06T23:30:00Z')).toBe('08:30');
    expect(kstDateKey('2026-10-06T23:30:00Z')).toBe('2026-10-07');
    expect(formatMonthDayWeekday(new Date('2026-10-06T15:00:00Z'), { padDay: true })).toBe(
      '10/07(수)',
    );
  });

  it('rejects unparseable input', () => {
    expect(() => formatTime('not a date')).toThrow(RangeError);
  });
});
