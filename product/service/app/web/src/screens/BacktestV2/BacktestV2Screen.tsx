// 백테스트(그림 V2-26): 입력(기간 · 시작 금액 · 칩) · 결과(숫자 · 선 · 거래 목록 · 고정 고지 · '실전이었다면' 줄 ·
// 보조 단추 둘). 주 단추는 없어요(SPEC 8-1).
import clsx from 'clsx';
import {
  AlertTriangle,
  ChevronLeft,
  GitCommitHorizontal,
  LineChart as ChartIcon,
} from 'lucide-react';
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { isApiError } from '../../api/client';
import {
  runBacktestV2,
  useBacktestInput,
  useStrategyDetail,
  type BacktestV2Result,
} from '../../api/v2';
import { LineChart } from '../../charts/LineChart';
import { LINE_HOME_1440 } from '../../charts/geometry/lineChart';
import { edgeAxis } from '../../charts/geometry/mvpAxis';
import { Button } from '../../components/Buttons';
import { backtestV2 as t } from '../../copy/backtestV2';
import styles from './BacktestV2.module.css';

const won = (v: number) => Math.round(v).toLocaleString();
const pct = (v: number | null) =>
  v === null ? '—' : `${v >= 0 ? '+' : '−'}${Math.abs(v * 100).toFixed(1)}%`;
const signed = (v: number) => `${v >= 0 ? '+' : '−'}${won(Math.abs(v))}원`;

function dayLabel(d: string): string {
  const w = new Date(`${d}T00:00:00`).getDay();
  return `${d}(${t.days[w] ?? ''})`;
}

function Result({
  r,
  onLive,
  onPaper,
}: {
  r: BacktestV2Result;
  onLive: () => void;
  onPaper: () => void;
}) {
  const toPct = (pts: [string, number][]) =>
    pts.map(([date, v]) => ({ date, value: (v / (r.curve[0]?.[1] ?? 1) - 1) * 100 }));
  const mine = toPct(r.curve);
  const bench = toPct(r.bench_curve);
  const axis = edgeAxis([...mine.map((p) => p.value), ...bench.map((p) => p.value), 0]);
  const cash = r.curve[0]?.[1] ?? 0;
  const metrics: [string, string, boolean][] = [
    [t.total, pct(r.total), true],
    [t.cagr, pct(r.cagr), true],
    [t.mdd, pct(r.mdd), false],
    [t.trades, t.tradesValue(r.trade_count), false],
    [t.winRate, r.win_rate === null ? '—' : `${String(Math.round(r.win_rate * 100))}%`, false],
    [t.bench, pct(r.bench_total), true],
  ];
  return (
    <div className={styles.result}>
      <div className={styles.rowBetween}>
        <strong className="t-heading-1">{t.result}</strong>
        <span className={clsx(styles.chip, 't-caption')}>{t.ranAt(r.ran_day, r.ran_hm)}</span>
      </div>
      <div className={styles.metrics}>
        {metrics.map(([k, v, colored]) => (
          <div key={k} className={styles.metric}>
            <span className={clsx(styles.muted, 't-caption')}>{k}</span>
            <strong className={clsx(colored && (v.startsWith('+') ? styles.up : styles.down))}>
              {v}
            </strong>
          </div>
        ))}
      </div>
      <p className={clsx(styles.muted, 't-caption')}>
        {t.moneyLine(won(cash), won(r.final), won(r.costs))}
      </p>
      <div className={styles.chartCard}>
        <div className={clsx(styles.legend, 't-caption')}>
          <span>— {t.legendMine}</span>
          {bench.length ? <span>--- {t.legendBench}</span> : null}
        </div>
        <LineChart
          layout={LINE_HOME_1440}
          start={r.start}
          end={r.end}
          axis={axis}
          mine={{ key: 'mine', points: mine }}
          baseline={bench.length ? { key: 'bench', points: bench } : undefined}
          formatDate={(d) => d.slice(0, 4)}
          label={t.chartLabel}
        />
      </div>
      <div className={styles.rowBetween}>
        <strong className="t-heading-1">{t.listTitle}</strong>
        <span className={clsx(styles.muted, 't-caption')}>
          {t.listRight(r.trade_count, r.recent.length)}
        </span>
      </div>
      <ul className={styles.trades}>
        {r.recent.map((x) => (
          <li key={`${x.d}-${x.sym}-${x.side}`} className={styles.trade}>
            <span className="t-caption">{dayLabel(x.d)}</span>
            <span
              className={clsx(
                styles.side,
                x.side === 'buy' ? styles.sideBuy : styles.sideSell,
                't-caption',
              )}
            >
              {x.side === 'buy' ? t.buy : t.sell}
            </span>
            <span>
              <strong>{x.name}</strong>
              <br />
              <span className={clsx(styles.muted, 't-caption')}>
                {t.qtyPrice(x.qty, won(x.price))}
              </span>
            </span>
            <strong className={clsx(x.pnl !== null && (x.pnl >= 0 ? styles.up : styles.down))}>
              {x.pnl === null ? '—' : signed(x.pnl)}
            </strong>
          </li>
        ))}
      </ul>
      <div className={clsx(r.wide_universe ? styles.warnCard : styles.plainLine)}>
        {r.wide_universe ? (
          <strong className="t-label">
            <AlertTriangle size={16} aria-hidden /> {r.wide_title}
          </strong>
        ) : null}
        <span className="t-caption">{r.survivor_line}</span>
      </div>
      <div className={styles.liveCard}>
        <strong className="t-label">
          {t.liveTitle(r.live_counts.no_buy, r.live_counts.no_sell)}
        </strong>
        <span className={clsx(styles.muted, 't-caption')}>{r.live_note}</span>
      </div>
      <div className={styles.buttons}>
        <Button onClick={onLive}>{t.toLive}</Button>
        <Button onClick={onPaper}>{t.toPaper}</Button>
      </div>
    </div>
  );
}

