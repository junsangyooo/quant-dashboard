// 구성 (Figma '구성'): 100% bar (출금 대기 = hatched end segment + a line under it) → 묶어 보기 chips
// (only criteria with two or more groups; the choice stays on this device) → group heads
// ('● 지수 반반 · 자산의 81.1% · 목표 80%') → instrument and cash rows. Row % is of all assets.
// 390: a holding row opens '115주 · 평균 32,005원'; 1440: that line is always there.
import clsx from 'clsx';
import { useState } from 'react';
import type { CompRow, Composition, HomeResponse, Instrument } from '../../api/types';
import {
  CompositionBar,
  type CompositionSegment,
  type SegmentTone,
} from '../../charts/CompositionBar';
import { Flag, InitialLogo, KindBadge, type LogoTone } from '../../components/Badges';
import { InfoChip, PeriodChip } from '../../components/Chips';
import { StaleMark } from '../../components/State';
import { copy } from '../../copy';
import { homeCopy } from '../../copy/home';
import {
  formatKrw,
  formatKrwEok,
  formatMonthDay,
  formatNumber,
  formatPercent,
  formatPercentSigned,
  formatTime,
  formatUsd,
  pnlDirection,
} from '../../lib/format';
import { countryOf, ruleName } from '../Plan/words';
import styles from './Home.module.css';

export type GroupKey = Composition['groupBy'][number];

const GROUP_KEYS: readonly GroupKey[] = ['instrument', 'kind', 'country', 'currency', 'rule'];
const STORE_KEY = 'quant.home.groupBy';

function isGroupKey(v: unknown): v is GroupKey {
  return typeof v === 'string' && (GROUP_KEYS as readonly string[]).includes(v);
}

/** The 묶어 보기 choice of this device (localStorage; absent in private windows). */
export function readGroupChoice(): GroupKey | null {
  try {
    const v = window.localStorage.getItem(STORE_KEY);
    return isGroupKey(v) ? v : null;
  } catch {
    return null;
  }
}

function saveGroupChoice(v: GroupKey): void {
  try {
    window.localStorage.setItem(STORE_KEY, v);
  } catch {
    // Storage can be blocked; the choice then lasts for this page only.
  }
}

const round1 = (n: number) => Math.round(n * 10) / 10;

function isWithdraw(row: CompRow): boolean {
  return row.chip?.kind === 'withdraw-wait';
}

export interface ViewGroup {
  key: string;
  /** Head text; null hides the head (종목 grouping: each row is its own group). */
  name: string | null;
  dot: SegmentTone;
  pct: number;
  target: number | null;
  rows: CompRow[];
  cash: boolean;
}

function ruleTone(colorIndex: number): SegmentTone {
  return colorIndex === 0 ? 'strategy-1' : 'strategy-2';
}

