// 05 자산: 모의투자 전(시작하기 · 예시) · 모의투자 중(포트폴리오 계좌 화면 짜임) · 첫 확인 전 · 보유 0종목 · 끝낸 뒤.
import clsx from 'clsx';
import { useNavigate } from 'react-router';
import { Flag } from 'lucide-react';
import { useExamples, useHome, type HomeResponse } from '../../api/mvp';
import { Button, LinkButton } from '../../components/Buttons';
import { Card } from '../../components/Card';
import { InfoChip } from '../../components/Chips';
import { StatusTag } from '../../components/Tags';
import { copy } from '../../copy';
import { homeCopy as t } from '../../copy/paper';
import {
  formatDateTime,
  formatKrw,
  formatKrwSigned,
  formatMonthDayWeekday,
  formatPercent,
} from '../../lib/format';
import { pct, times, tone, toneClass } from '../../lib/money';
import { runRange, startDay } from '../../lib/runDates';
import { useMediaQuery } from '../../lib/useMedia';
import { dayTime, nextWeekday } from '../../lib/when';
import { Page } from '../../shell/Layout';
import { useDocumentTitle } from '../../shell/page';
import { josa } from '../../graph/rules';
import { AssetChart } from '../Paper/AssetChart';
import { fillDay, PlanSummaryRows } from '../Paper/PlanRows';
import { ExampleCards, StartSteps } from '../Start/StartParts';
import { LoadError } from '../LoadError';
import { Cell, CompositionCard, Contribution, HoldingsCard, RecentCard } from './HomeParts';
import styles from './Home.module.css';
import { J } from '../../copy/particles';

type Running = Extract<HomeResponse, { running: true }>;
type Idle = Extract<HomeResponse, { running: false }>;

function asOf(h: Running): string {
  if (h.last === null) return t.startedAt(formatDateTime(h.started_at));
  if (h.price_as_of.kind === 'toss') return t.asOf(formatDateTime(h.price_as_of.at));
  return t.asOf(formatDateTime(h.last.made_at));
}

function PnlChip({ h }: { h: Running }) {
  const dir = tone(h.pnl);
  if (h.last === null || Math.round(h.pnl) === 0) return <InfoChip>{t.same}</InfoChip>;
  return (
    <span className={clsx(styles.pnlChip, 't-label', toneClass[dir])}>
      {dir === 'flat' ? null : (
        <svg width="12" height="10" viewBox="0 0 12 10" className={styles.triangle} aria-hidden>
          {dir === 'gain' ? <path d="M6 0 12 10H0z" /> : <path d="M6 10 0 0h12z" />}
        </svg>
      )}
      {`${formatKrwSigned(h.pnl)} · ${pct(h.pnl_pct)}`}
    </span>
  );
}

