// HealthResponse → the words and tones SCR-HEALTH shows. Pure functions (unit-tested); every
// string comes from copy/health.ts and the formatters. `now` is the server time of the shell.
import { copy } from '../../copy';
import { healthCopy as t } from '../../copy/health';
import type { CalendarState, HealthResponse } from '../../api/types';
import type { SignalKind } from '../../components/Chips';
import type { CalendarState as CellState } from '../../components/Markers';
import { calendarCell, marketName, sideName } from '../../api/adapters';
import {
  formatDateTime,
  formatFxRate,
  formatMonthDay,
  formatMonthDayWeekday,
  formatNumber,
  formatTime,
  kstDateKey,
} from '../../lib/format';

export type Health = HealthResponse;
export type Source = HealthResponse['sources'][number];
export type Todo = HealthResponse['todos'][number];
export type Day = HealthResponse['recent14'][number];
export type SummaryTone = 'ok' | 'check' | 'error' | 'unknown' | 'wait';

/** '08:30' on the same KST day as `now`, '10/6 16:00' otherwise. */
export function atTime(at: string, now: string | null): string {
  return now !== null && kstDateKey(at) === kstDateKey(now) ? formatTime(at) : formatDateTime(at);
}

const str = (v: string | number | undefined): string | undefined =>
  v === undefined ? undefined : String(v);
const num = (v: string | number | undefined): number | undefined => {
  if (v === undefined) return undefined;
  const n = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(n) ? n : undefined;
};

function market(v: string | number | undefined): string {
  const m = str(v);
  return m === 'KR' || m === 'US' || m === 'COIN' || m === 'FX' ? marketName(m) : (m ?? '');
}

/** '324만 토큰', '8,400 토큰'. */
function tokenAmount(n: number): string {
  return t.todo.tokens(
    n >= 10_000 ? `${formatNumber(Math.round(n / 10_000))}${copy.units.man}` : formatNumber(n),
  );
}

function aiTaskName(kind: string | undefined): string {
  return kind !== undefined && kind in t.todo.aiTasks
    ? t.todo.aiTasks[kind as keyof typeof t.todo.aiTasks]
    : t.todo.aiTaskOther;
}

function side(v: string | number | undefined): string {
  const s = str(v);
  return s === 'buy' || s === 'sell' || s === 'fx' ? sideName(s) : (s ?? '');
}

/** The reason words of a failed check ('no-quote' → '시세 응답 없음'). */
export function reasonWord(reason: string | number | undefined): string {
  return reason === 'no-quote' ? t.recent.reasons['no-quote'] : t.recent.reasons.other;
}

/** Cause words for a stale source: '미국 시세', '환율'. */
export function staleSourceName(m: string | number | undefined): string {
  const v = str(m);
  if (v === 'FX') return t.sources.names.fx;
  if (v === 'KR') return t.sources.names['kr-quotes'];
  if (v === 'US') return t.sources.names['us-quotes'];
  return v ?? '';
}

// ── 종합 ─────────────────────────────────────────────────────────────────────

export interface SummaryChip {
  kind: 'info' | SignalKind;
  label: string;
}

export interface SummaryView {
  tone: SummaryTone;
  label: string;
  line: string;
  chips: SummaryChip[];
}

/** 원인 단위 '점검 n': the red cards (each one cause), at least the stale count, at least 1. */
export function checkCount(h: Health): number {
  const red = h.todos.filter((todo) => todo.severity === 'red').length;
  return Math.max(1, red, h.summary.staleCount);
}

