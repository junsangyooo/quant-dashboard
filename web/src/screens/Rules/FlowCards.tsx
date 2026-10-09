// One 노드/D 지금 값 card of an AI rule flow, drawn from the engine's rule definition: kind head,
// title, kind-specific content (logos · flags, 입력/AI/출력, target weights, stage blocks,
// exception chips), subtitle, and the grey '지금' box built from NowBlock rows (Figma 1:62197).
import {
  ArrowLeftRight,
  Check,
  ChevronRight,
  CircleCheck,
  CircleMinus,
  CirclePlus,
  type LucideIcon,
} from 'lucide-react';
import { Fragment, useState, type ReactNode } from 'react';
import { ruleStatusChip } from '../../api/adapters';
import type { Instrument, NowBlock, Side } from '../../api/types';
import { Flag, InitialLogo, KindBadge, type Country } from '../../components/Badges';
import { ExceptionChip, RebalanceChip, type ExceptionKind } from '../../components/Chips';
import {
  NodeCard,
  NodeIcon,
  NodeRow,
  NodeRowLabel,
  type NodeKind,
} from '../../components/NodeCard';
import { StaleTag } from '../../components/Notices';
import { Text } from '../../components/Text';
import { rulesCopy as rc } from '../../copy/rules';
import {
  formatDateTime,
  formatMonthDay,
  formatPercent,
  formatPercentSigned,
  formatPp,
  formatPpMagnitude,
  formatTime,
  kstDateKey,
  pnlDirection,
} from '../../lib/format';
import { logoTone } from '../History/tones';
import {
  kvNoteOf,
  moreOf,
  nowNoteOf,
  nowUntilOf,
  retriedOf,
  targetsOf,
  type FlowNode,
  type NowRow,
} from './proposed';
import styles from './Rules.module.css';

const NODE_KIND: Record<FlowNode['type'], NodeKind> = {
  start: 'start',
  stock: 'asset',
  data: 'data',
  ai: 'ai',
  weight: 'weight',
  condition: 'condition',
  action: 'action',
  exception: 'exception',
  result: 'result',
};

export function nodeKind(type: FlowNode['type']): NodeKind {
  return NODE_KIND[type];
}

const SIDE_ICON: Record<Side, LucideIcon> = {
  sell: CircleMinus,
  fx: ArrowLeftRight,
  buy: CirclePlus,
};
const SIDES: readonly Side[] = ['sell', 'fx', 'buy'];

const EXCEPTION: Record<'holiday' | 'quote-wait' | 'withdraw-wait', ExceptionKind> = {
  holiday: 'holiday',
  'quote-wait': 'awaitingQuote',
  'withdraw-wait': 'withdrawPending',
};

function country(inst: Instrument): Country {
  return inst.market === 'KR' ? 'kr' : inst.market === 'US' ? 'us' : 'coin';
}

/** Does the date-time string carry a time ('2026-10-08T08:30…') or only a date? */
function hasTime(at: string): boolean {
  return at.includes('T');
}

/** '16시간 뒤' / '55일 뒤' from the server clock. */
function relative(at: string, now: string | null): string | null {
  if (!now) return null;
  if (hasTime(at)) {
    const hours = Math.round((Date.parse(at) - Date.parse(now)) / 3_600_000);
    return hours >= 0 ? rc.now.inHours(hours) : null;
  }
  const days = Math.round(
    (Date.parse(`${at}T00:00:00+09:00`) - Date.parse(`${kstDateKey(now)}T00:00:00+09:00`)) /
      86_400_000,
  );
  return days >= 0 ? rc.now.inDays(days) : null;
}

function when(at: string): string {
  return hasTime(at) ? formatDateTime(at) : formatMonthDay(at);
}

type InstrumentRow = Extract<NowRow, { kind: 'instrument' }>;

function instrumentRows(now: NowBlock): InstrumentRow[] {
  return now.rows.filter((r): r is InstrumentRow => r.kind === 'instrument');
}

