// 단계 매도 → 환전 → 매수: the one-line row of the 자산 card and the cards of the 계획 timeline.
// Stages with no orders are not sent, so they never show (명세 어긋남 2).
import clsx from 'clsx';
import { Fragment } from 'react';
import { Link } from 'react-router';
import { ChevronRight, CircleCheck, CircleX, Hourglass, type LucideIcon } from 'lucide-react';
import type { Stage } from '../../api/types';
import { OrderRow } from '../../components/Rows';
import { planCopy } from '../../copy/plan';
import { formatDateTime, formatTime, kstDateKey } from '../../lib/format';
import { orderText, orderTime, stageFailure, stageFill } from './words';
import styles from './Plan.module.css';

const ICON: Record<Stage['status'], { icon: LucideIcon; tone: string | undefined }> = {
  done: { icon: CircleCheck, tone: styles.success },
  pending: { icon: Hourglass, tone: styles.muted },
  failed: { icon: CircleX, tone: styles.error },
};

const ORDER_STATE = { done: 'filled', pending: 'pending', failed: 'failed' } as const;

/** '다시 10/8 22:30' or '직접 할 일' of a failed stage, else its time. */
function stageWhen(stage: Stage): string {
  const failure = stageFailure(stage);
  if (failure) {
    return failure.manual || failure.retryAt === null
      ? planCopy.stage.todo
      : planCopy.stage.retryAt(formatDateTime(failure.retryAt));
  }
  return formatTime(stage.at);
}

/** 자산 card: '✓ 매도 09:05 › ✓ 환전 09:10 › ⏳ 매수 22:30'. */
export function StageRow({ stages }: { stages: readonly Stage[] }) {
  return (
    <ol className={styles.stageRow}>
      {stages.map((stage, i) => (
        <Fragment key={stage.kind}>
          {i > 0 ? (
            <li aria-hidden className={styles.stageArrow}>
              <ChevronRight size={14} />
            </li>
          ) : null}
          <li>
            <OrderRow
              state={ORDER_STATE[stage.status]}
              stateLabel={planCopy.stage.state[stage.status]}
              time={stageWhen(stage)}
            >
              {planCopy.stage.name[stage.kind]}
            </OrderRow>
          </li>
        </Fragment>
      ))}
    </ol>
  );
}

/**
 * 계획 timeline card: head (icon · 매도 / 환전 원→달러 / 매수, fill label and time only on a
 * filled card, 인계 명세 정정) and one order row per order. A failed card is red with
 * '다시 [시각]' or '직접 할 일' (→ 작동). The card opens that day's panel.
 */
export function StageCard({ stage }: { stage: Stage }) {
  const { icon: Icon, tone } = ICON[stage.status];
  const failure = stageFailure(stage);
  const fill = stageFill(stage);
  const manual = failure !== null && (failure.manual || failure.retryAt === null);
  const day = kstDateKey(stage.orders[0]?.at ?? stage.at);
  return (
    <div className={clsx(styles.stageCard, failure && styles.stageFailed)}>
      <div className={styles.stageHead}>
        <Link to={`/day/${day}`} className={styles.stageLink}>
          <Icon size={16} className={tone} aria-hidden />
          <span className="sr-only">{planCopy.stage.state[stage.status]}</span>
          <span className="t-label">{planCopy.stage.cardName[stage.kind]}</span>
        </Link>
        {manual ? (
          <Link to="/health" className={clsx('t-caption', styles.error, styles.todoLink)}>
            {planCopy.stage.todo}
          </Link>
        ) : (
          <span
            className={clsx(styles.stageWhen, 't-caption', failure ? styles.error : styles.muted)}
          >
            {fill !== null ? <span>{fill}</span> : null}
            <span>{stageWhen(stage)}</span>
          </span>
        )}
      </div>
      {stage.orders.map((order) => (
        <OrderRow
          key={order.id}
          className={styles.stageOrder}
          state={order.status}
          stateLabel={planCopy.stage.orderState[order.status]}
          time={orderTime(order)}
        >
          {orderText(order)}
        </OrderRow>
      ))}
    </div>
  );
}