export function summaryView(h: Health, now: string | null): SummaryView {
  const s = h.summary;
  const total = s.sourcesTotal;
  const parts: string[] = [];
  if (s.staleCount > 0) parts.push(t.summary.stalePart(s.staleCount));
  if (s.todoCount > 0) parts.push(t.summary.todoPart(s.todoCount));
  const sourcesLine =
    parts.length > 0
      ? t.summary.sourcesWith(total, parts.join(' · '))
      : t.summary.sourcesFine(total);
  const lastNext: SummaryChip[] =
    s.lastCheckAt && s.nextCheckAt
      ? [
          {
            kind: 'info',
            label: t.summary.lastAndNext(
              formatDateTime(s.lastCheckAt),
              formatDateTime(s.nextCheckAt),
            ),
          },
        ]
      : [];

  switch (s.kind) {
    case 'ok':
      return {
        tone: 'ok',
        label: t.summary.ok,
        line: sourcesLine,
        chips: [
          ...lastNext,
          ...(s.todoCount > 0
            ? [{ kind: 'warn', label: t.summary.todoChip(s.todoCount) } as const]
            : []),
        ],
      };
    case 'check': {
      const n = checkCount(h);
      return {
        tone: 'check',
        label: t.summary.check(n),
        line: sourcesLine,
        chips: [...lastNext, { kind: 'warn', label: t.summary.checkChip(n, s.todoCount) }],
      };
    }
    case 'check-failed': {
      const at = h.lastRun?.at ?? s.lastCheckAt;
      const retry = s.retryAt ? atTime(s.retryAt, now) : null;
      const last = s.lastSuccessAt ? formatDateTime(s.lastSuccessAt) : null;
      const info =
        last !== null
          ? retry !== null
            ? t.summary.lastSuccessRetry(last, retry)
            : t.summary.lastSuccess(last)
          : null;
      return {
        tone: 'error',
        label: t.summary.checkFailed,
        line: at
          ? t.summary.failedLine(formatDateTime(at), reasonWord(h.lastRun?.reason))
          : t.summary.checkFailed,
        chips: [
          ...(info !== null ? [{ kind: 'info', label: info } as const] : []),
          { kind: 'error', label: t.summary.failChip(Math.max(1, s.failCount)) },
        ],
      };
    }
    case 'unknown':
      return {
        tone: 'unknown',
        label: t.summary.unknown,
        line: t.summary.unknownLine,
        chips: [
          ...(s.lastCheckAt
            ? [
                {
                  kind: 'info',
                  label: t.summary.lastReceived(formatDateTime(s.lastCheckAt)),
                } as const,
              ]
            : []),
          { kind: 'unknown', label: t.summary.unknownChip },
        ],
      };
    case 'before-first': {
      const first = s.firstCheckAt ?? s.nextCheckAt;
      return {
        tone: 'wait',
        label: t.summary.beforeFirst,
        line: first
          ? t.summary.firstCheckLine(`${formatMonthDayWeekday(first)} ${formatTime(first)}`)
          : t.summary.beforeFirst,
        chips: first ? [{ kind: 'info', label: t.summary.nextOnly(formatDateTime(first)) }] : [],
      };
    }
  }
}

/** The summary when the status itself could not be loaded (1:47224). */
export function unknownView(attemptAt: string, lastKnown: string | null): SummaryView {
  return {
    tone: 'unknown',
    label: t.summary.unknown,
    line: copy.state.errors.health(attemptAt),
    chips: [
      { kind: 'info', label: t.summary.lastReceived(lastKnown ?? t.sources.noValue) },
      { kind: 'unknown', label: t.summary.unknownChip },
    ],
  };
}

// ── 할 일 카드 ───────────────────────────────────────────────────────────────

export interface TodoView {
  tone: 'error' | 'warn';
  icon: 'stale' | 'failed' | 'expiring' | 'push' | 'ai' | 'filings';
  title: string;
  chip: string;
  lines: readonly string[];
  result: string | null;
}

function effectLine(effect: Todo['effect']): string | null {
  return effect === 'other' ? null : t.todo.effect[effect];
}

