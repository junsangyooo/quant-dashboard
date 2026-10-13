// ModeResponse → the words SCR-MODE shows. Pure functions (unit-tested); strings come from
// copy/mode.ts, numbers from lib/format. `now` is the shell's server time.
import { modeCopy as t } from '../../copy/mode';
import { healthCopy } from '../../copy/health';
import { marketName, sideName } from '../../api/adapters';
import { tossCause } from '../Health/text';
import type { Instrument, Market, ModeResponse, Order, Stage } from '../../api/types';
import {
  endsWithConsonant,
  formatDateTime,
  formatFxRate,
  formatKrw,
  formatMonthDay,
  formatMonthDayWeekday,
  formatNumber,
  formatPercentSigned,
  formatTime,
  formatUsd,
  kstDateKey,
} from '../../lib/format';

export type Mode = ModeResponse;
export type Preflight = NonNullable<ModeResponse['preflight']>[number];
export type Preview = NonNullable<ModeResponse['preview']>;
export type OkPreview = Extract<Preview, { kind: 'ok' }>;

/** '08:30' on the same KST day as `now`, '10/8 09:10' otherwise. */
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

/** Whole dollars for approximate sums: 3399.6 → '$3,400'. */
export function usdWhole(value: number): string {
  return `$${formatNumber(Math.round(value))}`;
}

const hasFinalConsonant = endsWithConsonant;

/** Topic particle after a figure or word: '$125.67은', '85,964원은', '시세는'. */
export function topicParticle(text: string): string {
  return hasFinalConsonant(text) ? t.particles.topicAfterConsonant : t.particles.topicAfterVowel;
}

/** Subject particle: '미국 시세가', '환율이'. */
export function withSubject(word: string): string {
  return `${word}${hasFinalConsonant(word) ? t.particles.subjectAfterConsonant : t.particles.subjectAfterVowel}`;
}

/** Display name of a data source id or market code from facts ('us-quotes', 'US', 'FX'). */
export function sourceName(source: string | number | undefined): string | null {
  switch (str(source)) {
    case 'kr-quotes':
    case 'KR':
      return healthCopy.sources.names['kr-quotes'];
    case 'us-quotes':
    case 'US':
      return healthCopy.sources.names['us-quotes'];
    case 'fx':
    case 'FX':
      return healthCopy.sources.names.fx;
    case 'toss-link':
      return healthCopy.sources.names['toss-link'];
    case 'toss-balance':
      return healthCopy.sources.names['toss-balance'];
    case 'push-devices':
      return healthCopy.sources.names['push-devices'];
    default:
      return null;
  }
}

/** Short legend name: ETFs drop the trailing ' ETF' ('KOSPI200 ETF' → 'KOSPI200'). */
export function shortName(instrument: Instrument): string {
  return instrument.kind === 'etf' ? instrument.name.replace(/\s*ETF$/i, '') : instrument.name;
}

export function signedPct(value: number, digits = 2): string {
  return formatPercentSigned(value, digits);
}

// ── 지금 모드 ────────────────────────────────────────────────────────────────

export function modeLine(m: Mode): string {
  if (m.mode === 'live') return t.line.live;
  return m.liveOff ? t.line.paperAfterLive : t.line.paper;
}

export function periodChip(m: Mode): string | null {
  if (m.mode === 'live' && m.live) return t.liveSince(formatMonthDay(m.live.since), m.live.days);
  if (m.liveOff)
    return t.liveOff(
      formatMonthDay(m.liveOff.from),
      formatMonthDay(m.liveOff.to),
      formatTime(m.liveOff.offAt),
    );
  return null;
}

// ── 켜기 전 점검 ─────────────────────────────────────────────────────────────

export type CheckState = 'pass' | 'blocked' | 'warn';

export interface PreflightRowView {
  id: Preflight['id'];
  state: CheckState;
  name: string;
  description: string;
}

export function preflightState(item: Preflight): CheckState {
  if (item.warn) return 'warn';
  return item.ok ? 'pass' : 'blocked';
}

