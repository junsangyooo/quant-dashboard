// 오른쪽 패널(그림 V2-23): 이 전략의 경로 / 줄 편집 / 시작하는 법.
import clsx from 'clsx';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Circle,
  Info,
  MinusCircle,
  X,
  XCircle,
} from 'lucide-react';
import type { Analysis, Block, Body, Catalog, ExecId, Problem, Row } from '../../api/v2';
import { blockEditor as t } from '../../copy/blockEditor';
import styles from './BlockEditor.module.css';

const circleOf = (catalog: Catalog, stage: string) =>
  catalog.stages.find((s) => s.id === stage)?.circle ?? '';
const nameOf = (catalog: Catalog, stage: string) =>
  catalog.stages.find((s) => s.id === stage)?.name ?? '';

function pathText(body: Body, catalog: Catalog, ids: string[]): string {
  const by = new Map(body.graph.blocks.map((b) => [b.id, b]));
  return ids
    .map((id) => {
      const b = by.get(id);
      if (!b) return id;
      const m = b.stage === 'signal' || b.stage === 'filter' || b.stage === 'sell';
      const tog = m ? `(${b.match === 'all' ? t.allShort : t.anyShort})` : '';
      return `${circleOf(catalog, b.stage)} ${nameOf(catalog, b.stage)}${tog}`;
    })
    .join(' → ');
}

export function PathsPanel({
  body,
  catalog,
  analysis,
  rowTexts,
}: {
  body: Body;
  catalog: Catalog;
  analysis: Analysis;
  rowTexts: Record<string, string[]>;
}) {
  const select = body.graph.blocks.find((b) => b.stage === 'select');
  const top = select?.rows[0];
  const by = String(top?.params.by ?? 'strength');
  const byName =
    by === 'strength' ? t.sortStrength : (catalog.items.find((i) => i.id === by)?.short ?? by);
  const n = typeof top?.value === 'number' ? String(top.value) : t.blank;
  const problemsOn = (ids: string[]) =>
    analysis.problems.filter((p) => p.block && ids.includes(p.block));
  return (
    <div>
      <h2 className={styles.sideTitle}>{t.pathsTitle}</h2>
      <p className={clsx(styles.muted, 't-caption')}>{t.pathsLead}</p>
      <div className={clsx(styles.tip, 't-caption')}>
        <Info size={16} aria-hidden />
        <span>{t.pathsTip}</span>
      </div>
      <section className={styles.section}>
        <div className={styles.sectionHead}>
          <strong className="t-label">{t.entryTitle(analysis.entry.length)}</strong>
          <span className={clsx(styles.muted, 't-caption')}>{t.entryRight}</span>
        </div>
        {select ? (
          <p className={clsx(styles.muted, 't-caption')}>
            {t.entryLead(circleOf(catalog, 'select'), byName, n)}
          </p>
        ) : null}
        {analysis.entry.map((p, i) => {
          const probs = problemsOn(p.blocks);
          const blanks = probs.filter((x) => x.kind === 'blank').length;
          return (
            <div
              key={p.blocks.join('-')}
              className={clsx(styles.pathCard, probs.length && styles.pathBad)}
            >
              <div className={styles.sectionHead}>
                <strong className="t-label">{t.pathName(t.entryWord, i + 1)}</strong>
                <span className="t-caption">
                  {probs.length
                    ? t.pathProblems(probs.length - blanks, blanks)
                    : t.pathSteps(p.blocks.length - 1)}
                </span>
              </div>
              <span className="t-caption">{pathText(body, catalog, p.blocks)}</span>
            </div>
          );
        })}
      </section>
      <section className={styles.section}>
        <div className={styles.sectionHead}>
          <strong className="t-label">{t.sellTitle(analysis.sell.length)}</strong>
          <span className={clsx(styles.muted, 't-caption')}>{t.sellRight}</span>
        </div>
        <p className={clsx(styles.muted, 't-caption')}>{t.sellLead}</p>
        {analysis.sell.map((p, i) => {
          const probs = problemsOn(p.blocks);
          const rows = p.blocks
            .slice(1)
            .flatMap((id) => rowTexts[id] ?? [])
            .join(' · ');
          return (
            <div
              key={p.blocks.join('-')}
              className={clsx(styles.pathCard, probs.length && styles.pathBad)}
            >
              <div className={styles.sectionHead}>
                <strong className="t-label">{t.pathName(t.sellWord, i + 1)}</strong>
                <span className="t-caption">
                  {probs.length
                    ? t.pathProblems(probs.length, 0)
                    : t.pathSteps(p.blocks.length - 1)}
                </span>
              </div>
              <span className="t-caption">{`${pathText(body, catalog, p.blocks)} · ${rows}`}</span>
            </div>
          );
        })}
      </section>
      {analysis.weight ? (
        <section className={styles.section}>
          <div className={styles.sectionHead}>
            <strong className="t-label">{t.weightTitle}</strong>
            <span className={clsx(styles.muted, 't-caption')}>{t.weightRight}</span>
          </div>
          <div className={styles.pathCard}>
            <strong className="t-label">{`${circleOf(catalog, 'weight')} ${nameOf(catalog, 'weight')}`}</strong>
            <span className="t-caption">
              {`${(rowTexts[analysis.weight] ?? []).map((r) => `${circleOf(catalog, 'weight')} ${r}`).join(' · ')} → ${circleOf(catalog, 'buy')} ${nameOf(catalog, 'buy')}`}
            </span>
          </div>
        </section>
      ) : null}
    </div>
  );
}