/** Text after '지금 ·' in the grey box head. */
export function nowSuffix(node: FlowNode): string | null {
  const now = node.now;
  const parts: string[] = [];
  switch (now.headKey) {
    case 'now-check':
      if (now.at) parts.push(rc.now.check(formatTime(now.at)));
      break;
    case 'now-last-judgment':
      if (now.at) parts.push(rc.now.lastJudgment(when(now.at)));
      break;
    case 'now-month':
      parts.push(rc.now.month);
      break;
    case 'now-last': {
      const until = nowUntilOf(now);
      if (now.at) {
        parts.push(rc.now.last(until ? rc.now.range(when(now.at), when(until)) : when(now.at)));
      }
      break;
    }
    case 'now':
      break;
  }
  const rows = instrumentRows(now);
  if (
    node.type !== 'weight' &&
    rows.length > 0 &&
    rows.length === now.rows.length &&
    rows.every((r) => r.weight !== undefined && r.ret !== undefined)
  ) {
    parts.push(rc.now.weightsPnl);
  }
  const note = nowNoteOf(now);
  if (note) parts.push(note);
  return parts.length ? `· ${parts.join(' · ')}` : null;
}

// ── 지금 rows ───────────────────────────────────────────────────────────────

function Logos({
  instruments,
  colorIndex,
}: {
  instruments: readonly Instrument[];
  colorIndex: number;
}) {
  return (
    <NodeRow tight>
      {instruments.map((inst, i) => (
        <InitialLogo
          key={inst.id}
          initials={inst.initials}
          size={20}
          tone={logoTone(colorIndex, i)}
        />
      ))}
    </NodeRow>
  );
}

function ProgressRow({ row }: { row: InstrumentRow }) {
  const progress = Math.max(0, Math.min(100, row.progress ?? 0));
  return (
    <div className={styles.nowStack}>
      <NodeRow>
        <Text variant="caption" grow className={styles.ellipsis}>
          {`${row.instrument.name} ${formatPercent(progress, 0)}`}
        </Text>
        {row.marginText ? <Text variant="label">{row.marginText}</Text> : null}
      </NodeRow>
      <span className={styles.progress} aria-hidden>
        <span className={styles.progressZone} />
        <span className={styles.progressDot} style={{ left: `${String(progress)}%` }} />
      </span>
      <NodeRow>
        <Text variant="caption" tone="muted" grow>
          {rc.now.progress.from}
        </Text>
        <Text variant="caption" tone="muted">
          {rc.now.progress.zone}
        </Text>
        <Text variant="caption" tone="muted" grow align="end">
          {rc.now.progress.to}
        </Text>
      </NodeRow>
    </div>
  );
}

function orderRight(row: Extract<NowRow, { kind: 'order' }>): string {
  if (row.status === 'filled' && row.at) {
    const date = formatMonthDay(row.at);
    return retriedOf(row) ? rc.now.retried(date) : rc.now.filled(date);
  }
  if (row.status === 'pending' && row.at) return rc.now.pending(formatTime(row.at));
  if (row.status === 'failed') return rc.now.failed;
  if (row.status === 'filled') return rc.now.filled('').trim();
  return rc.now.none;
}

function ExceptionRow({ row }: { row: Extract<NowRow, { kind: 'exceptions' }> }) {
  if (!row.active) {
    return (
      <NodeRow>
        <Text variant="caption" tone="success">
          <CircleCheck size={16} aria-hidden />
        </Text>
        <Text variant="caption" grow>
          {rc.now.exceptionsNone}
        </Text>
      </NodeRow>
    );
  }
  return (
    <NodeRow tight>
      {row.items.map((item) => (
        <ExceptionChip key={item} kind={EXCEPTION[item]} />
      ))}
    </NodeRow>
  );
}

/** Compact 벗어남 띠 of a 조건 card: −2×threshold…+2×threshold, band ±threshold, the value as a dot
 * (Figma 1:62197 '벗어남 띠': 4px axis, 8px band, 12px target, text/primary dot). */
