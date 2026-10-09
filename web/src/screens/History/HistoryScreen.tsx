// SCR-HISTORY 기록 (Figma 1:58215 · 1:58777 · 1:59344) and the host of SCR-DAY 그날.
// - /history: title (+ 장부 칩 for the other ledger) → 자산 변동 → 요약 타일 → 매일 확인 → 거르기 → 목록.
//   1100px up: left column (title, 자산 변동, 거르기, 목록) and right column (타일, 달력).
// - /day/:date: from 1100px the same page with the 그날 panel over the right column (chart line and
//   row highlight on that day, 1:60239); below that a full-height 그날 sheet (1:59915).
//   Both routes render this component, so the page keeps its state when the panel opens.
// Filters, ledger and year live in the URL, so they survive the PIN page and the day panel.
import clsx from 'clsx';
import { X } from 'lucide-react';
import { useCallback, useMemo } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router';
import { useHistory, useShell } from '../../api/queries';
import type { HistoryResponse, Ledger } from '../../api/types';
import { InfoChip, PeriodChip } from '../../components/Chips';
import { ErrorBlock, ExampleChip, Skeleton, SkeletonBlock } from '../../components/State';
import { copy } from '../../copy';
import { historyCopy as hc } from '../../copy/history';
import { formatMonthDay, kstParts } from '../../lib/format';
import { pageTitle, useDocumentTitle } from '../../shell/page';
import { DayPanel } from '../Day/DayPanel';
import { AssetCard } from './AssetCard';
import { EventList } from './EventList';
import { Filters } from './Filters';
import {
  parseDateKey,
  readParams,
  rebalanceFees,
  searchString,
  visibleMonths,
  withParam,
  type HistoryParams,
  type KindFilter,
} from './historyModel';
import { RunCalendar } from './RunCalendar';
import { SummaryTiles } from './SummaryTiles';
import { useMinWidth } from './useMinWidth';
import styles from './History.module.css';

/** React Router keeps `idx` in history.state; 0 means this entry opened the app. */
function canGoBack(): boolean {
  const state = window.history.state as { idx?: unknown } | null;
  return typeof state?.idx === 'number' && state.idx > 0;
}

export function HistoryScreen() {
  const { date: rawDate } = useParams();
  const day = parseDateKey(rawDate);
  const wide = useMinWidth(1100);
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const search = searchString(params);
  useDocumentTitle(pageTitle(day ? 'day' : 'history'));

  const dayHref = useCallback((date: string) => `/day/${date}${search}`, [search]);

  // × goes back to where the panel was opened (자산 · 계획 · 기록); a direct visit lands on 기록.
  const closeHref = `/history${search}`;
  const close = useCallback(() => {
    if (canGoBack()) void navigate(-1);
    else void navigate(closeHref, { replace: true });
  }, [navigate, closeHref]);

  const p = readParams(params);

  if (day && !wide) {
    return (
      <DayPanel
        date={day}
        ledger={p.ledger}
        search={search}
        onClose={close}
        closeHref={closeHref}
        variant="sheet"
      />
    );
  }
  return (
    <>
      <HistoryPage params={p} selected={day ?? undefined} dayHref={dayHref} />
      {day ? (
        <DayPanel
          date={day}
          ledger={p.ledger}
          search={search}
          onClose={close}
          closeHref={closeHref}
          variant="panel"
        />
      ) : null}
    </>
  );
}

function historyQueryParams(p: HistoryParams): { ledger?: Ledger; year?: number } {
  return {
    ...(p.ledger ? { ledger: p.ledger } : {}),
    ...(p.year !== null ? { year: p.year } : {}),
  };
}

interface HistoryPageProps {
  params: HistoryParams;
  /** Open day panel (1100px up). */
  selected: string | undefined;
  dayHref: (date: string) => string;
}

