// Semicircle gauge + its text column, shared by the rule cards (계획) and the 계획 card (자산):
// the same needle, instrument and numbers on both (SCR-HOME 완료 조건).
// - drift: −2 · 0 · +2, needle = the most deviated instrument (charts/Gauge).
// - mix (실전, D47): the same dial for 한국's share against its target; the band is where a
//   conversion is suggested ('환전 제안까지'), never a rebalance between the currencies.
// - sell-condition (AI rule, Figma 탐색 17:7108): 0 고른 날 → 100 팔 조건, 80~100 확인 구간.
import clsx from 'clsx';
import { marginText, metricName } from '../../api/adapters';
import { Gauge } from '../../charts/Gauge';
import { GAUGE, annularSector, insetSector, polar } from '../../charts/geometry/gauge';
import chartStyles from '../../charts/charts.module.css';
import { InitialLogo, type LogoTone } from '../../components/Badges';
import type { Gauge as GaugeData } from '../../api/types';
import { planCopy } from '../../copy/plan';
import { formatNumber, formatPp, formatPpMagnitude } from '../../lib/format';
import { toRebalanceText } from './words';
import styles from './Plan.module.css';

const CONDITION = { from: 0, to: 100, zone: 80 } as const;

function conditionAngle(progress: number): number {
  const v = Math.min(CONDITION.to, Math.max(CONDITION.from, progress));
  return -90 + (v / CONDITION.to) * 180;
}

/** 0–100 gauge of the AI rule: the 80~100 확인 구간 is the band, labels 0 · 50 · 100. */
export function ConditionGauge({ progress, label }: { progress: number | null; label: string }) {
  const { width, height, cx, cy, outerR, innerR, needleLength, needleWidth, hubR, labelR } = GAUGE;
  const a0 = conditionAngle(CONDITION.zone);
  const tip = progress === null ? null : polar(cx, cy, needleLength, conditionAngle(progress));
  const labels = [0, 50, 100].map((v) => ({ v, p: polar(cx, cy, labelR, conditionAngle(v)) }));
  return (
    <svg
      className={chartStyles.svg}
      width={width}
      height={height}
      viewBox={`0 0 ${String(width)} ${String(height)}`}
      role="img"
      aria-label={label}
    >
      <path className={chartStyles.track} d={annularSector(cx, cy, outerR, innerR, -90, 90)} />
      <path className={chartStyles.band} d={annularSector(cx, cy, outerR, innerR, a0, 90)} />
      <path
        className={chartStyles.bandEdge}
        d={insetSector(cx, cy, outerR, innerR, a0, 90, 0.5)}
        strokeWidth={1}
      />
      {labels.map(({ v, p }) => (
        <text
          key={v}
          className={clsx(chartStyles.tick, chartStyles.caption)}
          x={p.x}
          y={p.y}
          textAnchor="middle"
          dominantBaseline="central"
          aria-hidden
        >
          {v}
        </text>
      ))}
      {tip ? (
        <>
          <line
            className={chartStyles.needle}
            x1={cx}
            y1={cy}
            x2={tip.x}
            y2={tip.y}
            strokeWidth={needleWidth}
            strokeLinecap="round"
          />
          <circle className={chartStyles.hub} cx={cx} cy={cy} r={hubR} />
        </>
      ) : (
        <circle className={chartStyles.hubEmpty} cx={cx} cy={cy} r={hubR - 1} strokeWidth={2} />
      )}
    </svg>
  );
}

export interface GaugeBlockProps {
  gauge: GaugeData;
  /** 자산 shows the instrument's logo before its name (Figma 1:51434); 계획 does not (1:55865). */
  logoTone?: LogoTone | undefined;
  /** Caption under the '—' of a hollow gauge ('미국 시세 10/2 기준'). */
  emptyCaption?: string | null | undefined;
  className?: string | undefined;
}

/** '한국 76.9 : 미국 23.1' (whole shares without '.0'). */
function mixText(now: { kr: number; us: number }): string {
  const pct = (v: number) => formatNumber(v, Number.isInteger(v) ? 0 : 1);
  return planCopy.gauge.mix(pct(now.kr), pct(now.us));
}

export function GaugeBlock({ gauge, logoTone, emptyCaption, className }: GaugeBlockProps) {
  const g = planCopy.gauge;
  const head =
    gauge.kind === 'drift' ? g.mostDeviated : gauge.kind === 'mix' ? g.mixHead : g.closestToSell;

  let figure: string | null = null;
  let caption: string | null = emptyCaption ?? null;
  let summary: string = planCopy.row.dash;
  // The needle's name line: an instrument (with its logo on 자산), or the 실전 mix of won and dollars.
  let name: { text: string; initials: string | null } | null = null;
  if (gauge.kind === 'drift' && gauge.needle) {
    figure = formatPp(gauge.needle.deviation);
    caption = toRebalanceText(gauge.needle.toThreshold);
    name = { text: gauge.needle.instrument.name, initials: gauge.needle.instrument.initials };
  } else if (gauge.kind === 'mix' && gauge.needle) {
    figure = formatPp(gauge.needle.deviation);
    caption = g.toSuggest(formatPpMagnitude(gauge.needle.toThreshold));
    name = { text: mixText(gauge.needle.now), initials: null };
  } else if (gauge.kind === 'sell-condition' && gauge.needle) {
    figure = `${formatNumber(gauge.needle.progress)}%`;
    caption = g.toSell(metricName(gauge.needle.metric), marginText(gauge.needle.margin));
    name = { text: gauge.needle.instrument.name, initials: gauge.needle.instrument.initials };
  }
  if (name !== null && figure !== null && caption !== null) {
    summary = `${name.text} ${figure} · ${caption}`;
  } else if (caption !== null) {
    summary = `${planCopy.row.dash} · ${caption}`;
  }

  return (
    <div className={clsx(styles.gaugeBlock, className)}>
      <div className={styles.gaugeArt}>
        {gauge.kind === 'sell-condition' ? (
          <ConditionGauge progress={gauge.needle?.progress ?? null} label={summary} />
        ) : (
          <Gauge value={gauge.needle?.deviation ?? null} label={summary} />
        )}
      </div>
      <div className={styles.gaugeText}>
        <p className={clsx('t-caption', styles.muted)}>{head}</p>
        {name ? (
          <p className={styles.gaugeName}>
            {logoTone !== undefined && name.initials !== null ? (
              <InitialLogo initials={name.initials} size={20} tone={logoTone} />
            ) : null}
            <span className="t-label">{name.text}</span>
          </p>
        ) : (
          <p className="t-label">{planCopy.row.dash}</p>
        )}
        {figure !== null ? <p className="t-title">{figure}</p> : null}
        {caption !== null ? <p className={clsx('t-caption', styles.muted)}>{caption}</p> : null}
      </div>
    </div>
  );
}