function SummaryCard({ h }: { h: Running }) {
  const first = h.last === null;
  const none = h.holdings.length === 0;
  const dayDir = tone(h.day_pnl ?? h.equity_change ?? 0);
  const pnl = h.stock_value - h.cost;
  let today: [string, string, string | undefined];
  if (first) today = [copy.common.dash, t.beforeFirst, undefined];
  else if (none && h.sold_today > 0 && h.equity_change !== null)
    today = [
      formatKrwSigned(h.equity_change),
      t.todaySold(h.sold_today),
      toneClass[tone(h.equity_change)],
    ];
  else if (none || h.day_pnl === null) today = [copy.common.dash, t.noHoldings, undefined];
  else today = [formatKrwSigned(h.day_pnl), t.todayLine(pct(h.day_pct ?? 0)), toneClass[dayDir]];
  return (
    <Card className={styles.summary}>
      <div className={styles.rowBetween}>
        <p className="t-caption c-muted">{t.labelSince(startDay(h))}</p>
        <InfoChip>{asOf(h)}</InfoChip>
      </div>
      <p className={styles.display}>{formatKrw(h.total)}</p>
      <div className={styles.chips}>
        <PnlChip h={h} />
        <InfoChip>{t.principal(formatKrw(h.cash0))}</InfoChip>
      </div>
      <div className={styles.runningRow}>
        <StatusTag kind="paper">{t.running}</StatusTag>
        <LinkButton to={`/strategies/${String(h.strategy_id)}`}>
          {t.strategyLink(h.strategy, h.version_no)}
        </LinkButton>
      </div>
      <hr className={styles.rule} />
      <div className={styles.cells}>
        <Cell label={t.today} value={today[0]} line={today[1]} cls={today[2]} />
        <Cell
          label={t.pnl}
          value={none ? copy.common.dash : formatKrwSigned(pnl)}
          line={none ? t.noHoldings : pct(h.cost ? pnl / h.cost : 0)}
          cls={none ? undefined : toneClass[tone(pnl)]}
        />
        <Cell
          label={t.cash}
          value={formatKrw(h.cash)}
          line={t.cashShare(formatPercent((h.cash / h.total) * 100, 1))}
        />
        <Cell label={t.value} value={formatKrw(h.stock_value)} line={t.cost(formatKrw(h.cost))} />
      </div>
      {!none && !first ? (
        <>
          <hr className={styles.rule} />
          <Contribution holdings={h.holdings} />
        </>
      ) : null}
    </Card>
  );
}

function PlanCard({ h }: { h: Running }) {
  const first = h.first;
  let line: string;
  if (h.last === null && first)
    line = t.planFirst(
      `${formatMonthDayWeekday(first.check_d)} ${first.check_time}`,
      formatMonthDayWeekday(first.fill_d),
    );
  else if (h.plans.length > 0 && h.last)
    line = t.planHead(dayTime(h.last.made_at), fillDay(h.plans));
  else if (h.last)
    line = t.planNone(dayTime(h.last.made_at), formatMonthDayWeekday(nextWeekday(h.last.d)));
  else line = '';
  return (
    <Card className={styles.plan}>
      <div className={styles.rowBetween}>
        <h2 className="t-heading-1">{t.planTitle}</h2>
        <LinkButton to="/plan">{t.planLink}</LinkButton>
      </div>
      <p className="t-caption c-muted">{line}</p>
      {h.plans.length > 0 ? <PlanSummaryRows plans={h.plans} /> : null}
    </Card>
  );
}

function emptyHoldings(h: Running): string {
  const first = h.first;
  if (h.last === null && first)
    return t.emptyFirst(`${formatMonthDayWeekday(first.check_d)} ${first.check_time}`);
  const lastDay = h.curve.at(-1)?.[0];
  const sold = h.recent.filter((x) => x.side === 'sell' && x.d === lastDay);
  if (sold.length > 0 && lastDay) {
    const reasons = sold.map((x) => x.reasons[0]?.display ?? '');
    const circle = sold[0]?.reasons[0]?.circle ?? '';
    const same = reasons.every((r) => r && r === reasons[0]);
    return same
      ? t.emptySoldSame(
          sold.length,
          josa(`${circle} ${reasons[0] ?? ''}`, J.iga),
          formatMonthDayWeekday(lastDay),
        )
      : t.emptySold(sold.length, formatMonthDayWeekday(lastDay));
  }
  return t.emptyIdle;
}

function RunningView({ h }: { h: Running }) {
  const wide = useMediaQuery('(min-width: 900px)');
  const first = h.last === null;
  const firstLine = h.first
    ? `${formatMonthDayWeekday(h.first.check_d)} ${h.first.check_time}`
    : '';
  const priceNote = h.price_as_of.kind === 'toss' ? t.tossPrice : t.yahooPrice;
  return (
    <Page width="split">
      <div className={styles.row1}>
        <SummaryCard h={h} />
        <div className={styles.col}>
          <AssetChart
            curve={h.curve}
            cash0={h.cash0}
            title={t.chartTitle}
            emptyText={first ? t.firstChart(firstLine) : undefined}
          />
          <PlanCard h={h} />
        </div>
      </div>
      <div className={styles.row2}>
        <HoldingsCard
          holdings={h.holdings}
          priceNote={priceNote}
          wide={wide}
          empty={emptyHoldings(h)}
        />
        <div className={styles.col}>
          <CompositionCard holdings={h.holdings} cash={h.cash} />
          <RecentCard
            trades={h.recent}
            none={
              first && h.first ? t.recentNone(formatMonthDayWeekday(h.first.fill_d)) : undefined
            }
          />
        </div>
      </div>
    </Page>
  );
}