function MiniBand({ value, threshold }: { value: number | null; threshold: number }) {
  const span = threshold * 2;
  const pct = (v: number) => ((Math.max(-span, Math.min(span, v)) + span) / (2 * span)) * 100;
  return (
    <span className={styles.miniBand} aria-hidden>
      <span
        className={styles.miniBandZone}
        style={{ left: `${String(pct(-threshold))}%`, right: `${String(100 - pct(threshold))}%` }}
      />
      <span className={styles.miniBandTarget} style={{ left: `${String(pct(0))}%` }} />
      {value !== null ? (
        <span className={styles.miniBandDot} style={{ left: `${String(pct(value))}%` }} />
      ) : null}
    </span>
  );
}

export function NowRows({
  node,
  colorIndex,
  ai,
  nowIso,
  stale,
}: {
  node: FlowNode;
  colorIndex: number;
  ai: boolean;
  nowIso: string | null;
  stale: boolean;
}) {
  const now = node.now;
  const out: ReactNode[] = [];

  if (node.type === 'start' && now.at) {
    const rel = relative(now.at, nowIso);
    out.push(
      <NodeRow key="next">
        <Text variant="caption" grow>
          {rc.now.next(when(now.at))}
        </Text>
        {rel ? (
          <Text variant="caption" tone="muted">
            {rel}
          </Text>
        ) : null}
      </NodeRow>,
    );
  }

  const insts = instrumentRows(now);
  if (node.type === 'weight' && insts.length > 0) {
    const targets = targetsOf(node);
    const more = moreOf(node);
    out.push(
      <Text key="weights" variant="label" as="p">
        {insts.map((r) => (r.weight === undefined ? '—' : r.weight.toFixed(1))).join(' · ') +
          (more ? ' …' : '')}
      </Text>,
    );
    if (targets && targets.length > 0) {
      out.push(
        <Text key="targets" variant="caption" tone="muted" as="p">
          {rc.now.targets(targets.map((t) => String(t.weight)).join(' · '))}
        </Text>,
      );
    }
  }

  let bare: Instrument[] = [];
  const flushBare = (key: string) => {
    if (bare.length === 0) return;
    const list = bare;
    bare = [];
    out.push(
      <NodeRow key={key}>
        <Logos instruments={list} colorIndex={colorIndex} />
        {node.type === 'ai' ? (
          <Text variant="caption" grow>
            {rc.now.picked(list.length + (moreOf(node) ?? 0))}
          </Text>
        ) : null}
      </NodeRow>,
    );
  };

  now.rows.forEach((row, i) => {
    const key = `r${String(i)}`;
    if (
      row.kind !== 'instrument' ||
      row.weight !== undefined ||
      row.ret !== undefined ||
      row.progress !== undefined ||
      row.marginText !== undefined
    ) {
      flushBare(`${key}-logos`);
    }
    switch (row.kind) {
      case 'instrument': {
        if (node.type === 'weight') return;
        if (row.progress !== undefined) {
          out.push(<ProgressRow key={key} row={row} />);
          return;
        }
        if (row.weight === undefined && row.ret === undefined && row.marginText !== undefined) {
          out.push(
            <NodeRow key={key}>
              <InitialLogo
                initials={row.instrument.initials}
                size={20}
                tone={logoTone(colorIndex, i)}
              />
              <Text variant="caption" grow>
                {`${row.instrument.name} · ${row.marginText}`}
              </Text>
            </NodeRow>,
          );
          return;
        }
        if (row.weight === undefined && row.ret === undefined) {
          bare.push(row.instrument);
          return;
        }
        out.push(
          <NodeRow key={key}>
            <InitialLogo
              initials={row.instrument.initials}
              size={20}
              tone={logoTone(colorIndex, i)}
            />
            <Text variant="caption" grow className={styles.ellipsis}>
              {row.instrument.name}
            </Text>
            {row.weight !== undefined ? (
              <Text variant="label">{formatPercent(row.weight)}</Text>
            ) : null}
            {row.ret !== undefined ? (
              <Text variant="caption" tone={pnlDirection(row.ret, 1)}>
                {formatPercentSigned(row.ret)}
              </Text>
            ) : null}
          </NodeRow>,
        );
        return;
      }
      case 'rank':
        out.push(
          <NodeRow key={key}>
            <Text variant="caption" tone="muted">
              {String(row.rank)}
            </Text>
            <Text variant="caption" grow>
              {row.instrument.name}
            </Text>
            <Text variant="label" tone={pnlDirection(row.ret, 1)}>
              {formatPercentSigned(row.ret)}
            </Text>
          </NodeRow>,
        );
        return;
      case 'band': {
        const to = Math.max(0, row.threshold - Math.abs(row.value));
        out.push(
          <div key={key} className={styles.nowStack}>
            <NodeRow>
              <Text variant="caption" grow className={styles.nowrap}>
                {row.instrument
                  ? `${row.instrument.name} ${formatPp(row.value)}`
                  : formatPp(row.value)}
              </Text>
              <Text variant="label" tone="muted" className={styles.nowrap}>
                {rc.now.toThreshold(formatPpMagnitude(to))}
              </Text>
            </NodeRow>
            <MiniBand value={stale ? null : row.value} threshold={row.threshold} />
            <NodeRow>
              <Text variant="caption" tone="muted">
                {formatPp(-row.threshold * 2, 0).replace('%p', '')}
              </Text>
              <Text variant="caption" tone="muted" grow align="center">
                {rc.now.bandScale(formatPpMagnitude(row.threshold, 0))}
              </Text>
              <Text variant="caption" tone="muted">
                {formatPp(row.threshold * 2, 0).replace('%p', '')}
              </Text>
            </NodeRow>
          </div>,
        );
        return;
      }
      case 'order': {
        const Icon = SIDE_ICON[row.side];
        out.push(
          <NodeRow key={key}>
            <NodeIcon icon={Icon} />
            <Text variant="caption" grow>
              {row.text}
            </Text>
            <Text variant="caption" tone="muted">
              {orderRight(row)}
            </Text>
          </NodeRow>,
        );
        return;
      }
      case 'status': {
        const chip = ruleStatusChip(row.status, ai);
        out.push(
          <NodeRow key={key}>
            <RebalanceChip state={chip.state}>{chip.label}</RebalanceChip>
          </NodeRow>,
        );
        if (row.at) {
          out.push(
            <NodeRow key={`${key}-at`}>
              <Text variant="caption" tone="success">
                <Check size={16} aria-hidden />
              </Text>
              <Text variant="caption" grow>
                {rc.now.lastCheck(when(row.at))}
              </Text>
            </NodeRow>,
          );
        }
        return;
      }
      case 'kv': {
        const note = kvNoteOf(row);
        out.push(
          <NodeRow key={key}>
            {row.key ? (
              <Text variant="caption" tone="muted" className={styles.kvKey}>
                {row.key}
              </Text>
            ) : null}
            <Text variant="caption" tone={row.key ? undefined : 'muted'} grow>
              {row.value}
            </Text>
            {note ? <Text variant="label">{note}</Text> : null}
          </NodeRow>,
        );
        return;
      }
      case 'exceptions':
        out.push(<ExceptionRow key={key} row={row} />);
        return;
    }
  });
  flushBare('end-logos');

  return <>{out}</>;
}

