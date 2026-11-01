// 읽기 전용 그래프(전략 상세 · 예시 상세 · 가져오기 확인 · 좁은 창 편집): 넓으면 왼쪽 → 오른쪽(열이 넘치면
// 진입 줄 · 매수 줄 두 줄), 좁으면 위 → 아래. 빈칸이 있는 조건은 노란 칩.
import clsx from 'clsx';
import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { Analysis, Graph } from '../../api/mvp';
import { useElementWidth } from '../../charts/useElementWidth';
import {
  arrowPath,
  edgeHorizontal,
  edgeVertical,
  normalize,
  readLayout,
  verticalLayout,
  weightFromBelow,
  wrapMidY,
  type Box,
  type Sizes,
} from '../../graph/layout';
import { pieceTitle, stageOf, type RuleCatalog } from '../../graph/rules';
import { StageIcon } from '../StageIcon';
import styles from './Graph.module.css';

const WIDE_CARD = { w: 148, h: 24 };
const WIDE_PITCH = 182;
/** 이 폭보다 좁으면 위에서 아래로. */
export const VERTICAL_BELOW = 600;

export function GraphView({
  cat,
  graph,
  analysis,
  label,
  fixedWidth,
}: {
  cat: RuleCatalog;
  graph: Graph;
  analysis: Analysis;
  label: string;
  fixedWidth?: number;
}) {
  const [ref, width] = useElementWidth(736, fixedWidth);
  const vertical = width < VERTICAL_BELOW;
  const [sizes, setSizes] = useState<Sizes>({});
  const nodeRefs = useRef(new Map<string, HTMLDivElement>());

  const rowWidth = useMemo(() => {
    // 좁은 화면: 한 줄에 놓이는 조건 수로 칩 폭을 정한다
    const none: Record<string, number> = {};
    if (!vertical) return none;
    const pos = verticalLayout(cat, graph, {}, width, { w: 140, h: 40 });
    const rows = new Map<number, string[]>();
    for (const [id, p] of Object.entries(pos)) rows.set(p.y, [...(rows.get(p.y) ?? []), id]);
    const out: Record<string, number> = {};
    for (const ids of rows.values()) {
      const w = ids.length >= 3 ? Math.floor((width - 8 * (ids.length - 1)) / ids.length) : 140;
      for (const id of ids) out[id] = Math.min(140, w);
    }
    for (const n of graph.nodes) if (stageOf(cat, n.piece) === 'weight') out[n.id] = 140;
    return out;
  }, [cat, graph, vertical, width]);

  const cardFor = (id: string) => ({
    w: vertical ? (rowWidth[id] ?? 140) : WIDE_CARD.w,
    h: WIDE_CARD.h,
  });
  const filled: Sizes = {};
  for (const n of graph.nodes) filled[n.id] = sizes[n.id] ?? cardFor(n.id);
  const pos = normalize(
    vertical
      ? verticalLayout(cat, graph, filled, width, { w: 140, h: 24 }, 40)
      : readLayout(cat, graph, filled, width, WIDE_CARD, WIDE_PITCH),
    vertical,
  );

  // 조건 칩 크기를 재서 배치에 쓴다(ResizeObserver가 알려 줄 때만 상태를 바꾼다)
  useLayoutEffect(() => {
    if (typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => {
      const next: Sizes = {};
      for (const [id, el] of nodeRefs.current) next[id] = { w: el.offsetWidth, h: el.offsetHeight };
      setSizes((old) => (JSON.stringify(old) === JSON.stringify(next) ? old : next));
    });
    for (const el of nodeRefs.current.values()) ro.observe(el);
    return () => {
      ro.disconnect();
    };
  }, [graph, width]);

  const box = (id: string): Box | null => {
    const p = pos[id];
    const s = filled[id];
    return p && s ? { x: p.x, y: p.y, w: s.w, h: s.h } : null;
  };
  const height =
    Math.max(40, ...graph.nodes.map((n) => (box(n.id)?.y ?? 0) + (box(n.id)?.h ?? 0))) + 8;
  const minX = Math.min(0, ...graph.nodes.map((n) => box(n.id)?.x ?? 0));
  const contentW =
    Math.max(...graph.nodes.map((n) => (box(n.id)?.x ?? 0) + (box(n.id)?.w ?? 0))) - minX;
  const offsetX = vertical ? 0 : Math.max(0, Math.round((width - contentW) / 2)) - minX;
  const allBoxes = graph.nodes.map((n) => box(n.id)).filter((b) => b !== null);
  const blank = new Set(analysis.problems.filter((p) => p.kind === 'blank').map((p) => p.node));
  const by = new Map(graph.nodes.map((n) => [n.id, n]));

  return (
    <div ref={ref} className={styles.read} role="img" aria-label={label}>
      <div
        className={styles.readInner}
        style={{ height, transform: `translateX(${String(offsetX)}px)` }}
      >
        <svg
          className={styles.readSvg}
          width={Math.max(width, contentW + 40)}
          height={height}
          aria-hidden
        >
          {graph.edges.map((e) => {
            const a = box(e.from);
            const b = box(e.to);
            const an = by.get(e.from);
            if (!a || !b || !an) return null;
            const fromW = stageOf(cat, an.piece) === 'weight';
            const geom = vertical
              ? edgeVertical(a, b)
              : edgeHorizontal(a, b, {
                  fromBelow: fromW && weightFromBelow(a, b),
                  elbow: fromW && !weightFromBelow(a, b) && a.y > b.y + b.h,
                  midY: b.x < a.x ? wrapMidY(allBoxes, a) : null,
                });
            return (
              <g key={`${e.from}>${e.to}`} className={styles.readEdge}>
                <path d={geom.d} />
                <path d={arrowPath(geom.end, 4)} />
              </g>
            );
          })}
        </svg>
        {graph.nodes.map((n) => {
          const p = pos[n.id];
          if (!p) return null;
          const slot = stageOf(cat, n.piece);
          return (
            <div
              key={n.id}
              ref={(el) => {
                if (el) nodeRefs.current.set(n.id, el);
                else nodeRefs.current.delete(n.id);
              }}
              className={clsx('t-label', styles.chip, blank.has(n.id) && styles.chipBlank)}
              style={{ left: p.x, top: p.y, width: cardFor(n.id).w }}
            >
              <StageIcon slot={slot} size={14} />
              <span className={styles.chipText}>{pieceTitle(cat, n)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
