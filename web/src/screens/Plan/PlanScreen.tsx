// SCR-PLAN 계획 (기획 §5): 규칙별 자산 비중 막대 → 규칙 카드 → 예정 → 규칙 그림 보기 → 벗어남 흐름
// (390); 1440 puts the cards (each with its own drift chart) left and 예정 in a card right.
import clsx from 'clsx';
import { useState } from 'react';
import { useLedger, useNow, usePlan } from '../../api/queries';
import type { DriftPeriod, PlanResponse } from '../../api/types';
import { Gauge } from '../../charts/Gauge';
import type { ChartEvent } from '../../charts/geometry/lineChart';
import { PeriodChip } from '../../components/Chips';
import { ErrorBlock, OfflineChip, Skeleton, SkeletonBlock } from '../../components/State';
import { copy } from '../../copy';
import { planCopy } from '../../copy/plan';
import { formatMonthDay, formatPercent } from '../../lib/format';
import { pageTitle, useDocumentTitle } from '../../shell/page';
import { EventListSheet } from '../Home/EventListSheet';
import { WIDE, useMediaQuery } from '../Home/useMedia';
import { DriftPlot, driftSeries } from './Drift';
import { RuleCard } from './RuleCard';
import { NOW_ID, Schedule } from './Schedule';
import { ruleName, toneMap } from './words';
import styles from './Plan.module.css';

/** Scroll to an element and move focus there (respects reduced motion). */
export function revealElement(id: string): void {
  const el = document.getElementById(id);
  if (!el) return;
  const reduce =
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  el.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
  el.focus({ preventScroll: true });
}