// ── card content (between the title and the 지금 box) ──────────────────────

function StockContent({ node, colorIndex }: { node: FlowNode; colorIndex: number }) {
  const insts = instrumentRows(node.now).map((r) => r.instrument);
  if (insts.length === 0) return null;
  const more = moreOf(node);
  const markets = [...new Set(insts.map(country))];
  const kinds = [...new Set(insts.map((i) => i.kind))];
  return (
    <>
      <NodeRow>
        <Logos instruments={insts} colorIndex={colorIndex} />
        {more ? (
          <Text variant="caption" tone="muted">
            {rc.now.more(more)}
          </Text>
        ) : null}
      </NodeRow>
      <NodeRow tight>
        {markets.map((m) => (
          <Flag key={m} country={m} />
        ))}
        {kinds.map((k) => (
          <KindBadge key={k}>{rc.flow.kinds[k]}</KindBadge>
        ))}
      </NodeRow>
    </>
  );
}

function WeightContent({ node, colorIndex }: { node: FlowNode; colorIndex: number }) {
  const targets = targetsOf(node);
  if (!targets || targets.length === 0) return null;
  return (
    <NodeRow>
      {targets.map((t, i) => (
        <NodeRow key={t.instrument.id} tight>
          <InitialLogo initials={t.instrument.initials} size={20} tone={logoTone(colorIndex, i)} />
          <Text variant="label">{String(t.weight)}</Text>
        </NodeRow>
      ))}
    </NodeRow>
  );
}

