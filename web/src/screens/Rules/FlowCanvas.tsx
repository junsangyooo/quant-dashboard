// 노드 카드 흐름 (AI 규칙): a dotted canvas with one card per node, placed by col/row from the
// rule definition (1100px up: 3-column grid, Figma 1:62197) or as one column (390, 1:61226), and
// the lines between them in three styles (이번에 지난 길 · 안 지난 갈래 · 예외 갈래) with branch words.
// Lines are measured from the rendered cards, so any rule definition lays out without redesign.
import clsx from 'clsx';
import { useCallback, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { FlowDisplay } from '../../api/types';
import { copy } from '../../copy';
import { rulesCopy as rc } from '../../copy/rules';
import { useMinWidth } from '../History/useMinWidth';
import { FlowCard } from './FlowCards';
import {
  edgeLabelOf,
  routeGrid,
  routeStack,
  stackGaps,
  stackOrder,
  type Box,
  type RoutedEdge,
} from './flowLayout';
import styles from './Rules.module.css';

const LINE_CLASS: Record<RoutedEdge['style'], string | undefined> = {
  taken: styles.lineTaken,
  'not-taken': styles.lineNotTaken,
  exception: styles.lineException,
};

function EdgeLayer({ edges, grid }: { edges: readonly RoutedEdge[]; grid: boolean }) {
  return (
    <svg className={styles.edges} aria-hidden>
      {edges.map((e) => (
        <g key={e.key} className={clsx(styles.edge, LINE_CLASS[e.style])}>
          <path d={e.d} strokeWidth={grid ? 1.5 : e.style === 'taken' ? 2 : 1.5} />
          <polyline
            points={e.arrow}
            strokeWidth={1.5}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          {e.port ? (
            <circle
              className={styles.port}
              cx={e.port.x}
              cy={e.port.y}
              r={3.25}
              strokeWidth={1.5}
            />
          ) : null}
        </g>
      ))}
      {edges.map((e) =>
        e.label ? (
          <g key={`${e.key}-label`}>
            {e.label.boxed ? (
              <rect
                className={styles.labelBox}
                x={e.label.x - labelWidth(e) / 2 - 4}
                y={e.label.y - 9}
                width={labelWidth(e) + 8}
                height={18}
              />
            ) : null}
            <text
              className={styles.edgeLabel}
              x={e.label.x}
              y={e.label.y}
              textAnchor={e.label.anchor}
              dominantBaseline="central"
            >
              {rc.flow.edge[e.label.key]}
            </text>
          </g>
        ) : null,
      )}
    </svg>
  );
}

/** Approximate width of a branch word at 13px (Pretendard, ~12.5px per Hangul syllable). */
function labelWidth(e: RoutedEdge): number {
  const text = e.label ? rc.flow.edge[e.label.key] : '';
  let width = 0;
  for (const ch of text) width += /[가-힣]/.test(ch) ? 12.5 : 4.5;
  return width;
}

export function FlowLegend() {
  return (
    <ul className={styles.flowLegend}>
      {(
        [
          ['taken', rc.flow.legend.taken],
          ['not-taken', rc.flow.legend.notTaken],
          ['exception', rc.flow.legend.exception],
        ] as const
      ).map(([style, text]) => (
        <li key={style} className={styles.legendItem}>
          <svg width={24} height={8} className={clsx(styles.edge, LINE_CLASS[style])} aria-hidden>
            <line x1={0} y1={4} x2={24} y2={4} strokeWidth={1.5} />
          </svg>
          <span className={clsx('t-caption', styles.muted)}>{text}</span>
        </li>
      ))}
    </ul>
  );
}

export interface FlowCanvasProps {
  display: FlowDisplay;
  name: string;
  colorIndex: number;
  ai: boolean;
  nowIso: string | null;
  stale: boolean;
}

export function FlowCanvas({ display, name, colorIndex, ai, nowIso, stale }: FlowCanvasProps) {
  const grid = useMinWidth(1100);
  const { nodes, edges } = display;
  const order = useMemo(() => stackOrder(nodes, edges), [nodes, edges]);
  const gaps = useMemo(() => stackGaps(order, nodes, edges), [order, nodes, edges]);
  const byId = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);
  // Grid rows holding only 예외 cards hang 56 under the row above instead of 72.
  const exceptionRows = useMemo(() => {
    const rows = new Set(nodes.filter((n) => n.type === 'exception').map((n) => n.row));
    for (const n of nodes) if (n.type !== 'exception') rows.delete(n.row);
    return rows;
  }, [nodes]);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const cardRefs = useRef(new Map<string, HTMLElement>());
  const [boxes, setBoxes] = useState<ReadonlyMap<string, Box>>(new Map());

  const measure = useCallback(() => {
    const next = new Map<string, Box>();
    for (const [id, el] of cardRefs.current) {
      next.set(id, { x: el.offsetLeft, y: el.offsetTop, w: el.offsetWidth, h: el.offsetHeight });
    }
    setBoxes((prev) => {
      if (prev.size === next.size) {
        let same = true;
        for (const [id, b] of next) {
          const p = prev.get(id);
          if (p?.x !== b.x || p.y !== b.y || p.w !== b.w || p.h !== b.h) {
            same = false;
            break;
          }
        }
        if (same) return prev;
      }
      return next;
    });
  }, []);

  // The observer reports every card once when it starts watching (before paint) and again on
  // any resize, so the lines follow the cards without measuring during render.
  useLayoutEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(measure);
    ro.observe(canvas);
    for (const el of cardRefs.current.values()) ro.observe(el);
    return () => {
      ro.disconnect();
    };
  }, [measure, grid, display]);

  const routed = useMemo(
    () => (grid ? routeGrid(nodes, edges, boxes) : routeStack(order, nodes, edges, boxes)),
    [grid, nodes, edges, boxes, order],
  );

  const goesTo = (id: string) =>
    edges
      .filter((e) => e.from === id)
      .flatMap((e) => {
        const target = byId.get(e.to);
        if (!target) return [];
        const label = edgeLabelOf(e);
        return [
          rc.flow.goesTo(
            label ? rc.flow.edge[label] : null,
            `${copy.nodeKind[kindOf(target.type)]} ${target.title}`,
          ),
        ];
      });

  return (
    <div className={styles.flowBlock}>
      <div
        ref={canvasRef}
        className={clsx(styles.canvas, grid ? styles.canvasGrid : styles.canvasStack)}
        role="group"
        aria-label={rc.flow.canvas(name)}
      >
        {order.map((id) => {
          const node = byId.get(id);
          if (!node) return null;
          return (
            <div
              key={id}
              ref={(el) => {
                if (el) cardRefs.current.set(id, el);
                else cardRefs.current.delete(id);
              }}
              data-node={id}
              className={clsx(
                styles.cardSlot,
                !grid && styles[`gap-${gaps.get(id) ?? 'default'}`],
                !grid && node.type === 'exception' && styles.indent,
                grid && exceptionRows.has(node.row) && styles.exceptionRow,
              )}
              style={grid ? { gridColumn: node.col + 1, gridRow: node.row + 1 } : undefined}
            >
              <FlowCard
                node={node}
                lane={display.lane}
                colorIndex={colorIndex}
                ai={ai}
                nowIso={nowIso}
                stale={stale}
                goesTo={goesTo(id)}
              />
            </div>
          );
        })}
        <EdgeLayer edges={routed} grid={grid} />
      </div>
      <FlowLegend />
    </div>
  );
}

function kindOf(type: FlowDisplay['nodes'][number]['type']): keyof typeof copy.nodeKind {
  return type === 'stock' ? 'asset' : type;
}
