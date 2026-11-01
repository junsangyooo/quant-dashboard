// 자산 화면 부품(포트폴리오 계좌 화면 짜임 · 색 · 글꼴 · 부품은 MVP 것): 요약 네 칸 · 오늘 손익 기여 상위 3 ·
// 보유 목록(정렬 · 검색 · 30일 작은 그래프 · 보유 이유) · 구성(도넛 · 지도, 종목 · 주식·현금) · 최근 거래.
import clsx from 'clsx';
import { useMemo, useState, type ReactNode } from 'react';
import { ChevronDown, ChevronRight, Search } from 'lucide-react';
import type { Holding, RecentTrade } from '../../api/mvp';
import { LinkButton } from '../../components/Buttons';
import { Card } from '../../components/Card';
import { PeriodChip } from '../../components/Chips';
import { Dots } from '../../components/Dots';
import { SideTag } from '../../components/Tags';
import { copy } from '../../copy';
import { homeCopy as t } from '../../copy/paper';
import {
  formatKrw,
  formatKrwSigned,
  formatMonthDay,
  formatMonthDayWeekday,
  formatPercent,
} from '../../lib/format';
import { pct, shares, tone, toneClass } from '../../lib/money';
import { reasonParts } from '../Paper/PlanRows';
import styles from './Home.module.css';

export function Cell({
  label,
  value,
  line,
  cls,
}: {
  label: string;
  value: ReactNode;
  line: ReactNode;
  cls?: string | undefined;
}) {
  return (
    <div className={styles.cell}>
      <span className="t-caption c-muted">{label}</span>
      <span className={clsx('t-heading-1', cls)}>{value}</span>
      <span className={clsx('t-micro', styles.cellLine, cls)}>{line}</span>
    </div>
  );
}

export function Contribution({ holdings }: { holdings: Holding[] }) {
  const rows = holdings
    .filter((h) => h.day_pnl !== null)
    .sort((a, b) => Math.abs(b.day_pnl ?? 0) - Math.abs(a.day_pnl ?? 0))
    .slice(0, 3);
  if (rows.length === 0) return null;
  const max = Math.max(...rows.map((h) => Math.abs(h.day_pnl ?? 0)), 1);
  return (
    <div className={styles.contrib}>
      <div className={styles.rowBetween}>
        <span className="t-caption">{t.contribTitle}</span>
        <span className="t-caption c-muted">{t.contribBasis}</span>
      </div>
      {rows.map((h) => {
        const v = h.day_pnl ?? 0;
        const dir = tone(v);
        return (
          <a key={h.sym} href={`#h-${h.sym}`} className={styles.contribRow}>
            <span className="t-caption">{h.name}</span>
            <span className={styles.track}>
              <span
                className={clsx(styles.bar, dir === 'loss' ? styles.barLoss : styles.barGain)}
                style={{ width: `${String(Math.max(6, (Math.abs(v) / max) * 100))}%` }}
              />
            </span>
            <span className={clsx('t-label', styles.num, toneClass[dir])}>
              {formatKrwSigned(v)}
            </span>
            <ChevronRight size={14} className="c-muted" aria-hidden />
          </a>
        );
      })}
    </div>
  );
}

function Spark({ values }: { values: number[] }) {
  if (values.length < 2) return <span className={styles.spark} />;
  const w = 56;
  const h = 20;
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const span = hi - lo || 1;
  const pts = values
    .map(
      (v, i) =>
        `${((i / (values.length - 1)) * w).toFixed(1)},${(h - ((v - lo) / span) * h).toFixed(1)}`,
    )
    .join(' ');
  const up = (values[values.length - 1] ?? 0) >= (values[0] ?? 0);
  return (
    <svg
      className={styles.spark}
      width={w}
      height={h}
      viewBox={`0 0 ${String(w)} ${String(h)}`}
      aria-hidden
    >
      <polyline points={pts} className={up ? styles.sparkGain : styles.sparkLoss} />
    </svg>
  );
}

type SortKey = keyof typeof t.sorts;

function reasonLine(h: Holding): string {
  const r = h.reasons[0];
  const head = r ? reasonParts(r, false).join(' · ') : '';
  return head ? t.bought(head, formatMonthDay(h.entry_d)) : '';
}

