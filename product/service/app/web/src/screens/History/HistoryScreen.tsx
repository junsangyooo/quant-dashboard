// MVP-09 기록: 거래 있음 · 빈 상태 · 지난 실행 · 거래 0회. 머리에 실행 고르기(지금 실행 / 지난 실행).
import clsx from 'clsx';
import { useSearchParams } from 'react-router';
import { useRun, useRuns, type RunRow, type RunView } from '../../api/mvp';
import { LinkButton } from '../../components/Buttons';
import { Card } from '../../components/Card';
import { PeriodChip } from '../../components/Chips';
import { Dots } from '../../components/Dots';
import { SideTag } from '../../components/Tags';
import { copy } from '../../copy';
import { historyCopy as t } from '../../copy/paper';
import { formatKrw, formatKrwSigned, formatMonthDayWeekday } from '../../lib/format';
import { pct, shares, times, tone, toneClass } from '../../lib/money';
import { runRange as runRangeOf, startDay } from '../../lib/runDates';
import { Page } from '../../shell/Layout';
import { useDocumentTitle } from '../../shell/page';
import { LoadError } from '../LoadError';
import styles from '../Paper/Paper.module.css';

function reasonLine(trade: RunView['trades'][number]): string {
  return trade.reasons.map((r) => `${r.circle} ${r.display}`.trim()).join(' · ');
}

function runRange(r: RunRow): string {
  return runRangeOf(r);
}

/** '10/29(목) 16:30' — 서버가 시작할 때 정한 첫 확인. */
function firstLine(v: RunView): string {
  if (v.first) return `${formatMonthDayWeekday(v.first.check_d)} ${v.first.check_time}`;
  return formatMonthDayWeekday(v.first_d ?? v.started_at);
}

function Pnl({ value }: { value: number | null }) {
  if (value === null) return <span className="t-body c-muted">{copy.common.dash}</span>;
  return (
    <span className={clsx('t-body-strong', toneClass[tone(value)])}>{formatKrwSigned(value)}</span>
  );
}

function Tiles({ run }: { run: RunView }) {
  return (
    <div className={styles.tiles}>
      <div className={styles.tile}>
        <span className="t-caption c-muted">{t.realized}</span>
        <span
          className={clsx(
            't-body-strong',
            tone(run.realized) !== 'flat' && toneClass[tone(run.realized)],
          )}
        >
          {formatKrwSigned(run.realized)}
        </span>
        <span className="t-label">{t.afterCost}</span>
      </div>
      <div className={styles.tile}>
        <span className="t-caption c-muted">{t.trades}</span>
        <span className="t-body-strong">{times(run.trades_count)}</span>
        <span className="t-label">
          <Dots parts={t.buySell(run.buys, run.sells)} />
        </span>
      </div>
      <div className={styles.tile}>
        <span className="t-caption c-muted">{t.costs}</span>
        <span className="t-body-strong">{formatKrw(run.costs)}</span>
        <span className="t-label">{t.costsLine}</span>
      </div>
    </div>
  );
}

function TradeRows({ run }: { run: RunView }) {
  return (
    <ul className={clsx(styles.tradeList, styles.narrowOnly)}>
      {run.trades.map((x, i) => (
        <li key={`${x.d}-${x.sym}-${String(i)}`} className={styles.tradeRow}>
          <span className="t-caption c-muted">{formatMonthDayWeekday(x.d)}</span>
          <div className={styles.tradeMain}>
            <span className={styles.tradeName}>
              <SideTag side={x.side} />
              <span className="t-body-strong">{x.name}</span>
            </span>
            <span className="t-caption">
              <Dots parts={t.priceQty(x.sym, formatKrw(x.price), shares(x.qty))} />
            </span>
            <span className="t-caption c-muted">
              {[t.reasonLabel, ...x.reasons.map((r) => `${r.circle} ${r.display}`)].join(' · ')}
            </span>
          </div>
          <Pnl value={x.side === 'sell' ? x.pnl : null} />
        </li>
      ))}
    </ul>
  );
}

