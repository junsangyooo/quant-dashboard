// Contract values → the words of the 계획 screens (and the 계획 card on 자산). Pure functions:
// the screens only place their results. Numbers use lib/format; dates have no zero padding.
import { marketName, ruleStatusChip, sideName } from '../../api/adapters';
import type {
  Instrument,
  Market,
  NextAction,
  Order,
  RuleCard,
  RuleRef,
  RuleStatus,
  ScheduleItem,
  Stage,
} from '../../api/types';
import type { LogoTone } from '../../components/Badges';
import { planCopy } from '../../copy/plan';
import {
  formatDateTime,
  formatFxRate,
  formatKrw,
  formatMonthDay,
  formatMonthDayWeekday,
  formatNumber,
  formatPercent,
  formatPpMagnitude,
  formatTime,
  formatUsd,
  kstDateKey,
} from '../../lib/format';
import { reviewAtOf } from './proposed';

/** '[예시] 종목 모멘텀' for example rules. */
export function ruleName(rule: RuleRef): string {
  return rule.example ? planCopy.exampleRule(rule.name) : rule.name;
}

/** Status chip label; AI rules use their own words for the same chips. */
export function statusLabel(status: RuleStatus, ai = false): string {
  return ruleStatusChip(status, ai).label;
}

/** '한국' · '한국·미국'. */
export function marketsText(markets: readonly Market[]): string {
  return markets.map((m) => marketName(m)).join('·');
}

/** '오늘 22:30' on the day of `now`, '10/8 22:30' otherwise. */
export function whenText(at: string, now: string | null): string {
  if (now !== null && kstDateKey(at) === kstDateKey(now)) {
    return `${planCopy.next.today} ${formatTime(at)}`;
  }
  return formatDateTime(at);
}

export interface NextTextOptions {
  /** The clock of the state (shell `now`); decides '오늘'. */
  now: string | null;
  /**
   * line: the hero plan line (자산) and the plan card status line (계획);
   * card: the 계획 card on 자산 — shorter first-order words, and the waiting amount for 출금 대기.
   */
  variant?: 'line' | 'card' | undefined;
  /** 출금 대기 amount (자산 card: '500,425원 · 10/12까지 · 주문 0건'). */
  withdrawKrw?: number | undefined;
  /** 휴장: append '· 다음 확인 …' (계획 status line). */
  withNextCheck?: boolean | undefined;
}

/** The next action after a status chip ('오늘 22:30 미국 매수 2주'). */
export function nextActionText(next: NextAction, options: NextTextOptions): string {
  const { now, variant = 'line' } = options;
  const n = planCopy.next;
  switch (next.kind) {
    case 'order':
      return n.order(
        whenText(next.at, now),
        marketName(next.market),
        sideName(next.side),
        next.qty,
      );
    case 'first-check':
      return n.firstCheck(
        variant === 'line'
          ? `${formatMonthDayWeekday(next.at)} ${formatTime(next.at)}`
          : formatDateTime(next.at),
      );
    case 'first-order': {
      const head = n.firstOrder(whenText(next.at, now));
      return variant === 'card'
        ? head
        : `${head} · ${n.firstOrderDetail(marketName(next.market), sideName(next.side), next.count)}`;
    }
    case 'retry':
      return n.retry(formatDateTime(next.at), marketName(next.market), sideName(next.side));
    case 'todo':
      return n.todo;
    case 'withdraw-wait':
      return variant === 'card' && options.withdrawKrw !== undefined
        ? n.withdrawCard(formatKrw(options.withdrawKrw), formatMonthDay(next.until))
        : n.withdrawWait(formatMonthDay(next.until));
    case 'holiday': {
      const text = n.holiday(marketsText(next.markets));
      return options.withNextCheck
        ? `${text} · ${n.nextCheck(formatDateTime(next.nextCheckAt))}`
        : text;
    }
    case 'quote-wait':
      return `${quoteWaitBasis(next)} · ${n.ordersZero}`;
    case 'next-check': {
      const text = n.nextCheck(formatDateTime(next.at));
      const review = reviewAtOf(next);
      return review === null ? text : `${text} · ${n.review(formatMonthDay(review))}`;
    }
  }
}

/** '미국 시세 10/2 기준' (the caption under a hollow gauge). */
export function quoteWaitBasis(next: Extract<NextAction, { kind: 'quote-wait' }>): string {
  return next.market === 'FX'
    ? planCopy.next.fxQuoteWait(formatMonthDay(next.basisDate))
    : planCopy.next.quoteWait(marketName(next.market), formatMonthDay(next.basisDate));
}

/** '자산의 81.1%' parts; null pct means the share is hidden (첫 확인 전 · 첫 체결 전). */
export function shareParts(share: { pct: number; target: number | null }): {
  pct: string | null;
  target: string | null;
} {
  return {
    pct: share.pct > 0 ? formatPercent(share.pct) : null,
    target: share.target === null ? null : `${formatNumber(share.target)}%`,
  };
}

/** The small basis line under a rule card. */
export function basisLineText(card: RuleCard, metricTableAt: string | null): string {
  const b = card.basisLine;
  const c = planCopy.basis;
  if (card.gauge.kind === 'sell-condition') {
    return metricTableAt === null
      ? c.sellCondition
      : `${c.sellCondition} · ${c.metricTable(formatMonthDay(metricTableAt))}`;
  }
  if (b.staleMarket !== null && b.staleBasisDate !== null) {
    return [c.head, c.stale(marketName(b.staleMarket), formatMonthDay(b.staleBasisDate))].join(
      ' · ',
    );
  }
  const parts: string[] = [c.head, c.krw];
  if (b.pendingBuyIncluded) parts.push(c.pendingBuy);
  if (b.withdrawExcluded) parts.push(c.withdrawExcluded);
  if (b.fxRate !== null && b.fxAt !== null) {
    parts.push(c.fx(formatFxRate(b.fxRate), formatTime(b.fxAt)));
  }
  return parts.join(' · ');
}