export function todoView(todo: Todo, now: string | null): TodoView {
  const f = todo.facts;
  const tone = todo.severity === 'red' ? 'error' : 'warn';
  const chip =
    todo.action.kind === 'auto-retry'
      ? t.todo.autoRetry(atTime(todo.action.at, now))
      : t.todo.manual;
  const day = (key: string) => {
    const v = str(f[key]);
    return v ? formatMonthDay(v) : '';
  };
  switch (todo.kind) {
    case 'stale': {
      const m = str(f.market);
      const days = num(f.tradingDays) ?? 0;
      const missing = str(f.missingDates)
        ?.split(',')
        .filter(Boolean)
        .map((d) => formatMonthDay(d))
        .join('·');
      const first =
        m === 'FX'
          ? t.todo.staleFxMissing(days)
          : missing
            ? t.todo.staleMissing(missing, market(m))
            : t.todo.staleMissingCount(market(m), days);
      return {
        tone,
        icon: 'stale',
        title: t.todo.staleTitle(staleSourceName(m), day('basisDate'), days),
        chip,
        lines:
          todo.action.kind === 'auto-retry'
            ? [first, t.todo.nextAttempt(atTime(todo.action.at, now))]
            : [first],
        result: effectLine(todo.effect),
      };
    }
    case 'check-failed': {
      const at = str(f.at);
      const reason = reasonWord(f.reason);
      const auto = todo.action.kind === 'auto-retry';
      return {
        tone,
        icon: 'failed',
        title: t.todo.checkFailedTitle(at ? formatDateTime(at) : ''),
        chip,
        lines:
          todo.action.kind === 'auto-retry'
            ? t.todo.checkFailedLines(reason, atTime(todo.action.at, now))
            : t.todo.checkFailedManualLines(reason),
        result: auto ? t.todo.checkFailedResult : null,
      };
    }
    case 'toss-expiring':
      return {
        tone,
        icon: 'expiring',
        title: t.todo.tossExpiringTitle(day('expiresAt')),
        chip,
        lines: t.todo.tossExpiringLines(num(f.daysLeft) ?? 0),
        result: effectLine(todo.effect),
      };
    case 'order-failed':
      return {
        tone,
        icon: 'failed',
        title: t.todo.orderFailedTitle(day('date'), market(f.market), side(f.side)),
        chip,
        lines: t.todo.orderFailedLines,
        result: effectLine(todo.effect),
      };
    case 'order-rejected':
      return {
        tone,
        icon: 'failed',
        title: t.todo.orderRejectedTitle(day('date'), market(f.market), side(f.side)),
        chip,
        lines: t.todo.orderRejectedLines,
        result: effectLine(todo.effect),
      };
    case 'cancel-failed': {
      const at = str(f.at);
      return {
        tone,
        icon: 'failed',
        title: t.todo.cancelFailedTitle,
        chip,
        lines: t.todo.cancelFailedLines(at ? formatTime(at) : ''),
        result: effectLine(todo.effect),
      };
    }
    case 'push-undelivered':
      return {
        tone,
        icon: 'push',
        title: t.todo.pushUndeliveredTitle(num(f.days) ?? 0),
        chip,
        lines: t.todo.pushUndeliveredLines,
        result: effectLine(todo.effect),
      };
    case 'ai-cli': {
      // Yellow: the month's tokens passed the budget (no time; nothing stops).
      if (str(f.reason) === 'over-budget') {
        return {
          tone,
          icon: 'ai',
          title: t.todo.aiBudgetTitle,
          chip,
          lines: t.todo.aiBudgetLines(
            tokenAmount(num(f.tokens) ?? 0),
            tokenAmount(num(f.budget) ?? 0),
          ),
          result: effectLine(todo.effect),
        };
      }
      // Red: tasks failed three times and wait for a person (since = the oldest one).
      const since = str(f.since);
      const count = num(f.count);
      return {
        tone,
        icon: 'ai',
        title: since ? t.todo.aiCliTitle(atTime(since, now)) : t.sources.names['ai-cli'],
        chip,
        lines:
          count === undefined
            ? [t.todo.aiLogin]
            : [t.todo.aiTaskFailed(aiTaskName(str(f.taskKind)), count), t.todo.aiLogin],
        result: effectLine(todo.effect),
      };
    }
    case 'filings': {
      const m = market(f.market);
      const since = str(f.since);
      const maintenance = str(f.state) === 'maintenance';
      const lines = maintenance ? t.todo.filingsLines(m) : t.todo.filingsStoppedLines(m);
      return {
        tone,
        icon: 'filings',
        title: maintenance ? t.todo.filingsTitle(m) : t.todo.filingsStoppedTitle(m),
        chip,
        lines: since ? [...lines, t.todo.filingsSince(atTime(since, now))] : lines,
        result: effectLine(todo.effect),
      };
    }
  }
}

// ── 자료별 ───────────────────────────────────────────────────────────────────

/** Canonical row order: phase 1 three, the Toss rows, push, then the 2단계 rows. */
export const SOURCE_ORDER: readonly Source['id'][] = [
  'kr-quotes',
  'us-quotes',
  'fx',
  'toss-link',
  'toss-balance',
  'push-devices',
  'filings',
  'ai-cli',
  'metric-table',
];