function HistoryPage({ params: p, selected, dayHref }: HistoryPageProps) {
  const [params, setParams] = useSearchParams();
  const shell = useShell();
  const q = useHistory(historyQueryParams(p));
  const mode = shell.data?.mode ?? null;
  const ledger: Ledger | null = q.data?.ledger ?? p.ledger ?? mode;
  // 장부 칩: ?ledger= names the ledger the current mode is not.
  const other =
    p.ledger !== null && mode !== null && p.ledger !== mode ? { ledger: p.ledger, mode } : null;
  const panelOpen = selected !== undefined;
  const months = useMemo(
    () => (q.data ? visibleMonths(q.data, p.rule, p.kind) : []),
    [q.data, p.rule, p.kind],
  );

  const set = (key: 'ledger' | 'year' | 'rule' | 'kind', value: string | null) => {
    setParams(withParam(params, key, value), { replace: true, preventScrollReset: true });
  };

  const year = q.data?.year ?? p.year ?? (shell.data ? kstParts(shell.data.now).year : null);
  const title = ledger && year !== null ? hc.title(copy.mode[ledger], year) : null;

  const head = (
    <div className={clsx(styles.head, styles.headArea)}>
      {other ? (
        <>
          <h1 className="sr-only">{title}</h1>
          <InfoChip>{hc.ledgerChip(copy.mode[other.ledger])}</InfoChip>
          <span className={clsx('t-label', styles.muted, styles.grow)}>
            {hc.viewingWhile(copy.mode[other.mode])}
          </span>
        </>
      ) : title ? (
        <h1 className={clsx('t-label', styles.muted, styles.grow)}>{title}</h1>
      ) : (
        <>
          <h1 className="sr-only">{copy.pages.history}</h1>
          <span className={styles.grow}>
            <Skeleton text="label" width={140} />
          </span>
        </>
      )}
      {q.data && q.data.years.length > 1 ? (
        <div className={styles.years} role="group" aria-label={hc.years}>
          {q.data.years.map((y) => (
            <PeriodChip
              key={y}
              selected={y === q.data.year}
              onClick={() => {
                set('year', y === Math.max(...q.data.years) ? null : String(y));
              }}
            >
              {String(y)}
            </PeriodChip>
          ))}
        </div>
      ) : null}
      <ExampleChip show={q.data?.example ?? false} />
      {other ? (
        <button
          type="button"
          className={styles.closeChip}
          aria-label={hc.closeLedger(copy.mode[other.mode])}
          onClick={() => {
            set('ledger', null);
          }}
        >
          <X size={20} aria-hidden />
        </button>
      ) : null}
    </div>
  );

  if (q.isPending) {
    return (
      <div className={clsx(styles.page, panelOpen && styles.withPanel)} aria-busy="true">
        {head}
        <HistorySkeleton />
      </div>
    );
  }

  if (!q.data) {
    return (
      <div className={clsx(styles.page, panelOpen && styles.withPanel)}>
        {head}
        <ErrorBlock
          className={styles.listArea}
          message={copy.state.errors.history}
          onRetry={() => void q.refetch()}
          retrying={q.isFetching}
        />
      </div>
    );
  }

  const data: HistoryResponse = q.data;
  return (
    <div className={clsx(styles.page, panelOpen && styles.withPanel)}>
      {head}
      <AssetCard trend={data.trend} hrefFor={dayHref} selected={selected} />
      <div className={clsx(styles.side, styles.sideArea)}>
        <p className={clsx('t-label', styles.muted, styles.tilesHead)}>
          {hc.tiles.head(formatMonthDay(data.trend.since))}
        </p>
        <SummaryTiles tiles={data.tiles} fees={rebalanceFees(data)} />
        <RunCalendar
          calendar={data.calendar}
          checks={data.tiles.checks}
          offPeriods={data.offPeriods}
          hrefFor={dayHref}
        />
      </div>
      <Filters
        filters={data.filters}
        rule={p.rule}
        kind={p.kind}
        onRule={(r) => {
          set('rule', r === 'all' ? null : r);
        }}
        onKind={(k: KindFilter | null) => {
          set('kind', k);
        }}
      />
      <EventList months={months} hrefFor={dayHref} selected={selected} replace={panelOpen} />
    </div>
  );
}

/** 카드 틀 유지 스켈레톤 (기획 §5 SCR-HISTORY loading). */
function HistorySkeleton() {
  return (
    <>
      <section className={clsx(styles.assetCard, styles.asset)}>
        <Skeleton text="caption" width={120} />
        <Skeleton text="title" width={150} />
        <Skeleton text="label" width={200} />
        <SkeletonBlock height={200} />
      </section>
      <div className={clsx(styles.side, styles.sideArea)}>
        <div className={styles.tiles}>
          {[0, 1, 2].map((i) => (
            <div key={i} className={styles.tile}>
              <Skeleton text="label" width={60} />
              <Skeleton text="title" width={70} />
              <Skeleton text="caption" width={50} />
            </div>
          ))}
        </div>
        <SkeletonBlock height={246} />
      </div>
      <div className={clsx(styles.filters, styles.filtersArea)}>
        <SkeletonBlock height={36} />
        <SkeletonBlock height={34} />
      </div>
      <div className={clsx(styles.list, styles.listArea)}>
        {[0, 1, 2].map((i) => (
          <SkeletonBlock key={i} height={70} />
        ))}
      </div>
    </>
  );
}
