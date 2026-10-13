// Contract enums → component props and words. One place, so every screen maps them the same way.
import { copy } from '../copy';
import { metricCopy } from '../copy/metrics';
import type { RebalanceState } from '../components/Chips';
import type { CalendarState as CellState, EventKind as MarkerKind } from '../components/Markers';
import {
  MINUS,
  endsWithConsonant,
  formatDateTime,
  formatKrw,
  formatMonthDay,
  formatNumber,
  formatPercent,
  formatTime,
  formatUsd,
  kstDateKey,
} from '../lib/format';
import type {
  Banner,
  CalendarState,
  EventKind,
  FxSuggestion,
  Margin,
  Market,
  MetricRef,
  NewMoneyWait,
  RuleStatus,
  Side,
} from './types';

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
    case 'fx-suggest':
      return { state: 'fxSuggest', label: copy.rebalance.fxSuggest };
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

// ── AI rule metrics ──────────────────────────────────────────────────────────

/** '이익률', 'AI 매출', '지상방산 수주잔고' — the server sends the key and the company's word. */
export function metricName(metric: MetricRef): string {
  const name = metricCopy.names[metric.key];
  if (typeof name === 'string') return name;
  const param = metric.param?.trim();
  if (param) return name(param);
  return metric.key === 'guidance' ? metricCopy.noParam.guidance : name(metricCopy.noParam.segment);
}

/** One decimal under 100 of a unit ('3.1조', '45.5억'), whole above ('4,500억'); no '.0'. */
function scaled(abs: number, scale: number, unit: string, whole = false): string {
  const value = abs / scale;
  const text = formatNumber(value, whole || value >= 100 ? 0 : 1);
  return `${text.endsWith('.0') ? text.slice(0, -2) : text}${unit}`;
}

function compactKrw(abs: number): string {
  const u = metricCopy.units;
  if (abs >= 1e12) return scaled(abs, 1e12, u.jo);
  if (abs >= 1e8) return scaled(abs, 1e8, u.eok);
  if (abs >= 1e4) return scaled(abs, 1e4, u.man, true);
  return formatKrw(abs);
}

function compactUsd(abs: number): string {
  const u = metricCopy.units;
  if (abs >= 1e9) return `$${scaled(abs, 1e9, u.usdBillion)}`;
  if (abs >= 1e6) return `$${scaled(abs, 1e6, u.usdMillion)}`;
  return formatUsd(abs);
}

/**
 * What is left to the line (CONTRACT Margin): '2.3%p', '2.1%', '3.1조', '$350M', '0.12x',
 * '2분기', '3개월', '1년'; a count is the bare number.
 */
export function marginText(margin: Margin): string {
  const { value } = margin;
  const u = metricCopy.units;
  switch (margin.unit) {
    case 'pp':
      return `${formatNumber(value, 1)}${copy.units.pp}`;
    case 'pct':
      return formatPercent(value, 1);
    case 'KRW':
      return `${value < 0 ? MINUS : ''}${compactKrw(Math.abs(value))}`;
    case 'USD':
      return `${value < 0 ? MINUS : ''}${compactUsd(Math.abs(value))}`;
    case 'x':
      return `${formatNumber(value, 2)}${u.times}`;
    case 'count':
      return formatNumber(value);
    case 'quarter':
      return `${formatNumber(value)}${u.quarter}`;
    case 'month':
      return `${formatNumber(value)}${u.month}`;
    case 'year':
      return `${formatNumber(value)}${u.year}`;
  }
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

// ── the live ledger's money as deposited (D47·D48) ───────────────────────────────────

const pct = (value: number): string => formatNumber(value, Number.isInteger(value) ? 0 : 1);

/** '약 5,000,000원을 달러로 바꾸면 50:50' · '약 $1,437을 원화로 바꾸면 50:50'. */
export function fxSuggestionText(s: FxSuggestion): string {
  const m = copy.liveMoney;
  const toUsd = s.direction === 'krw-usd';
  const amount = toUsd ? formatKrw(s.krw) : `$${formatNumber(Math.round(s.usd))}`;
  const particle = endsWithConsonant(amount) ? m.objectAfterConsonant : m.objectAfterVowel;
  return m.suggestion(
    `${amount}${particle}`,
    toUsd ? m.toUsd : m.toKrw,
    pct(s.target.kr),
    pct(s.target.us),
  );
}

/** '지금 한국 100 : 미국 0'. */
export function fxMixText(s: FxSuggestion): string {
  return copy.liveMoney.mix(pct(s.now.kr), pct(s.now.us));
}

/** '새로 들어온 돈 3,000,000원 · $718.39 · 다음 거래일 08:30부터 써요'. */
export function newMoneyText(n: NewMoneyWait): string {
  const amounts = [
    ...(n.krw > 0 ? [formatKrw(n.krw)] : []),
    ...(n.usd > 0 ? [formatUsd(n.usd)] : []),
  ];
  return copy.liveMoney.newMoney(amounts.join(' · '), formatTime(n.from));
}
