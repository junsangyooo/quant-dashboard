import { describe, expect, it } from 'vitest';
import { dayTime, nextWeekday } from '../src/lib/when';

describe('MVP date words', () => {
  it('writes 10/29(목) 14:32 in KST', () => {
    expect(dayTime('2026-10-29T05:32:00Z')).toBe('10/29(목) 14:32');
  });

  it('skips the weekend for the next fill day', () => {
    expect(nextWeekday('2026-10-29')).toBe('2026-10-30');
    expect(nextWeekday('2026-10-30')).toBe('2026-11-02');
  });
});