export function BacktestV2Screen() {
  const params = useParams();
  const id = Number(params.id);
  const navigate = useNavigate();
  const detail = useStrategyDetail(id);
  const vid = detail.data?.version.id ?? null;
  const input = useBacktestInput(vid);
  const [range, setRange] = useState<{ start: string; end: string } | null>(null);
  const [cash, setCash] = useState('10,000,000');
  const [result, setResult] = useState<BacktestV2Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const inp = input.data;
  if (!inp || !detail.data) return null;
  const r = range ?? { start: inp.range.start, end: inp.range.end };
  const amount = Number(cash.replace(/,/g, ''));
  const go = () => {
    setBusy(true);
    setError('');
    runBacktestV2({ version_id: inp.version.id, start: r.start, end: r.end, cash: amount })
      .then(setResult)
      .catch((err: unknown) => {
        setError(isApiError(err) ? err.message : String(err));
      })
      .finally(() => {
        setBusy(false);
      });
  };
  return (
    <div className={styles.page}>
      <button
        type="button"
        className={clsx(styles.back, 't-caption')}
        onClick={() => void navigate(`/strategies/${String(id)}`)}
      >
        <ChevronLeft size={14} aria-hidden />
        {inp.name}
      </button>
      <div className={styles.titleRow}>
        <h1 className={styles.title}>{t.title}</h1>
        <span className={clsx(styles.chip, 't-label')}>
          <GitCommitHorizontal size={14} aria-hidden /> {t.version(inp.version.no)}
        </span>
      </div>
      <div className={styles.cols}>
        <div className={styles.inputCard}>
          <strong className="t-heading-1">{t.inputTitle}</strong>
          <div className={styles.dates}>
            <label className={styles.field}>
              <span className="t-label">{t.start}</span>
              <input
                className={styles.input}
                type="date"
                min={inp.range.first || undefined}
                value={r.start}
                onChange={(e) => {
                  setRange({ ...r, start: e.target.value });
                }}
              />
            </label>
            <label className={styles.field}>
              <span className="t-label">{t.end}</span>
              <input
                className={styles.input}
                type="date"
                value={r.end}
                onChange={(e) => {
                  setRange({ ...r, end: e.target.value });
                }}
              />
            </label>
          </div>
          {inp.range.first ? (
            <p className={clsx(styles.muted, 't-caption')}>
              {t.firstLine(inp.range.first, inp.range.reason)}
            </p>
          ) : null}
          <label className={styles.field}>
            <span className="t-label">{t.cash}</span>
            <span className={styles.cashBox}>
              <input
                className={styles.input}
                inputMode="numeric"
                value={cash}
                onChange={(e) => {
                  const n = Number(e.target.value.replace(/[^\d]/g, ''));
                  setCash(n ? n.toLocaleString() : '');
                }}
              />
              <span className={styles.muted}>{t.won}</span>
            </span>
          </label>
          <p className={clsx(styles.muted, 't-caption')}>{t.cashRange}</p>
          <div className={styles.chips}>
            {inp.chips.map((c) => (
              <span key={c} className={clsx(styles.chipLine, 't-caption')}>
                {c}
              </span>
            ))}
          </div>
          <p className={clsx(styles.muted, 't-caption')}>{inp.judge_line}</p>
          <Button kind="primary" block disabled={busy} onClick={go}>
            {busy ? t.running : t.run}
          </Button>
          {error ? <p className={styles.error}>{error}</p> : null}
        </div>
        {result ? (
          <Result
            r={result}
            onLive={() => void navigate(`/live/start?version=${String(inp.version.id)}`)}
            onPaper={() => void navigate(`/paper/start?version=${String(inp.version.id)}`)}
          />
        ) : (
          <div className={styles.empty}>
            <ChartIcon size={24} aria-hidden />
            <span>{t.emptyTitle}</span>
            <span className={clsx(styles.muted, 't-caption')}>{t.emptyLine}</span>
          </div>
        )}
      </div>
    </div>
  );
}
