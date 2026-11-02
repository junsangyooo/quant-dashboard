// 모의투자 탭(그림 V2-40 목록 · V2-41 상세 · V2-42 시작 창). 모의 숫자는 이 탭 안에서만(R-V5).
import clsx from 'clsx';
import { ChevronLeft, ChevronRight, Clock, Info, X } from 'lucide-react';
import { useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router';
import { isApiError } from '../../api/client';
import {
  startPaper,
  stopPaper,
  usePaperPreview,
  usePaperRun,
  usePaperRuns,
  type PaperRunV2,
} from '../../api/v2';
import { LineChart } from '../../charts/LineChart';
import { LINE_HOME_1440 } from '../../charts/geometry/lineChart';
import { edgeAxis } from '../../charts/geometry/mvpAxis';
import { Button } from '../../components/Buttons';
import { paperV2 as t } from '../../copy/paperV2';
import styles from './PaperV2.module.css';

const won = (v: number) => Math.round(v).toLocaleString();
const pct = (v: number | null) =>
  v === null ? '—' : `${v >= 0 ? '+' : '−'}${Math.abs(v * 100).toFixed(2)}%`;
const signedWon = (v: number) => `${v >= 0 ? '+' : '−'}${won(Math.abs(v))}${t.won}`;
const md = (d: string) => `${String(Number(d.slice(5, 7)))}/${String(Number(d.slice(8, 10)))}`;

function Chips({ run }: { run: PaperRunV2 }) {
  return (
    <>
      <span
        className={clsx(
          styles.chip,
          run.status === 'running' ? styles.chipOn : styles.chipOff,
          't-caption',
        )}
      >
        ● {run.status === 'running' ? t.chipRunning : t.chipEnded}
      </span>
      <span className={clsx(styles.chipVirtual, 't-caption')}>{t.chipVirtual}</span>
    </>
  );
}

function Chart({ run }: { run: PaperRunV2 }) {
  const pts = run.curve.map(([date, v]) => ({ date, value: v }));
  const start = run.curve[0]?.[0] ?? run.started_at.slice(0, 10);
  const end = run.curve.at(-1)?.[0] ?? start;
  const base = pts.map((p) => ({ date: p.date, value: run.cash0 }));
  const axis = edgeAxis([...pts.map((p) => p.value), run.cash0]);
  return (
    <div>
      <strong className="t-label">{t.chartTitle}</strong>
      <LineChart
        layout={LINE_HOME_1440}
        start={start}
        end={end === start ? start : end}
        axis={axis}
        mine={{ key: 'mine', points: pts }}
        baseline={{ key: 'base', points: base }}
        formatDate={md}
        label={t.chartTitle}
      />
      <div className={clsx(styles.legend, 't-caption')}>
        <span>— {t.legendMine}</span>
        <span>···· {t.legendBase}</span>
      </div>
    </div>
  );
}

export function PaperListScreen() {
  const q = usePaperRuns();
  const navigate = useNavigate();
  const runs = q.data?.runs ?? [];
  const live = runs.filter((r) => r.status === 'running');
  const past = runs.filter((r) => r.status === 'ended');
  return (
    <div className={styles.page}>
      <h1 className={styles.title}>{t.title}</h1>
      <p className={clsx(styles.muted, 't-caption')}>{t.lead}</p>
      <strong className="t-heading-1">{t.runningTitle(live.length)}</strong>
      {q.data && live.length === 0 ? (
        <div className={styles.empty}>
          <strong>{t.emptyTitle}</strong>
          <span className={clsx(styles.muted, 't-caption')}>{t.emptyLine}</span>
        </div>
      ) : null}
      <div className={styles.grid}>
        {live.map((r) => (
          <div key={r.id} className={styles.card}>
            <div className={styles.rowBetween}>
              <span className={styles.chips}>
                <Chips run={r} />
                <strong>{t.nameVersion(r.name, r.version_no)}</strong>
              </span>
              <button
                type="button"
                className={clsx(styles.link, 't-caption')}
                onClick={() => void navigate(`/paper/${String(r.id)}`)}
              >
                {t.view} <ChevronRight size={14} aria-hidden />
              </button>
            </div>
            <span className={clsx(styles.muted, 't-caption')}>
              {[t.startLine(won(r.cash0)), r.first_check].filter(Boolean).join(' · ')}
            </span>
            <div className={styles.rowBetween}>
              <span className={styles.amount}>
                {won(r.total)}
                {t.won}{' '}
                {r.trades.length ? (
                  <span
                    className={clsx(r.total >= r.cash0 ? styles.up : styles.down, 't-body-strong')}
                  >
                    {`${signedWon(r.total - r.cash0)} · ${pct(r.return)}`}
                  </span>
                ) : (
                  <span className={clsx(styles.muted, 't-body')}>{t.firstCheck}</span>
                )}
              </span>
              <span className={clsx(styles.muted, 't-caption')}>
                {t.bench(pct(r.bench_return))}
              </span>
            </div>
            <Chart run={r} />
          </div>
        ))}
      </div>
      {past.length ? (
        <div className={styles.past}>
          <strong className="t-heading-1">{t.pastTitle(past.length)}</strong>
          {past.map((r) => (
            <div key={r.id} className={styles.rowBetween}>
              <span className={styles.chips}>
                <span className={clsx(styles.chip, styles.chipOff, 't-caption')}>
                  ● {t.chipEnded}
                </span>
                <strong>{t.nameVersion(r.name, r.version_no)}</strong>
              </span>
              <span className={clsx(r.total >= r.cash0 ? styles.up : styles.down, 't-label')}>
                {t.pastLine(won(r.cash0), won(r.total), pct(r.return))}
              </span>
              <button
                type="button"
                className={clsx(styles.link, 't-caption')}
                onClick={() => void navigate(`/paper/${String(r.id)}`)}
              >
                {t.view}
              </button>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function PaperDetailScreen() {
  const id = Number(useParams().id);
  const navigate = useNavigate();
  const q = usePaperRun(id);
  const [tab, setTab] = useState<'assets' | 'plan' | 'history'>('assets');
  const r = q.data;
  if (!r) return null;
  const evalAmount = r.total - r.cash;
  const recent = [...r.trades].reverse().slice(0, 5);
  return (
    <div className={styles.page}>
      <button
        type="button"
        className={clsx(styles.back, 't-caption')}
        onClick={() => void navigate('/paper')}
      >
        <ChevronLeft size={14} aria-hidden /> {t.back}
      </button>
      <div className={styles.rowBetween}>
        <span className={styles.chips}>
          <h1 className={styles.title}>{t.title}</h1>
          <Chips run={r} />
          <strong>{t.nameVersion(r.name, r.version_no)}</strong>
        </span>
        {r.status === 'running' ? (
          <span className={styles.chips}>
            <Button
              kind="dangerOutline"
              onClick={() => {
                if (window.confirm(t.stopConfirm)) void stopPaper(id).then(() => q.refetch());
              }}
            >
              {t.stop}
            </Button>
            <Button onClick={() => void navigate(`/live/start?paper=${String(id)}`)}>
              {t.toLive}
            </Button>
          </span>
        ) : null}
      </div>
      <div className={clsx(styles.diff, 't-caption')}>
        <Info size={14} aria-hidden /> {r.diff_line}
      </div>
      <div className={styles.chips}>
        {(['assets', 'plan', 'history'] as const).map((k) => (
          <button
            key={k}
            type="button"
            className={clsx(styles.tab, tab === k && styles.tabOn, 't-caption')}
            onClick={() => {
              setTab(k);
            }}
          >
            {t.tabs[k]}
          </button>
        ))}
      </div>
      {tab === 'assets' ? (
        <>
          <div className={styles.cols}>
            <div className={styles.stack}>
              <div className={styles.card}>
                <span className={clsx(styles.muted, 't-caption')}>
                  <span className={clsx(styles.chipVirtual, 't-caption')}>{t.chipVirtual}</span>{' '}
                  {t.assetHead(md(r.curve[0]?.[0] ?? r.started_at.slice(0, 10)))}
                </span>
                <span className={styles.big}>
                  {won(r.total)}
                  {t.won}
                </span>
                <span className="t-caption">
                  <span className={r.total >= r.cash0 ? styles.up : styles.down}>
                    {`${signedWon(r.total - r.cash0)} · ${pct(r.return)}`}
                  </span>{' '}
                  <span className={styles.muted}>{t.startCash(won(r.cash0))}</span>
                </span>
              </div>
              <div className={styles.kvCard}>
                <div className={styles.rowBetween}>
                  <span className={styles.muted}>{t.cash}</span>
                  <strong>
                    {won(r.cash)}
                    {t.won}
                  </strong>
                </div>
                <div className={styles.rowBetween}>
                  <span className={styles.muted}>{t.eval}</span>
                  <strong>
                    {won(evalAmount)}
                    {t.won}
                  </strong>
                </div>
                <div className={styles.rowBetween}>
                  <span className={styles.muted}>{t.benchRow}</span>
                  <strong>{pct(r.bench_return)}</strong>
                </div>
              </div>
            </div>
            <div className={styles.card}>
              <Chart run={r} />
            </div>
          </div>
          <div className={styles.cols}>
            <div className={styles.kvCard}>
              <strong className="t-heading-1">
                <span className={clsx(styles.chipVirtual, 't-caption')}>{t.chipVirtual}</span>{' '}
                {t.holdingsTitle(r.holdings.length)}
              </strong>
              {r.holdings.map((h) => (
                <div key={h.sym} className={styles.rowBetween}>
                  <span className="t-caption">{t.qtyAvg(h.sym, h.qty, won(h.avg))}</span>
                </div>
              ))}
            </div>
            <div className={styles.kvCard}>
              <div className={styles.rowBetween}>
                <strong className="t-heading-1">{t.recentTitle}</strong>
                <button
                  type="button"
                  className={clsx(styles.link, 't-caption')}
                  onClick={() => {
                    setTab('history');
                  }}
                >
                  {t.record}
                </button>
              </div>
              {recent.map((x, i) => (
                <div key={`${x.d}-${x.symbol}-${String(i)}`} className={styles.rowBetween}>
                  <span className="t-caption">{md(x.d)}</span>
                  <span>
                    {x.symbol}{' '}
                    <span
                      className={clsx(
                        styles.side,
                        x.side === 'buy' ? styles.up : styles.down,
                        't-caption',
                      )}
                    >
                      {x.side === 'buy' ? t.buy : t.sell}
                    </span>
                    <br />
                    <span className={clsx(styles.muted, 't-caption')}>
                      {t.qtyPrice(x.qty, won(x.price))}
                    </span>
                  </span>
                  <strong>
                    {won(x.amount)}
                    {t.won}
                  </strong>
                </div>
              ))}
            </div>
          </div>
        </>
      ) : null}
      {tab === 'plan' ? (
        <div className={styles.kvCard}>
          {r.plans.length === 0 ? <span className={styles.muted}>{t.planEmpty}</span> : null}
          {r.plans.map((p, i) => (
            <div key={`${p.sym}-${String(i)}`} className={styles.rowBetween}>
              <span>
                {p.sym}{' '}
                <span
                  className={clsx(
                    styles.side,
                    p.side === 'buy' ? styles.up : styles.down,
                    't-caption',
                  )}
                >
                  {p.side === 'buy' ? t.buy : t.sell}
                </span>
              </span>
              <span className={clsx(styles.muted, 't-caption')}>{p.reason.join(' · ')}</span>
            </div>
          ))}
        </div>
      ) : null}
      {tab === 'history' ? (
        <div className={styles.kvCard}>
          {r.trades.length === 0 ? <span className={styles.muted}>{t.historyEmpty}</span> : null}
          {[...r.trades].reverse().map((x, i) => (
            <div key={`${x.d}-${x.symbol}-${String(i)}`} className={styles.rowBetween}>
              <span className="t-caption">{md(x.d)}</span>
              <span>
                {x.symbol} {x.side === 'buy' ? t.buy : t.sell} · {t.qtyPrice(x.qty, won(x.price))}
              </span>
              <strong>{x.pnl === null ? `${won(x.amount)}${t.won}` : signedWon(x.pnl)}</strong>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function PaperStartScreen() {
  const [params] = useSearchParams();
  const vid = Number(params.get('version') ?? 0);
  const navigate = useNavigate();
  const pv = usePaperPreview(vid);
  const [cash, setCash] = useState('10,000,000');
  const [error, setError] = useState('');
  const p = pv.data;
  if (!p) return null;
  const amount = Number(cash.replace(/,/g, ''));
  return (
    <div className={styles.back2}>
      <div className={styles.sheet} role="dialog" aria-label={t.sheetTitle}>
        <div className={styles.rowBetween}>
          <h1 className={clsx(styles.chips, 't-heading-1')}>
            {t.sheetTitle}{' '}
            <span className={clsx(styles.chipVirtual, 't-caption')}>{t.chipVirtual}</span>
          </h1>
          <button type="button" aria-label={t.cancel} onClick={() => void navigate(-1)}>
            <X size={20} aria-hidden />
          </button>
        </div>
        <div className={styles.rowBetween}>
          <span className={clsx(styles.muted, 't-caption')}>{t.strategy}</span>
          <strong>{t.nameVersion(p.name, p.version_no)}</strong>
        </div>
        <label className={styles.field}>
          <span className="t-label">{t.cashLabel}</span>
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
          <span className={clsx(styles.muted, 't-caption')}>{t.cashRange}</span>
        </label>
        <div className={clsx(styles.kvCard, 't-caption')}>{p.limits}</div>
        {p.already ? (
          <div className={clsx(styles.warn, 't-caption')}>
            <strong>{p.already}</strong>
            {p.running_id ? (
              <button
                type="button"
                className={styles.link}
                onClick={() => void navigate(`/paper/${String(p.running_id)}`)}
              >
                {t.seeRun}
              </button>
            ) : null}
          </div>
        ) : (
          <div className={clsx(styles.diff, 't-caption')}>
            <Clock size={16} aria-hidden />
            <span>
              <strong className="t-label">{p.first_line}</strong>
              <br />
              {p.line}
            </span>
          </div>
        )}
        {error ? <p className={styles.error}>{error}</p> : null}
        <div className={styles.buttons}>
          <Button block onClick={() => void navigate(-1)}>
            {t.cancel}
          </Button>
          <Button
            kind="primary"
            block
            disabled={Boolean(p.already)}
            onClick={() => {
              startPaper(vid, amount)
                .then((r) => navigate(`/paper/${String(r.id)}`))
                .catch((err: unknown) => {
                  setError(isApiError(err) ? err.message : String(err));
                });
            }}
          >
            {t.start}
          </Button>
        </div>
      </div>
    </div>
  );
}
