// 마지막 확인 지적: 기간 글은 lib/runDates.ts 한 곳에서(시작 = 시작한 날, 끝 = 끝낸 날 · 마지막 확인 일봉).
import { describe, expect, it } from 'vitest';
import { runRange, runSpan, startDay, startDayWeekday } from '../src/lib/runDates';

const NOW = new Date('2026-10-29T08:00:00Z');

describe('실행 기간 글', () => {
  it('끝이 시작보다 앞이면 끝 = 시작', () => {
    // 토요일에 시작했는데 마지막 확인 일봉은 금요일
    expect(
      runRange({ started_at: '2026-10-24T02:00:00Z', status: 'running', last_d: '2026-10-23' }),
    ).toBe('10/24~10/24');
    expect(
      runSpan({ started_at: '2026-10-21T02:00:00Z', status: 'running', last_d: '2026-10-22' }),
    ).toEqual(['2026-10-21', '2026-10-22']);
  });

  it('끝냈으면 끝낸 날, 실행 중이면 마지막 확인 일봉', () => {
    const r = {
      started_at: '2026-09-29T00:00:00Z',
      ended_at: '2026-10-12T06:00:00Z',
      last_d: '2026-10-10',
    };
    expect(runRange({ ...r, status: 'ended' })).toBe('9/29~10/12');
    expect(runRange({ started_at: r.started_at, status: 'running', last_d: '2026-10-28' })).toBe(
      '9/29~10/28',
    );
  });

  it('해가 다르면 시작에 연도, 올해가 아니면 …부터 · 시작에도 연도', () => {
    const r = {
      started_at: '2025-06-02T00:00:00Z',
      status: 'running' as const,
      last_d: '2026-10-28',
    };
    expect(runRange(r)).toBe('2025.6/2~10/28');
    expect(startDay(r, NOW)).toBe('2025.6/2');
    expect(startDayWeekday(r, NOW)).toBe('2025.6/2(월)');
    expect(startDay({ started_at: '2026-10-13T00:00:00Z' }, NOW)).toBe('10/13');
  });
});
