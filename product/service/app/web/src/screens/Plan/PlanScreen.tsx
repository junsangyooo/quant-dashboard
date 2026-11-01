// MVP-08 계획: 계획 있음 · 계획 없음 · 확인 전 · 이어서 채움 · 지금 확인 중 · 지금 확인(새 일봉 있음 / 없음).
import clsx from 'clsx';
import { useState } from 'react';
import { useNavigate } from 'react-router';
import { Clock, Hourglass } from 'lucide-react';
import { isApiError } from '../../api/client';
import { usePlan, usePost, type JudgeResult, type PlanResponse } from '../../api/mvp';
import { Box } from '../../components/Box';
import { Button } from '../../components/Buttons';
import { Card } from '../../components/Card';
import { StatusTag } from '../../components/Tags';
import { copy } from '../../copy';
import { homeCopy, planCopy as t } from '../../copy/paper';
import { formatMonthDayWeekday, formatTime, kstDateKey } from '../../lib/format';
import { dayTime, isWeekday } from '../../lib/when';
import { Page, Split } from '../../shell/Layout';
import { useDocumentTitle } from '../../shell/page';
import { LoadError } from '../LoadError';
import { fillDay, PlanCard } from '../Paper/PlanRows';
import styles from '../Paper/Paper.module.css';

type Running = Extract<PlanResponse, { running: true }>;

function CheckPanel({
  checking,
  onCheck,
  error,
  boxed,
}: {
  checking: boolean;
  onCheck: () => void;
  error: string | null;
  boxed: boolean;
}) {
  const inner = (
    <>
      {boxed ? <h2 className="t-heading-1">{t.checkNow}</h2> : null}
      <Button kind="default" className="full" disabled={checking} onClick={onCheck}>
        {checking ? t.checking : t.checkNow}
      </Button>
      {checking ? (
        <p className={clsx('t-caption', styles.noteRow)}>
          <Hourglass size={14} className={clsx(styles.noteIcon, 'c-accent')} aria-hidden />
          <span className="c-flat">{t.checkingLine}</span>
        </p>
      ) : null}
      {error ? <p className="t-caption c-error">{error}</p> : null}
      <p className={clsx('t-caption', styles.noteRow)}>
        <Clock size={14} className={styles.noteIcon} aria-hidden />
        {t.autoNote}
      </p>
    </>
  );
  return boxed ? <Card>{inner}</Card> : <div className="stack-inline">{inner}</div>;
}

function Body({ p, result }: { p: Running; result: JudgeResult | null }) {
  const last = p.last;
  const buys = p.plans.filter((x) => x.side === 'buy');
  const sells = p.plans.filter((x) => x.side === 'sell');
  const fill = p.auto.last_fill;
  const filled =
    !result &&
    last?.how === 'auto' &&
    fill?.run_id === p.run_id &&
    fill.to === last.d &&
    fill.new_days > 1
      ? fill
      : null;
  const today = kstDateKey(p.auto.now);
  const checkedToday = last ? kstDateKey(last.made_at) === today || last.d === today : false;
  const before = p.plans.length === 0 && !checkedToday && isWeekday(today);
  const how = last ? t.how[last.how] : '';
  // 시작 뒤 아직 확인하지 않았으면 '마지막 확인' 대신 '첫 확인 … 예정'
  const firstWhen = p.first
    ? `${formatMonthDayWeekday(p.first.check_d)} ${p.first.check_time}`
    : null;

  const notice = result ? (
    result.new_days > 0 ? (
      <Box tone="success" title={t.filledTitle(result.new_days)}>
        {t.newBarLine(formatMonthDayWeekday(result.judged), formatTime(result.at))}
      </Box>
    ) : (
      <Box
        tone="info"
        icon="info"
        title={
          last || !firstWhen
            ? t.noBarTitle(formatMonthDayWeekday(result.judged))
            : t.noBarFirst(firstWhen)
        }
      >
        {t.noBarBody}
      </Box>
    )
  ) : filled ? (
    <Box tone="info" icon="refresh" title={t.filledTitle(filled.new_days)}>
      <span>
        {t.filledRange(
          formatMonthDayWeekday(filled.from ?? filled.to),
          formatMonthDayWeekday(filled.to),
          dayTime(last?.made_at ?? filled.at),
        )}
      </span>
      {(filled.off_days?.length ?? 0) > 0 ? <span>{t.filledBody}</span> : null}
    </Box>
  ) : null;

  const headLine =
    p.plans.length > 0
      ? notice
        ? t.fillOnly(fillDay(p.plans))
        : t.head(dayTime(last?.made_at ?? ''), how, fillDay(p.plans))
      : before || result?.new_days === 0
        ? last
          ? t.lastCheck(dayTime(last.made_at))
          : firstWhen
            ? t.firstPlanned(firstWhen)
            : ''
        : last
          ? t.headNoPlan(dayTime(last.made_at), how)
          : '';

  return (
    <>
      {notice}
      {headLine && result?.new_days !== 0 ? <p className="t-caption c-muted">{headLine}</p> : null}
      {p.plans.length > 0 ? (
        <>
          <PlanCard side="buy" plans={buys} />
          <PlanCard side="sell" plans={sells} />
          {p.keep.length > 0 ? (
            <p className="t-caption c-muted">
              {t.keep(p.keep.length, p.keep.map((k) => k.name).join(' · '))}
            </p>
          ) : null}
        </>
      ) : before ? (
        <Card>
          <h2 className="t-heading-1">{t.beforeTitle}</h2>
          <p className="t-body c-muted">{t.beforeBody}</p>
        </Card>
      ) : (
        <Card>
          <h2 className="t-heading-1">{t.noneTitle}</h2>
          <p className="t-body c-muted">{t.noneBody(p.held)}</p>
        </Card>
      )}
    </>
  );
}

export function PlanScreen() {
  useDocumentTitle(copy.pages.plan);
  const q = usePlan();
  const navigate = useNavigate();
  const judge = usePost<undefined, JudgeResult>('/api/paper/judge');
  const [result, setResult] = useState<JudgeResult | null>(null);
  const p = q.data;
  if (q.isError) return <LoadError onRetry={() => void q.refetch()} />;
  if (!p) return null;

  if (!p.running) {
    return (
      <Page width="narrow">
        <h1 className="t-title">{t.title}</h1>
        <Card>
          <h2 className="t-heading-1">{t.noRunTitle}</h2>
          <p className="t-body c-muted">{t.noRunBody}</p>
          <Button kind="primary" className="full" onClick={() => void navigate('/strategies')}>
            {copy.common.toStrategies}
          </Button>
        </Card>
      </Page>
    );
  }

  const onCheck = () => {
    setResult(null);
    judge.mutate(undefined, {
      onSuccess: (r) => {
        setResult(r);
      },
    });
  };
  const error = judge.error
    ? isApiError(judge.error)
      ? judge.error.message
      : copy.common.noConnection
    : null;
  const panel = (boxed: boolean) => (
    <CheckPanel checking={judge.isPending} onCheck={onCheck} error={error} boxed={boxed} />
  );

  return (
    <Page width="split">
      <h1 className="t-title">{t.title}</h1>
      <Split
        main={
          <>
            <div className={styles.runningRow}>
              <StatusTag kind="paper">{t.running}</StatusTag>
              <span className="t-body-strong">
                {homeCopy.strategyLink(p.strategy, p.version_no)}
              </span>
            </div>
            <Body p={p} result={result} />
            <div className={styles.narrowOnly}>{panel(false)}</div>
          </>
        }
        side={<div className={styles.wideOnly}>{panel(true)}</div>}
      />
    </Page>
  );
}