/** Regroup the rows by a 묶어 보기 criterion (the API sends them grouped by rule). */
export function viewGroups(c: Composition, by: GroupKey, tones: ReadonlyMap<string, LogoTone>) {
  const rows = c.groups.flatMap((g) => g.rows);
  const cashRows = rows.filter((r) => r.kind === 'cash');
  const holdings = rows.filter(
    (r): r is CompRow & { instrument: Instrument } =>
      r.kind === 'holding' && r.instrument !== undefined,
  );
  const cashGroup = (): ViewGroup => ({
    key: 'cash',
    name: homeCopy.composition.cash,
    dot: 'cash',
    pct: round1(cashRows.reduce((s, r) => s + r.pct, 0)),
    target: null,
    rows: cashRows,
    cash: true,
  });

  if (by === 'rule') {
    return c.groups
      .filter((g) => g.rows.length > 0)
      .map((g): ViewGroup => ({
        key: g.key,
        name: g.rule ? ruleName(g.rule) : homeCopy.composition.cash,
        dot: g.rule ? ruleTone(g.rule.colorIndex) : 'cash',
        pct: g.pct,
        target: g.target,
        rows: g.rows,
        cash: !g.rule,
      }));
  }

  if (by === 'instrument') {
    const sorted = [...holdings].sort((a, b) => b.pct - a.pct);
    return [
      ...sorted.map((r): ViewGroup => ({
        key: r.instrument.id,
        name: null,
        dot: `cat-${String(tones.get(r.instrument.id) ?? 1)}` as SegmentTone,
        pct: r.pct,
        target: null,
        rows: [r],
        cash: false,
      })),
      ...(cashRows.length > 0 ? [{ ...cashGroup(), name: null }] : []),
    ];
  }

  const keyOf = (inst: Instrument): { key: string; name: string } => {
    if (by === 'kind') return { key: inst.kind, name: homeCopy.composition.kinds[inst.kind] };
    if (by === 'country') {
      const country = countryOf(inst.market);
      return { key: country, name: copy.country[country] };
    }
    return { key: inst.currency, name: homeCopy.composition.currencies[inst.currency] };
  };

  const byKey = new Map<string, ViewGroup>();
  const place = (r: CompRow, key: string, name: string) => {
    let g = byKey.get(key);
    if (!g) {
      g = { key, name, dot: 'cat-1', pct: 0, target: null, rows: [], cash: false };
      byKey.set(key, g);
    }
    g.rows.push(r);
    g.pct = round1(g.pct + r.pct);
  };
  for (const r of holdings) {
    const k = keyOf(r.instrument);
    place(r, k.key, k.name);
  }
  // Cash joins its currency, and its country (CONTRACT CompRow.cash.country: 원화 현금 한국,
  // 달러 현금 미국); by kind it keeps its own '현금' group.
  if (by === 'currency' || by === 'country') {
    for (const r of cashRows) {
      if (by === 'currency') {
        const cur = r.cash?.currency ?? 'KRW';
        place(r, cur, homeCopy.composition.currencies[cur]);
      } else {
        const country = r.cash?.country === 'US' ? 'us' : 'kr';
        place(r, country, copy.country[country]);
      }
    }
  }
  // Map keeps insertion order: groups appear in the order of their first row.
  const groups = [...byKey.values()].map((g, i): ViewGroup => ({
    ...g,
    dot: `cat-${String((i % 5) + 1)}` as SegmentTone,
  }));
  return by !== 'kind' || cashRows.length === 0 ? groups : [...groups, cashGroup()];
}

/** Bar segments: groups, with waiting-to-withdraw cash hatched at the end. */
export function barSegments(groups: readonly ViewGroup[]): CompositionSegment[] {
  const segs: CompositionSegment[] = [];
  let pending = 0;
  for (const g of groups) {
    const withdraw = round1(g.rows.filter(isWithdraw).reduce((s, r) => s + r.pct, 0));
    pending += withdraw;
    segs.push({ key: g.key, value: Math.max(0, round1(g.pct - withdraw)), tone: g.dot });
  }
  if (pending > 0) segs.push({ key: 'pending', value: pending, tone: 'cash', pending: true });
  return segs;
}

function shareText(g: ViewGroup): string {
  const c = homeCopy.composition;
  return g.target !== null
    ? c.shareTarget(formatPercent(g.pct), `${formatNumber(g.target)}%`)
    : c.share(formatPercent(g.pct));
}

function cashName(row: CompRow): string {
  if (isWithdraw(row)) return homeCopy.composition.withdrawCash;
  return homeCopy.composition.cashName[row.cash?.currency ?? 'KRW'];
}

/**
 * '매수 대기 · S&P 500 ETF 2주'; when no dollar instrument is held yet the name says nothing
 * new and is left out ('매수 대기 · 54주', 기획 §5 SCR-HOME.first-day).
 */
function chipText(chip: NonNullable<CompRow['chip']>, dollarHoldings: number): string {
  const c = homeCopy.composition.chip;
  switch (chip.kind) {
    case 'buy-wait':
      return dollarHoldings > 0
        ? c.buyWait(chip.instrumentName, chip.qty)
        : c.buyWaitShort(chip.qty);
    case 'sub-share':
      return c.subShare;
    case 'withdraw-wait':
      return c.withdrawWait(formatMonthDay(chip.until));
    case 'first-buy':
      return c.firstBuy;
    case 'buy-from':
      return c.buyFrom(formatTime(chip.at));
  }
}

