// 요약 타일 6칸 (고정 규칙, Figma 1:61916 · 1:60971 · 1:61661): ① 무엇·비중 (donut) ② 언제·시작
// (weekdays + 0–24h axis) ③ 조건 (deviation band) ④ 행동 (매도 → 환전 → 매수) ⑤ 과거 1년 수익·측정
// (measured points; ⌄ opens the source, period and definitions) ⑥ 지금·결과 (stages, status chip,
// next check). Each tile: kind stripe + head icon/label, picture, big value, small line.
// 실전 (display.mix, D47): ③ is 한국's share against its target, '±2%p 넘으면 환전 제안'; ④ buys
// with each currency's money ('매수 주문 · 원화로 한국 · 달러로 미국 종목'). No rebalance across.
import clsx from 'clsx';
import {
  ArrowLeftRight,
  ChartLine,
  ChartPie,
  ChevronDown,
  ChevronUp,
  CircleCheck,
  CircleMinus,
  CirclePlus,
  CircleX,
  Clock,
  Flag as FlagIcon,
  Hourglass,
  Send,
  Split,
  ChevronRight,
  type LucideIcon,
} from 'lucide-react';
import { useId, useState, type ReactNode } from 'react';
import { ruleStatusChip } from '../../api/adapters';
import type { Stage, TilesDisplay } from '../../api/types';
import { InitialLogo } from '../../components/Badges';
import { RebalanceChip } from '../../components/Chips';
import { StaleTag } from '../../components/Notices';
import { useElementWidth } from '../../charts/useElementWidth';
import { rulesCopy as rc } from '../../copy/rules';
import {
  formatDateTime,
  formatNumber,
  formatPercent,
  formatPercentSigned,
  formatPpMagnitude,
  formatTime,
  MINUS,
} from '../../lib/format';
import { logoTone } from '../History/tones';
import styles from './Rules.module.css';

type TileKind = 'weight' | 'start' | 'condition' | 'action' | 'data' | 'result';

function Tile({
  kind,
  icon: Icon,
  label,
  picture,
  value,
  note,
  extra,
  headEnd,
  stale,
}: {
  kind: TileKind;
  icon: LucideIcon;
  label: string;
  picture: ReactNode;
  value: ReactNode;
  note: ReactNode;
  extra?: ReactNode;
  headEnd?: ReactNode;
  stale?: boolean | undefined;
}) {
  return (
    <section className={clsx(styles.tile, styles[`k-${kind}`])} aria-label={label}>
      <span className={styles.tileStripe} aria-hidden />
      <div className={styles.tileBody}>
        <div className={styles.tileHead}>
          <Icon size={16} aria-hidden />
          <h3 className={clsx('t-label', styles.grow)}>{label}</h3>
          {stale ? <StaleTag /> : null}
          {headEnd}
        </div>
        <div className={styles.tilePicture}>{picture}</div>
        <div className={styles.tileValue}>{value}</div>
        <div className={clsx('t-caption', styles.muted)}>{note}</div>
        {extra}
      </div>
    </section>
  );
}

// ① 무엇 · 비중 ───────────────────────────────────────────────────────────────

function donutPath(cx: number, cy: number, r: number, ir: number, a0: number, a1: number): string {
  const p = (a: number, rad: number) =>
    `${String(cx + rad * Math.cos(a))} ${String(cy + rad * Math.sin(a))}`;
  const large = a1 - a0 > Math.PI ? 1 : 0;
  return `M${p(a0, r)}A${String(r)} ${String(r)} 0 ${String(large)} 1 ${p(a1, r)}L${p(a1, ir)}A${String(ir)} ${String(ir)} 0 ${String(large)} 0 ${p(a0, ir)}Z`;
}

function Donut({ weights, colorIndex }: { weights: readonly number[]; colorIndex: number }) {
  const size = 58;
  const r = size / 2;
  const total = weights.reduce((a, b) => a + b, 0) || 1;
  const sweeps = weights.map((w) => (w / total) * Math.PI * 2);
  const starts = sweeps.map((_, i) => -Math.PI / 2 + sweeps.slice(0, i).reduce((a, b) => a + b, 0));
  return (
    <svg className={styles.donut} viewBox={`0 0 ${String(size)} ${String(size)}`} aria-hidden>
      {sweeps.map((sweep, i) => {
        const a0 = starts[i] ?? 0;
        const d = donutPath(r, r, r, r * 0.6, a0, a0 + Math.min(sweep, Math.PI * 2 - 0.0001));
        return (
          <path key={i} d={d} className={styles[`fill-cat-${String(logoTone(colorIndex, i))}`]} />
        );
      })}
    </svg>
  );
}

