// Contract enums → component props and words. One place, so every screen maps them the same way.
import { copy } from '../copy';
import type { RebalanceState } from '../components/Chips';
import type { CalendarState as CellState, EventKind as MarkerKind } from '../components/Markers';
import { formatDateTime, formatMonthDay, formatTime, kstDateKey } from '../lib/format';
import type { Banner, CalendarState, EventKind, Market, RuleStatus, Side } from './types';

/** Status chip of a rule. AI rules use other words for the same seven chips. */
export function ruleStatusChip(
  status: RuleStatus,
  ai = false,
): { state: RebalanceState; label: string } {
  switch (status) {
    case 'in-range':
      return { state: 'inRange', label: copy.rebalance.inRange };
    case 'scheduled':
      return { state: 'scheduled', label: copy.rebalance.scheduled };
    case 'in-progress':
      return {
        state: 'inProgress',
        label: ai ? copy.ruleStatusAi.inProgress : copy.rebalance.inProgress,
      };
    case 'partial-failed':
      return { state: 'partialFail', label: copy.rebalance.partialFail };
    case 'holiday':
      return { state: 'holiday', label: copy.rebalance.holiday };
    case 'quote-wait':
      return { state: 'awaitingQuote', label: copy.rebalance.awaitingQuote };
    case 'withdraw-wait':
      return { state: 'withdrawPending', label: copy.rebalance.withdrawPending };
    case 'hold':
      return { state: 'inRange', label: copy.ruleStatusAi.hold };
    case 'sell-scheduled':
      return { state: 'scheduled', label: copy.ruleStatusAi.sellScheduled };
    case 'buy-scheduled':
      return { state: 'scheduled', label: copy.ruleStatusAi.buyScheduled };
  }
}

/** Event marker (Figma 표식/사건); null for AI events, which have no marker yet. */
export function markerKind(kind: EventKind): MarkerKind | null {
  switch (kind) {
    case 'start':
      return 'start';
    case 'rebalance':
      return 'rebalance';
    case 'partial-failed':
      return 'partialFail';
    case 'in-progress':
      return 'rebalanceInProgress';
    case 'check-failed':
      return 'runFail';
    case 'dividend':
      return 'dividend';
    case 'deposit':
      return 'deposit';
    case 'withdrawal':
      return 'withdraw';
    case 'live-on':
    case 'live-off':
      return 'liveOn';
    case 'discovery':
    case 'ai-buy':
    case 'ai-sell':
    case 'ai-check':
    case 'monthly-review':
      return null;
  }
}

/** Word for an event ('리밸런싱', '배당' …). */
export function eventName(kind: EventKind): string {
  switch (kind) {
    case 'start':
      return copy.event.start;
    case 'rebalance':
      return copy.event.rebalance;
    case 'partial-failed':
      return copy.event.partialFail;
    case 'in-progress':
      return copy.event.rebalanceInProgress;
    case 'check-failed':
      return copy.event.runFail;
    case 'dividend':
      return copy.event.dividend;
    case 'deposit':
      return copy.event.deposit;
    case 'withdrawal':
      return copy.event.withdraw;
    case 'live-on':
      return copy.event.liveOn;
    case 'live-off':
      return copy.event.liveOff;
    case 'discovery':
      return copy.event.discovery;
    case 'ai-buy':
      return copy.event.aiBuy;
    case 'ai-sell':
      return copy.event.aiSell;
    case 'ai-check':
      return copy.event.aiCheck;
    case 'monthly-review':
      return copy.event.monthlyReview;
  }
}

/** Calendar cell (Figma 칸/실행 달력). */
export function calendarCell(state: CalendarState): CellState {
  switch (state) {
    case 'normal':
      return 'ok';
    case 'rebalance':
      return 'rebalance';
    case 'in-progress':
      return 'rebalanceInProgress';
    case 'partial-failed':
      return 'partialFail';
    case 'failed':
      return 'fail';
    case 'no-run':
      return 'noRun';
    case 'holiday-one':
      return 'oneMarketHoliday';
    case 'holiday-both':
      return 'holiday';
    case 'quote-wait':
      return 'awaitingQuote';
    case 'future':
      return 'future';
    case 'before-record':
      return 'beforeRecord';
  }
}

export function marketName(market: Market | 'FX'): string {
  return copy.market[market];
}

export function sideName(side: Side): string {
  return copy.side[side];
}

/** A retry time on the same KST day reads '09:30'; on another day '10/8 22:30'. */
function retryTime(at: string, retryAt: string): string {
  return kstDateKey(at) === kstDateKey(retryAt) ? formatTime(retryAt) : formatDateTime(retryAt);
}

/** The banner's fact line, e.g. '미국 시세 10/2 기준 · 2거래일째 갱신 없음'. */
export function bannerText(banner: Banner): string {
  switch (banner.kind) {
    case 'stale':
      return banner.market === 'FX'
        ? copy.banner.staleFx(formatMonthDay(banner.basisDate), banner.tradingDays)
        : copy.banner.stale(
            marketName(banner.market),
            formatMonthDay(banner.basisDate),
            banner.tradingDays,
          );
    case 'partial-retry':
      return copy.banner.partialRetry(
        formatMonthDay(banner.date),
        marketName(banner.market),
        sideName(banner.side),
        retryTime(banner.date, banner.retryAt),
      );
    case 'partial-todo':
      return copy.banner.partialTodo(
        formatMonthDay(banner.date),
        marketName(banner.market),
        sideName(banner.side),
        copy.banner.todoReason[banner.reason],
      );
    case 'check-failed':
      return copy.banner.checkFailed(
        formatDateTime(banner.at),
        banner.retryAt === null ? null : retryTime(banner.at, banner.retryAt),
      );
    case 'cancel-failed':
      return copy.banner.cancelFailed(marketName(banner.market), sideName(banner.side));
    case 'push-undelivered':
      return copy.banner.pushUndelivered(banner.days);
  }
}

const LINK_PATH = { health: '/health', plan: '/plan', mode: '/mode', account: '/account' } as const;
export type BannerPage = keyof typeof LINK_PATH;

/**
 * Where the banner's link goes. It never points at the page the user is on: on 계획 the
 * partial-failure link goes to 작동 instead (인계 '그림에 남은 작은 불일치' 10); elsewhere it hides.
 */
export function bannerLink(
  banner: Banner,
  currentPath: string,
): { to: string; label: string } | null {
  let target: BannerPage = banner.link;
  if (currentPath === LINK_PATH[target]) {
    if (target !== 'plan') return null;
    target = 'health';
  }
  return { to: LINK_PATH[target], label: copy.banner.link[target] };
}