export function preflightRow(item: Preflight, now: string | null): PreflightRowView {
  const f = item.facts;
  const state = preflightState(item);
  const same = item.sameCauseAs ? ` · ${t.preflight.sameCause}` : '';
  switch (item.id) {
    case 'health': {
      if (item.ok) {
        const at = str(f.lastCheckAt);
        return {
          id: item.id,
          state,
          name: t.preflight.healthOk,
          description: at ? t.preflight.lastCheck(formatDateTime(at)) : '',
        };
      }
      const cause = sourceName(f.source);
      return {
        id: item.id,
        state,
        name: t.preflight.health,
        description: cause
          ? t.preflight.healthCause(num(f.count) ?? 1, t.preflight.staleCause(cause)) + same
          : t.preflight.blocked + same,
      };
    }
    case 'toss-link': {
      const date = str(f.expiresAt);
      const days = num(f.daysLeft);
      const cause = tossCause(f.cause);
      const checked = str(f.checkedAt);
      const account = str(f.account);
      let description: string;
      if (!item.ok && cause) {
        // 3단계: why the link cannot carry orders, and what to do (the to-do card's second line).
        description = t.preflight.tossLinkCause(
          healthCopy.toss.cause[cause],
          healthCopy.toss.lines[cause][1],
        );
      } else if (date && days !== undefined) {
        description = t.preflight.tossLinkLine(formatMonthDay(date), days);
      } else if (item.ok && account && checked) {
        description = t.preflight.tossLinkOk(account, atTime(checked, now));
      } else {
        description = item.ok ? '' : t.preflight.blocked;
      }
      return { id: item.id, state, name: t.preflight.tossLink, description: description + same };
    }
    case 'freshness': {
      if (item.ok) {
        const b = str(f.balanceAt);
        const p = str(f.priceAt);
        const x = str(f.fxAt);
        return {
          id: item.id,
          state,
          name: t.preflight.freshness,
          description:
            b && p && x
              ? t.preflight.freshLine(atTime(b, now), atTime(p, now), atTime(x, now))
              : '',
        };
      }
      const source = sourceName(f.source);
      const date = str(f.basisDate);
      return {
        id: item.id,
        state,
        name: t.preflight.freshness,
        description:
          source && date
            ? t.preflight.staleLine(source, formatMonthDay(date)) + same
            : t.preflight.blocked + same,
      };
    }
    case 'push': {
      const n = num(f.devices) ?? 0;
      const at = str(f.lastDelivery);
      return {
        id: item.id,
        state,
        name: t.preflight.push,
        description:
          n > 0 && at ? t.preflight.pushLine(n, formatDateTime(at)) : t.preflight.pushNone,
      };
    }
  }
}

/** Distinct causes of ✕ rows (rows naming another row's cause count once) and their names. */
export function blockingCauses(preflight: Mode['preflight']): { count: number; names: string[] } {
  const rows = (preflight ?? []).filter((r) => preflightState(r) === 'blocked');
  const ids = new Set(rows.map((r) => r.id));
  const causes = rows.filter((r) => !(r.sameCauseAs && ids.has(r.sameCauseAs as Preflight['id'])));
  const names = causes
    .map((r) =>
      r.id === 'toss-link'
        ? t.preflight.tossLink
        : r.id === 'push'
          ? t.preflight.push
          : sourceName(r.facts.source),
    )
    .filter((n): n is string => n !== null);
  return { count: causes.length, names: [...new Set(names)] };
}

/** Red line under a closed 켜기 card, or null when it may be turned on. */
export function blockedLine(m: Mode): string | null {
  if (m.canTurnOn.ok) return null;
  switch (m.canTurnOn.cause) {
    case 'checks': {
      const { count, names } = blockingCauses(m.preflight);
      return names.length > 0
        ? t.turnOn.blockedChecks(Math.max(1, count), names.join(', '))
        : t.turnOn.blockedChecksCount(Math.max(1, count));
    }
    case 'preview':
      return t.turnOn.blockedPreview;
    case 'live-not-available':
      return t.turnOn.blockedNotAvailable;
    case 'cancel-pending':
      return t.turnOn.blockedCancelPending;
  }
}

/** The source the preview waits for, from the ✕ checks ('미국 시세'). */
export function waitingSource(preflight: Mode['preflight']): string | null {
  for (const row of preflight ?? []) {
    if (preflightState(row) !== 'blocked') continue;
    const name = sourceName(row.facts.source);
    if (name) return name;
  }
  return null;
}

// ── 첫 주문 미리보기 ─────────────────────────────────────────────────────────

const MARKET_ORDER: readonly Market[] = ['KR', 'US', 'COIN'];

function byMarket(orders: readonly Order[]): { market: Market; orders: Order[] }[] {
  return MARKET_ORDER.map((market) => ({
    market,
    orders: orders.filter((o) => o.market === market),
  })).filter((g) => g.orders.length > 0);
}

export interface StageView {
  kind: 'sell' | 'buy';
  label: string;
  time: string;
  body: string[];
  amount: string;
}

function qty(value: number | undefined): string {
  if (value === undefined) return '';
  return Number.isInteger(value) ? formatNumber(value) : String(value);
}

function sumKrw(orders: readonly Order[]): number {
  return orders.reduce((s, o) => s + (o.amountKrw ?? 0), 0);
}

function sumUsd(orders: readonly Order[]): number {
  return orders.reduce((s, o) => s + (o.amountUsd ?? 0), 0);
}