/** '리밸런싱까지 1.8%p'. */
export function toRebalanceText(pp: number): string {
  return planCopy.gauge.toRebalance(formatPpMagnitude(pp));
}

// ── orders and stages ────────────────────────────────────────────────────────

function orderAmount(order: Order): string {
  if (order.amountKrw !== undefined) return formatKrw(order.amountKrw);
  if (order.amountUsd !== undefined) {
    const usd = formatUsd(order.amountUsd);
    return order.approx ? planCopy.order.approx(usd) : usd;
  }
  return '';
}

function quantity(order: Order): string {
  const qty = order.qty ?? 0;
  if (order.instrument?.kind === 'coin') return `${String(qty)} ${order.instrument.name}`;
  return planCopy.order.shares(qty);
}

/**
 * One order line of a stage card: 'KOSPI200 ETF 매도 5주 · 181,900원',
 * '173,000원 → $125.30 · 1,380.6원', 'S&P 500 ETF 매수 2주 · 약 $124.80', and for a failure
 * 'S&P 500 ETF 매수 2주 · 시세 응답 없음'.
 */
export function orderText(order: Order): string {
  if (order.side === 'fx' && order.fx) {
    const krw = formatKrw(order.fx.krw);
    const usd = formatUsd(order.fx.usd);
    return planCopy.order.fx(
      order.approx ? planCopy.order.approx(krw) : krw,
      order.approx ? planCopy.order.approx(usd) : usd,
      formatFxRate(order.fx.rate),
    );
  }
  const name = order.instrument?.name ?? '';
  const side = sideName(order.side);
  if (order.status === 'failed' && order.failure) {
    return planCopy.order.failedTrade(
      name,
      side,
      quantity(order),
      planCopy.order.reason[order.failure.reason],
    );
  }
  return planCopy.order.trade(name, side, quantity(order), orderAmount(order));
}

/** The time printed at the end of an order line (failed orders keep their date). */
export function orderTime(order: Order): string {
  return order.status === 'failed' ? formatDateTime(order.at) : formatTime(order.at);
}

/** The fill label of a filled stage ('모의 체결' / '실제 체결'); pending cards have none. */
export function stageFill(stage: Stage): string | null {
  if (stage.status !== 'done') return null;
  const fill = stage.orders.find((o) => o.fill !== undefined)?.fill;
  return fill ? planCopy.stage.fill[fill] : null;
}

/** A failed stage's retry time ('다시 10/8 22:30') or '직접 할 일'. */
export function stageFailure(stage: Stage): { retryAt: string | null; manual: boolean } | null {
  if (stage.status !== 'failed') return null;
  const failed = stage.orders.find((o) => o.status === 'failed');
  const retryAt = failed?.failure?.retryAt ?? null;
  return { retryAt, manual: retryAt === null || failed?.failure?.manual === true };
}

// ── schedule ─────────────────────────────────────────────────────────────────

export interface ScheduleText {
  /** Small line above the title (time, date or '원화 현금'). */
  caption: string | null;
  title: string;
  /** Amount chip after the title ('56,548원'). */
  chip: string | null;
  /** A second line under the title (출금 대기). */
  note: string | null;
}

export function scheduleItemText(item: ScheduleItem): ScheduleText {
  const s = planCopy.schedule;
  switch (item.kind) {
    case 'next-check':
      return { caption: formatDateTime(item.at), title: s.nextCheck, chip: null, note: null };
    case 'holiday':
      return {
        caption: formatMonthDay(item.date),
        title: s.holiday(marketsText(item.markets)),
        chip: null,
        note: null,
      };
    case 'retry':
      return {
        caption: formatDateTime(item.at),
        title: s.retry(marketName(item.market), sideName(item.side)),
        chip: null,
        note: null,
      };
    case 'sub-share-cash':
      return { caption: s.krwCash, title: s.subShare, chip: formatKrw(item.krw), note: null };
    case 'withdraw-wait':
      return {
        caption: null,
        title: s.withdrawWait(formatKrw(item.krw), formatMonthDay(item.until)),
        chip: null,
        note: s.withdrawAfter,
      };
    case 'new-cash':
      return { caption: null, title: s.newCash(formatKrw(item.krw)), chip: null, note: null };
    case 'first-check':
      return {
        caption: null,
        title: s.firstCheck(formatDateTime(item.at)),
        chip: null,
        note: null,
      };
    case 'monthly-review':
      return { caption: formatDateTime(item.at), title: s.monthlyReview, chip: null, note: null };
    case 'discovery':
      return { caption: formatDateTime(item.at), title: s.discovery, chip: null, note: null };
    case 'earnings':
      return {
        caption: formatMonthDay(item.date),
        title: s.earnings(item.instrument.name),
        chip: null,
        note: null,
      };
  }
}

// ── logos ────────────────────────────────────────────────────────────────────

/** Ring color of each instrument by first appearance (Figma: K2 · SP · 삼 · NV · B = cat-1…5). */
export function toneMap(instruments: readonly Instrument[]): Map<string, LogoTone> {
  const tones = new Map<string, LogoTone>();
  for (const inst of instruments) {
    if (!tones.has(inst.id)) tones.set(inst.id, ((tones.size % 5) + 1) as LogoTone);
  }
  return tones;
}

/** 국기 of an instrument's market. */
export function countryOf(market: Market): 'kr' | 'us' | 'coin' {
  return market === 'KR' ? 'kr' : market === 'US' ? 'us' : 'coin';
}
