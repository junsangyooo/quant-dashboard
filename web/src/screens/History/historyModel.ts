// Pure helpers of the 기록 screen: URL state, filters, row words, tiles. No React here, so the
// unit tests can check every 완료 조건 number without rendering.
import { eventName, sideName } from '../../api/adapters';
import type { EventKind, HistoryEvent, HistoryResponse, Ledger } from '../../api/types';
import { copy } from '../../copy';
import { historyCopy as hc, failureCopy, treatmentCopy } from '../../copy/history';
import {
  formatKrw,
  formatMonthDay,
  formatPpMagnitude,
  formatTime,
  kstDateKey,
} from '../../lib/format';
import { pendingOf } from './proposed';

// ── URL state ───────────────────────────────────────────────────────────────

export type KindFilter = HistoryResponse['filters']['kinds'][number]['kind'];

const KIND_FILTERS: readonly KindFilter[] = [
  'rebalance',
  'deposit',
  'withdrawal',
  'dividend',
  'failed',
  'ai',
];

export interface HistoryParams {
  ledger: Ledger | null;
  year: number | null;
  /** 'all' or a rule id. */
  rule: string;
  kind: KindFilter | null;
}

export function readParams(params: URLSearchParams): HistoryParams {
  const ledger = params.get('ledger');
  const year = Number(params.get('year'));
  const kind = params.get('kind');
  return {
    ledger: ledger === 'paper' || ledger === 'live' ? ledger : null,
    year: Number.isInteger(year) && year > 2000 ? year : null,
    rule: params.get('rule') ?? 'all',
    kind: KIND_FILTERS.find((k) => k === kind) ?? null,
  };
}

/** A copy of `params` with one key set (or removed when the value is null). */
export function withParam(
  params: URLSearchParams,
  key: 'ledger' | 'year' | 'rule' | 'kind',
  value: string | null,
): URLSearchParams {
  const next = new URLSearchParams(params);
  if (value === null) next.delete(key);
  else next.set(key, value);
  return next;
}

/** `?…` or '' (keeps the order of the keys the user built). */
export function searchString(params: URLSearchParams): string {
  const s = params.toString();
  return s ? `?${s}` : '';
}

/** `YYYY-MM-DD` from a route param, or null. */
export function parseDateKey(raw: string | undefined): string | null {
  if (!raw || !/^\d{4}-\d{2}-\d{2}$/.test(raw)) return null;
  try {
    return kstDateKey(raw) === raw ? raw : null;
  } catch {
    return null;
  }
}

// ── filters ─────────────────────────────────────────────────────────────────

/** The 종류 chip an event counts under; 시작 and 실전 켬/끔 count under none (기획 §5 거르기). */
export function kindOf(kind: EventKind): KindFilter | null {
  switch (kind) {
    case 'rebalance':
    case 'partial-failed':
    case 'in-progress':
      return 'rebalance';
    case 'deposit':
      return 'deposit';
    case 'withdrawal':
      return 'withdrawal';
    case 'dividend':
      return 'dividend';
    case 'check-failed':
      return 'failed';
    case 'discovery':
    case 'ai-buy':
    case 'ai-sell':
    case 'ai-check':
    case 'monthly-review':
      return 'ai';
    case 'start':
    case 'live-on':
    case 'live-off':
      return null;
  }
}

/** Both chip rows apply together (기획 §5 거르기 '두 줄은 함께 적용'). */
export function matches(event: HistoryEvent, rule: string, kind: KindFilter | null): boolean {
  if (rule !== 'all' && event.rule?.id !== rule) return false;
  if (kind !== null && kindOf(event.kind) !== kind) return false;
  return true;
}

export interface OffPeriodRow {
  kind: 'off-period';
  from: string;
  to: string;
}

export type ListRow = { kind: 'event'; event: HistoryEvent } | OffPeriodRow;

export interface MonthGroup {
  month: string;
  change: number;
  rows: ListRow[];
}

function monthKey(date: string): string {
  return date.slice(0, 7);
}

/**
 * Month groups newest first, each with its rows newest first. 끈 기간 rows sit at their start
 * date and show only without a 종류 filter. Without filters every month keeps its head (the
 * month changes add up to the 손익); with filters, months with nothing left are dropped.
 */
export function visibleMonths(
  data: Pick<HistoryResponse, 'months' | 'offPeriods'>,
  rule: string,
  kind: KindFilter | null,
): MonthGroup[] {
  return data.months.flatMap((m) => {
    const rows: { date: string; row: ListRow }[] = m.events
      .filter((e) => matches(e, rule, kind))
      .map((event) => ({ date: event.date, row: { kind: 'event', event } }));
    if (kind === null) {
      for (const p of data.offPeriods) {
        if (monthKey(p.from) === m.month.slice(0, 7)) {
          rows.push({ date: p.from, row: { kind: 'off-period', from: p.from, to: p.to } });
        }
      }
    }
    if (rows.length === 0 && (rule !== 'all' || kind !== null)) return [];
    rows.sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));
    return [{ month: m.month, change: m.change, rows: rows.map((r) => r.row) }];
  });
}