/** '115주 · 평균 32,005원', '0.0027 BTC · 평균 1억 5,493만원', '3주 · 평균 $172.17'. */
export function detailText(row: CompRow): string | null {
  if (row.qty === undefined || !row.avgCost || !row.instrument) return null;
  const c = homeCopy.composition;
  const qty =
    row.instrument.kind === 'coin'
      ? c.coinQty(String(row.qty), row.instrument.name)
      : c.shares(row.qty);
  const avg =
    row.avgCost.currency === 'USD'
      ? formatUsd(row.avgCost.amount)
      : formatKrwEok(row.avgCost.amount);
  return c.detail(qty, avg);
}

function pnlText(pct: number): string {
  const dir = pnlDirection(pct, 1);
  const arrow = dir === 'gain' ? homeCopy.hero.up : dir === 'loss' ? homeCopy.hero.down : '';
  const body = formatPercentSigned(pct, 1);
  return arrow ? `${arrow} ${body}` : body;
}

function Row({
  row,
  tones,
  wide,
  showPct,
  dollarHoldings,
}: {
  row: CompRow;
  tones: ReadonlyMap<string, LogoTone>;
  wide: boolean;
  showPct: boolean;
  /** Dollar instruments held (decides the 매수 대기 chip wording). */
  dollarHoldings: number;
}) {
  const [open, setOpen] = useState(false);
  const pct = showPct ? (
    <span className={clsx('t-caption', styles.muted)}>{formatPercent(row.pct)}</span>
  ) : null;

  if (row.kind === 'cash') {
    const currency = row.cash?.currency ?? 'KRW';
    const usd = row.usd !== undefined;
    return (
      <div className={clsx(styles.row, usd && styles.rowCashUsd)}>
        <InitialLogo
          className={styles.rowLogo}
          initials={homeCopy.composition.cashSymbol[currency]}
          tone="cash"
        />
        <span className={clsx('t-body-strong', styles.rowName)}>{cashName(row)}</span>
        <span className={styles.rowValues}>
          <span className="t-figure">{formatKrw(row.krw)}</span>
        </span>
        <span className={styles.rowAttrs}>
          {row.chip ? <InfoChip>{chipText(row.chip, dollarHoldings)}</InfoChip> : null}
          {pct}
          {row.usd !== undefined ? (
            <span className={clsx('t-caption', styles.muted, styles.rowUsd)}>
              {formatUsd(row.usd)}
            </span>
          ) : null}
        </span>
      </div>
    );
  }

  const inst = row.instrument;
  if (!inst) return null;
  const detail = detailText(row);
  const showDetail = detail !== null && (wide || open);
  const dir = row.pnlPct === undefined ? 'flat' : pnlDirection(row.pnlPct, 1);
  const body = (
    <>
      <InitialLogo className={styles.rowLogo} initials={inst.initials} tone={tones.get(inst.id)} />
      <span className={clsx('t-body-strong', styles.rowName)}>{inst.name}</span>
      <span className={styles.rowAttrs}>
        <Flag country={countryOf(inst.market)} />
        <KindBadge>{homeCopy.composition.kinds[inst.kind]}</KindBadge>
        {pct}
      </span>
      <span className={styles.rowValues}>
        <span className="t-figure">{formatKrw(row.krw)}</span>
        {row.pnlPct !== undefined ? (
          <span className={clsx('t-caption', styles[dir])}>{pnlText(row.pnlPct)}</span>
        ) : null}
      </span>
      {showDetail ? (
        <span className={clsx('t-caption', styles.muted, styles.rowDetail)}>{detail}</span>
      ) : null}
    </>
  );
  const cls = clsx(styles.row, showDetail && styles.rowDetailOpen);
  if (wide || detail === null) return <div className={cls}>{body}</div>;
  return (
    <button
      type="button"
      className={clsx(cls, styles.rowButton)}
      aria-expanded={open}
      onClick={() => {
        setOpen(!open);
      }}
    >
      {body}
    </button>
  );
}