export function ProblemList({
  problems,
  warnings,
  catalog,
  onGo,
}: {
  problems: Problem[];
  warnings: Problem[];
  catalog: Catalog;
  onGo: (p: Problem) => void;
}) {
  // 그림 V2-23: 경로 · 단계 문제(줄이 없는 것)를 먼저, 그다음 줄 문제
  const ordered = [
    ...problems.filter((p) => p.row === null),
    ...problems.filter((p) => p.row !== null),
  ];
  return (
    <div>
      {ordered.map((p, i) => {
        const Icon = p.kind === 'blank' ? AlertTriangle : XCircle;
        const detail =
          p.kind === 'blank' || p.kind === 'range' || p.kind === 'locked' ? p.detail : p.detail;
        return (
          <button
            key={`${p.kind}-${p.block}-${String(p.row)}-${String(i)}`}
            type="button"
            className={styles.problemRow}
            onClick={() => {
              onGo(p);
            }}
          >
            <Icon
              size={18}
              aria-hidden
              color={p.kind === 'blank' ? 'var(--status-warning)' : 'var(--status-error)'}
            />
            <span>
              <strong className="t-label">{p.title}</strong>
              <br />
              <span className={clsx(styles.muted, 't-caption')}>
                {detail || circleOf(catalog, p.stage)}
              </span>
            </span>
            <span className={styles.muted}>
              {t.move} <ChevronRight size={14} aria-hidden />
            </span>
          </button>
        );
      })}
      {warnings.map((w) => (
        <div key={`${w.block}-${String(w.row)}`} className={styles.warnBox}>
          <strong className="t-label">
            <AlertTriangle size={14} aria-hidden />{' '}
            {`${t.warning(warnings.indexOf(w) + 1)} · ${w.title}`}
          </strong>
          <span className="t-caption">{`${w.detail} · ${t.warningNote}`}</span>
        </div>
      ))}
    </div>
  );
}

export function StartGuide({
  problems,
  warnings,
  summaryTitle,
  catalog,
  onGo,
}: {
  problems: Problem[];
  warnings: Problem[];
  summaryTitle: string;
  catalog: Catalog;
  onGo: (p: Problem) => void;
}) {
  return (
    <div>
      <h2 className={styles.sideTitle}>{t.startTitle}</h2>
      <ol className={styles.steps}>
        {t.startSteps.map((s, i) => (
          <li key={s.title} className={styles.step}>
            <span className={styles.stepNo}>{i + 1}</span>
            <span>
              <strong className="t-label">{s.title}</strong>
              <br />
              <span className={clsx(styles.muted, 't-caption')}>{s.line}</span>
            </span>
          </li>
        ))}
      </ol>
      {problems.length ? (
        <section className={styles.section}>
          <strong className="t-label">{summaryTitle}</strong>
          <ProblemList problems={problems} warnings={warnings} catalog={catalog} onGo={onGo} />
        </section>
      ) : null}
    </div>
  );
}

