// 규칙 카드 (계획): head '이름 · 자산의 81.1% · 목표 80%' → status chip + next action (› scrolls to
// '지금' when the rule has one) → gauge + most deviated instrument → instrument rows → basis
// line. At 1440 the card carries its own drift chart (or, for an AI rule, '지수 대비').
import clsx from 'clsx';
import { ChevronRight } from 'lucide-react';
import { marginText, metricName, ruleStatusChip } from '../../api/adapters';
import type { PlanResponse, RuleCard as RuleCardData } from '../../api/types';
import type { ChartEvent } from '../../charts/geometry/lineChart';
import { InitialLogo, type LogoTone } from '../../components/Badges';
import { RebalanceChip } from '../../components/Chips';
import { planCopy } from '../../copy/plan';
import { formatMonthDay, formatNumber, formatPercent } from '../../lib/format';
import { DriftPlot, VsIndexChart, driftHeading } from './Drift';
import { GaugeBlock } from './GaugeBlock';
import {
  basisLineText,
  nextActionText,
  quoteWaitBasis,
  ruleName,
  shareParts,
  toRebalanceText,
} from './words';
import styles from './Plan.module.css';

export interface RuleCardProps {
  card: RuleCardData;
  plan: PlanResponse;
  now: string | null;
  tones: ReadonlyMap<string, LogoTone>;
  /** Draw the card's own chart beside it (1440). */
  wide: boolean;
  /** Present when this rule has the '지금' item: the next action scrolls to it. */
  onShowNow?: (() => void) | undefined;
  onGroup?: ((events: ChartEvent[]) => void) | undefined;
}

export function RuleCard({ card, plan, now, tones, wide, onShowNow, onGroup }: RuleCardProps) {
  const chip = ruleStatusChip(card.status, card.rule.ai);
  const share = shareParts(card.share);
  const next = nextActionText(card.next, { now, withNextCheck: card.next.kind === 'holiday' });
  const vsIndex = card.vsIndex ?? null;
  const name = ruleName(card.rule);
  const quoteWait = card.status === 'quote-wait';
  const emptyCaption = card.next.kind === 'quote-wait' ? quoteWaitBasis(card.next) : null;
  const headingId = `rule-${card.rule.id}-name`;

  const chart = vsIndex ? (
    <div className={styles.cardChart}>
      <p className={clsx('t-label', styles.muted)}>
        {planCopy.drift.vsIndex(formatMonthDay(vsIndex.since))}
      </p>
      <VsIndexChart
        since={vsIndex.since}
        points={vsIndex.points}
        label={`${name} · ${planCopy.drift.vsIndex(formatMonthDay(vsIndex.since))}`}
      />
    </div>
  ) : wide &&
    plan.drift.empty === null &&
    plan.drift.lines.some((l) => l.ruleId === card.rule.id) ? (
    <div className={styles.cardChart}>
      <p className={clsx('t-label', styles.muted)}>{driftHeading(plan.drift)}</p>
      <DriftPlot
        drift={plan.drift}
        rules={plan.rules.map((r) => r.rule)}
        only={card.rule.id}
        size="1440"
        onGroup={onGroup}
      />
    </div>
  ) : null;

  return (
    <article
      id={`rule-${card.rule.id}`}
      className={clsx(styles.card, styles.ruleCard, wide && styles.ruleCardWide)}
      aria-labelledby={headingId}
      tabIndex={-1}
    >
      <div className={styles.ruleMain}>
        <div className={styles.nameRow}>
          <h2 id={headingId} className="t-heading-1">
            {name}
          </h2>
          <p className={styles.share}>
            {share.pct !== null ? (
              <>
                <span className={clsx('t-caption', styles.muted)}>{planCopy.share.of}</span>
                <span className="t-heading-1">{share.pct}</span>
              </>
            ) : null}
            {share.target !== null ? (
              <span className={clsx('t-caption', styles.muted)}>
                {share.pct !== null
                  ? planCopy.share.targetAfter(share.target)
                  : planCopy.share.target(share.target)}
              </span>
            ) : null}
          </p>
        </div>

        <div className={styles.statusRow}>
          <RebalanceChip state={chip.state}>{chip.label}</RebalanceChip>
          {onShowNow ? (
            <button
              type="button"
              className={clsx('t-label', styles.nextButton)}
              onClick={onShowNow}
            >
              <span>{next}</span>
              <ChevronRight size={16} className={styles.muted} aria-hidden />
            </button>
          ) : (
            <span className="t-label">{next}</span>
          )}
        </div>

        <GaugeBlock gauge={card.gauge} emptyCaption={quoteWait ? emptyCaption : null} />

        <ul className={styles.rows}>
          {card.rows.map((row) => {
            const sell = card.gauge.kind === 'sell-condition' && row.progress !== undefined;
            let first: string;
            let second: string | null = null;
            if (sell) {
              first = planCopy.row.progress(
                `${formatNumber(row.progress ?? 0)}%`,
                row.metric ? metricName(row.metric) : '',
              );
              second = row.margin ? planCopy.row.margin(marginText(row.margin)) : null;
            } else {
              // Equal AI weights are not whole numbers (1/15 = 6.7%): no rounding to '7%'.
              first = planCopy.row.weight(
                row.weight === null ? planCopy.row.dash : formatPercent(row.weight),
                `${formatNumber(row.target, Number.isInteger(row.target) ? 0 : 1)}%`,
              );
              if (row.toThreshold !== null) second = toRebalanceText(row.toThreshold);
              else if (quoteWait) second = chip.label;
            }
            return (
              <li key={row.instrument.id} className={styles.ruleRow}>
                <span className={styles.ruleRowName}>
                  <InitialLogo
                    initials={row.instrument.initials}
                    size={20}
                    tone={tones.get(row.instrument.id)}
                  />
                  <span className="t-label">{row.instrument.name}</span>
                </span>
                <span className={styles.ruleRowValue}>
                  <span className="t-caption">{first}</span>
                  {second !== null ? (
                    <span className={clsx('t-caption', styles.muted)}>{second}</span>
                  ) : null}
                </span>
              </li>
            );
          })}
        </ul>

        <p className={clsx('t-caption', styles.muted)}>{basisLineText(card)}</p>
      </div>
      {chart}
    </article>
  );
}