/** Legend names drop a trailing 'ETF' (the line under the tile says 'ETF 2개', Figma 1:61916). */
function shortName(name: string, kind: string): string {
  return kind === 'etf' ? name.replace(/\s*ETF$/, '') : name;
}

// ② 언제 · 시작 ───────────────────────────────────────────────────────────────

function WhenPicture({ time }: { time: string }) {
  const [h = 0, m = 0] = time.split(':').map(Number);
  const pct = ((h * 60 + m) / (24 * 60)) * 100;
  return (
    <div className={styles.whenPicture} aria-hidden>
      <div className={styles.weekdays}>
        {rc.tiles.weekdays.map((d, i) => (
          <span key={d} className={clsx('t-micro', i < 5 ? styles.dayOn : styles.dayOff)}>
            {d}
          </span>
        ))}
      </div>
      <div className={styles.dayAxis}>
        <span className={styles.dayDot} style={{ left: `${String(pct)}%` }} />
      </div>
      <div className={styles.axisLabels}>
        <span className="t-micro">{rc.tiles.hour0}</span>
        <span className="t-micro">{rc.tiles.hour24}</span>
      </div>
    </div>
  );
}

// ③ 조건 ──────────────────────────────────────────────────────────────────────

function ConditionPicture({
  threshold,
  now,
  atCheck,
}: {
  threshold: number;
  now: number | null;
  atCheck: number | null;
}) {
  const [ref, width] = useElementWidth(260);
  const span = threshold * 2;
  const x = (v: number) => ((Math.max(-span, Math.min(span, v)) + span) / (2 * span)) * width;
  const bandX = x(-threshold);
  const bandW = x(threshold) - bandX;
  return (
    <div ref={ref} className={styles.svgFrame} aria-hidden>
      <svg width={width} height={56} className={styles.svg}>
        <rect className={styles.track} x={0} y={24} width={width} height={4} rx={2} />
        <rect className={styles.band} x={bandX} y={18} width={bandW} height={16} rx={2} />
        <rect
          className={styles.bandEdge}
          x={bandX + 0.5}
          y={18.5}
          width={bandW - 1}
          height={15}
          rx={1.5}
        />
        <rect className={styles.target} x={x(0) - 1} y={15} width={2} height={22} />
        {now !== null ? (
          <circle className={styles.dotNow} cx={x(now)} cy={26} r={4.25} strokeWidth={1.5} />
        ) : null}
        {atCheck !== null ? (
          <circle className={styles.dotCheck} cx={x(atCheck)} cy={26} r={4.25} strokeWidth={1.5} />
        ) : null}
        <text className={styles.svgMicro} x={bandX} y={46} textAnchor="middle">
          {rc.tiles.minus(formatPpMagnitude(threshold, 0))}
        </text>
        <text className={styles.svgMicro} x={x(0)} y={46} textAnchor="middle">
          {rc.tiles.targetMark}
        </text>
        <text className={styles.svgMicro} x={bandX + bandW} y={46} textAnchor="middle">
          {rc.tiles.plus(formatPpMagnitude(threshold, 0))}
        </text>
      </svg>
    </div>
  );
}

// ④ 행동 ──────────────────────────────────────────────────────────────────────

const STAGE_ICON: Record<Stage['kind'], LucideIcon> = {
  sell: CircleMinus,
  fx: ArrowLeftRight,
  buy: CirclePlus,
};