/** A preview leg (매도 · n건 / 매수 · n건). */
export function stageView(stage: PreviewStage, now: string | null): StageView {
  const groups = byMarket(stage.orders);
  const count = stage.orders.length;
  const time =
    groups.length > 1
      ? groups
          .map((g) =>
            t.preview.marketTime(
              marketName(g.market),
              formatTime(
                g.orders.reduce((a, o) => (o.at < a ? o.at : a), g.orders[0]?.at ?? stage.at),
              ),
            ),
          )
          .join(' · ')
      : t.preview.expected(atTime(stage.at, now));
  const body = groups.map((g) => {
    const names = g.orders
      .map((o) => t.preview.shares(o.instrument?.name ?? '', qty(o.qty)))
      .join(' · ');
    return groups.length > 1 ? t.preview.marketLine(marketName(g.market), names) : names;
  });
  const krw = sumKrw(stage.orders);
  const usd = sumUsd(stage.orders);
  const amounts = [
    ...(krw > 0 ? [t.preview.approx(formatKrw(krw))] : []),
    ...(usd > 0 ? [t.preview.approx(usdWhole(usd))] : []),
  ];
  return {
    kind: stage.kind,
    label: stage.kind === 'buy' ? t.preview.stage.buy(count) : t.preview.stage.sell(count),
    time,
    body,
    amount: amounts.join(' · '),
  };
}

/** A stage of the turn-on preview: the live ledger never converts (D47), so sell or buy. */
export type PreviewStage = Stage & { kind: 'sell' | 'buy' };

/** Stages in 매도 → 매수 order; a stage with no orders (or a conversion) is not drawn. */
export function visibleStages(stages: readonly Stage[]): PreviewStage[] {
  const rank = { sell: 0, buy: 1 } as const;
  return stages
    .filter((s): s is PreviewStage => s.kind !== 'fx' && s.orders.length > 0)
    .sort((a, b) => rank[a.kind] - rank[b.kind]);
}

export function currentItems(p: OkPreview): string[] {
  return p.current.map((c) =>
    c.label === 'krw-cash'
      ? t.preview.krwCash(formatKrw(c.krw))
      : c.label === 'usd-cash'
        ? t.preview.usdCash(formatKrw(c.krw))
        : `${c.instrument?.name ?? ''} ${formatKrw(c.krw)}`,
  );
}

export function basisChips(p: OkPreview, now: string | null): string[] {
  return [
    t.preview.basisBalance(atTime(p.basis.balanceAt, now)),
    t.preview.basisPrice(atTime(p.basis.priceAt, now)),
    t.preview.basisFx(formatFxRate(p.basis.fxRate), atTime(p.basis.fxAt, now)),
  ];
}

export function outsideLine(o: OkPreview['outside'][number]): string {
  return t.preview.outside(o.instrument.name, String(o.qty), formatKrw(o.approxKrw));
}

export function notComputableLines(
  p: Extract<Preview, { kind: 'not-computable' }>,
  preflight: Mode['preflight'],
): { chip: string; note: string } {
  const source = p.cause === 'stale' ? waitingSource(preflight) : null;
  return {
    chip: t.preview.notComputable(formatDateTime(p.at)),
    note:
      p.cause === 'stale'
        ? t.preview.recomputeWhen(withSubject(source ?? t.preview.quotes))
        : t.preview.recomputeLater,
  };
}

// ── 실전 끄기 · 취소 안 된 주문 ─────────────────────────────────────────────

export function orderAmount(o: Order): string {
  if (o.amountUsd !== undefined) return formatUsd(o.amountUsd);
  if (o.amountKrw !== undefined) return formatKrw(o.amountKrw);
  return '';
}

export function cancelHead(o: Order, now: string | null): string {
  return t.turnOff.orderHead(sideName(o.side), marketName(o.market), atTime(o.at, now));
}

export function cancelBody(o: Order): string {
  return t.turnOff.orderBody(o.instrument?.name ?? '', qty(o.qty), orderAmount(o));
}

export function cancelFailedRow(o: Order): string {
  return t.cancelFailed.order(
    sideName(o.side),
    marketName(o.market),
    o.instrument?.name ?? '',
    qty(o.qty),
    orderAmount(o),
  );
}

/** '달러 현금 $125.67은 계좌에 남아요'. */
export function cashStaysLine(currency: 'USD' | 'KRW', amount: number): string {
  const figure = currency === 'USD' ? formatUsd(amount) : formatKrw(amount);
  return t.turnOff.cashStays(
    currency === 'USD' ? t.turnOff.usd : t.turnOff.krw,
    `${figure}${topicParticle(figure)}`,
  );
}

// ── 성적 ─────────────────────────────────────────────────────────────────────

export function firstCheckText(at: string): string {
  return `${formatMonthDayWeekday(at)} ${formatTime(at)}`;
}