export function CompositionCard({
  home,
  wide,
  tones,
}: {
  home: HomeResponse;
  wide: boolean;
  tones: ReadonlyMap<string, LogoTone>;
}) {
  const c = home.composition;
  const cc = homeCopy.composition;
  const [choice, setChoice] = useState<GroupKey | null>(readGroupChoice);
  const selected: GroupKey | null =
    choice !== null && c.groupBy.includes(choice)
      ? choice
      : c.groupBy.includes('rule')
        ? 'rule'
        : null;
  const view: GroupKey = selected ?? 'rule';
  const groups = viewGroups(c, view, tones);
  const beforeCheck = home.trend.empty === 'before-first-check';

  const targets = c.groups.filter((g) => g.rule && g.target !== null);
  const segments: CompositionSegment[] = beforeCheck
    ? targets.map((g) => ({
        key: g.key,
        value: g.target ?? 0,
        tone: ruleTone(g.rule?.colorIndex ?? 0),
        outline: true,
      }))
    : barSegments(groups);
  const barLabel = beforeCheck
    ? cc.targetNote(
        targets
          .map((g) =>
            cc.targetPart(g.rule ? ruleName(g.rule) : '', `${formatNumber(g.target ?? 0)}%`),
          )
          .join(' · '),
      )
    : groups
        .map(
          (g) =>
            `${g.name ?? g.rows.map((r) => r.instrument?.name ?? cashName(r)).join(' ')} ${formatPercent(g.pct)}`,
        )
        .join(' · ');
  const withdraw = c.pendingBar?.withdraw;
  const dollarHoldings = c.groups
    .flatMap((g) => g.rows)
    .filter((r) => r.kind === 'holding' && r.instrument?.currency === 'USD').length;

  return (
    <section className={clsx(styles.card, styles.composition)} aria-labelledby="home-composition">
      <div className={styles.cardHead}>
        <h2 id="home-composition" className="t-heading-1">
          {cc.title}
        </h2>
        <StaleMark stale={home.stale} section="composition" />
      </div>
      <div className={styles.barBlock}>
        <CompositionBar segments={segments} label={barLabel} />
        {withdraw ? (
          <p className={clsx('t-caption', styles.muted, styles.barNote)}>
            {cc.pendingNote(formatKrw(withdraw.krw), formatMonthDay(withdraw.until))}
          </p>
        ) : null}
        {beforeCheck ? <p className={clsx('t-caption', styles.muted)}>{barLabel}</p> : null}
      </div>
      {c.groupBy.length > 0 ? (
        <div className={styles.chips} role="group" aria-label={cc.groupLabel}>
          {c.groupBy.map((k) => (
            <PeriodChip
              key={k}
              selected={k === selected}
              onClick={() => {
                setChoice(k);
                saveGroupChoice(k);
              }}
            >
              {cc.groupBy[k]}
            </PeriodChip>
          ))}
        </div>
      ) : null}
      <div className={styles.groups}>
        {groups.map((g, i) => (
          <div key={g.key} className={clsx(styles.group, g.cash && i > 0 && styles.groupDivided)}>
            {g.name !== null ? (
              <div className={styles.groupHead}>
                <span className={clsx(styles.groupDot, styles[`dot-${g.dot}`])} aria-hidden />
                <h3 className="t-label">{g.name}</h3>
                {!beforeCheck ? (
                  <span className={clsx('t-caption', styles.muted, styles.groupShare)}>
                    {shareText(g)}
                  </span>
                ) : null}
              </div>
            ) : null}
            <ul className={styles.rows}>
              {g.rows.map((row, j) => (
                <li key={row.instrument?.id ?? `${g.key}-cash-${String(j)}`}>
                  <Row
                    row={row}
                    tones={tones}
                    wide={wide}
                    showPct={!beforeCheck}
                    dollarHoldings={dollarHoldings}
                  />
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      {c.outsideRules ? (
        <p className={clsx('t-caption', styles.muted)}>
          {cc.outsideRules(c.outsideRules.count, formatKrw(c.outsideRules.krw))}
        </p>
      ) : null}
    </section>
  );
}
