// MVP-15 백테스트: 입력 · 실행 중 · 결과 · 시세 못 받음 (390 · 1440).
import clsx from 'clsx';
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { isApiError } from '../../api/client';
import { useExample, usePost, useStrategy, type BacktestResult } from '../../api/mvp';
import { LineChart } from '../../charts/LineChart';
import { LINE_HOME_1440, LINE_HOME_390 } from '../../charts/geometry/lineChart';
import { edgeAxis } from '../../charts/geometry/mvpAxis';
import { Box } from '../../components/Box';
import { Button } from '../../components/Buttons';
import { Card } from '../../components/Card';
import { InfoChip } from '../../components/Chips';
import { Dots } from '../../components/Dots';
import { TextField } from '../../components/Field';
import { SideTag, StatusTag } from '../../components/Tags';
import { copy } from '../../copy';
import { backtestCopy as t } from '../../copy/backtest';
import {
  formatDateTime,
  formatKrw,
  formatKrwSigned,
  formatMonthDayWeekday,
  formatNumber,
  formatPercent,
  formatPercentSigned,
  kstDateKey,
} from '../../lib/format';
import { shares, times, tone, toneClass } from '../../lib/money';
import { useMediaQuery } from '../../lib/useMedia';
import { BackLink, Page } from '../../shell/Layout';
import { useDocumentTitle } from '../../shell/page';
import { LoadError } from '../LoadError';
import { parseWon, StartSheet, wonInput } from '../Strategies/PaperSheets';
import styles from './Backtest.module.css';

function defaultRange(): { start: string; end: string } {
  const today = kstDateKey(new Date());
  return { start: `${String(Number(today.slice(0, 4)) - 5)}-01-04`, end: today };
}

const ratioPct = (v: number | null, signed = true) =>
  v === null
    ? copy.common.dash
    : signed
      ? formatPercentSigned(v * 100, 1)
      : formatPercent(v * 100, 0);

function Tile({ label, value, cls }: { label: string; value: string; cls?: string | undefined }) {
  return (
    <div className={styles.tile}>
      <span className="t-caption c-muted">{label}</span>
      <span className={clsx('t-body-strong', cls)}>{value}</span>
    </div>
  );
}

function yearTicks(start: string, end: string): string[] {
  const out: string[] = [];
  for (let y = Number(start.slice(0, 4)) + 1; y <= Number(end.slice(0, 4)); y++)
    out.push(`${String(y)}-01-01`);
  return [start, ...out.filter((d) => d > start && d < end)];
}

function pctTick(v: number): string {
  return v === 0 ? '0%' : formatPercentSigned(v, 0);
}

function ResultChart({ r }: { r: BacktestResult }) {
  const wide = useMediaQuery('(min-width: 900px)');
  const toPct = (pts: [string, number][]) =>
    pts.map(([date, v]) => ({ date, value: (v / r.cash - 1) * 100 }));
  const mine = toPct(r.curve);
  const bench = toPct(r.bench);
  const axis = edgeAxis([...mine.map((p) => p.value), ...bench.map((p) => p.value), 0]);
  return (
    <div className={styles.chartCard}>
      <div className={clsx('t-caption', styles.legend)} aria-hidden>
        <span className={styles.legendItem}>
          <span className={styles.swatch} />
          {t.legendMine}
        </span>
        {bench.length > 0 ? (
          <span className={styles.legendItem}>
            <span className={styles.swatchDashed} />
            {t.legendBench}
          </span>
        ) : null}
      </div>
      <LineChart
        layout={wide ? LINE_HOME_1440 : { ...LINE_HOME_390, plotHeight: 160 }}
        start={r.start}
        end={r.end}
        axis={axis}
        mine={{ key: 'mine', points: mine }}
        baseline={bench.length > 0 ? { key: 'bench', points: bench } : undefined}
        dateTicks={yearTicks(r.start, r.end)}
        formatDate={(d) => d.slice(0, 4)}
        formatTick={pctTick}
        label={t.chartLabel}
      />
    </div>
  );
}

