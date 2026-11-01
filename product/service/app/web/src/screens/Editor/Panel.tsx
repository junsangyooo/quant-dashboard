// 오른쪽 패널: 이 전략의 경로 · 문제 목록 · 고른 조건(숫자 칸 · 리밸런싱 방식 · 다음 조건 연결) · 고른 연결 ·
// 잇는 중 안내 · 끌어 오는 중 미리 보기 · 눌러서 추가.
import clsx from 'clsx';
import { useEffect, useRef, useState } from 'react';
import { Check, CircleCheck, CircleX, Info, Lock, TriangleAlert } from 'lucide-react';
import type {
  Analysis,
  Catalog,
  Graph,
  GraphEdge,
  GraphNode,
  ModeId,
  ParamValue,
  Problem,
} from '../../api/mvp';
import { PathsPanel } from '../../components/graph/PathsPanel';
import { StageIcon } from '../../components/StageIcon';
import { editorCopy as t } from '../../copy/editor';
import { graphText, kindNames, modeNames } from '../../copy/graph';
import {
  fieldProblem,
  josa,
  labelOf,
  rangeText,
  slotLabel,
  stageOf,
  type RuleCatalog,
} from '../../graph/rules';
import { pathText } from '../../graph/text';
import { fieldText, parseNumber, parseSymbols } from './model';
import styles from './Editor.module.css';
import { J } from '../../copy/particles';

export interface NextOption {
  id: string;
  ok: boolean;
  line: string;
  order: number;
}

export interface AddOption {
  key: string;
  title: string;
  line: string;
  kind: 'split' | 'free' | 'toBuy' | 'afterBuy';
  edge?: GraphEdge;
}

function ProblemIcon({ p }: { p: Problem }) {
  return p.kind === 'blank' || p.kind === 'required' ? (
    <TriangleAlert size={18} className="c-warn" aria-hidden />
  ) : (
    <CircleX size={18} className="c-error" aria-hidden />
  );
}

