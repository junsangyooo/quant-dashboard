// 그날 확인 card (Figma 1:59915 · 1:60076): head + result chip → deviation band (−4…+4%p, band
// ±2, target tick, 전·후 points with their weights) → one line saying the same judgment as the chip.
import clsx from 'clsx';
import { useId } from 'react';
import type { DayResponse } from '../../api/types';
import { DeviationBand } from '../../charts/DeviationBand';
import { InfoChip, RebalanceChip } from '../../components/Chips';
import { dayCopy as dc } from '../../copy/day';
import { failureCopy, historyCopy as hc } from '../../copy/history';
import { formatMonthDay, formatPpMagnitude, formatTime } from '../../lib/format';
import { bandWeights, checkChip, openMarkets, positionLine } from './dayModel';
import styles from './Day.module.css';

export function CheckCard({
  check,
  ruleName,
}: {
  check: DayResponse['check'];
  ruleName: string | null;
}) {
  const id = useId();
  const chip = checkChip(check);
  const band = check.band;
  const weights = bandWeights(check);
  const position = positionLine(check, ruleName);
  const failure = check.failure;
  const decided =
    check.result === 'rebalance' ||
    check.result === 'in-progress' ||
    check.result === 'partial-failed';

  const points =
    band === null
      ? []
      : [
          ...(band.before === null
            ? []
            : [
                {
                  value: band.before,
                  kind: 'before' as const,
                  label: weights.before ? dc.check.pointBefore(weights.before) : undefined,
                },
              ]),
          ...(band.after === null
            ? []
            : [
                {
                  value: band.after,
                  kind: 'after' as const,
                  label: weights.after ? dc.check.pointAfter(weights.after) : undefined,
                },
              ]),
        ];

  return (
    <section className={styles.checkCard} aria-labelledby={id}>
      <div className={styles.checkHead}>
        <h3 id={id} className={clsx('t-label', styles.grow)}>
          {check.at ? dc.check.title(formatTime(check.at)) : dc.check.titleNoRun}
        </h3>
        {chip ? <RebalanceChip state={chip.state}>{chip.label}</RebalanceChip> : null}
      </div>
      {band && points.length > 0 ? (
        <DeviationBand
          points={points}
          span={band.threshold * 2}
          band={band.threshold}
          label={dc.check.band(
            weights.before ?? formatPpMagnitude(band.before ?? 0),
            weights.after ?? formatPpMagnitude(band.after ?? 0),
            formatPpMagnitude(band.threshold, 0),
          )}
        />
      ) : null}
      {check.result === 'weekend' ? (
        <p className={clsx('t-caption', styles.muted)}>{dc.check.weekend}</p>
      ) : null}
      {decided && band?.before != null ? (
        <p className={styles.checkLine}>
          <span className={clsx('t-label', styles.warningText)}>
            {dc.check.deviation(formatPpMagnitude(band.before))}
          </span>
          {check.over !== undefined ? (
            <span className={clsx('t-caption', styles.muted)}>
              {dc.check.over(formatPpMagnitude(check.over))}
            </span>
          ) : null}
        </p>
      ) : null}
      {check.result === 'holiday' && openMarkets(check) ? (
        <p className={clsx('t-caption', styles.muted)}>
          {dc.check.onlyOpen(openMarkets(check) ?? '')}
        </p>
      ) : null}
      {check.result === 'quote-wait' ? (
        <p className={clsx('t-caption', styles.muted)}>{dc.check.quoteWait}</p>
      ) : null}
      {check.result === 'withdraw-wait' ? (
        <p className={clsx('t-caption', styles.muted)}>{dc.check.withdrawWait}</p>
      ) : null}
      {check.result === 'failed' ? (
        <div className={styles.chips}>
          {failure && failure.reason !== 'other' ? (
            <InfoChip>{failureCopy[failure.reason]}</InfoChip>
          ) : null}
          {failure?.recoveredOn ? (
            <InfoChip>{hc.list.recovered(formatMonthDay(failure.recoveredOn))}</InfoChip>
          ) : null}
          <span className={clsx('t-caption', styles.muted)}>{dc.check.failed}</span>
        </div>
      ) : null}
      {!decided && position ? <p className={clsx('t-caption', styles.muted)}>{position}</p> : null}
    </section>
  );
}
