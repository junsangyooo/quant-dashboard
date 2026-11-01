// '이 전략의 경로': 진입 경로 · 매도 경로 · 비중 · 필요한 조건(편집 오른쪽 · 예시 상세 · 좁은 창 편집).
import clsx from 'clsx';
import { useState } from 'react';
import { ChevronDown, ChevronUp, TriangleAlert } from 'lucide-react';
import type { Analysis, Graph } from '../../api/mvp';
import { editorCopy as t } from '../../copy/editor';
import { josa, pieceTitle, stageOf, type RuleCatalog } from '../../graph/rules';
import {
  condCount,
  noSignalPaths,
  pathProblemCount,
  pathText,
  requiredTitle,
  stepText,
} from '../../graph/text';
import styles from './Graph.module.css';
import { J } from '../../copy/particles';

const COMPACT_OVER = 3;

export function PathsPanel({
  cat,
  graph,
  analysis,
  weights = false,
  required = false,
  hoverNote = false,
  headed = true,
  hot,
  onHover,
}: {
  cat: RuleCatalog;
  graph: Graph;
  analysis: Analysis;
  /** ⑦ 비중 칸(편집 화면). */
  weights?: boolean;
  /** 필요한 조건 상자(편집 화면). */
  required?: boolean;
  hoverNote?: boolean;
  headed?: boolean;
  /** 진하게 보일 경로('e0' 진입 · 's0' 매도). */
  hot?: string | null;
  onHover?: ((key: string | null, nodes: string[] | null) => void) | undefined;
}) {
  const [open, setOpen] = useState(false);
  const a = analysis;
  const entry = a.entry;
  const compact = entry.length > COMPACT_OVER;
  const shown = compact && !open ? entry.slice(0, COMPACT_OVER) : entry;
  const noSignal = noSignalPaths(a);
  const select = graph.nodes.find((n) => stageOf(cat, n.piece) === 'select');
  const selectN = select ? select.params.n : null;
  const req = required ? requiredTitle(cat, a) : null;
  const hover = (key: string, nodes: string[]) => ({
    onMouseEnter: () => onHover?.(key, nodes),
    onMouseLeave: () => onHover?.(null, null),
  });

  return (
    <div className={styles.paths}>
      {headed ? (
        <div className="stack-tight">
          <h2 className="t-heading-1">{t.paths.title}</h2>
          <p className="t-caption c-muted">{t.paths.lead}</p>
        </div>
      ) : null}

      <section className={styles.section}>
        <div className={styles.sectionHead}>
          <h3 className="t-body-strong">{t.paths.entry(entry.length)}</h3>
          {entry.length > 0 ? <span className="t-caption c-muted">{t.paths.anyPass}</span> : null}
        </div>
        {entry.length === 0 ? (
          <p className="t-caption c-muted">{t.paths.noPaths}</p>
        ) : compact ? (
          <p className="t-caption c-muted">{t.paths.entryLimit(20)}</p>
        ) : entry.length > 1 || select ? (
          <p className="t-caption c-muted">
            {select
              ? t.paths.entryLead(typeof selectN === 'number' ? String(selectN) : 'n')
              : t.paths.entryLeadNoSelect}
          </p>
        ) : null}
        {shown.map((p, i) => {
          const k = i + 1;
          const dead = !p.complete;
          const ranges = pathProblemCount(a, p.nodes, 'range');
          const blanks = pathProblemCount(a, p.nodes, 'blank');
          const bad = dead || (noSignal.has(k) && ranges === 0 && blanks === 0);
          const tag = dead
            ? t.paths.dead
            : ranges > 0
              ? t.paths.ranges(ranges)
              : blanks > 0
                ? t.paths.blanks(blanks)
                : noSignal.has(k)
                  ? t.paths.noSignal
                  : t.paths.conds(condCount(cat, graph, p.nodes));
          const key = `e${String(i)}`;
          return (
            <div
              key={key}
              className={clsx(styles.row, bad ? styles.rowBad : hot === key && styles.rowHot)}
              {...(onHover ? hover(key, p.nodes) : {})}
            >
              <div className={styles.rowHead}>
                <span className={clsx('t-body-strong', styles.rowTitle)}>
                  {t.paths.entryRow(k)}
                </span>
                <span className={clsx('t-caption', styles.rowTag)}>{tag}</span>
              </div>
              <span className="t-caption">{pathText(cat, graph, p.nodes, compact)}</span>
            </div>
          );
        })}
        {compact ? (
          <button
            type="button"
            className={clsx('t-label', styles.more)}
            aria-expanded={open}
            onClick={() => {
              setOpen(!open);
            }}
          >
            {open ? t.paths.less : t.paths.more(entry.length - COMPACT_OVER)}
            {open ? <ChevronUp size={14} aria-hidden /> : <ChevronDown size={14} aria-hidden />}
          </button>
        ) : null}
      </section>

      <section className={styles.section}>
        {a.sell.length === 0 ? (
          <>
            <h3 className="t-body-strong">{t.paths.sellNone}</h3>
            <p className="t-caption c-muted">{t.paths.sellNoneLead}</p>
          </>
        ) : (
          <>
            <div className={styles.sectionHead}>
              <h3 className="t-body-strong">{t.paths.sell(a.sell.length)}</h3>
              <span className="t-caption c-muted">
                {a.sell.length === 1 && (a.sell[0]?.nodes.length ?? 0) > 2
                  ? t.paths.sellAll
                  : t.paths.sellAny}
              </span>
            </div>
            {a.sell.length > 1 || (a.sell[0]?.nodes.length ?? 0) <= 2 ? (
              <p className="t-caption c-muted">{t.paths.sellLead}</p>
            ) : null}
            {a.sell.map((p, i) => {
              const key = `s${String(i)}`;
              const chain = p.nodes.length > 2;
              const names = p.nodes.slice(1).map((id) => {
                const n = graph.nodes.find((x) => x.id === id);
                return n ? pieceTitle(cat, n) : id;
              });
              return (
                <div
                  key={key}
                  className={clsx(styles.row, hot === key && styles.rowHot)}
                  {...(onHover ? hover(key, p.nodes) : {})}
                >
                  <div className={styles.rowHead}>
                    <span className="t-body-strong">{t.paths.sellRow(i + 1)}</span>
                    {chain ? (
                      <span className={clsx('t-caption', styles.rowTag)}>
                        {t.paths.conds(p.nodes.length - 1)}
                      </span>
                    ) : null}
                  </div>
                  <span className="t-caption">
                    {pathText(cat, graph, p.nodes)}
                    {chain ? ` · ${t.paths.chainLine(chainNames(names))}` : ''}
                  </span>
                </div>
              );
            })}
          </>
        )}
      </section>

      {weights && a.weights.length > 0 ? (
        <section className={styles.section}>
          <div className={styles.sectionHead}>
            <h3 className="t-body-strong">{t.paths.weight}</h3>
            <span className="t-caption c-muted">{t.paths.weightTogether}</span>
          </div>
          <div className={styles.row}>
            <span className="t-body-strong">{t.paths.weightRow}</span>
            {a.weights.map((id) => (
              <span key={id} className="t-caption">
                {`${stepText(cat, graph, id)} → ${t.paths.buy}`}
              </span>
            ))}
          </div>
        </section>
      ) : null}

      {req ? (
        <div className={styles.required}>
          <TriangleAlert size={18} className={styles.requiredIcon} aria-hidden />
          <div className={styles.requiredText}>
            <p className="t-body-strong">{req}</p>
            {a.problems
              .filter((p) => p.kind === 'required')
              .map((p) => (
                <p key={p.short} className="t-caption">
                  {p.hint ? `${p.short} · ${p.hint}` : p.short}
                </p>
              ))}
          </div>
        </div>
      ) : null}

      {hoverNote && onHover ? <p className="t-caption c-muted">{t.paths.hoverNote}</p> : null}
    </div>
  );
}

/** '손절 −8%와 최대 보유 30거래일이'. */
function chainNames(names: string[]): string {
  return joinParticles(names);
}

function joinParticles(names: string[]): string {
  if (names.length === 0) return '';
  const head = names.slice(0, -1).map((n) => josa(n, J.gwa));
  return josa([...head, names[names.length - 1] ?? ''].join(' '), J.iga);
}