function ActionPicture({ stages }: { stages: readonly Stage['kind'][] }) {
  return (
    <div className={styles.actionPicture} aria-hidden>
      {stages.map((s, i) => {
        const Icon = STAGE_ICON[s];
        return (
          <div key={s} className={styles.actionStep}>
            {i > 0 ? <ChevronRight size={14} className={styles.actionChevron} /> : null}
            <span className={styles.actionStage}>
              <span className={styles.actionCircle}>
                <Icon size={18} />
              </span>
              <span className="t-micro">{rc.tiles.stages[s]}</span>
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ⑤ 과거 1년 수익 · 측정 ──────────────────────────────────────────────────────

function measuredDomain(m: NonNullable<TilesDisplay['measured']>): [number, number] {
  const lo = Math.floor((Math.min(m.worst, m.badYear, 0) - 5) / 10) * 10;
  const hi = Math.ceil((Math.max(m.median, 0) + 5) / 10) * 10;
  return [lo, hi];
}

function MeasuredPicture({ m }: { m: NonNullable<TilesDisplay['measured']> }) {
  const [ref, width] = useElementWidth(260);
  const [lo, hi] = measuredDomain(m);
  const x = (v: number) => ((v - lo) / (hi - lo)) * width;
  const fmt = (v: number) => (v > 0 ? `+${String(v)}` : v < 0 ? `${MINUS}${String(-v)}` : '0');
  return (
    <div ref={ref} className={styles.svgFrame} aria-hidden>
      <svg width={width} height={56} className={styles.svg}>
        <rect className={styles.track} x={0} y={31} width={width} height={2} rx={1} />
        <rect className={styles.target} x={x(0) - 1} y={20} width={2} height={24} />
        <rect
          className={styles.band}
          x={x(m.worst)}
          y={29}
          width={x(m.median) - x(m.worst)}
          height={6}
          rx={2}
        />
        <rect
          className={styles.bandEdge}
          x={x(m.worst) + 0.5}
          y={29.5}
          width={Math.max(0, x(m.median) - x(m.worst) - 1)}
          height={5}
          rx={1.5}
        />
        <circle className={styles.dotMeasured} cx={x(m.worst)} cy={32} r={3.75} strokeWidth={1.5} />
        <circle
          className={styles.dotMeasured}
          cx={x(m.badYear)}
          cy={32}
          r={3.75}
          strokeWidth={1.5}
        />
        <circle className={styles.dotMedian} cx={x(m.median)} cy={32} r={5.25} strokeWidth={1.5} />
        <text className={styles.svgMicro} x={x(m.worst)} y={52} textAnchor="start">
          {fmt(m.worst)}
        </text>
        <text className={styles.svgMicro} x={x(0)} y={14} textAnchor="middle">
          {fmt(0)}
        </text>
        <text className={styles.svgMicro} x={x(m.median)} y={14} textAnchor="middle">
          {fmt(m.median)}
        </text>
      </svg>
    </div>
  );
}

// ⑥ 지금 · 결과 ───────────────────────────────────────────────────────────────

function NowPicture({ stages }: { stages: readonly Stage[] }) {
  const done = stages.filter((s) => s.status === 'done').length;
  // The done line reaches halfway to a waiting stage: on the way there (Figma '진행선 완료').
  const reach = done > 0 && stages[done]?.status === 'pending' ? done - 0.5 : done - 1;
  return (
    <div className={styles.nowPicture} aria-hidden>
      <div className={styles.nowTrack}>
        <span
          className={styles.nowTrackDone}
          style={{
            width:
              stages.length > 1
                ? `${String((Math.max(0, reach) / (stages.length - 1)) * 100)}%`
                : '0%',
          }}
        />
      </div>
      {stages.map((s) => {
        const Icon =
          s.status === 'done' ? CircleCheck : s.status === 'failed' ? CircleX : Hourglass;
        return (
          <div key={s.kind} className={styles.nowStage}>
            <span className={clsx(styles.nowCircle, styles[`now-${s.status}`])}>
              {s.status === 'pending' ? (
                // 1.5px dash [3 2] ring: CSS borders cannot set a dash pattern.
                <svg className={styles.nowRing} viewBox="0 0 24 24">
                  <circle cx="12" cy="12" r="11.25" strokeWidth="1.5" strokeDasharray="3 2" />
                </svg>
              ) : null}
              <Icon size={16} />
            </span>
            <span className="t-micro">{rc.tiles.stages[s.kind]}</span>
            <span className={clsx('t-micro', styles.muted)}>{formatTime(s.at)}</span>
          </div>
        );
      })}
    </div>
  );
}

export function RuleTiles({
  display,
  colorIndex,
  stale,
}: {
  display: TilesDisplay;
  colorIndex: number;
  stale: boolean;
}) {
  const [open, setOpen] = useState(false);
  const detailsId = useId();
  const { what, when, condition, action, measured, now } = display;
  const allEtf = what.instruments.every((i) => i.kind === 'etf');
  const targets = condition.targetEach;
  const sameTarget = targets.every((t) => t === targets[0]);
  const deviation = condition.deviation;
  const chip = ruleStatusChip(now.status);
  // 실전 (D47): the band is where a conversion is suggested, its dots 한국's share against its
  // target; the orders buy with each currency's own money.
  const mix = display.mix === true;
  const krTarget = what.instruments.reduce(
    (sum, inst, i) => (inst.currency === 'KRW' ? sum + (what.weights[i] ?? 0) : sum),
    0,
  );

  return (
    <div className={styles.tiles}>
      <Tile
        kind="weight"
        icon={ChartPie}
        label={rc.tiles.what}
        picture={
          <div className={styles.whatPicture}>
            <Donut weights={what.weights} colorIndex={colorIndex} />
            <ul className={styles.donutLegend}>
              {what.instruments.map((inst, i) => (
                <li key={inst.id} className={styles.donutItem}>
                  <InitialLogo initials={inst.initials} size={20} tone={logoTone(colorIndex, i)} />
                  <span className="t-caption">{shortName(inst.name, inst.kind)}</span>
                </li>
              ))}
            </ul>
          </div>
        }
        value={
          <p className="t-heading-1">{rc.tiles.ratio(what.weights.map((w) => formatNumber(w)))}</p>
        }
        note={`${rc.tiles.krwBasis} · ${
          allEtf
            ? rc.tiles.etfCount(what.instruments.length)
            : rc.tiles.instrumentCount(what.instruments.length)
        }`}
      />
      <Tile
        kind="start"
        icon={Clock}
        label={rc.tiles.when}
        picture={<WhenPicture time={when.time} />}
        value={<p className="t-heading-1">{rc.tiles.daily(when.time)}</p>}
        note={rc.tiles.kstWeekdays}
      />
      <Tile
        kind="condition"
        icon={Split}
        label={rc.tiles.condition}
        picture={
          <ConditionPicture
            threshold={condition.threshold}
            now={stale ? null : deviation.now}
            atCheck={stale ? null : deviation.atCheck}
          />
        }
        value={
          <p className="t-heading-1">
            {(mix ? rc.tiles.overSuggest : rc.tiles.over)(
              formatPpMagnitude(condition.threshold, 0),
            )}
          </p>
        }
        note={
          mix
            ? rc.tiles.mixBasis(formatPercent(krTarget, 0))
            : rc.tiles.targetBasis(
                sameTarget && targets[0] !== undefined
                  ? formatPercent(targets[0], 0)
                  : targets.map((t) => String(t)).join(' · '),
              )
        }
      />
      <Tile
        kind="action"
        icon={Send}
        label={rc.tiles.action}
        picture={<ActionPicture stages={action.stages} />}
        value={<p className="t-heading-1">{mix ? rc.tiles.buyOrder : rc.tiles.rebalanceOrder}</p>}
        note={mix ? rc.tiles.asDeposited : rc.tiles.toTarget}
      />
      {measured ? (
        <Tile
          kind="data"
          icon={ChartLine}
          label={rc.tiles.measured}
          headEnd={
            <button
              type="button"
              className={styles.disclosure}
              aria-expanded={open}
              aria-controls={detailsId}
              aria-label={rc.tiles.measuredRows.source}
              onClick={() => {
                setOpen(!open);
              }}
            >
              {open ? <ChevronUp size={16} aria-hidden /> : <ChevronDown size={16} aria-hidden />}
            </button>
          }
          picture={<MeasuredPicture m={measured} />}
          value={<p className="t-heading-1">{formatPercentSigned(measured.median)}</p>}
          note={rc.tiles.measuredSub(measured.period, measured.afterTax)}
          extra={
            <dl id={detailsId} hidden={!open} className={styles.measuredRows}>
              <dt className={styles.muted}>{rc.tiles.measuredRows.source}</dt>
              <dd>{measured.source}</dd>
              <dt className={styles.muted}>{rc.tiles.measuredRows.period}</dt>
              <dd>{measured.period}</dd>
              <dt className={styles.muted}>{rc.tiles.measuredRows.median}</dt>
              <dd>{formatPercentSigned(measured.median)}</dd>
              <dt className={styles.muted}>{rc.tiles.measuredRows.badYear}</dt>
              <dd>{formatPercentSigned(measured.badYear)}</dd>
              <dt className={styles.muted}>{rc.tiles.measuredRows.worst}</dt>
              <dd>{formatPercentSigned(measured.worst)}</dd>
              {measured.afterTax ? (
                <>
                  <dt className={styles.muted}>{rc.tiles.measuredRows.afterTax}</dt>
                  <dd>{rc.tiles.measuredRows.afterTax}</dd>
                </>
              ) : null}
            </dl>
          }
        />
      ) : null}
      <Tile
        kind="result"
        icon={FlagIcon}
        label={rc.tiles.now}
        stale={stale}
        picture={now.stages && now.stages.length > 0 ? <NowPicture stages={now.stages} /> : null}
        value={<RebalanceChip state={chip.state}>{chip.label}</RebalanceChip>}
        note={rc.tiles.nextCheck(formatDateTime(now.nextCheckAt))}
      />
    </div>
  );
}
