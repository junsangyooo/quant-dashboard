// 계획 미리보기 (Figma '계획 미리보기', D-home-plan-gauge): '계획' + '계획 보기 ›' → the rule with the
// highest-priority status: 이름 · 자산의 n% · 목표, status chip + next action → the same gauge as
// the 계획 tab → stage row while it runs → '다음 확인' chip → '외 n개 규칙 · [상태]'.
// Before the first check or fill: no gauge, a chip line only (the API sends the card then too,
// with no needle and no stages). 1440: rule | stages side by side.
import clsx from 'clsx';
import { ruleStatusChip } from '../../api/adapters';
import type { HomeResponse } from '../../api/types';
import type { LogoTone } from '../../components/Badges';
import { LinkButton } from '../../components/Buttons';
import { InfoChip, RebalanceChip } from '../../components/Chips';
import { StaleMark } from '../../components/State';
import { homeCopy } from '../../copy/home';
import { planCopy } from '../../copy/plan';
import { formatDateTime } from '../../lib/format';
import { GaugeBlock } from '../Plan/GaugeBlock';
import { StageRow } from '../Plan/Stages';
import { nextActionText, quoteWaitBasis, ruleName, shareParts, statusLabel } from '../Plan/words';
import styles from './Home.module.css';

export function PlanPreview({
  home,
  now,
  wide,
  tones,
}: {
  home: HomeResponse;
  now: string | null;
  wide: boolean;
  tones: ReadonlyMap<string, LogoTone>;
}) {
  const card = home.planCard;
  const head = (
    <div className={styles.cardHead}>
      <div className={styles.cardTitle}>
        <h2 className="t-heading-1">{homeCopy.plan.title}</h2>
        <StaleMark stale={home.stale} section="plan" />
      </div>
      <LinkButton to="/plan">{homeCopy.plan.link}</LinkButton>
    </div>
  );
  const firstCheck = card.next.kind === 'first-check';
  const chip = ruleStatusChip(card.status, card.rule.ai);
  const share = shareParts(card.share);
  const showGauge = card.gauge.needle !== null || card.status === 'quote-wait';
  const withdrawKrw = home.composition.pendingBar?.withdraw?.krw;
  const next = nextActionText(card.next, { now, variant: 'card', withdrawKrw });
  const needleId = card.gauge.needle?.instrument.id;

  const rule = (
    <div className={styles.planRule}>
      <div className={styles.planHead}>
        <div className={styles.nameRow}>
          <h3 className="t-body-strong">{ruleName(card.rule)}</h3>
          <p className={styles.share}>
            {share.pct !== null ? (
              <>
                <span className={clsx('t-caption', styles.muted)}>{planCopy.share.of}</span>
                <span className="t-body-strong">{share.pct}</span>
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
        {!firstCheck ? (
          <div className={styles.statusRow}>
            <RebalanceChip state={chip.state}>{chip.label}</RebalanceChip>
            <span className="t-label">{next}</span>
          </div>
        ) : null}
      </div>
      {showGauge ? (
        <GaugeBlock
          gauge={card.gauge}
          logoTone={needleId !== undefined ? (tones.get(needleId) ?? 1) : 1}
          emptyCaption={card.next.kind === 'quote-wait' ? quoteWaitBasis(card.next) : null}
        />
      ) : null}
    </div>
  );

  const progress = (
    <div className={styles.planProgress}>
      {card.stages && card.stages.length > 0 ? <StageRow stages={card.stages} /> : null}
      <div>
        <InfoChip>
          {firstCheck ? next : planCopy.next.nextCheck(formatDateTime(card.nextCheckAt))}
        </InfoChip>
      </div>
      {card.others ? (
        <p className={clsx('t-caption', styles.muted)}>
          {homeCopy.plan.others(
            card.others.count,
            firstCheck || card.others.status === 'before-first'
              ? homeCopy.plan.beforeFirstCheck
              : statusLabel(card.others.status),
          )}
        </p>
      ) : null}
    </div>
  );

  return (
    <section className={clsx(styles.card, styles.planCard)} aria-label={homeCopy.plan.title}>
      {head}
      <div className={clsx(styles.planBody, wide && styles.planBodyWide)}>
        {rule}
        {progress}
      </div>
    </section>
  );
}