function TradeTable({ run }: { run: RunView }) {
  const c = t.cols;
  return (
    <table className={clsx(styles.table, styles.wideTable)}>
      <thead className="t-caption">
        <tr>
          <th>{c.date}</th>
          <th>{c.stock}</th>
          <th>{c.side}</th>
          <th className={styles.num}>{c.price}</th>
          <th className={styles.num}>{c.qty}</th>
          <th className={styles.num}>{c.pnl}</th>
          <th>{c.reason}</th>
        </tr>
      </thead>
      <tbody>
        {run.trades.map((x, i) => (
          <tr key={`${x.d}-${x.sym}-${String(i)}`}>
            <td className="t-caption c-muted">{formatMonthDayWeekday(x.d)}</td>
            <td>
              <span className="t-body-strong">{x.name}</span>{' '}
              <span className="t-caption c-muted">{x.sym}</span>
            </td>
            <td>
              <SideTag side={x.side} />
            </td>
            <td className={clsx('t-body', styles.num)}>{formatKrw(x.price)}</td>
            <td className={clsx('t-body', styles.num)}>{shares(x.qty)}</td>
            <td className={styles.num}>
              <Pnl value={x.side === 'sell' ? x.pnl : null} />
            </td>
            <td className="t-caption c-muted">{reasonLine(x)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function runLine(run: RunView): string[] {
  const since = startDay(run);
  if (run.status === 'running') return t.runLine(run.strategy, run.version_no, since);
  const range = runRangeOf(run);
  return t.pastLine(run.strategy, run.version_no, range, formatKrw(run.final), pct(run.ret ?? 0));
}

export function HistoryScreen() {
  useDocumentTitle(copy.pages.history);
  const [params, setParams] = useSearchParams();
  const runs = useRuns();
  const list: RunRow[] = runs.data?.runs ?? [];
  const asked = Number(params.get('run'));
  const chosen = list.find((r) => r.id === asked) ?? list[0] ?? null;
  const run = useRun(chosen?.id ?? null);
  if (runs.isError) return <LoadError onRetry={() => void runs.refetch()} />;
  if (!runs.data) return null;

  if (!chosen) {
    return (
      <Page width="wide">
        <h1 className="t-title">{t.title}</h1>
        <Card>
          <h2 className="t-heading-1">{t.emptyTitle}</h2>
          <p className="t-body c-muted">{t.emptyBody}</p>
          <LinkButton to="/strategies">{copy.common.toStrategies}</LinkButton>
        </Card>
      </Page>
    );
  }

  const v = run.data;
  return (
    <Page width="wide">
      <h1 className="t-title">{t.title}</h1>
      <div className={styles.chips} role="group">
        {list.map((r) => (
          <PeriodChip
            key={r.id}
            selected={r.id === chosen.id}
            onClick={() => {
              setParams({ run: String(r.id) }, { replace: true });
            }}
          >
            {r.status === 'running' ? t.current(r.version_no) : t.past(r.version_no, runRange(r))}
          </PeriodChip>
        ))}
      </div>
      {v ? (
        <>
          <p className="t-caption c-muted">
            <Dots parts={runLine(v)} />
          </p>
          <Tiles run={v} />
          {v.trades.length === 0 ? (
            <Card>
              <h2 className="t-heading-1">{t.zeroTitle}</h2>
              <p className="t-body c-muted">{t.zeroBody(firstLine(v))}</p>
            </Card>
          ) : (
            <>
              {v.status === 'running' ? <p className="t-label">{t.formula}</p> : null}
              <div className={styles.cardHead}>
                <h2 className="t-heading-1">{t.list}</h2>
                <span className="t-caption c-muted">{t.count(v.trades_count)}</span>
              </div>
              {v.trades.some((x) => x.reasons.length > 1) ? (
                <p className="t-caption c-muted">{t.reasonRule}</p>
              ) : null}
              <TradeRows run={v} />
              <TradeTable run={v} />
            </>
          )}
        </>
      ) : null}
    </Page>
  );
}