function ActionContent({ node }: { node: FlowNode }) {
  const sides = SIDES.filter((s) => node.now.rows.some((r) => r.kind === 'order' && r.side === s));
  const shown = sides.length > 0 ? sides : SIDES;
  return (
    <NodeRow tight>
      {shown.map((s, i) => (
        <Fragment key={s}>
          {i > 0 ? (
            <Text variant="caption" tone="muted">
              <ChevronRight size={16} aria-hidden />
            </Text>
          ) : null}
          <NodeRow tight>
            <NodeIcon icon={SIDE_ICON[s]} />
            <Text variant="caption">{rc.tiles.stages[s]}</Text>
          </NodeRow>
        </Fragment>
      ))}
    </NodeRow>
  );
}

function ExceptionContent({ node }: { node: FlowNode }) {
  const row = node.now.rows.find(
    (r): r is Extract<NowRow, { kind: 'exceptions' }> => r.kind === 'exceptions',
  );
  const items = row?.items ?? (['holiday', 'quote-wait', 'withdraw-wait'] as const);
  const [open, setOpen] = useState<ExceptionKind | null>(null);
  return (
    <div className={styles.exceptionChips}>
      <div className={styles.chipWrap}>
        {items.map((item) => {
          const kind = EXCEPTION[item];
          return (
            <button
              key={item}
              type="button"
              className={styles.exceptionButton}
              aria-expanded={open === kind}
              onClick={() => {
                setOpen(open === kind ? null : kind);
              }}
            >
              <ExceptionChip kind={kind} />
            </button>
          );
        })}
      </div>
      {open ? (
        <Text variant="caption" tone="muted" as="p">
          {rc.exceptionHelp[open as keyof typeof rc.exceptionHelp]}
        </Text>
      ) : null}
    </div>
  );
}

function AiFields({ node }: { node: FlowNode }) {
  const label = rc.flow.fields;
  return (
    <>
      {(node.fields ?? []).map((f) => (
        <NodeRow key={f.key}>
          <NodeRowLabel>{label[f.key]}</NodeRowLabel>
          <Text
            variant={f.key === 'ai' ? 'label' : 'caption'}
            tone={f.key === 'ai' ? 'ai' : undefined}
            grow
          >
            {f.value}
          </Text>
        </NodeRow>
      ))}
    </>
  );
}

export function FlowCard({
  node,
  colorIndex,
  ai,
  nowIso,
  stale,
  goesTo,
}: {
  node: FlowNode;
  colorIndex: number;
  ai: boolean;
  nowIso: string | null;
  stale: boolean;
  /** Screen-reader lines: where this card's lines go. */
  goesTo: readonly string[];
}) {
  const kind = nodeKind(node.type);
  const suffix = nowSuffix(node);
  return (
    <NodeCard
      kind={kind}
      title={node.title}
      nowSuffix={stale ? <StaleTag /> : (suffix ?? undefined)}
      now={<NowRows node={node} colorIndex={colorIndex} ai={ai} nowIso={nowIso} stale={stale} />}
      className={styles.flowCard}
    >
      {node.type === 'stock' ? <StockContent node={node} colorIndex={colorIndex} /> : null}
      {node.type === 'weight' ? <WeightContent node={node} colorIndex={colorIndex} /> : null}
      {node.type === 'ai' ? <AiFields node={node} /> : null}
      {node.type === 'action' ? <ActionContent node={node} /> : null}
      {node.type === 'exception' ? <ExceptionContent node={node} /> : null}
      {node.subtitle ? (
        <Text variant="caption" tone="muted" as="p">
          {node.subtitle}
        </Text>
      ) : null}
      {goesTo.length > 0 ? <span className="sr-only">{goesTo.join(' · ')}</span> : null}
    </NodeCard>
  );
}