export function ProblemsSection({
  analysis,
  onClose,
  onGo,
}: {
  analysis: Analysis;
  onClose: () => void;
  onGo: (p: Problem) => void;
}) {
  return (
    <section className={styles.panelSection}>
      <div className={styles.panelHead}>
        <h2 className="t-heading-1">{t.problems.title(analysis.problems.length)}</h2>
        <button type="button" className="t-label textLink" onClick={onClose}>
          {t.problems.close}
        </button>
      </div>
      <p className="t-caption c-muted">{t.problems.lead}</p>
      <ul className={styles.problemList}>
        {analysis.problems.map((p, i) => (
          <li key={`${p.kind}-${p.node}-${p.field}-${String(i)}`}>
            <button
              type="button"
              className={styles.problemRow}
              onClick={() => {
                onGo(p);
              }}
            >
              <ProblemIcon p={p} />
              <span className="stack-tight">
                <span className="t-body-strong">{p.title}</span>
                <span className="t-caption c-muted">{p.detail}</span>
              </span>
              <span
                className={clsx('t-label', 'c-accent', styles.problemGo)}
              >{`${t.problems.go} ›`}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function Field({
  cat,
  catalog,
  node,
  pkey,
  focus,
  onChange,
}: {
  cat: RuleCatalog;
  catalog: Catalog;
  node: GraphNode;
  pkey: string;
  focus: boolean;
  onChange: (key: string, v: ParamValue) => void;
}) {
  const spec = cat.pieces[node.piece];
  const p = spec?.params.find((x) => x.key === pkey);
  const [typed, setTyped] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement & HTMLTextAreaElement>(null);
  useEffect(() => {
    if (focus) inputRef.current?.focus();
  }, [focus]);
  if (!spec || !p) return null;
  const value = node.params[pkey];
  const text = fieldText(p.kind === 'symbols' ? 'symbols' : 'number', typed, value);
  const setText = setTyped;
  const prob = fieldProblem(p, value);
  const id = `f-${node.id}-${p.key}`;
  if (p.kind === 'choice') {
    const blank = value !== 'target' && value !== 'rank';
    return (
      <fieldset className={styles.howSet}>
        <legend className="t-label">{t.node.how}</legend>
        {catalog.how.map((o) => {
          const on = value === o.id;
          return (
            <button
              key={o.id}
              type="button"
              aria-pressed={on}
              className={clsx(styles.howOpt, on && styles.howOn, blank && styles.howBlank)}
              onClick={() => {
                onChange(p.key, o.id);
              }}
            >
              <span className="stack-tight">
                <span className="t-body-strong">{o.name}</span>
                <span className="t-caption c-muted">{o.line}</span>
              </span>
              {on ? <CircleCheck size={20} className="c-accent" aria-hidden /> : null}
            </button>
          );
        })}
        {blank ? <p className="t-caption c-warn">{t.node.howBlank}</p> : null}
        <p className="t-caption c-muted">{t.node.howNote}</p>
      </fieldset>
    );
  }
  const error = prob?.[0] === 'range' ? prob[1] : null;
  if (p.kind === 'symbols') {
    const list = Array.isArray(value) ? value : [];
    const names = list.slice(0, 3).map((s) => catalog.names[s] ?? s);
    const head = names.join(' · ');
    const shown = list.length > 3 ? graphText.more(head, list.length - 3) : head;
    return (
      <div className="stack-tight">
        <label className="t-label" htmlFor={id}>
          {p.label}
        </label>
        <textarea
          id={id}
          className={clsx('t-body', styles.input, styles.textarea, error && styles.inputBad)}
          value={text}
          spellCheck={false}
          ref={inputRef}
          onChange={(e) => {
            setText(e.target.value);
            onChange(p.key, parseSymbols(e.target.value));
          }}
        />
        {error ? <p className="t-caption c-error">{error}</p> : null}
        <p className="t-caption c-muted">
          {list.length > 0 ? t.node.symbolsLine(shown, p.max) : t.node.symbolsMax(p.max)}
        </p>
      </div>
    );
  }
  return (
    <div className="stack-tight">
      <label className="t-label" htmlFor={id}>
        {p.label}
      </label>
      <span className={clsx(styles.input, styles.inputRow, error && styles.inputBad)}>
        <input
          id={id}
          className="t-body"
          inputMode="decimal"
          value={text}
          ref={inputRef}
          onChange={(e) => {
            setText(e.target.value);
            onChange(p.key, parseNumber(e.target.value));
          }}
        />
        {p.unit ? <span className="t-body c-muted">{p.unit}</span> : null}
      </span>
      {error ? (
        <p className="t-caption c-error">{error}</p>
      ) : (
        <p className="t-caption c-muted">
          {p.range_name
            ? t.node.allowedNamed(p.range_name, rangeText(p))
            : t.node.allowed(rangeText(p))}
        </p>
      )}
    </div>
  );
}

export function NodePanel({
  cat,
  catalog,
  graph,
  analysis,
  node,
  focusField,
  nextOpen,
  next,
  onParam,
  onNext,
  onPickNext,
  onRemove,
}: {
  cat: RuleCatalog;
  catalog: Catalog;
  graph: Graph;
  analysis: Analysis;
  node: GraphNode;
  focusField: string | null;
  nextOpen: boolean;
  next: NextOption[];
  onParam: (key: string, v: ParamValue) => void;
  onNext: () => void;
  onPickNext: (id: string) => void;
  onRemove: () => void;
}) {
  const firstNext = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (nextOpen) firstNext.current?.focus();
  }, [nextOpen]);
  const spec = cat.pieces[node.piece];
  if (!spec) return null;
  const slot = stageOf(cat, node.piece);
  const mode = analysis.mode;
  const help =
    spec.help_rebalance && (mode === 'target' || mode === 'rank') ? spec.help_rebalance : spec.help;
  const entry = analysis.entry.map((p, i) => ({ p, i })).filter((x) => x.p.nodes.includes(node.id));
  const sells = analysis.sell.map((p, i) => ({ p, i })).filter((x) => x.p.nodes.includes(node.id));
  const onSell = slot === 'sell' || (slot === 'buy' && entry.length === 0);
  const mine = onSell ? sells : entry;
  const all = onSell ? analysis.sell.length : analysis.entry.length;
  const kind = onSell ? t.node.sellKind : t.node.entryKind;
  const ok = next.filter((o) => o.ok);
  const no = next.filter((o) => !o.ok);
  const numeric = spec.params.filter((p) => p.kind !== 'choice').length;
  return (
    <div className={styles.panelSection}>
      <p className="t-caption c-muted">{t.node.picked}</p>
      <p className={clsx('t-label', styles.panelStage)}>
        <StageIcon slot={slot} size={16} />
        {slotLabel(cat, slot)}
      </p>
      <div className={styles.fieldCard}>
        <h2 className="t-heading-1">{spec.name}</h2>
        <p className="t-caption c-muted">{help}</p>
        {spec.params.map((p) => (
          <Field
            key={`${node.id}-${p.key}`}
            cat={cat}
            catalog={catalog}
            node={node}
            pkey={p.key}
            focus={focusField === p.key}
            onChange={onParam}
          />
        ))}
      </div>
      {slot !== 'weight' ? (
        <section className="stack-inline">
          <div className={styles.panelHead}>
            <h3 className="t-body-strong">{t.node.pathsTitle}</h3>
            {mine.length > 0 ? (
              <span className="t-caption c-muted">{t.node.pathsCount(all, mine.length, kind)}</span>
            ) : null}
          </div>
          {mine.length === 0 ? <p className="t-caption c-muted">{t.node.noPath}</p> : null}
          {mine.slice(0, 3).map(({ p, i }) => (
            <div key={i} className={styles.pathRow}>
              <div className={styles.panelHead}>
                <span className="t-body-strong">
                  {onSell ? t.paths.sellRow(i + 1) : t.paths.entryRow(i + 1)}
                </span>
                {!onSell && 'complete' in p && !p.complete ? (
                  <span className="t-caption c-error">{t.paths.dead}</span>
                ) : null}
              </div>
              <span className="t-caption">{pathText(cat, graph, p.nodes)}</span>
            </div>
          ))}
        </section>
      ) : null}
      {node.piece === 'rsi_below' ? <p className="t-caption c-muted">{t.node.twoBoxes}</p> : null}
      {(slot === 'signal' || slot === 'filter') && numeric > 0 && node.piece !== 'rsi_below' ? (
        <p className="t-caption c-muted">{t.node.repeat}</p>
      ) : null}
      <button
        type="button"
        className={clsx('t-body-strong', styles.panelButton, nextOpen && styles.panelButtonOn)}
        aria-expanded={nextOpen}
        onClick={onNext}
      >
        {t.node.next}
      </button>
      {nextOpen ? (
        <div className={styles.nextList}>
          <p className="t-caption c-muted">{t.next.head(ok.length, no.length)}</p>
          <p className="t-caption c-muted">{t.next.keys}</p>
          {ok.length === 0 ? <p className="t-caption">{t.next.none}</p> : null}
          {[...ok, ...no].map((o, i) => {
            const n = graph.nodes.find((x) => x.id === o.id);
            if (!n) return null;
            return (
              <button
                key={o.id}
                type="button"
                className={clsx(
                  styles.nextItem,
                  !o.ok && styles.nextLocked,
                  i === 0 && o.ok && styles.nextFirst,
                )}
                disabled={!o.ok}
                ref={i === 0 && o.ok ? firstNext : undefined}
                onClick={() => {
                  onPickNext(o.id);
                }}
              >
                {!o.ok ? <Lock size={14} className="c-muted" aria-hidden /> : null}
                <span className="stack-tight">
                  <span className="t-label">{labelOf(cat, n)}</span>
                  <span className="t-caption c-muted">{o.line}</span>
                </span>
                {i === 0 && o.ok ? <Check size={16} className="c-accent" aria-hidden /> : null}
              </button>
            );
          })}
        </div>
      ) : null}
      <button
        type="button"
        className={clsx('t-body-strong', styles.panelDanger)}
        onClick={onRemove}
      >
        {t.node.remove}
      </button>
      <p className="t-caption c-muted">{t.node.removeNote}</p>
    </div>
  );
}

export function EdgePanel({
  cat,
  graph,
  analysis,
  edge,
  effects,
  onRemove,
}: {
  cat: RuleCatalog;
  graph: Graph;
  analysis: Analysis;
  edge: GraphEdge;
  effects: string[];
  onRemove: () => void;
}) {
  const a = graph.nodes.find((n) => n.id === edge.from);
  const b = graph.nodes.find((n) => n.id === edge.to);
  if (!a || !b) return null;
  const has = (nodes: string[]) =>
    nodes.some((id, i) => id === edge.from && nodes[i + 1] === edge.to);
  const entry = analysis.entry.map((p, i) => (has(p.nodes) ? i + 1 : 0)).filter((k) => k > 0);
  const sell = analysis.sell.map((p, i) => (has(p.nodes) ? i + 1 : 0)).filter((k) => k > 0);
  const weightLine = stageOf(cat, a.piece) === 'weight';
  const line =
    entry.length > 0
      ? t.edge.inEntry(josa(entry.join(' · '), J.eul))
      : sell.length > 0
        ? t.edge.inSell(josa(sell.join(' · '), J.eul))
        : weightLine
          ? t.edge.weightLine
          : t.edge.noPath;
  return (
    <div className={styles.panelSection}>
      <p className="t-caption c-muted">{t.edge.picked}</p>
      <div className={styles.fieldCard}>
        <h2 className="t-heading-1">{t.edge.title(labelOf(cat, a), labelOf(cat, b))}</h2>
        <p className="t-caption c-muted">{line}</p>
      </div>
      <div className={styles.effectBox}>
        <p className={clsx('t-body-strong', styles.effectTitle)}>
          <Info size={16} className="c-warn" aria-hidden />
          {t.edge.effectTitle}
        </p>
        {(effects.length > 0 ? effects : [t.edge.nothing]).map((x) => (
          <p key={x} className="t-caption">
            {x}
          </p>
        ))}
      </div>
      <button
        type="button"
        className={clsx('t-body-strong', styles.panelDanger)}
        onClick={onRemove}
      >
        {t.edge.remove}
      </button>
      <p className="t-caption c-muted">{t.edge.removeNote}</p>
    </div>
  );
}

export function ConnectInfo({ lines, bad }: { lines: string[]; bad: string | null }) {
  return (
    <div className={styles.panelSection}>
      <p className="t-caption c-muted">{t.node.none}</p>
      {bad ? (
        <div className={clsx(styles.infoCard, styles.infoBad)}>
          <p className={clsx('t-body-strong', styles.effectTitle, 'c-error')}>
            <CircleX size={18} aria-hidden />
            {t.connect.badTitle}
          </p>
          <p className="t-caption">{bad}</p>
        </div>
      ) : (
        <div className={styles.infoCard}>
          <p className={clsx('t-body-strong', styles.effectTitle)}>
            <Info size={18} className="c-muted" aria-hidden />
            {t.connect.infoTitle}
          </p>
          {lines.map((l) => (
            <p key={l} className="t-caption">
              {l}
            </p>
          ))}
        </div>
      )}
      <div className={styles.infoCard}>
        <p className="t-body-strong">{t.connect.rulesTitle}</p>
        {t.connect.rules.map((r) => (
          <p key={r} className="t-caption">{`· ${r}`}</p>
        ))}
      </div>
    </div>
  );
}

export function DropInfo({ title, path, free }: { title: string; path: string; free: boolean }) {
  return (
    <div className={styles.panelSection}>
      <div className={styles.infoCard}>
        <p className={clsx('t-body-strong', styles.effectTitle)}>
          <Info size={18} className="c-muted" aria-hidden />
          {free ? t.drop.freeTitle : title}
        </p>
        {free ? null : <p className="t-caption">{path}</p>}
        <p className="t-caption">{free ? t.drop.freeNote : t.drop.previewNote}</p>
      </div>
    </div>
  );
}

export function AddPanel({
  cat,
  piece,
  head,
  options,
  choice,
  onChoice,
  onAdd,
}: {
  cat: RuleCatalog;
  piece: string;
  head: string;
  options: AddOption[];
  choice: string;
  onChoice: (k: string) => void;
  onAdd: () => void;
}) {
  const spec = cat.pieces[piece];
  if (!spec) return null;
  return (
    <div className={styles.panelSection}>
      <p className="t-caption c-muted">{t.add.title}</p>
      <p className={clsx('t-label', styles.panelStage)}>
        <StageIcon slot={spec.slot} size={16} />
        {`${slotLabel(cat, spec.slot)} · ${spec.name}`}
      </p>
      <p className="t-body">{head}</p>
      {options.map((o) => (
        <button
          key={o.key}
          type="button"
          aria-pressed={choice === o.key}
          className={clsx(styles.addOpt, choice === o.key && styles.howOn)}
          onClick={() => {
            onChoice(o.key);
          }}
        >
          <span className="stack-tight">
            <span className="t-body-strong">{o.title}</span>
            <span className="t-caption c-muted">{o.line}</span>
          </span>
          {choice === o.key ? <CircleCheck size={20} className="c-accent" aria-hidden /> : null}
        </button>
      ))}
      <button type="button" className={clsx('t-body-strong', styles.panelPrimary)} onClick={onAdd}>
        {t.add.go}
      </button>
      <p className="t-caption c-muted">{t.add.note}</p>
    </div>
  );
}

export function PathsSide({
  cat,
  graph,
  analysis,
  hot,
  onHover,
  problemsOpen,
  onCloseProblems,
  onGo,
  note,
}: {
  note?: string | null;
  cat: RuleCatalog;
  graph: Graph;
  analysis: Analysis;
  hot: string | null;
  onHover: (key: string | null, nodes: string[] | null) => void;
  problemsOpen: boolean;
  onCloseProblems: () => void;
  onGo: (p: Problem) => void;
}) {
  return (
    <div className={styles.panelSection}>
      {problemsOpen && analysis.problems.length > 0 ? (
        <ProblemsSection analysis={analysis} onClose={onCloseProblems} onGo={onGo} />
      ) : null}
      <PathsPanel
        cat={cat}
        graph={graph}
        analysis={analysis}
        weights
        required={!problemsOpen}
        hoverNote
        hot={hot}
        onHover={onHover}
      />
      {note ? <p className="t-caption c-muted">{note}</p> : null}
    </div>
  );
}

export function kindName(k: Problem['kind']): string {
  return kindNames[k];
}

export function modeName(m: ModeId): string {
  return modeNames[m];
}
