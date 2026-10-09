// Pure helpers of the 그날 panel: order lines, the 그날 확인 chip and lines, the basis line.
import { marketName, sideName } from '../../api/adapters';
import type { AiJudgment, Basis, DayResponse, JudgmentItem, Order, Stage } from '../../api/types';
import type { RebalanceState } from '../../components/Chips';
import { dayCopy as dc } from '../../copy/day';
import {
  formatFxRate,
  formatKrw,
  formatMonthDay,
  formatPercent,
  formatPpMagnitude,
  formatTime,
  formatUsd,
} from '../../lib/format';

export function prevNextLine(prev: string | null, next: string | null): string | null {
  const parts = [
    prev ? dc.prev(formatMonthDay(prev)) : null,
    next ? dc.next(formatMonthDay(next)) : null,
  ].filter((p): p is string => p !== null);
  return parts.length ? parts.join(' · ') : null;
}

// ── orders ──────────────────────────────────────────────────────────────────

const STAGE_ORDER: Record<Stage['kind'], number> = { sell: 0, fx: 1, buy: 2 };

/** Orders in stage order (매도 → 환전 → 매수), each with the stage it belongs to. */
export function stageOrders(stages: readonly Stage[]): { stage: Stage; order: Order }[] {
  return [...stages]
    .sort((a, b) => STAGE_ORDER[a.kind] - STAGE_ORDER[b.kind])
    .flatMap((stage) => stage.orders.map((order) => ({ stage, order })));
}

/**
 * 원→달러 unless the buys of the same day are in won (then the dollars came back). The order's
 * own `direction` (CONTRACT Order) wins; this is the fallback for an order without it.
 */
export function fxDirection(stages: readonly Stage[]): 'krw-usd' | 'usd-krw' {
  const buys = stages.filter((s) => s.kind === 'buy').flatMap((s) => s.orders);
  const usdBuy = buys.some((o) => o.instrument?.currency === 'USD');
  const krwBuy = buys.some((o) => o.instrument?.currency === 'KRW');
  return krwBuy && !usdBuy && buys.length > 0 ? 'usd-krw' : 'krw-usd';
}

/** '매도 · 한국', '환전 · 원→달러'. */
export function orderHead(order: Order, direction: 'krw-usd' | 'usd-krw'): string {
  if (order.side === 'fx')
    return direction === 'krw-usd' ? dc.stage.fxKrwToUsd : dc.stage.fxUsdToKrw;
  return dc.stage.head(sideName(order.side), marketName(order.market));
}

function qtyText(qty: number): string {
  return Number.isInteger(qty) ? qty.toLocaleString('en-US') : String(qty);
}

function money(value: number, currency: 'KRW' | 'USD', approx: boolean): string {
  const text = currency === 'USD' ? formatUsd(value) : formatKrw(value);
  return approx ? dc.stage.approx(text) : text;
}

/** 'KOSPI200 ETF 5주 · 33,800원', 'BTC 0.0004 · 133,880,000원', '175,000원 → $125.93'. */
export function orderMain(order: Order, direction: 'krw-usd' | 'usd-krw'): string {
  if (order.side === 'fx' && order.fx) {
    const krw = formatKrw(order.fx.krw);
    const usd = formatUsd(order.fx.usd);
    return direction === 'krw-usd' ? `${krw} → ${usd}` : `${usd} → ${krw}`;
  }
  const inst = order.instrument;
  if (!inst) return '';
  const what =
    order.qty === undefined
      ? inst.name
      : inst.kind === 'coin'
        ? dc.stage.units(inst.name, qtyText(order.qty))
        : dc.stage.shares(inst.name, qtyText(order.qty));
  if (order.price === undefined) return what;
  return `${what} · ${money(order.price, inst.currency, order.approx === true)}`;
}

/** '169,000원 · 수수료 25원', '$126.00 · 수수료 $0.13', '환율 1,389.6원'. */
export function orderFoot(order: Order): string {
  if (order.side === 'fx' && order.fx) return dc.stage.rate(formatFxRate(order.fx.rate));
  const approx = order.approx === true;
  const parts: string[] = [];
  if (order.amountUsd !== undefined) parts.push(money(order.amountUsd, 'USD', approx));
  else if (order.amountKrw !== undefined) parts.push(money(order.amountKrw, 'KRW', approx));
  if (order.fee?.usd !== undefined) parts.push(dc.stage.fee(money(order.fee.usd, 'USD', approx)));
  else if (order.fee?.krw !== undefined)
    parts.push(dc.stage.fee(money(order.fee.krw, 'KRW', approx)));
  return parts.join(' · ');
}

export function orderTime(order: Order): string {
  return formatTime(order.at);
}

// ── 그날 확인 ───────────────────────────────────────────────────────────────

type Check = DayResponse['check'];

function holidayWords(markets: Check['holidayMarkets']): string {
  const m = markets ?? [];
  if (m.includes('KR') && m.includes('US')) return dc.check.chip.bothMarkets;
  return m.map((x) => marketName(x)).join('·');
}

