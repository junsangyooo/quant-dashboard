// 예정: vertical timeline + '예시'. First '지금 · [상태]' with its stage cards, then the next
// check, holidays, retries and waiting cash; items that do not apply are not drawn.
import clsx from 'clsx';
import type { ReactNode } from 'react';
import type { PlanResponse, Stage } from '../../api/types';
import { LinkButton } from '../../components/Buttons';
import { InfoChip } from '../../components/Chips';
import { ExampleChip } from '../../components/State';
import { planCopy } from '../../copy/plan';
import { StageCard } from './Stages';
import { scheduleItemText, stageFailure, statusLabel } from './words';
import styles from './Plan.module.css';

/** Id of the '지금' entry; rule cards scroll to it. */
export const NOW_ID = 'plan-now';

/** '지금 · 리밸런싱 중', '지금 · 시세 대기 · 주문 0건', '지금 · 일부 실패 · 직접 할 일'. */
export function nowTitle(now: NonNullable<PlanResponse['schedule']['now']>, ai: boolean): string {
  const parts = [planCopy.schedule.now(statusLabel(now.status, ai))];
  if (now.stages.length === 0) parts.push(planCopy.schedule.ordersZero);
  const manual = now.stages.some((s: Stage) => {
    const f = stageFailure(s);
    return f !== null && (f.manual || f.retryAt === null);
  });
  if (manual) parts.push(planCopy.schedule.todo);
  return parts.join(' · ');
}

interface Entry {
  key: string;
  id?: string | undefined;
  accent: boolean;
  body: ReactNode;
}

export function Schedule({ plan, card }: { plan: PlanResponse; card: boolean }) {
  const { now, items } = plan.schedule;
  const entries: Entry[] = [];

  if (now) {
    const rule = plan.rules.find((r) => r.rule.id === now.ruleId)?.rule;
    entries.push({
      key: 'now',
      id: NOW_ID,
      accent: true,
      body: (
        <>
          <p className={clsx('t-body-strong', styles.entryTitle)}>
            {nowTitle(now, rule?.ai ?? false)}
          </p>
          {now.stages.length > 0 ? (
            <div className={styles.stageCards}>
              {now.stages.map((stage) => (
                <StageCard key={stage.kind} stage={stage} />
              ))}
            </div>
          ) : null}
        </>
      ),
    });
  }

  items.forEach((item, i) => {
    const t = scheduleItemText(item);
    // 출금 대기 has no stages: its item is the '지금' of the page.
    const isNow = now === null && i === 0 && item.kind === 'withdraw-wait';
    entries.push({
      key: `${item.kind}-${String(i)}`,
      id: isNow ? NOW_ID : undefined,
      accent: isNow,
      body: (
        <>
          {t.caption !== null ? (
            <p className={clsx('t-caption', styles.muted)}>{t.caption}</p>
          ) : null}
          <p className={clsx('t-body-strong', styles.entryTitle)}>
            <span>{t.title}</span>
            {t.chip !== null ? <InfoChip>{t.chip}</InfoChip> : null}
          </p>
          {t.note !== null ? <p className={clsx('t-caption', styles.muted)}>{t.note}</p> : null}
        </>
      ),
    });
  });

  return (
    <section className={clsx(styles.schedule, card && styles.card)} aria-labelledby="plan-schedule">
      <div className={styles.scheduleHead}>
        <h2 id="plan-schedule" className="t-heading-1">
          {planCopy.schedule.title}
        </h2>
        <ExampleChip show={plan.example} />
      </div>
      <ol className={styles.timeline}>
        {entries.map((e, i) => (
          <li
            key={e.key}
            id={e.id}
            tabIndex={e.id !== undefined ? -1 : undefined}
            className={styles.entry}
          >
            <span className={styles.rail} aria-hidden>
              <span className={clsx(styles.dot, e.accent && styles.dotNow)} />
              {i < entries.length - 1 ? <span className={styles.railLine} /> : null}
            </span>
            <div className={styles.entryBody}>{e.body}</div>
          </li>
        ))}
      </ol>
      <LinkButton to="/rules" className={styles.rulesLink}>
        {planCopy.schedule.rulesLink}
      </LinkButton>
    </section>
  );
}