export function sortSources(sources: readonly Source[]): Source[] {
  return [...sources].sort((a, b) => SOURCE_ORDER.indexOf(a.id) - SOURCE_ORDER.indexOf(b.id));
}

export interface SourceView {
  name: string;
  tone: SignalKind;
  chip: string;
  line: string;
  /** Bar fill 0…1 over two cadences (fresh zone to 1, late to 1.5, stale after). */
  fill: number;
}

const STATE_TONE: Record<Source['state'], SignalKind> = {
  fresh: 'ok',
  late: 'warn',
  stale: 'error',
  maintenance: 'warn',
  unknown: 'unknown',
};

/** The bar spans two cadences: age 1 sits at the end of the fresh zone (50%). */
export function ageFill(age: number): number {
  if (!Number.isFinite(age) || age <= 0) return 0;
  return Math.min(1, age / 2);
}

/**
 * 토스 연결: age is days since connecting ÷ 90 (CONTRACT), so 1 is the expiry day. The bar puts
 * the expiry at the late/stale edge (75%): the late zone is the last 30 days, past it is stale.
 */
export function tossFill(age: number): number {
  if (!Number.isFinite(age) || age <= 0) return 0;
  return Math.min(1, age * 0.75);
}

/** Markets whose filing feed is not 'ok' (filings extra { dart, edgar }): '한국', '미국'. */
function stoppedFilingMarkets(extra: Record<string, string | number>): string {
  const out: string[] = [];
  if (extra.dart !== undefined && extra.dart !== 'ok') out.push(marketName('KR'));
  if (extra.edgar !== undefined && extra.edgar !== 'ok') out.push(marketName('US'));
  return out.join('·');
}

export function sourceView(src: Source, now: string | null): SourceView {
  const name = t.sources.names[src.id];
  const tone = STATE_TONE[src.state];
  const extra = src.extra ?? {};
  const daysLeft = num(extra.daysLeft);
  const chip =
    src.id === 'toss-link' && src.state === 'late' && daysLeft !== undefined
      ? t.sources.expiresIn(daysLeft)
      : t.sources.state[src.state];
  const fill =
    src.state === 'unknown' ? 0 : src.id === 'toss-link' ? tossFill(src.age) : ageFill(src.age);
  const received = src.receivedAt ? t.sources.received(atTime(src.receivedAt, now)) : null;
  const cadence = t.sources.cadence[src.cadence];
  const join = (...parts: (string | null)[]) =>
    parts.filter((p): p is string => p !== null && p !== '').join(' · ');
  if (src.state === 'unknown' && src.basis === null && src.receivedAt === null) {
    return { name, tone, chip, line: join(t.sources.noValue, cadence), fill };
  }
  let line: string;
  switch (src.id) {
    case 'kr-quotes':
      line = join(src.basis ? t.sources.close(formatMonthDay(src.basis)) : null, received, cadence);
      break;
    case 'us-quotes':
      line = join(
        src.basis ? t.sources.closeEt(formatMonthDay(src.basis)) : null,
        received,
        cadence,
      );
      break;
    case 'fx': {
      const rate = src.basis === null ? undefined : num(src.basis);
      line = join(rate === undefined ? null : formatFxRate(rate), received, cadence);
      break;
    }
    case 'toss-link':
      line = join(
        src.basis ? t.sources.expires(formatMonthDay(src.basis)) : null,
        daysLeft === undefined ? null : t.sources.daysLeft(daysLeft),
        cadence,
      );
      break;
    case 'toss-balance': {
      const time = src.receivedAt ? atTime(src.receivedAt, now) : t.sources.noValue;
      line = join(
        src.basis === 'mismatch' ? t.sources.balanceMismatch(time) : t.sources.balanceMatch(time),
        cadence,
      );
      break;
    }
    case 'push-devices':
      line = join(
        t.sources.devices(num(extra.devices) ?? 0),
        src.receivedAt ? t.sources.lastDelivery(formatDateTime(src.receivedAt)) : null,
      );
      break;
    case 'filings':
      line =
        src.state === 'maintenance'
          ? join(t.sources.maintenanceStop(stoppedFilingMarkets(extra)), received)
          : join(
              src.basis ? t.sources.filingsBasis(formatMonthDay(src.basis)) : null,
              received,
              cadence,
            );
      break;
    case 'ai-cli':
      line = join(
        src.receivedAt ? t.sources.lastSuccess(atTime(src.receivedAt, now)) : null,
        cadence,
      );
      break;
    case 'metric-table':
      line = join(src.basis ? t.sources.metricBasis(formatMonthDay(src.basis)) : null, cadence);
      break;
  }
  return { name, tone, chip, line, fill };
}