function RuleShares({ shares }: { shares: NonNullable<PlanResponse['ruleShares']> }) {
  const total = shares.reduce((s, r) => s + r.pct, 0) || 1;
  return (
    <section className={styles.ruleShares} aria-labelledby="plan-rule-shares">
      <h2 id="plan-rule-shares" className={clsx('t-caption', styles.muted)}>
        {planCopy.ruleShares}
      </h2>
      <div className={styles.shareBar}>
        {shares.map(({ rule, pct }) => (
          <button
            key={rule.id}
            type="button"
            className={clsx(styles.shareSeg, styles[`strategy-${rule.colorIndex === 0 ? 1 : 2}`])}
            style={{ flexGrow: pct / total }}
            aria-label={`${ruleName(rule)} ${formatPercent(pct)}`}
            onClick={() => {
              revealElement(`rule-${rule.id}`);
            }}
          >
            <span className={styles.shareFill} />
          </button>
        ))}
      </div>
      <ul className={styles.legend}>
        {shares.map(({ rule }) => (
          <li key={rule.id} className={styles.legendItem}>
            <span
              className={clsx(styles.legendDot, styles[`dot-${rule.colorIndex === 0 ? 1 : 2}`])}
              aria-hidden
            />
            <span className="t-caption">{ruleName(rule)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function DriftSection({
  plan,
  onPeriod,
  onGroup,
}: {
  plan: PlanResponse;
  onPeriod: (p: DriftPeriod) => void;
  onGroup: (events: ChartEvent[]) => void;
}) {
  const drift = plan.drift;
  const rules = plan.rules.map((r) => r.rule);
  const series = driftSeries(drift, rules);
  return (
    <section className={styles.drift} aria-labelledby="plan-drift">
      <div className={styles.driftHead}>
        <h2 id="plan-drift" className="t-heading-1">
          {planCopy.drift.title}
        </h2>
        {drift.empty === null && drift.periods !== null ? (
          <div className={styles.chips} role="group" aria-label={planCopy.drift.periodGroup}>
            {drift.periods.map((p) => (
              <PeriodChip
                key={p}
                selected={p === drift.period}
                onClick={() => {
                  onPeriod(p);
                }}
              >
                {planCopy.drift.periods[p]}
              </PeriodChip>
            ))}
          </div>
        ) : drift.empty === null ? (
          <span className={clsx('t-caption', styles.muted)}>
            {planCopy.drift.since(formatMonthDay(drift.since))}
          </span>
        ) : null}
      </div>
      {drift.empty !== null || series.length === 0 ? (
        <p className={clsx('t-caption', styles.muted)}>{planCopy.drift.secondDay}</p>
      ) : (
        <>
          <DriftPlot drift={drift} rules={rules} size="390" onGroup={onGroup} />
          <ul className={styles.legend}>
            {series.map((s) => {
              const rule = rules.find((r) => r.id === s.key);
              return (
                <li key={s.key} className={styles.legendItem}>
                  <svg className={styles.swatch} viewBox="0 0 16 8" aria-hidden>
                    <line
                      className={s.tone === 1 ? styles.swatch1 : styles.swatch2}
                      x1="0"
                      y1="4"
                      x2="16"
                      y2="4"
                      strokeWidth="2"
                    />
                  </svg>
                  <span className={clsx('t-caption', styles.muted)}>
                    {rule ? ruleName(rule) : s.key}
                  </span>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </section>
  );
}

function PlanSkeleton({ wide }: { wide: boolean }) {
  const card = (key: number) => (
    <div key={key} className={clsx(styles.card, styles.ruleCard)}>
      <div className={styles.ruleMain}>
        <div className={styles.nameRow}>
          <Skeleton text="heading-1" width={96} />
          <Skeleton text="heading-1" width={140} />
        </div>
        <Skeleton text="label" width={220} />
        <div className={styles.gaugeBlock}>
          <div className={styles.gaugeArt}>
            <Gauge value={null} label={planCopy.gauge.empty} />
          </div>
          <div className={styles.gaugeText}>
            <Skeleton text="caption" width={110} />
            <Skeleton text="label" width={88} />
            <Skeleton text="title" width={80} />
            <Skeleton text="caption" width={106} />
          </div>
        </div>
        <Skeleton text="caption" width="100%" />
        <Skeleton text="caption" width="100%" />
      </div>
      {wide ? <SkeletonBlock height={218} className={styles.cardChart} /> : null}
    </div>
  );
  const schedule = (
    <div className={clsx(styles.schedule, wide && styles.card)}>
      <div className={styles.scheduleHead}>
        <h2 className="t-heading-1">{planCopy.schedule.title}</h2>
      </div>
      <Skeleton text="body" width={140} />
      <SkeletonBlock height={160} />
      <Skeleton text="body" width={120} />
      <Skeleton text="body" width={160} />
    </div>
  );
  return (
    <div className={styles.columns}>
      <div className={styles.left}>{[0, 1].map(card)}</div>
      <div className={styles.right}>{schedule}</div>
    </div>
  );
}

export function PlanScreen() {
  useDocumentTitle(pageTitle('plan'));
  const [drift, setDrift] = useState<DriftPeriod | undefined>(undefined);
  const [group, setGroup] = useState<ChartEvent[] | null>(null);
  const plan = usePlan(drift ? { drift } : {});
  const now = useNow();
  const wide = useMediaQuery(WIDE);
  const ledger = useLedger();
  // Keep the previous answer of the same ledger while another drift period loads (no flash);
  // a ledger switch (another device) drops it so the skeleton shows.
  const [kept, setKept] = useState<PlanResponse | null>(null);
  if (plan.data && plan.data !== kept) setKept(plan.data);
  const data = plan.data ?? (kept !== null && kept.ledger === ledger ? kept : null);

  let body;
  if (data) {
    const tones = toneMap(data.rules.flatMap((r) => r.rows.map((row) => row.instrument)));
    const nowRule =
      data.schedule.now?.ruleId ??
      (data.schedule.items[0]?.kind === 'withdraw-wait' ? 'withdraw-wait' : null);
    const cards = data.rules.map((card) => (
      <RuleCard
        key={card.rule.id}
        card={card}
        plan={data}
        now={now}
        tones={tones}
        wide={wide}
        onGroup={setGroup}
        onShowNow={
          nowRule === card.rule.id ||
          (nowRule === 'withdraw-wait' && card.status === 'withdraw-wait')
            ? () => {
                revealElement(NOW_ID);
              }
            : undefined
        }
      />
    ));
    const shares =
      data.ruleShares && data.ruleShares.filter((s) => s.pct > 0).length >= 2 ? (
        <RuleShares shares={data.ruleShares} />
      ) : null;
    body = (
      <div className={styles.columns}>
        <div className={styles.left}>
          {shares}
          {cards}
        </div>
        <div className={styles.right}>
          <Schedule plan={data} card={wide} />
          {!wide ? <DriftSection plan={data} onPeriod={setDrift} onGroup={setGroup} /> : null}
        </div>
      </div>
    );
  } else if (plan.isError) {
    body = (
      <ErrorBlock
        message={planCopy.errors.load}
        onRetry={() => void plan.refetch()}
        retrying={plan.isFetching}
      />
    );
  } else {
    body = <PlanSkeleton wide={wide} />;
  }

  return (
    <div className={styles.page}>
      <h1 className="sr-only">{copy.pages.plan}</h1>
      <div className={styles.offline}>
        <OfflineChip />
      </div>
      {body}
      {group ? (
        <EventListSheet
          events={group}
          onClose={() => {
            setGroup(null);
          }}
        />
      ) : null}
    </div>
  );
}