/** Result chip: the same judgment as the line under it (완료 조건). null on weekends. */
export function checkChip(check: Check): { state: RebalanceState; label: string } | null {
  switch (check.result) {
    case 'rebalance':
      return { state: 'scheduled', label: dc.check.chip.rebalance };
    case 'in-range':
      return { state: 'inRange', label: dc.check.chip.inRange };
    case 'partial-failed':
      return { state: 'partialFail', label: dc.check.chip.partialFailed };
    case 'failed':
      return { state: 'partialFail', label: dc.check.chip.failed };
    case 'holiday':
      return { state: 'holiday', label: dc.check.chip.holiday(holidayWords(check.holidayMarkets)) };
    case 'quote-wait':
      return { state: 'awaitingQuote', label: dc.check.chip.quoteWait };
    case 'in-progress':
      return { state: 'inProgress', label: dc.check.chip.inProgress };
    case 'withdraw-wait':
      return { state: 'withdrawPending', label: dc.check.chip.withdrawWait };
    case 'no-run':
      return { state: 'holiday', label: dc.check.chip.noRun };
    case 'weekend':
      return null;
  }
}

/** The market(s) still open on a one-market holiday ('미국'). */
export function openMarkets(check: Check): string | null {
  const closed = check.holidayMarkets ?? [];
  const open = (['KR', 'US'] as const).filter((m) => !closed.includes(m));
  return open.length === 1 && open[0] ? marketName(open[0]) : null;
}

/** '지수 반반 KOSPI200 ETF 51.1% · 리밸런싱까지 0.9%p' when the check carries a position. */
export function positionLine(check: Check, ruleName: string | null): string | null {
  if (!check.instrument || check.weight === undefined || check.toThreshold === undefined) {
    return null;
  }
  return dc.check
    .position(
      ruleName ?? '',
      check.instrument.name,
      formatPercent(check.weight),
      formatPpMagnitude(check.toThreshold),
    )
    .trim();
}

/** '전 52.3' / '후 50.2' labels of the band (weights; the band's axis is %p from target). */
export function bandWeights(check: Check): { before: string | null; after: string | null } {
  const band = check.band;
  if (!band || check.weight === undefined) return { before: null, after: null };
  const fmt = (v: number) => (Math.round(v * 10) / 10).toFixed(1);
  const before = band.before === null ? null : fmt(check.weight);
  const after =
    band.after === null || band.before === null
      ? null
      : fmt(check.weight - band.before + band.after);
  return { before, after };
}

// ── 기준 ────────────────────────────────────────────────────────────────────

/** '한국 8/20 종가 · 미국 8/20 종가(ET) · 환율 1,389.6원 08:30'. */
export function basisParts(basis: Basis): string {
  return [
    basis.krClose ? dc.basisKr(formatMonthDay(basis.krClose)) : null,
    basis.usClose ? dc.basisUs(formatMonthDay(basis.usClose)) : null,
    basis.fxRate !== null && basis.fxAt
      ? dc.basisFx(formatFxRate(basis.fxRate), formatTime(basis.fxAt))
      : null,
  ]
    .filter((p): p is string => p !== null)
    .join(' · ');
}

// ── AI 판단 ─────────────────────────────────────────────────────────────────

/** '약 12만 토큰', '약 6천 토큰', '840 토큰'. */
export function tokensLabel(n: number): string {
  if (n >= 10_000) return dc.ai.tokensMan(Math.round(n / 10_000));
  if (n >= 1_000) return dc.ai.tokensCheon(Math.round(n / 1_000));
  return dc.ai.tokens(String(n));
}

/** "두 번 다 '유지'" or "'유지' · '약화'". */
export function votesLabel(votes: AiJudgment['votes']): string | null {
  if (!votes || votes.length === 0) return null;
  const words = votes.map((v) => dc.ai.vote[v]);
  const [a, b] = words;
  if (words.length === 2 && a !== undefined && b !== undefined) {
    return a === b ? dc.ai.twice(a) : dc.ai.votes(a, b);
  }
  return words.join(' · ');
}

/** One item of the 입력 · 출력 lines (CONTRACT JudgmentItem) in words. */
export function judgmentItemText(item: JudgmentItem): string {
  const w = dc.ai.items;
  switch (item.key) {
    case 'instrument':
      return item.instrument.name;
    case 'sold':
      return w.sold(item.instrument.name);
    case 'bought':
      return w.bought(item.instrument.name);
    case 'shock':
      return w.shock(formatMonthDay(item.date), formatPercent(item.value, 1));
    case 'condition':
      return w.condition(item.value);
    case 'filing':
      return w.filing(formatMonthDay(item.date));
    case 'review': {
      const verdict = dc.ai.verdict[item.value];
      return item.months === undefined ? w.review(verdict) : w.reviewMonths(verdict, item.months);
    }
    case 'month':
      return w.month(Number(item.value.slice(5, 7)));
    case 'cost':
      return w.cost(formatPercent(item.value, 2));
    case 'slot-full':
      return w['slot-full'];
    default:
      return w[item.key](item.value);
  }
}

/** The 입력 or 출력 line: items in the server's order, joined with ' · '; null when empty. */
export function judgmentLine(items: readonly JudgmentItem[]): string | null {
  return items.length === 0 ? null : items.map(judgmentItemText).join(' · ');
}