// ── 최근 14일 ────────────────────────────────────────────────────────────────

export interface RecentSummary {
  fails: number;
  quoteWait: number;
}

export function recentCounts(days: readonly Day[]): RecentSummary {
  return {
    fails: days.filter((d) => d.state === 'failed').length,
    quoteWait: days.filter((d) => d.state === 'quote-wait').length,
  };
}

const RESULTS = t.recent.results as Record<string, string>;

/** '10/7 08:30 확인 · 리밸런싱 시작 · 42초' · '… 확인 실패 · 시세 응답 없음 · 12초' · '… 시세 대기 · 주문 0건'. */
export function runLine(run: {
  at: string;
  result: string;
  seconds: number;
  reason?: string;
}): string {
  const at = formatDateTime(run.at);
  const seconds = t.recent.seconds(Math.round(run.seconds));
  if (run.result === 'failed' || run.result === 'todo') {
    return run.reason === undefined
      ? t.recent.runFailedShort(at, seconds)
      : t.recent.runFailed(at, reasonWord(run.reason), seconds);
  }
  if (run.result === 'quote-wait') {
    return t.recent.run(at, t.recent.results['quote-wait'], t.recent.noOrders);
  }
  return t.recent.run(at, RESULTS[run.result] ?? t.sources.noValue, seconds);
}

/** Cell art: before the record the 14-day grid keeps an empty outline ('14일 칸 빈칸'). */
export function recentCell(state: CalendarState): CellState {
  return state === 'before-record' ? 'future' : calendarCell(state);
}

/** Accessible name of a cell / a weekday without a run: '10/7(수) 리밸런싱 중'. */
export function dayLabel(day: Day): string {
  return `${formatMonthDayWeekday(day.date)} ${copy.calendar.state[recentCell(day.state)]}`;
}

/** The detail line under a chosen cell; the last run carries the failure reason. */
export function dayLine(day: Day, lastRun: Health['lastRun']): string {
  if (lastRun && day.run && kstDateKey(lastRun.at) === day.date) return runLine(lastRun);
  if (day.run) return runLine(day.run);
  return t.recent.day(formatMonthDayWeekday(day.date), copy.calendar.state[recentCell(day.state)]);
}

export type RunIcon = 'rebalance' | 'failed' | 'wait' | 'ok';

export function runIcon(result: string): RunIcon {
  if (result === 'rebalance' || result === 'already-planned' || result === 'in-progress')
    return 'rebalance';
  if (result === 'failed' || result === 'todo' || result === 'partial-failed') return 'failed';
  if (result === 'quote-wait' || result === 'withdraw-wait' || result === 'running') return 'wait';
  return 'ok';
}

/** Monday of a date's week (YYYY-MM-DD). */
export function mondayOf(date: string): string {
  const [y, m, d] = date.split('-').map(Number) as [number, number, number];
  const utc = new Date(Date.UTC(y, m - 1, d));
  const back = (utc.getUTCDay() + 6) % 7;
  utc.setUTCDate(utc.getUTCDate() - back);
  return utc.toISOString().slice(0, 10);
}

/** 0 = Monday … 6 = Sunday. */
export function weekdayIndex(date: string): number {
  const [y, m, d] = date.split('-').map(Number) as [number, number, number];
  return (new Date(Date.UTC(y, m - 1, d)).getUTCDay() + 6) % 7;
}

/** Weeks (rows) of the 14-day grid: Monday label and the days placed by weekday. */
export function recentWeeks(days: readonly Day[]): { monday: string; days: (Day | null)[] }[] {
  const weeks = new Map<string, (Day | null)[]>();
  for (const day of days) {
    const monday = mondayOf(day.date);
    const row = weeks.get(monday) ?? Array<Day | null>(7).fill(null);
    row[weekdayIndex(day.date)] = day;
    weeks.set(monday, row);
  }
  return [...weeks.entries()]
    .sort(([a], [b]) => (a < b ? -1 : 1))
    .map(([monday, row]) => ({ monday, days: row }));
}