function Result({
  r,
  running,
  onStart,
  example,
}: {
  r: BacktestResult;
  running: boolean;
  onStart: () => void;
  example?: string | undefined;
}) {
  const navigate = useNavigate();
  const recent = [...r.trades].reverse().slice(0, 5);
  return (
    <div className="stack-block">
      <div className={styles.resultHead}>
        <h2 className="t-heading-1">{t.result}</h2>
        <InfoChip>{t.ranAt(formatDateTime(r.ran_at))}</InfoChip>
      </div>
      <div className={styles.tiles}>
        <Tile
          label={t.total}
          value={ratioPct(r.total)}
          cls={toneClass[tone((r.total ?? 0) * 100, 1)]}
        />
        <Tile
          label={t.cagr}
          value={ratioPct(r.cagr)}
          cls={toneClass[tone((r.cagr ?? 0) * 100, 1)]}
        />
        <Tile label={t.mdd} value={ratioPct(r.mdd)} />
        <Tile label={t.trades} value={times(r.trades_count)} />
        <Tile label={t.winRate} value={ratioPct(r.win_rate, false)} />
        <Tile label={t.bench} value={ratioPct(r.bench_total)} />
      </div>
      <p className="t-caption c-muted">
        <Dots parts={t.money(formatKrw(r.cash), formatKrw(r.final))} />
      </p>
      <ResultChart r={r} />
      <div className={styles.resultHead}>
        <h2 className="t-heading-1">{t.list}</h2>
        <span className="t-caption c-muted">{t.recent(r.trades_count, recent.length)}</span>
      </div>
      <ul className={styles.trades}>
        {recent.map((x, i) => (
          <li key={`${x.d}-${x.sym}-${String(i)}`} className={styles.trade}>
            <span className="t-caption c-muted">{formatMonthDayWeekday(x.d)}</span>
            <SideTag side={x.side} />
            <span className="stack-tight">
              <span className="t-body-strong">{x.name}</span>
              <span className="t-caption">{t.qtyPrice(shares(x.qty), formatKrw(x.price))}</span>
            </span>
            {x.side === 'sell' && x.pnl !== null ? (
              <span className={clsx('t-body-strong', toneClass[tone(x.pnl)])}>
                {formatKrwSigned(x.pnl)}
              </span>
            ) : (
              <span className="t-body c-muted">{copy.common.dash}</span>
            )}
          </li>
        ))}
      </ul>
      {example ? (
        <>
          <Button
            kind="primary"
            className={styles.startButton}
            onClick={() => void navigate(`/strategies/new?start=example&example=${example}`)}
          >
            {t.exampleCopy}
          </Button>
          <p className="t-caption c-muted">{t.exampleNote}</p>
        </>
      ) : running ? (
        <p className="t-body-strong">{t.paperRunning}</p>
      ) : (
        <Button kind="primary" className={styles.startButton} onClick={onStart}>
          {t.startPaper}
        </Button>
      )}
      <p className="t-caption c-muted">{t.footnote}</p>
    </div>
  );
}

