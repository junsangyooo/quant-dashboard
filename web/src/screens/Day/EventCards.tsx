// 그날 사건 카드 (Figma 1:59915 '사건 리밸런싱'): head (marker · name · rule · ✓✓✓) → 전후 비중 →
// one card per order (✓ · 시장 · 시각 · 종목 수량 · 가격 · 금액 · 수수료 · 체결 라벨) → 수수료 합계.
// 입출금 · 배당 · 시작 · 실전 켬/끔 cards have no drawing (기획 §5 문구), nor does the AI 판단 card,
// which reuses the node card language (노드/D, kind = AI 판단) of the 규칙 screen.
import clsx from 'clsx';
import {
  ArrowLeftRight,
  CircleCheck,
  CircleMinus,
  CirclePlus,
  CircleX,
  Hourglass,
  Power,
  type LucideIcon,
} from 'lucide-react';
import type { ReactNode } from 'react';
import { eventName, markerKind } from '../../api/adapters';
import type { DayEvent, Order, RuleRef, Stage } from '../../api/types';
import { Flag, InitialLogo, KindBadge, type Country } from '../../components/Badges';
import { LinkButton } from '../../components/Buttons';
import { InfoChip } from '../../components/Chips';
import { EventMarker } from '../../components/Markers';
import { NodeCard, NodeRow, NodeRowLabel } from '../../components/NodeCard';
import { Text } from '../../components/Text';
import { CompositionBar, type SegmentTone } from '../../charts/CompositionBar';
import { dayCopy as dc } from '../../copy/day';
import { failureCopy, fillCopy, historyCopy } from '../../copy/history';
import {
  formatDateTime,
  formatKrw,
  formatMonthDay,
  formatPercent,
  formatPpMagnitude,
  formatTime,
} from '../../lib/format';
import { MiniStages, RuleDot } from '../History/EventList';
import { treatmentLabel } from '../History/historyModel';
import { logoTone } from '../History/tones';
import {
  fxDirection,
  judgmentLine,
  orderFoot,
  orderHead,
  orderMain,
  orderTime,
  stageOrders,
  tokensLabel,
  votesLabel,
} from './dayModel';
import styles from './Day.module.css';

const SIDE_ICON: Record<Order['side'], LucideIcon> = {
  sell: CircleMinus,
  fx: ArrowLeftRight,
  buy: CirclePlus,
};

const STATUS_ICON: Record<Order['status'], LucideIcon> = {
  filled: CircleCheck,
  pending: Hourglass,
  failed: CircleX,
};

export function OrderCard({
  order,
  direction,
}: {
  order: Order;
  direction: 'krw-usd' | 'usd-krw';
}) {
  const SideIcon = SIDE_ICON[order.side];
  const StatusIcon = STATUS_ICON[order.status];
  const failed = order.status === 'failed';
  const retried = order.retried;
  const fx = order.direction ?? direction;
  const head = orderHead(order, fx);
  const foot = orderFoot(order);
  return (
    <li className={clsx(styles.order, failed && styles.orderFailed)}>
      <span className={styles.orderIcon} aria-hidden>
        <SideIcon size={18} />
      </span>
      <div className={styles.orderBody}>
        <p className={styles.orderHead}>
          <StatusIcon size={14} className={styles[`status-${order.status}`]} aria-hidden />
          <span className="sr-only">{dc.stage.status[order.status]}</span>{' '}
          <span className={clsx('t-label', styles.grow)}>{head}</span>
          <span className="t-label">{orderTime(order)}</span>
        </p>
        <p className="t-body">{orderMain(order, fx)}</p>
        <div className={styles.orderFoot}>
          <span className={clsx('t-caption', styles.muted, styles.grow)}>{foot}</span>
          {order.status === 'filled' && order.fill ? (
            <KindBadge>{fillCopy[order.fill]}</KindBadge>
          ) : null}
        </div>
        {failed ? (
          <div className={styles.orderFail}>
            {order.failure && order.failure.reason !== 'other' ? (
              <span className={clsx('t-caption', styles.errorText)}>
                {failureCopy[order.failure.reason]}
              </span>
            ) : null}
            {retried?.status === 'filled' ? (
              <InfoChip>{dc.stage.retried(formatMonthDay(retried.at))}</InfoChip>
            ) : order.failure?.retryAt ? (
              <span className="t-caption">
                {dc.stage.retry(formatDateTime(order.failure.retryAt))}
              </span>
            ) : order.failure?.manual ? (
              <LinkButton to="/health">{dc.stage.todo}</LinkButton>
            ) : null}
          </div>
        ) : null}
      </div>
    </li>
  );
}