export function HoldingsCard({
  holdings,
  priceNote,
  wide,
  empty,
}: {
  holdings: Holding[];
  priceNote: string;
  wide: boolean;
  /** 보유가 없을 때 둘째 줄. */
  empty: string;
}) {
  const [q, setQ] = useState('');
  const [sort, setSort] = useState<SortKey>('value');
  const [searching, setSearching] = useState(false);
  const list = useMemo(() => {
    const f = holdings.filter(
      (h) => !q.trim() || h.name.includes(q.trim()) || h.sym.includes(q.trim()),
    );
    const by: Record<SortKey, (a: Holding, b: Holding) => number> = {
      value: (a, b) => b.value - a.value,
      ret: (a, b) => (b.pnl_pct ?? 0) - (a.pnl_pct ?? 0),
      day: (a, b) => (b.day_pct ?? 0) - (a.day_pct ?? 0),
      name: (a, b) => a.name.localeCompare(b.name, 'ko'),
    };
    return [...f].sort(by[sort]);
  }, [holdings, q, sort]);

  if (holdings.length === 0) {
    return (
      <Card>
        <h2 className="t-heading-1">{t.holdings(0)}</h2>
        <div className={styles.emptyBox}>
          <p className="t-body-strong">{t.emptyTitle}</p>
          <p className="t-caption c-muted">{empty}</p>
        </div>
      </Card>
    );
  }
  const controls = (
    <div className={styles.controls}>
      {wide || searching ? (
        <label className={styles.searchBox}>
          <Search size={16} className="c-muted" aria-hidden />
          <input
            className="t-caption"
            value={q}
            placeholder={t.search}
            aria-label={t.search}
            onChange={(e) => {
              setQ(e.target.value);
            }}
          />
        </label>
      ) : (
        <button
          type="button"
          className={styles.iconBtn}
          aria-label={t.search}
          onClick={() => {
            setSearching(true);
          }}
        >
          <Search size={20} aria-hidden />
        </button>
      )}
      <label className={clsx('t-label', styles.sortBox)}>
        <select
          value={sort}
          aria-label={t.sort}
          onChange={(e) => {
            setSort(e.target.value as SortKey);
          }}
        >
          {(Object.keys(t.sorts) as SortKey[]).map((k) => (
            <option key={k} value={k}>
              {t.sorts[k]}
            </option>
          ))}
        </select>
        <ChevronDown size={14} aria-hidden />
      </label>
    </div>
  );
  return (
    <Card>
      <div className={styles.rowBetween}>
        <h2 className="t-heading-1">{t.holdings(holdings.length)}</h2>
        {controls}
      </div>
      {wide ? (
        <div className={styles.table} role="table" aria-label={t.holdings(holdings.length)}>
          <div className={clsx('t-caption c-muted', styles.tr, styles.th)} role="row">
            <span role="columnheader">{t.cols.stock}</span>
            <span role="columnheader">{t.cols.spark}</span>
            <span role="columnheader" className={styles.right}>
              {t.cols.price}
            </span>
            <span role="columnheader" className={styles.right}>
              {t.cols.value}
            </span>
            <span role="columnheader">{t.cols.weight}</span>
            <span role="columnheader" className={styles.right}>
              {t.cols.pnl}
            </span>
          </div>
          {list.map((h) => (
            <div key={h.sym} id={`h-${h.sym}`} className={styles.tr} role="row">
              <span role="cell" className="stack-tight">
                <span className="t-body-strong">{h.name}</span>
                <span className="t-caption c-muted">
                  <Dots parts={t.holdingLine(h.sym, shares(h.qty), formatKrw(h.avg))} />
                </span>
                {reasonLine(h) ? (
                  <span className={clsx('t-micro', styles.reason)}>{reasonLine(h)}</span>
                ) : null}
              </span>
              <span role="cell">
                <Spark values={h.spark} />
              </span>
              <span role="cell" className={clsx(styles.right, 'stack-tight')}>
                <span className="t-body">{formatKrw(h.price)}</span>
                <span className={clsx('t-micro', toneClass[tone((h.day_pct ?? 0) * 100, 2)])}>
                  {h.day_pct === null ? copy.common.dash : pct(h.day_pct)}
                </span>
              </span>
              <span role="cell" className={clsx(styles.right, 't-body-strong')}>
                {formatKrw(h.value)}
              </span>
              <span role="cell" className={styles.weight}>
                <span className={styles.weightTrack}>
                  <span
                    className={styles.weightBar}
                    style={{ width: `${String((h.weight ?? 0) * 100)}%` }}
                  />
                </span>
                <span className="t-caption">{formatPercent((h.weight ?? 0) * 100, 1)}</span>
              </span>
              <span role="cell" className={clsx(styles.right, 'stack-tight')}>
                <span className={clsx('t-body-strong', toneClass[tone(h.pnl)])}>
                  {formatKrwSigned(h.pnl)}
                </span>
                <span className={clsx('t-micro', toneClass[tone(h.pnl)])}>
                  {pct(h.pnl_pct ?? 0)}
                </span>
              </span>
            </div>
          ))}
          {list.length === 0 ? <p className="t-caption c-muted">{t.noMatch}</p> : null}
        </div>
      ) : (
        <ul className={styles.mobileList}>
          {list.map((h) => (
            <li key={h.sym} id={`h-${h.sym}`} className={styles.mobileRow}>
              <div className={styles.rowBetween}>
                <span className="t-body-strong">{h.name}</span>
                <span className="t-body-strong">{formatKrw(h.value)}</span>
              </div>
              <span className="t-caption c-muted">
                <Dots parts={t.holdingLine(h.sym, shares(h.qty), formatKrw(h.avg))} />
              </span>
              {reasonLine(h) ? (
                <span className={clsx('t-micro', styles.reason)}>{reasonLine(h)}</span>
              ) : null}
              <div className={styles.rowBetween}>
                <span className={clsx('t-caption', toneClass[tone((h.day_pct ?? 0) * 100, 2)])}>
                  {t.priceToday(
                    formatKrw(h.price),
                    h.day_pct === null ? copy.common.dash : pct(h.day_pct),
                  )}
                </span>
                <span className={clsx('t-caption', toneClass[tone(h.pnl)])}>
                  <Dots parts={[formatKrwSigned(h.pnl), pct(h.pnl_pct ?? 0)]} />
                </span>
              </div>
            </li>
          ))}
          {list.length === 0 ? <li className="t-caption c-muted">{t.noMatch}</li> : null}
        </ul>
      )}
      <p className="t-caption c-muted">{`${t.avgNote} · ${priceNote}`}</p>
    </Card>
  );
}

