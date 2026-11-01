// 편집 모델: 그래프 고치기(조건 놓기 · 선 잇기 · 선 위에 놓기 · 삭제), 되돌리기/다시 하기, 저장 전 변경 세기,
// 숫자 칸 입력 해석(서버 app/graph.py clean_params와 같게).
import type { Body, Catalog, Graph, GraphEdge, GraphNode, ParamValue } from '../../api/mvp';
import { stageOf, type RuleCatalog } from '../../graph/rules';

export function ruleCatalog(c: Catalog): RuleCatalog {
  return { pieces: c.pieces, slots: c.slots, names: c.names };
}

/** Text typed in a number box → what the server stores (number, null, or the text when not a number). */
export function parseNumber(text: string): ParamValue {
  const clean = text.replace(/,/g, '').trim();
  if (clean === '') return null;
  const n = Number(clean);
  return Number.isFinite(n) ? n : text;
}

export function parseSymbols(text: string): string[] {
  const out: string[] = [];
  for (const raw of text.split(/[\s,]+/)) {
    let s = raw.trim().toUpperCase();
    for (const suf of ['.KS', '.KQ']) if (s.endsWith(suf)) s = s.slice(0, -suf.length);
    if (s && !out.includes(s)) out.push(s);
  }
  return out;
}

export function blankParams(cat: Catalog, piece: string): Record<string, ParamValue> {
  const params: Record<string, ParamValue> = {};
  for (const p of cat.pieces[piece]?.params ?? []) params[p.key] = p.kind === 'symbols' ? [] : null;
  return params;
}

const PREFIX: Record<string, string> = {
  universe: 'u',
  signal: 's',
  filter: 'f',
  select: 'k',
  buy: 'b',
  sell: 'x',
  weight: 'w',
};

export function newId(cat: Catalog, g: Graph, piece: string): string {
  const prefix = PREFIX[cat.pieces[piece]?.slot ?? 'filter'] ?? 'n';
  const taken = new Set(g.nodes.map((n) => n.id));
  let i = 1;
  while (taken.has(`${prefix}${String(i)}`)) i++;
  return `${prefix}${String(i)}`;
}

// ── 그래프 고치기 ─────────────────────────────────────────────────────────────

export function addNode(g: Graph, node: GraphNode): Graph {
  return { nodes: [...g.nodes, node], edges: g.edges };
}

export function removeNode(g: Graph, id: string): { graph: Graph; lines: number } {
  const keep = g.edges.filter((e) => e.from !== id && e.to !== id);
  return {
    graph: { nodes: g.nodes.filter((n) => n.id !== id), edges: keep },
    lines: g.edges.length - keep.length,
  };
}

export function addEdge(g: Graph, from: string, to: string): Graph {
  return { nodes: g.nodes, edges: [...g.edges, { from, to }] };
}

export function removeEdge(g: Graph, e: GraphEdge): Graph {
  return { nodes: g.nodes, edges: g.edges.filter((x) => !(x.from === e.from && x.to === e.to)) };
}

/** 선 위에 놓기: A → B를 A → 새 조건 → B로. 선 순서는 그 자리 그대로. */
export function splitEdge(g: Graph, e: GraphEdge, node: GraphNode): Graph {
  const edges: GraphEdge[] = [];
  for (const x of g.edges) {
    if (x.from === e.from && x.to === e.to) {
      edges.push({ from: e.from, to: node.id }, { from: node.id, to: e.to });
    } else edges.push(x);
  }
  return { nodes: [...g.nodes, node], edges };
}

export function setParam(g: Graph, id: string, key: string, value: ParamValue): Graph {
  return {
    nodes: g.nodes.map((n) => (n.id === id ? { ...n, params: { ...n.params, [key]: value } } : n)),
    edges: g.edges,
  };
}

export function moveNode(g: Graph, id: string, x: number, y: number): Graph {
  return {
    nodes: g.nodes.map((n) => (n.id === id ? { ...n, x: Math.round(x), y: Math.round(y) } : n)),
    edges: g.edges,
  };
}

export function placeAll(g: Graph, pos: Record<string, { x: number; y: number }>): Graph {
  return {
    nodes: g.nodes.map((n) => {
      const p = pos[n.id];
      return p ? { ...n, x: p.x, y: p.y } : n;
    }),
    edges: g.edges,
  };
}