function OrderList({ stages }: { stages: readonly Stage[] }) {
  const direction = fxDirection(stages);
  const items = stageOrders(stages);
  if (items.length === 0) return null;
  return (
    <ul className={styles.orders}>
      {items.map(({ order }) => (
        <OrderCard key={order.id} order={order} direction={direction} />
      ))}
    </ul>
  );
}

function FeesTotal({ krw }: { krw: number }) {
  return (
    <p className={styles.feesTotal}>
      <span className="t-label">{dc.feesTotal(formatKrw(krw))}</span>
      <span className={clsx('t-caption', styles.muted)}>{dc.feesNote}</span>
    </p>
  );
}

function segmentTone(colorIndex: number, i: number): SegmentTone {
  return `cat-${String(logoTone(colorIndex, i))}` as SegmentTone;
}

function Weights({ event }: { event: Extract<DayEvent, { weights: unknown }> }) {
  const { instruments, before, after, target, threshold } = event.weights;
  const colorIndex = event.rule.colorIndex;
  const two = instruments.length === 2;
  const t0 = target[0];
  const bar = (values: readonly number[], when: string) => (
    <CompositionBar
      barHeight={24}
      height={32}
      target={
        two && t0 !== undefined
          ? { at: t0 / 100, band: [(t0 - threshold) / 100, (t0 + threshold) / 100] }
          : undefined
      }
      label={dc.weights.bar(
        when,
        instruments.map((inst, i) => `${inst.name} ${formatPercent(values[i] ?? 0)}`).join(' · '),
      )}
      segments={instruments.map((inst, i) => {
        const tone = segmentTone(colorIndex, i);
        return {
          key: inst.id,
          value: values[i] ?? 0,
          tone,
          label: formatPercent(values[i] ?? 0),
          labelTone:
            tone === 'cat-1' || tone === 'cat-4' ? ('inverse' as const) : ('primary' as const),
        };
      })}
    />
  );
  return (
    <div className={styles.weights}>
      <p className={styles.weightsHead}>
        <span className="t-label">{dc.weights.title}</span>
        <span className={clsx('t-caption', styles.muted)}>{dc.weights.note}</span>
      </p>
      <div className={styles.weightRow}>
        <span className={clsx('t-label', styles.muted, styles.weightWhen)}>
          {dc.weights.before}
        </span>
        <div className={styles.weightBar}>{bar(before, dc.weights.before)}</div>
      </div>
      <div className={styles.weightRow}>
        <span className={clsx('t-label', styles.muted, styles.weightWhen)}>{dc.weights.after}</span>
        <div className={styles.weightBar}>{bar(after, dc.weights.after)}</div>
      </div>
      <div className={styles.weightScale}>
        {two && t0 !== undefined ? (
          <span
            className={clsx('t-micro', styles.muted, styles.scaleMark)}
            style={{ left: `${String(t0)}%` }}
          >
            {dc.weights.target(formatPercent(t0, 0), formatPpMagnitude(threshold, 0))}
          </span>
        ) : (
          <span className={clsx('t-micro', styles.muted)}>
            {dc.weights.targets(
              target.map((v) => String(v)).join(' · '),
              formatPpMagnitude(threshold, 0),
            )}
          </span>
        )}
      </div>
      <ul className={styles.legend}>
        {instruments.map((inst, i) => (
          <li key={inst.id} className={styles.legendItem}>
            <InitialLogo initials={inst.initials} size={20} tone={logoTone(colorIndex, i)} />
            <span className="t-caption">{inst.name}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function EventHead({
  marker,
  title,
  rule,
  right,
}: {
  marker: ReactNode;
  title: string;
  rule?: RuleRef | undefined;
  right?: ReactNode;
}) {
  return (
    <div className={styles.eventHead}>
      {marker}
      <div className={styles.eventTitle}>
        <h3 className="t-body-strong">{title}</h3>
        {rule ? <RuleDot rule={rule} /> : null}
      </div>
      {right}
    </div>
  );
}

function Marker({ event }: { event: DayEvent }) {
  const kind = markerKind(event.kind);
  if (event.kind === 'live-on' || event.kind === 'live-off') {
    return (
      <span className={styles.powerMarker} aria-hidden>
        <Power size={14} />
      </span>
    );
  }
  return kind ? (
    <span aria-hidden className={styles.marker}>
      <EventMarker kind={kind} label={eventName(event.kind)} inert />
    </span>
  ) : null;
}

function marketCountry(market: string): Country {
  return market === 'KR' ? 'kr' : market === 'US' ? 'us' : 'coin';
}

export function EventCard({ event, toPlan }: { event: DayEvent; toPlan: boolean }) {
  switch (event.kind) {
    case 'rebalance':
    case 'partial-failed':
    case 'in-progress':
      return (
        <section className={styles.eventCard} aria-label={eventName(event.kind)}>
          <EventHead
            marker={<Marker event={event} />}
            title={
              event.kind === 'partial-failed'
                ? historyCopy.list.partialFailed
                : eventName(event.kind)
            }
            rule={event.rule}
            right={<MiniStages stages={event.stagesMini} />}
          />
          <Weights event={event} />
          <OrderList stages={event.stages} />
          <FeesTotal krw={event.feesKrw} />
          {toPlan ? <LinkButton to="/plan#now">{dc.toPlan}</LinkButton> : null}
        </section>
      );
    case 'deposit':
    case 'withdrawal':
    case 'dividend':
    case 'start':
      return (
        <section className={styles.eventCard} aria-label={eventName(event.kind)}>
          <EventHead marker={<Marker event={event} />} title={eventName(event.kind)} />
          <p className="t-title">{formatKrw(event.krw)}</p>
          <div className={styles.chips}>
            <InfoChip>{treatmentLabel(event.treatment, event.until ?? null)}</InfoChip>
            {event.instrument ? <InfoChip>{event.instrument.name}</InfoChip> : null}
          </div>
          {event.stages && event.stages.length > 0 ? <OrderList stages={event.stages} /> : null}
          {event.feesKrw !== undefined ? <FeesTotal krw={event.feesKrw} /> : null}
        </section>
      );
    case 'live-on':
    case 'live-off':
      return (
        <section className={styles.eventCard} aria-label={eventName(event.kind)}>
          <EventHead
            marker={<Marker event={event} />}
            title={eventName(event.kind)}
            right={<span className="t-label">{formatTime(event.at)}</span>}
          />
        </section>
      );
    case 'ai-check':
    case 'ai-sell':
    case 'ai-buy':
    case 'monthly-review':
    case 'discovery':
      return <AiJudgmentCard event={event} />;
  }
}

/** AI 판단 사건: what triggered it, input, model and tokens, output, verdict and action. */
export function AiJudgmentCard({ event }: { event: Extract<DayEvent, { judgment: unknown }> }) {
  const j = event.judgment;
  const votes = votesLabel(j.votes);
  // The server sends codes, counts and dates (JudgmentItem); the lines are worded here. An empty
  // 출력 hides its row (verdict, votes and action already sit in the 판단 box).
  const input = judgmentLine(j.input);
  const output = judgmentLine(j.output);
  return (
    <section className={styles.aiCard} aria-label={eventName(event.kind)}>
      <NodeCard
        kind="ai"
        title={
          j.instrument ? `${eventName(event.kind)} · ${j.instrument.name}` : eventName(event.kind)
        }
        nowLabel={dc.ai.judgment}
        nowSuffix={`· ${formatTime(j.at)}`}
        now={
          <>
            <NodeRow>
              <Text variant="label" tone="ai" grow>
                {dc.ai.verdict[j.verdict]}
              </Text>
              <Text variant="caption">{dc.ai.action[j.action]}</Text>
            </NodeRow>
            {votes ? (
              <Text variant="caption" tone="muted" as="p">
                {votes}
              </Text>
            ) : null}
          </>
        }
      >
        <NodeRow>
          <RuleDot rule={event.rule} />
          <Text variant="caption" tone="muted">
            {dc.ai.trigger[j.trigger]}
          </Text>
        </NodeRow>
        {j.instrument ? (
          <NodeRow tight>
            <InitialLogo
              initials={j.instrument.initials}
              size={20}
              tone={logoTone(event.rule.colorIndex, 0)}
            />
            <Flag country={marketCountry(j.instrument.market)} decorative />
          </NodeRow>
        ) : null}
        {input !== null ? (
          <NodeRow>
            <NodeRowLabel>{dc.ai.input}</NodeRowLabel>
            <Text variant="caption" grow>
              {input}
            </Text>
          </NodeRow>
        ) : null}
        <NodeRow>
          <NodeRowLabel>{dc.ai.ai}</NodeRowLabel>
          <Text variant="label" tone="ai" grow>
            {`${dc.ai.model[j.model]} · ${tokensLabel(j.tokens)}`}
          </Text>
        </NodeRow>
        {output !== null ? (
          <NodeRow>
            <NodeRowLabel>{dc.ai.output}</NodeRowLabel>
            <Text variant="caption" grow>
              {output}
            </Text>
          </NodeRow>
        ) : null}
      </NodeCard>
    </section>
  );
}