export function BacktestScreen() {
  useDocumentTitle(copy.pages.backtest);
  const params = useParams();
  const eid = params.eid;
  const id = Number(params.id ?? 0);
  const q = useStrategy(id, eid === undefined);
  const exq = useExample(eid ?? '', eid !== undefined);
  const [range, setRange] = useState(defaultRange);
  const [cash, setCash] = useState(() => formatNumber(10_000_000));
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [starting, setStarting] = useState(false);
  const run = usePost<
    { version_id?: number; example?: string; start: string; end: string; cash: number },
    BacktestResult
  >('/api/backtest');
  if (q.isError || exq.isError)
    return <LoadError onRetry={() => void (eid ? exq.refetch() : q.refetch())} />;
  const ex = exq.data;
  const s = q.data;
  if (eid ? !ex : !s) return null;
  const v = s?.version;
  const blocked = (v?.problems.length ?? 0) > 0;
  const title = ex ? ex.name : (s?.name ?? '');
  const backTo = ex ? `/examples/${ex.id}` : `/strategies/${String(id)}`;
  const amount = parseWon(cash);
  const busy = run.isPending;
  const err = run.error;
  const failed = err !== null && !busy;
  const marketFail = failed && isApiError(err) && err.body?.kind === 'market';
  const ready = !blocked && !busy && amount !== null && range.start !== '' && range.end !== '';

  const go = () => {
    if (amount === null) return;
    setResult(null);
    run.mutate(
      ex
        ? { example: ex.id, start: range.start, end: range.end, cash: amount }
        : { version_id: v?.id ?? 0, start: range.start, end: range.end, cash: amount },
      {
        onSuccess: (r) => {
          setResult(r);
        },
      },
    );
  };

  const status = busy ? (
    <Box tone="info" icon="wait" title={t.runningTitle}>
      {t.runningBody}
    </Box>
  ) : failed ? (
    <Box
      tone="error"
      title={marketFail ? t.failTitle : isApiError(err) ? err.message : copy.common.noConnection}
      strongTitle
      role="alert"
    >
      {marketFail ? t.failBody : null}
    </Box>
  ) : null;

  return (
    <Page width="backtest">
      <BackLink to={backTo}>{title}</BackLink>
      <div className={styles.title}>
        <h1 className="t-title">{t.title}</h1>
        {ex ? (
          <StatusTag kind="plain">{copy.common.example}</StatusTag>
        ) : (
          <StatusTag kind="version">{copy.common.version(v?.no ?? 1)}</StatusTag>
        )}
      </div>
      <div className={styles.layout}>
        <Card className={styles.inputs}>
          <h2 className="t-heading-1">{t.inputs}</h2>
          <div className="stack-inline">
            <div className={styles.dates}>
              <TextField
                label={t.start}
                value={range.start}
                inputMode="numeric"
                placeholder="2000-01-01"
                spellCheck={false}
                disabled={busy}
                onChange={(e) => {
                  setRange({ ...range, start: e.target.value });
                }}
              />
              <TextField
                label={t.end}
                value={range.end}
                inputMode="numeric"
                placeholder="2000-01-01"
                spellCheck={false}
                disabled={busy}
                onChange={(e) => {
                  setRange({ ...range, end: e.target.value });
                }}
              />
            </div>
            <p className="t-caption c-muted">{t.rangeHint}</p>
          </div>
          <TextField
            label={t.cash}
            inputMode="numeric"
            value={cash}
            unit={t.unit}
            disabled={busy}
            hint={t.cashHint}
            onChange={(e) => {
              setCash(wonInput(e.target.value));
            }}
          />
          <div className={styles.chips}>
            {t.chips.map((c) => (
              <InfoChip key={c}>{c}</InfoChip>
            ))}
          </div>
          <p className="t-caption c-muted">{t.rule}</p>
          {blocked ? <Box tone="warn" title={t.blocked} /> : null}
          <Button kind="primary" className="full" disabled={!ready} onClick={go}>
            {busy ? t.running : failed ? t.again : t.run}
          </Button>
        </Card>
        <div className={styles.output}>
          {status}
          {result ? (
            <Result
              r={result}
              running={s?.paper?.version_no === result.version?.no}
              example={ex?.id}
              onStart={() => {
                setStarting(true);
              }}
            />
          ) : !busy && !failed ? (
            <div className={clsx(styles.empty, styles.wideOnly)}>
              <span className="t-body c-muted">{t.emptyWide}</span>
            </div>
          ) : null}
        </div>
      </div>
      {starting && result?.version && s ? (
        <StartSheet
          strategy={s.name}
          versionId={result.version.id}
          versionNo={result.version.no}
          onClose={() => {
            setStarting(false);
          }}
        />
      ) : null}
    </Page>
  );
}