// ── 되돌리기 ─────────────────────────────────────────────────────────────────

export interface History {
  now: Graph;
  past: Graph[];
  future: Graph[];
  /** 같은 숫자 칸을 이어서 칠 때는 한 번으로 묶는다. */
  lastKey: string | null;
}

export function historyOf(g: Graph): History {
  return { now: g, past: [], future: [], lastKey: null };
}

export function push(h: History, g: Graph, key: string | null = null): History {
  if (key !== null && key === h.lastKey) return { ...h, now: g };
  return { now: g, past: [...h.past.slice(-99), h.now], future: [], lastKey: key };
}

export function undo(h: History): History {
  const prev = h.past[h.past.length - 1];
  if (!prev) return h;
  return { now: prev, past: h.past.slice(0, -1), future: [h.now, ...h.future], lastKey: null };
}

export function redo(h: History): History {
  const next = h.future[0];
  if (!next) return h;
  return { now: next, past: [...h.past, h.now], future: h.future.slice(1), lastKey: null };
}

// ── 저장 전 변경 ─────────────────────────────────────────────────────────────

export interface Changes {
  added: number;
  removed: number;
  lines: number;
  values: number;
  moved: number;
  name: boolean;
}

export function changes(saved: Body, draft: Body): Changes {
  const a = new Map(saved.graph.nodes.map((n) => [n.id, n]));
  const b = new Map(draft.graph.nodes.map((n) => [n.id, n]));
  let added = 0;
  let removed = 0;
  let values = 0;
  let moved = 0;
  for (const [id, n] of b) {
    const o = a.get(id);
    if (o?.piece !== n.piece) {
      added++;
      continue;
    }
    for (const k of new Set([...Object.keys(o.params), ...Object.keys(n.params)]))
      if (JSON.stringify(o.params[k] ?? null) !== JSON.stringify(n.params[k] ?? null)) values++;
    if (o.x !== n.x || o.y !== n.y) moved++;
  }
  for (const [id, o] of a) {
    const n = b.get(id);
    if (n?.piece !== o.piece) removed++;
  }
  const key = (e: GraphEdge) => `${e.from}>${e.to}`;
  // 삭제 · 추가한 조건에 딸린 선은 조건 수로만 센다
  const both = (e: GraphEdge) => a.has(e.from) && a.has(e.to) && b.has(e.from) && b.has(e.to);
  const ea = new Set(saved.graph.edges.filter(both).map(key));
  const eb = new Set(draft.graph.edges.filter(both).map(key));
  let lines = 0;
  for (const k of ea) if (!eb.has(k)) lines++;
  for (const k of eb) if (!ea.has(k)) lines++;
  return { added, removed, lines, values, moved, name: saved.name !== draft.name };
}

export function changeCount(c: Changes): number {
  return c.added + c.removed + c.lines + c.values + c.moved + (c.name ? 1 : 0);
}

/**
 * 숫자 칸에 보일 글: 치던 글이 지금 그래프 값과 같은 값이면 그 글(쉼표 · 소수점 그대로), 아니면 그래프 값.
 * 되돌리기 · 다시 하기 · 다른 조건 고르기 · 문제 목록에서 이동 뒤에도 칸 = 카드 = 저장 값이 같다.
 */
export function fieldText(
  kind: 'symbols' | 'number',
  typed: string | null,
  value: ParamValue | undefined,
): string {
  if (typed !== null) {
    const parsed = kind === 'symbols' ? parseSymbols(typed) : parseNumber(typed);
    if (JSON.stringify(parsed) === JSON.stringify(value ?? (kind === 'symbols' ? [] : null)))
      return typed;
  }
  return paramText(value);
}

/** 조건 카드에 숫자 칸을 칠 때 보이는 글(빈칸이면 ''). */
export function paramText(v: ParamValue | undefined): string {
  if (Array.isArray(v)) return v.join(', ');
  if (v === null || v === undefined) return '';
  return String(v);
}

export function isStage(cat: RuleCatalog, n: GraphNode, s: string): boolean {
  return stageOf(cat, n.piece) === s;
}