export function RowPanel({
  block,
  index,
  catalog,
  effectiveExec,
  onChange,
  onDelete,
  onClose,
}: {
  block: Block;
  index: number;
  catalog: Catalog;
  effectiveExec: ExecId | null;
  onChange: (row: Row) => void;
  onDelete: () => void;
  onClose: () => void;
}) {
  const row = block.rows[index];
  if (!row) return null;
  const item = catalog.items.find((i) => i.id === row.item);
  if (!item) return null;
  const unit = item.value?.unit ?? '';
  const range = item.value
    ? `${item.value.min.toLocaleString()}~${item.value.max.toLocaleString()}${unit}`
    : '';
  const isHolding = item.execs.length > 0;
  const execs: ExecId[] = ['intraday', 'broker', 'close'];
  return (
    <div>
      <div className={styles.sectionHead}>
        <span className={clsx(styles.muted, 't-caption')}>
          {t.panelHead(circleOf(catalog, block.stage), nameOf(catalog, block.stage), index + 1)}
        </span>
        <button type="button" aria-label={t.close} onClick={onClose}>
          <X size={18} aria-hidden />
        </button>
      </div>
      <h2 className={styles.sideTitle}>{item.name}</h2>
      <div className={clsx(styles.section, styles.fieldRow)}>
        {item.ops.length > 1 ? (
          <label className={styles.field}>
            <span className="t-caption">{t.compare}</span>
            <select
              className={styles.input}
              value={row.op}
              onChange={(e) => {
                onChange({ ...row, op: e.target.value });
              }}
            >
              {item.ops.map((o) => (
                <option key={o} value={o}>
                  {catalog.ops[o]}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        {item.value ? (
          <label className={styles.field}>
            <span className="t-caption">
              {isHolding && item.id in t.holdingLabel
                ? t.holdingLabel[item.id as keyof typeof t.holdingLabel]
                : t.value}
            </span>
            <span className={styles.fieldRow}>
              <input
                className={styles.input}
                inputMode="decimal"
                value={typeof row.value === 'number' ? String(row.value) : ''}
                onChange={(e) => {
                  const raw = e.target.value.replace(/,/g, '').trim();
                  onChange({
                    ...row,
                    value: raw === '' || Number.isNaN(Number(raw)) ? null : Number(raw),
                  });
                }}
              />
              <span className={styles.unit}>{unit}</span>
            </span>
          </label>
        ) : null}
      </div>
      {range ? (
        <p className={clsx(styles.muted, 't-caption')}>{t.rangeHint(item.short, range)}</p>
      ) : null}
      <section className={styles.section}>
        <strong className="t-label">{t.help}</strong>
        <p className="t-caption">{item.help}</p>
        <div className={clsx(styles.kv, 't-caption')}>
          <span className={styles.muted}>{t.source}</span>
          <span>{item.source_display}</span>
        </div>
        <div className={clsx(styles.kv, 't-caption')}>
          <span className={styles.muted}>{t.updated}</span>
          <span>{isHolding ? t.updatedIntraday : t.updatedDaily}</span>
        </div>
        <div className={clsx(styles.kv, 't-caption')}>
          <span className={styles.muted}>{t.backtestRow}</span>
          <span>{item.backtest_display}</span>
        </div>
        <div className={clsx(styles.kv, 't-caption')}>
          <span className={styles.muted}>{t.startRow}</span>
          <span>{item.start ? t.startFrom(item.start) : t.noLimit}</span>
        </div>
        {item.chips.map((c) => (
          <div key={c} className={clsx(styles.tip, 't-caption')}>
            <Info size={16} aria-hidden />
            <span>{c}</span>
          </div>
        ))}
      </section>
      {isHolding ? (
        <section className={styles.section}>
          <strong className="t-label">{t.exec}</strong>
          {execs.map((ex) => {
            const allowed = item.execs.includes(ex);
            const on = row.exec === ex;
            const info = t.execs[ex];
            return (
              <button
                key={ex}
                type="button"
                className={clsx(styles.execOption, on && styles.execOptionOn)}
                disabled={!allowed}
                onClick={() => {
                  onChange({ ...row, exec: ex });
                }}
              >
                {on ? <CheckCircle2 size={18} aria-hidden /> : <Circle size={18} aria-hidden />}
                <span>
                  <strong className="t-label">{info.name}</strong>
                  <br />
                  <span className={clsx(styles.muted, 't-caption')}>{info.line}</span>
                  {on && ex === 'intraday' ? (
                    <span className={clsx(styles.warnLine, 't-caption')}>
                      <AlertTriangle size={12} aria-hidden /> {t.execs.intraday.warn}
                    </span>
                  ) : null}
                </span>
              </button>
            );
          })}
          {row.exec !== effectiveExec && effectiveExec === 'close' ? (
            <p className={clsx(styles.muted, 't-caption')}>{t.execRule}</p>
          ) : null}
        </section>
      ) : null}
      <button type="button" className={styles.danger} onClick={onDelete}>
        <MinusCircle size={16} aria-hidden />
        {t.deleteRow}
      </button>
    </div>
  );
}