/** Number of event rows a filter leaves (the chip counts must equal this, 완료 조건). */
export function countRows(
  data: Pick<HistoryResponse, 'months'>,
  rule: string,
  kind: KindFilter | null,
): number {
  return data.months.reduce((n, m) => n + m.events.filter((e) => matches(e, rule, kind)).length, 0);
}

/** Month number of a `month` key ('2026-10' or '2026-10-01'). */
export function monthNumber(month: string): number {
  return Number(month.slice(5, 7));
}

// ── row words ───────────────────────────────────────────────────────────────

/** '[예시] 종목 모멘텀' — the prefix word is copy.state.example. */
export function ruleName(rule: { name: string; example?: boolean | undefined }): string {
  return rule.example ? `[${copy.state.example}] ${rule.name}` : rule.name;
}

/** Main line of a row: '리밸런싱 · 2.3%p 벗어남', '배당 16,243원', '시작 · 10,000,000원' … */
export function rowTitle(e: HistoryEvent): string {
  switch (e.kind) {
    case 'rebalance':
      return e.deviation !== undefined
        ? hc.list.rebalance(formatPpMagnitude(e.deviation))
        : hc.list.rebalancePlain;
    case 'in-progress':
      return hc.list.inProgress;
    case 'partial-failed':
      return hc.list.partialFailed;
    case 'check-failed':
      return hc.list.checkFailed;
    case 'dividend':
      return e.amount !== undefined ? hc.list.dividend(formatKrw(e.amount)) : eventName(e.kind);
    case 'deposit':
      return e.amount !== undefined ? hc.list.deposit(formatKrw(e.amount)) : eventName(e.kind);
    case 'withdrawal':
      return e.amount !== undefined ? hc.list.withdrawal(formatKrw(e.amount)) : eventName(e.kind);
    case 'start':
      return e.amount !== undefined ? hc.list.start(formatKrw(e.amount)) : eventName(e.kind);
    default:
      return eventName(e.kind);
  }
}

/** Text after the mini stage icons: '매수 22:30', '9/15 다시 · 체결', '수수료 206원'. */
export function stageNote(e: HistoryEvent): string | null {
  const pending = pendingOf(e);
  if (e.kind === 'in-progress' && pending) {
    return hc.list.pending(sideName(pending.side), formatTime(pending.at));
  }
  if (e.retry) return hc.list.retry(formatMonthDay(e.retry.date), e.retry.filled);
  if (e.fees !== undefined) return hc.list.fees(formatKrw(e.fees));
  return null;
}

/** 처리 칩 words ('손익 제외', '수익', '다음 확인에 투자', '출금 대기 ~10/12'). */
export function treatmentLabel(
  treatment: NonNullable<HistoryEvent['treatment']>,
  until?: string | null,
): string {
  if (treatment === 'withdraw-wait') {
    return treatmentCopy.withdrawWait(until ? formatMonthDay(until) : null);
  }
  return treatmentCopy[treatment];
}

/** '시세 응답 없음' …; null for 'other' (no wording in the spec). */
export function failureLabel(reason: HistoryEvent['failureReason']): string | null {
  if (reason === undefined || reason === 'other') return null;
  return failureCopy[reason];
}

/** Accessible name of a row link: the visible facts in reading order. */
export function rowLabel(e: HistoryEvent, parts: readonly (string | null)[]): string {
  return [rowTitle(e), ...parts].filter((p): p is string => Boolean(p)).join(' · ');
}

// ── tiles ───────────────────────────────────────────────────────────────────

export type MiniCell = 'rebalance' | 'partialFail' | 'rebalanceInProgress';

/** Mini icons of the 리밸런싱 tile, oldest first (완료 · 일부 실패 · 진행 중), at most `max`. */
export function rebalanceCells(tiles: HistoryResponse['tiles']['rebalances'], max = 5): MiniCell[] {
  const done = Math.max(0, tiles.count - tiles.partialFailed - tiles.inProgress);
  const cells: MiniCell[] = [
    ...Array<MiniCell>(done).fill('rebalance'),
    ...Array<MiniCell>(tiles.partialFailed).fill('partialFail'),
    ...Array<MiniCell>(tiles.inProgress).fill('rebalanceInProgress'),
  ];
  return cells.slice(-max);
}

/** Fees of each rebalance (oldest first) for the 수수료 tile's mini bars. */
export function rebalanceFees(data: Pick<HistoryResponse, 'months'>): number[] {
  return data.months
    .flatMap((m) => m.events)
    .filter((e) => kindOf(e.kind) === 'rebalance' && e.fees !== undefined)
    .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0))
    .map((e) => e.fees ?? 0);
}