const CAT = ['cat1', 'cat2', 'cat3', 'cat4', 'cat5'] as const;

interface Slice {
  key: string;
  name: string;
  value: number;
  cls: string;
}

function donutPath(cx: number, cy: number, r: number, a0: number, a1: number): string {
  const p = (a: number) => [cx + r * Math.sin(a), cy - r * Math.cos(a)] as const;
  const [x0, y0] = p(a0);
  const [x1, y1] = p(a1);
  const large = a1 - a0 > Math.PI ? 1 : 0;
  return `M${x0.toFixed(2)} ${y0.toFixed(2)} A${String(r)} ${String(r)} 0 ${String(large)} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
}

function Donut({ slices, center, unit }: { slices: Slice[]; center: string; unit: string }) {
  const total = slices.reduce((s, x) => s + x.value, 0) || 1;
  const gap = slices.length > 1 ? 0.03 : 0;
  const starts = slices.map((_, i) =>
    slices.slice(0, i).reduce((s, x) => s + (x.value / total) * Math.PI * 2, 0),
  );
  return (
    <svg width={120} height={120} viewBox="0 0 120 120" className={styles.donut} aria-hidden>
      {slices.map((s, i) => {
        const a = starts[i] ?? 0;
        const da = (s.value / total) * Math.PI * 2;
        const a0 = a + gap / 2;
        const a1 = Math.max(a0 + 0.001, a + da - gap / 2);
        if (slices.length === 1)
          return (
            <circle
              key={s.key}
              cx={60}
              cy={60}
              r={51}
              className={clsx(styles.ring, styles[s.cls])}
            />
          );
        return (
          <path
            key={s.key}
            d={donutPath(60, 60, 51, a0, a1)}
            className={clsx(styles.ring, styles[s.cls])}
          />
        );
      })}
      <text x={60} y={56} textAnchor="middle" className={clsx('t-body-strong', styles.donutText)}>
        {center}
      </text>
      <text x={60} y={74} textAnchor="middle" className={clsx('t-micro', styles.donutUnit)}>
        {unit}
      </text>
    </svg>
  );
}

function Treemap({ slices }: { slices: Slice[] }) {
  const total = slices.reduce((s, x) => s + x.value, 0) || 1;
  const widths = slices.map((s) => (s.value / total) * 100);
  const lefts = widths.map((_, i) => widths.slice(0, i).reduce((s, w) => s + w, 0));
  return (
    <div className={styles.treemap} aria-hidden>
      {slices.map((s, i) => (
        <div
          key={s.key}
          className={clsx(styles.tile, styles[`${s.cls}Bg`])}
          style={{ left: `${String(lefts[i] ?? 0)}%`, width: `${String(widths[i] ?? 0)}%` }}
        >
          <span className="t-micro">{s.name}</span>
          <span className="t-micro">{formatPercent(widths[i] ?? 0, 1)}</span>
        </div>
      ))}
    </div>
  );
}

export function CompositionCard({ holdings, cash }: { holdings: Holding[]; cash: number }) {
  const [view, setView] = useState<'donut' | 'map'>('donut');
  const [basis, setBasis] = useState<'stock' | 'kind'>('stock');
  const stockValue = holdings.reduce((s, h) => s + h.value, 0);
  const slices: Slice[] =
    basis === 'stock'
      ? [...holdings]
          .sort((a, b) => b.value - a.value)
          .map((h, i) => ({
            key: h.sym,
            name: h.name,
            value: h.value,
            cls: CAT[i % CAT.length] ?? 'cat1',
          }))
      : [
          { key: 'stock', name: t.stock, value: stockValue, cls: 'cat1' },
          { key: 'cash', name: t.cash, value: cash, cls: 'cash' },
        ];
  const total = slices.reduce((s, x) => s + x.value, 0) || 1;
  return (
    <Card>
      <div className={styles.rowBetween}>
        <h2 className="t-heading-1">{t.compTitle}</h2>
        <div className={styles.chips} role="group" aria-label={t.compTitle}>
          <PeriodChip
            selected={view === 'donut'}
            onClick={() => {
              setView('donut');
            }}
          >
            {t.donut}
          </PeriodChip>
          <PeriodChip
            selected={view === 'map'}
            onClick={() => {
              setView('map');
            }}
          >
            {t.map}
          </PeriodChip>
        </div>
      </div>
      <div className={styles.chips} role="group" aria-label={t.compLabel}>
        <PeriodChip
          selected={basis === 'stock'}
          onClick={() => {
            setBasis('stock');
          }}
        >
          {t.byStock}
        </PeriodChip>
        <PeriodChip
          selected={basis === 'kind'}
          onClick={() => {
            setBasis('kind');
          }}
        >
          {t.byKind}
        </PeriodChip>
      </div>
      {holdings.length === 0 ? (
        <p className="t-caption c-muted">{t.compEmpty}</p>
      ) : view === 'donut' ? (
        <div className={styles.donutRow}>
          <Donut
            slices={slices}
            center={
              basis === 'stock'
                ? t.stocksCount(holdings.length)
                : formatPercent((stockValue / total) * 100, 0)
            }
            unit={basis === 'stock' ? t.stocksUnit : t.stock}
          />
          <ul className={styles.legendList}>
            {slices.map((s) => (
              <li key={s.key} className={styles.legendRow}>
                <span className={clsx(styles.dot, styles[`${s.cls}Bg`])} />
                <span className="t-caption">{s.name}</span>
                <span className={clsx('t-caption', styles.legendPct)}>
                  {formatPercent((s.value / total) * 100, 1)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <Treemap slices={slices} />
      )}
    </Card>
  );
}

export function RecentCard({ trades, none }: { trades: RecentTrade[]; none?: string | undefined }) {
  return (
    <Card>
      <div className={styles.rowBetween}>
        <h2 className="t-heading-1">{t.recentTitle}</h2>
        <LinkButton to="/history">{t.recentLink}</LinkButton>
      </div>
      {trades.length === 0 ? (
        <p className="t-caption c-muted">{none ?? t.recentEmpty}</p>
      ) : (
        <>
          <p className="t-caption c-muted">{t.recentLead}</p>
          <ul className={styles.recent}>
            {trades.map((x, i) => (
              <li key={`${x.d}-${x.sym}-${String(i)}`} className={styles.recentRow}>
                <span className="t-caption c-muted">{formatMonthDayWeekday(x.d)}</span>
                <span className="stack-tight">
                  <span className={styles.recentName}>
                    <span className="t-body-strong">{x.name}</span>
                    <SideTag side={x.side} />
                  </span>
                  <span className="t-caption c-muted">
                    {t.qtyPrice(shares(x.qty), formatKrw(x.price))}
                  </span>
                </span>
                <span className={clsx('t-body-strong', styles.num)}>{formatKrw(x.amount)}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}