function EndedView({ h }: { h: Idle }) {
  const navigate = useNavigate();
  const run = h.last_run;
  if (!run) return null;
  const range = runRange(run);
  return (
    <Page width="split">
      <div className={styles.row1}>
        <Card className={styles.summary}>
          <div className="stack-tight">
            <p className="t-caption c-muted">{t.label}</p>
            <h1 className={clsx('t-title', styles.muted)}>{t.noRun}</h1>
          </div>
          <div className={styles.endBox}>
            <Flag size={18} aria-hidden />
            <div className="stack-tight">
              <p className="t-body-strong">{t.ended}</p>
              <p className="t-caption">
                {t.endedLine(
                  dayTime(run.ended_at ?? run.started_at),
                  run.last_eval_d ? formatMonthDayWeekday(run.last_eval_d) : '',
                  run.held_end,
                )}
              </p>
            </div>
          </div>
          <hr className={styles.rule} />
          <p className="t-label">{t.pastHead(run.strategy, run.version_no, range)}</p>
          <div className={styles.cells}>
            <Cell
              label={t.lastTotal}
              value={formatKrw(run.final)}
              line={t.vsPrincipal(pct(run.ret))}
            />
            <Cell
              label={t.realized}
              value={formatKrwSigned(run.realized)}
              line={t.afterCost}
              cls={toneClass[tone(run.realized)]}
            />
            <Cell
              label={t.tradesTitle}
              value={times(run.trades_count)}
              line={t.buySell(run.buys, run.sells)}
            />
            <Cell label={t.costs} value={formatKrw(run.costs)} line={t.costsLine} />
          </div>
          <LinkButton to={`/history?run=${String(run.id)}`}>{t.toHistory}</LinkButton>
        </Card>
        <div className={styles.col}>
          <AssetChart
            curve={run.curve}
            cash0={run.cash0}
            title={t.pastChartTitle}
            periods={false}
          />
          <Card>
            <p className="t-body">{t.newRun}</p>
            <Button kind="primary" className="full" onClick={() => void navigate('/strategies')}>
              {copy.common.toStrategies}
            </Button>
          </Card>
          <RecentCard trades={h.recent ?? []} />
        </div>
      </div>
    </Page>
  );
}

function BeforeView({ h }: { h: Idle }) {
  const examples = useExamples().data?.examples ?? [];
  return (
    <Page width="split">
      <div className={styles.before}>
        <div className={clsx('stack-tight', styles.beforeHead)}>
          <p className="t-caption c-muted">{t.label}</p>
          <h1 className={clsx(styles.display, styles.muted)}>{t.before}</h1>
        </div>
        <div className={styles.beforeSide}>
          <StartSteps steps={h.steps} layout="column" />
        </div>
        <div className={styles.beforeMain}>
          <ExampleCards examples={examples} columns={2} />
        </div>
        <div className={styles.emptyBand}>
          <span className="t-caption">{t.emptyChart}</span>
        </div>
      </div>
    </Page>
  );
}

export function HomeScreen() {
  useDocumentTitle(copy.pages.home);
  const q = useHome();
  const h = q.data;
  if (q.isError) return <LoadError onRetry={() => void q.refetch()} />;
  if (!h) return null;
  if (h.running) return <RunningView h={h} />;
  if (h.last_run) return <EndedView h={h} />;
  return <BeforeView h={h} />;
}
