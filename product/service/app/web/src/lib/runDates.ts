// 모의투자 실행의 날짜 글 — 기간 글은 모두 이 파일만 쓴다.
// - 시작 = 시작한 날(시작 시각의 날짜). 끝 = 끝낸 날(끝냈으면) 또는 마지막 확인 일봉(실행 중).
//   끝이 시작보다 앞이면 끝 = 시작.
// - 시작과 끝의 해가 다르면 '2025.6/2~10/28'(차트 축과 같은 꼴). '…부터' · '시작'은 올해가 아니면 연도.
// 자산 차트의 첫 점은 기준 일봉이라 시작한 날과 다를 수 있다.
import {
  formatMonthDay,
  formatMonthDayWeekday,
  formatYearDate,
  kstDateKey,
  kstParts,
} from './format';

export interface RunDates {
  started_at: string;
  status?: 'running' | 'ended' | undefined;
  ended_at?: string | null | undefined;
  last_d?: string | null | undefined;
}

const yearOf = (input: string | Date) => kstParts(input).year;

/** `[시작, 끝]` 날짜 키(YYYY-MM-DD, KST). */
export function runSpan(r: RunDates): [string, string] {
  const start = kstDateKey(r.started_at);
  const endSource = r.ended_at ?? (r.status === 'ended' ? null : r.last_d) ?? r.started_at;
  const end = kstDateKey(endSource);
  return [start, end < start ? start : end];
}

export function runRange(r: RunDates): string {
  const [start, end] = runSpan(r);
  const head = yearOf(start) !== yearOf(end) ? formatYearDate(start) : formatMonthDay(start);
  return `${head}~${formatMonthDay(end)}`;
}

/** '5/30' · 올해가 아니면 '2025.5/30' ('…부터'). */
export function startDay(r: RunDates, now: Date = new Date()): string {
  const start = kstDateKey(r.started_at);
  return yearOf(start) !== yearOf(now) ? formatYearDate(start) : formatMonthDay(start);
}

/** '5/30(금)' · 올해가 아니면 '2025.5/30(금)' ('시작'). */
export function startDayWeekday(r: RunDates, now: Date = new Date()): string {
  const start = kstDateKey(r.started_at);
  const day = formatMonthDayWeekday(start);
  return yearOf(start) !== yearOf(now) ? `${String(yearOf(start))}.${day}` : day;
}
