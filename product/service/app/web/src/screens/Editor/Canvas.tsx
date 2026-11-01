// 캔버스: 조건 카드 · 선 · 연결점 · 이름표. 끌어 옮기기, 연결점 끌어 잇기, 빈 곳 끌어 화면 옮기기, Ctrl/⌘+휠 확대.
// 좌표는 캔버스 좌표(world). 화면 좌표 = world × zoom + view.
import clsx from 'clsx';
import {
  forwardRef,
  useImperativeHandle,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react';
import { ArrowRight, CircleX, Split, Trash2 } from 'lucide-react';
import type { Analysis, Graph, GraphEdge, ProblemKind } from '../../api/mvp';
import { StageIcon } from '../../components/StageIcon';
import { editorCopy as t } from '../../copy/editor';
import {
  arrowPath,
  edgeHorizontal,
  weightFromBelow,
  wrapMidY,
  type Box,
  type Sizes,
} from '../../graph/layout';
import { pieceTitle, slotLabel, stageOf, type RuleCatalog } from '../../graph/rules';
import styles from './Editor.module.css';

export interface View {
  x: number;
  y: number;
  z: number;
}

export type Selection = { kind: 'node'; id: string } | { kind: 'edge'; edge: GraphEdge } | null;

export interface Connecting {
  from: string;
  x: number;
  y: number;
  over: string | null;
  /** 이을 수 있는 조건(보라색 연결점). */
  ok: ReadonlySet<string>;
  why: string | null;
}

export interface DropState {
  /** 선 위에 놓을 수 있는 선(점선) · 지금 가까운 선. */
  candidates: GraphEdge[];
  near: GraphEdge | null;
  ghost: { x: number; y: number; title: string; slot: string } | null;
}

export interface CanvasHandle {
  toWorld: (clientX: number, clientY: number) => { x: number; y: number } | null;
  rect: () => DOMRect | null;
  focusNode: (id: string) => void;
}

const HIT = 12; // 연결점 누르는 영역 24px(반지름 12)

export function edgeKey(e: GraphEdge) {
  return `${e.from}>${e.to}`;
}

export function nodeBox(g: Graph, sizes: Sizes, id: string): Box | null {
  const n = g.nodes.find((x) => x.id === id);
  if (!n) return null;
  if (n.x === null || n.y === null) return null;
  const s = sizes[id] ?? { w: 150, h: 64 };
  return { x: n.x, y: n.y, w: s.w, h: s.h };
}

export function edgeGeom(cat: RuleCatalog, g: Graph, sizes: Sizes, e: GraphEdge) {
  const a = nodeBox(g, sizes, e.from);
  const b = nodeBox(g, sizes, e.to);
  const an = g.nodes.find((x) => x.id === e.from);
  if (!a || !b || !an) return null;
  const fromBelow = stageOf(cat, an.piece) === 'weight' && weightFromBelow(a, b);
  const mid =
    b.x < a.x
      ? wrapMidY(
          g.nodes.map((n) => nodeBox(g, sizes, n.id)).filter((x) => x !== null),
          a,
        )
      : null;
  return { a, b, fromBelow, mid, geom: edgeHorizontal(a, b, { fromBelow, midY: mid }) };
}

interface Props {
  cat: RuleCatalog;
  graph: Graph;
  analysis: Analysis;
  sizes: Sizes;
  onSizes: (s: Sizes) => void;
  view: View;
  onView: (v: View) => void;
  sel: Selection;
  hot: ReadonlySet<string> | null;
  tags: Record<string, 'branch' | 'chain'>;
  conn: Connecting | null;
  drop: DropState | null;
  onSelect: (s: Selection) => void;
  onMove: (id: string, x: number, y: number) => void;
  onConnectStart: (from: string, x: number, y: number) => void;
  onConnectMove: (x: number, y: number, over: string | null) => void;
  onConnectEnd: () => void;
  onRemoveEdge: (e: GraphEdge) => void;
  onKey: (e: ReactKeyboardEvent<HTMLDivElement>) => void;
  editable: boolean;
}

export const Canvas = forwardRef<CanvasHandle, Props>(function Canvas(p, ref) {
  const wrap = useRef<HTMLDivElement>(null);
  const nodeRefs = useRef(new Map<string, HTMLDivElement>());
  const [moving, setMoving] = useState<{ id: string; x: number; y: number } | null>(null);
  const [size, setSize] = useState({ w: 872, h: 800 });
  useLayoutEffect(() => {
    const el = wrap.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => {
      setSize({ w: el.clientWidth, h: el.clientHeight });
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
    };
  }, []);
  /** 설명 상자 자리: 오른쪽 · 왼쪽 · 아래 · 위 가운데 조건 카드와 겹치지 않고 캔버스 안에 드는 첫 자리. */
  const CALLOUT = { w: 200, h: 84 };
  const calloutAt = (b: Box, others: Box[]) => {
    const lefts = [b.x + b.w + 20, b.x - CALLOUT.w - 20, b.x, b.x + b.w - CALLOUT.w];
    const tops = [
      b.y - 8,
      b.y + b.h + 14,
      b.y - CALLOUT.h - 14,
      b.y + b.h + 110,
      b.y - CALLOUT.h - 110,
    ];
    const cands = tops.flatMap((top) => lefts.map((left) => ({ left, top })));
    const hits = (c: { left: number; top: number }) =>
      others.some(
        (o) =>
          c.left < o.x + o.w + 6 &&
          c.left + CALLOUT.w > o.x - 6 &&
          c.top < o.y + o.h + 6 &&
          c.top + CALLOUT.h > o.y - 6,
      );
    const inside = (c: { left: number; top: number }) =>
      c.left * view.z + view.x >= 0 &&
      (c.left + CALLOUT.w) * view.z + view.x <= size.w &&
      c.top * view.z + view.y >= 60 &&
      (c.top + CALLOUT.h) * view.z + view.y <= size.h - 70;
    return (
      cands.find((c) => !hits(c) && inside(c)) ??
      cands.find((c) => !hits(c)) ??
      cands[0] ?? { left: 0, top: 0 }
    );
  };
  const gesture = useRef<
    | { kind: 'pan'; sx: number; sy: number; vx: number; vy: number; moved: boolean }
    | { kind: 'node'; id: string; sx: number; sy: number; nx: number; ny: number; moved: boolean }
    | { kind: 'conn'; from: string }
    | null
  >(null);
  const { cat, analysis, view } = p;
  const graph: Graph = moving
    ? {
        nodes: p.graph.nodes.map((n) =>
          n.id === moving.id ? { ...n, x: moving.x, y: moving.y } : n,
        ),
        edges: p.graph.edges,
      }
    : p.graph;

  useImperativeHandle(ref, () => ({
    toWorld: (cx, cy) => {
      const r = wrap.current?.getBoundingClientRect();
      if (!r) return null;
      return { x: (cx - r.left - view.x) / view.z, y: (cy - r.top - view.y) / view.z };
    },
    rect: () => wrap.current?.getBoundingClientRect() ?? null,
    focusNode: (id) => {
      nodeRefs.current.get(id)?.focus({ preventScroll: true });
    },
  }));

  useLayoutEffect(() => {
    const next: Sizes = {};
    let changed = false;
    for (const n of p.graph.nodes) {
      const el = nodeRefs.current.get(n.id);
      if (!el) continue;
      const s = { w: el.offsetWidth, h: el.offsetHeight };
      next[n.id] = s;
      const old = p.sizes[n.id];
      if (old?.w !== s.w || old.h !== s.h) changed = true;
    }
    if (changed || Object.keys(p.sizes).length !== Object.keys(next).length) p.onSizes(next);
  });

  const world = (cx: number, cy: number) => {
    const r = wrap.current?.getBoundingClientRect();
    return r
      ? { x: (cx - r.left - view.x) / view.z, y: (cy - r.top - view.y) / view.z }
      : { x: 0, y: 0 };
  };

  const overNode = (wx: number, wy: number): string | null => {
    for (const n of [...graph.nodes].reverse()) {
      const b = nodeBox(graph, p.sizes, n.id);
      if (!b) continue;
      if (wx >= b.x - HIT && wx <= b.x + b.w + HIT && wy >= b.y - HIT && wy <= b.y + b.h + HIT)
        return n.id;
    }
    return null;
  };

  const onBgDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (e.button !== 0 || e.target !== e.currentTarget) return;
    gesture.current = {
      kind: 'pan',
      sx: e.clientX,
      sy: e.clientY,
      vx: view.x,
      vy: view.y,
      moved: false,
    };
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const onMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const g = gesture.current;
    if (!g) return;
    if (g.kind === 'pan') {
      const dx = e.clientX - g.sx;
      const dy = e.clientY - g.sy;
      if (Math.abs(dx) + Math.abs(dy) > 3) g.moved = true;
      if (g.moved) p.onView({ ...view, x: g.vx + dx, y: g.vy + dy });
    } else if (g.kind === 'node') {
      const dx = (e.clientX - g.sx) / view.z;
      const dy = (e.clientY - g.sy) / view.z;
      if (Math.abs(dx) + Math.abs(dy) > 3) g.moved = true;
      if (g.moved) setMoving({ id: g.id, x: Math.round(g.nx + dx), y: Math.round(g.ny + dy) });
    } else {
      const w = world(e.clientX, e.clientY);
      const over = overNode(w.x, w.y);
      p.onConnectMove(w.x, w.y, over === g.from ? null : over);
    }
  };

  const onUp = () => {
    const g = gesture.current;
    gesture.current = null;
    if (!g) return;
    if (g.kind === 'pan' && !g.moved) p.onSelect(null);
    if (g.kind === 'node') {
      if (g.moved && moving) p.onMove(g.id, moving.x, moving.y);
      else p.onSelect({ kind: 'node', id: g.id });
      setMoving(null);
    }
    if (g.kind === 'conn') p.onConnectEnd();
  };

  const onWheel = (e: React.WheelEvent<HTMLDivElement>) => {
    if (e.ctrlKey || e.metaKey) {
      const r = wrap.current?.getBoundingClientRect();
      if (!r) return;
      const z = Math.min(2, Math.max(0.3, view.z * (e.deltaY < 0 ? 1.1 : 1 / 1.1)));
      const px = e.clientX - r.left;
      const py = e.clientY - r.top;
      p.onView({ z, x: px - ((px - view.x) / view.z) * z, y: py - ((py - view.y) / view.z) * z });
    } else {
      p.onView({ ...view, x: view.x - e.deltaX, y: view.y - e.deltaY });
    }
  };

  const kinds = (id: string): Set<ProblemKind> =>
    new Set(analysis.problems.filter((x) => x.node === id).map((x) => x.kind));
  const outCount = new Map<string, number>();
  const inCount = new Map<string, number>();
  for (const e of graph.edges) {
    outCount.set(e.from, (outCount.get(e.from) ?? 0) + 1);
    inCount.set(e.to, (inCount.get(e.to) ?? 0) + 1);
  }
  const selEdge = p.sel?.kind === 'edge' ? edgeKey(p.sel.edge) : null;
  const selNode = p.sel?.kind === 'node' ? p.sel.id : null;
  const candidates = new Set((p.drop?.candidates ?? []).map(edgeKey));
  const near = p.drop?.near ? edgeKey(p.drop.near) : null;
  const dead = new Set(analysis.problems.filter((x) => x.kind === 'dead').map((x) => x.node));
  const unusable = analysis.problems.filter((x) => x.kind === 'unusable');
  const boxes = graph.nodes
    .map((n) => ({ id: n.id, b: nodeBox(graph, p.sizes, n.id) }))
    .filter((x): x is { id: string; b: Box } => x.b !== null);
  const othersOf = (id: string) => boxes.filter((x) => x.id !== id).map((x) => x.b);
  /** 이름표 자리: 카드 위 가운데, 다른 카드와 겹치면 카드 아래 → 카드 오른쪽 위. */
  const TAG = { w: 112, h: 22 };
  const tagAt = (id: string): 'top' | 'bottom' | 'side' => {
    const b = boxes.find((x) => x.id === id)?.b;
    if (!b) return 'top';
    const hit = (x: number, y: number) =>
      othersOf(id).some(
        (o) => x < o.x + o.w && x + TAG.w > o.x && y < o.y + o.h && y + TAG.h > o.y,
      );
    const cx = b.x + b.w / 2 - TAG.w / 2;
    if (!hit(cx, b.y - 8 - TAG.h)) return 'top';
    if (!hit(cx, b.y + b.h + 8)) return 'bottom';
    return 'side';
  };

  const edgeEls = graph.edges.map((e) => {
    const eg = edgeGeom(cat, graph, p.sizes, e);
    if (!eg) return null;
    const k = edgeKey(e);
    const isHot = p.hot !== null && p.hot.has(e.from) && p.hot.has(e.to);
    return (
      <g
        key={k}
        className={clsx(
          styles.edge,
          isHot && styles.edgeHot,
          selEdge === k && styles.edgeSel,
          candidates.has(k) && styles.edgeCand,
          near === k && styles.edgeNear,
        )}
      >
        {p.editable ? (
          <path
            d={eg.geom.d}
            className={styles.edgeHit}
            data-edge={k}
            onPointerDown={(ev) => {
              ev.stopPropagation();
            }}
            onClick={(ev) => {
              ev.stopPropagation();
              p.onSelect({ kind: 'edge', edge: e });
            }}
          />
        ) : null}
      </g>
    );
  });

  // 보이는 선은 조건 카드 위에 그린다(다른 카드 아래로 지나가도 보이게). 누르는 자리는 카드 아래 층.
  const lineEls = graph.edges.map((e) => {
    const eg = edgeGeom(cat, graph, p.sizes, e);
    if (!eg) return null;
    const k = edgeKey(e);
    const isHot = p.hot !== null && p.hot.has(e.from) && p.hot.has(e.to);
    return (
      <g
        key={k}
        className={clsx(
          styles.edge,
          isHot && styles.edgeHot,
          selEdge === k && styles.edgeSel,
          candidates.has(k) && styles.edgeCand,
          near === k && styles.edgeNear,
        )}
      >
        <path d={eg.geom.d} className={styles.edgeLine} />
        <path d={arrowPath(eg.geom.end, 5)} className={styles.edgeArrow} />
      </g>
    );
  });

  // 잇는 중인 선
  let connLine = null;
  if (p.conn) {
    const a = nodeBox(graph, p.sizes, p.conn.from);
    if (a) {
      const target = p.conn.over ? nodeBox(graph, p.sizes, p.conn.over) : null;
      const okTarget = p.conn.over !== null && p.conn.ok.has(p.conn.over);
      const end = target
        ? { x: target.x, y: target.y + target.h / 2 }
        : { x: p.conn.x, y: p.conn.y };
      const sx = a.x + a.w;
      const sy = a.y + a.h / 2;
      const dx = Math.max(30, Math.abs(end.x - sx) / 2);
      connLine = (
        <path
          className={clsx(styles.connLine, p.conn.over && !okTarget && styles.connBad)}
          d={`M${String(sx)} ${String(sy)} C${String(sx + dx)} ${String(sy)} ${String(end.x - dx)} ${String(end.y)} ${String(end.x)} ${String(end.y)}`}
        />
      );
    }
  }

  const sorted = [...graph.nodes].sort(
    (a, b) => (a.x ?? 0) - (b.x ?? 0) || (a.y ?? 0) - (b.y ?? 0),
  );

  return (
    // 캔버스(끌어 옮기기 · 연결점 잇기 · 휠 확대)는 포인터로 다룬다. 키보드는 조건 카드(Tab · Enter · Delete)와
    // 오른쪽 패널 '다음 조건 연결'로 같은 일을 한다.
    // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
    <div
      ref={wrap}
      className={styles.canvas}
      onPointerDown={onBgDown}
      onPointerMove={onMove}
      onPointerUp={onUp}
      onLostPointerCapture={onUp}
      onWheel={onWheel}
      onKeyDown={p.onKey}
      role="application"
      aria-label={t.tool.canvas}
      tabIndex={-1}
    >
      <div
        className={styles.world}
        style={{
          transform: `translate(${String(view.x)}px, ${String(view.y)}px) scale(${String(view.z)})`,
        }}
      >
        <svg className={styles.svg} width="1" height="1" aria-hidden>
          {edgeEls}
        </svg>
        <svg className={clsx(styles.svg, styles.svgTop)} width="1" height="1" aria-hidden>
          {lineEls}
          {connLine}
        </svg>
        {/* 고른 선 가운데의 '연결 삭제' */}
        {p.sel?.kind === 'edge' && p.editable
          ? (() => {
              const eg = edgeGeom(cat, graph, p.sizes, p.sel.edge);
              if (!eg) return null;
              const edge = p.sel.edge;
              return (
                <button
                  type="button"
                  className={clsx('t-label', styles.edgeChip)}
                  style={{ left: eg.geom.mid.x, top: eg.geom.mid.y }}
                  onPointerDown={(ev) => {
                    ev.stopPropagation();
                  }}
                  onClick={() => {
                    p.onRemoveEdge(edge);
                  }}
                >
                  <Trash2 size={14} aria-hidden />
                  {t.edge.remove}
                </button>
              );
            })()
          : null}
        {sorted.map((n) => {
          if (n.x === null || n.y === null) return null;
          const slot = stageOf(cat, n.piece);
          const k = kinds(n.id);
          const isSel = selNode === n.id;
          const isHot = p.hot?.has(n.id) ?? false;
          const errorKinds: ProblemKind[] = ['range', 'loose', 'unusable', 'dead', 'rule'];
          const bad = errorKinds.some((x) => k.has(x));
          const warn = k.has('blank');
          const okTarget = p.conn?.ok.has(n.id) ?? false;
          const badTarget = p.conn?.over === n.id && !okTarget;
          const hasIn = slot !== 'universe' && slot !== 'weight';
          const tag = p.tags[n.id];
          return (
            <div
              key={n.id}
              ref={(el) => {
                if (el) nodeRefs.current.set(n.id, el);
                else nodeRefs.current.delete(n.id);
              }}
              className={clsx(
                styles.node,
                isSel ? styles.nodeSel : bad ? styles.nodeBad : warn ? styles.nodeWarn : null,
                isHot && styles.nodeHot,
                badTarget && styles.nodeBad,
                moving?.id === n.id && styles.nodeMoving,
              )}
              style={{ left: n.x, top: n.y }}
              data-node={n.id}
              tabIndex={0}
              role="button"
              aria-pressed={isSel}
              aria-label={`${slotLabel(cat, slot)} · ${pieceTitle(cat, n)}`}
              onPointerDown={(e) => {
                if (e.button !== 0 || !p.editable) return;
                e.stopPropagation();
                gesture.current = {
                  kind: 'node',
                  id: n.id,
                  sx: e.clientX,
                  sy: e.clientY,
                  nx: n.x ?? 0,
                  ny: n.y ?? 0,
                  moved: false,
                };
                wrap.current?.setPointerCapture(e.pointerId);
              }}
              onClick={() => {
                if (!p.editable) p.onSelect({ kind: 'node', id: n.id });
              }}
              onKeyDown={(e) => {
                if (!p.editable && (e.key === 'Enter' || e.key === ' ')) {
                  e.preventDefault();
                  p.onSelect({ kind: 'node', id: n.id });
                }
              }}
            >
              {tag ? (
                <span
                  className={clsx(
                    't-label',
                    styles.tag,
                    tagAt(n.id) === 'bottom' && styles.tagBottom,
                    tagAt(n.id) === 'side' && styles.tagSide,
                  )}
                >
                  {tag === 'branch' ? (
                    <Split size={12} aria-hidden />
                  ) : (
                    <ArrowRight size={12} aria-hidden />
                  )}
                  {tag === 'branch' ? t.tags.branch : t.tags.chain}
                </span>
              ) : null}
              <span className={clsx('t-caption', styles.nodeStage)}>
                <StageIcon slot={slot} size={14} />
                {slotLabel(cat, slot)}
              </span>
              <span className={clsx('t-body-strong', styles.nodeTitle)}>{pieceTitle(cat, n)}</span>
              {warn || k.has('range') || k.has('loose') || k.has('unusable') ? (
                <span className={styles.nodeChips}>
                  {warn ? (
                    <span className={clsx('t-micro', styles.chipWarn)}>{t.chips.blank}</span>
                  ) : null}
                  {k.has('range') ? (
                    <span className={clsx('t-micro', styles.chipBad)}>{t.chips.range}</span>
                  ) : null}
                  {k.has('loose') ? (
                    <span className={clsx('t-micro', styles.chipBad)}>{t.chips.loose}</span>
                  ) : null}
                  {k.has('unusable') ? (
                    <span className={clsx('t-micro', styles.chipBad)}>{t.chips.unusable}</span>
                  ) : null}
                </span>
              ) : null}
              {hasIn ? (
                <span
                  className={clsx(
                    styles.port,
                    styles.portIn,
                    (inCount.get(n.id) ?? 0) > 0 && styles.portOn,
                    okTarget && styles.portOk,
                    badTarget && styles.portBad,
                  )}
                  aria-hidden
                />
              ) : null}
              <span
                className={clsx(
                  styles.port,
                  styles.portOut,
                  (outCount.get(n.id) ?? 0) > 0 && styles.portOn,
                  p.conn?.from === n.id && styles.portOk,
                )}
                aria-hidden
                onPointerDown={(e) => {
                  if (e.button !== 0 || !p.editable) return;
                  e.stopPropagation();
                  const b = nodeBox(graph, p.sizes, n.id);
                  gesture.current = { kind: 'conn', from: n.id };
                  wrap.current?.setPointerCapture(e.pointerId);
                  if (b) p.onConnectStart(n.id, b.x + b.w, b.y + b.h / 2);
                }}
              />
              {dead.has(n.id) && !isSel ? (
                <span className={clsx('t-label', styles.deadPill)}>
                  <CircleX size={14} aria-hidden />
                  {t.chips.dead}
                </span>
              ) : null}
            </div>
          );
        })}
        {/* 못 쓰는 조건 설명 · 잇는 중 안 되는 곳 설명(조건 오른쪽) */}
        {unusable.map((u) => {
          const b = nodeBox(graph, p.sizes, u.node);
          if (!b || selNode === u.node) return null;
          return (
            <div
              key={`u-${u.node}`}
              className={clsx('t-caption', styles.callout)}
              style={calloutAt(
                b,
                boxes.map((x) => x.b),
              )}
            >
              <CircleX size={16} className={styles.calloutIcon} aria-hidden />
              <span>{u.short}</span>
            </div>
          );
        })}
        {p.conn?.over && !p.conn.ok.has(p.conn.over) && p.conn.why
          ? (() => {
              const b = nodeBox(graph, p.sizes, p.conn.over);
              if (!b) return null;
              return (
                <div
                  className={clsx('t-caption', styles.callout)}
                  style={calloutAt(
                    b,
                    boxes.map((x) => x.b),
                  )}
                >
                  <CircleX size={16} className={styles.calloutIcon} aria-hidden />
                  <span>{t.connect.badTip(p.conn.why)}</span>
                </div>
              );
            })()
          : null}
        {p.drop?.ghost ? (
          <div
            className={clsx(styles.node, styles.nodeGhost)}
            style={{ left: p.drop.ghost.x, top: p.drop.ghost.y }}
            aria-hidden
          >
            <span className={clsx('t-caption', styles.nodeStage)}>
              <StageIcon slot={p.drop.ghost.slot as never} size={14} />
              {slotLabel(cat, p.drop.ghost.slot as never)}
            </span>
            <span className={clsx('t-body-strong', styles.nodeTitle)}>{p.drop.ghost.title}</span>
            <span className={clsx(styles.port, styles.portIn)} />
            <span className={clsx(styles.port, styles.portOut)} />
          </div>
        ) : null}
      </div>
    </div>
  );
});
