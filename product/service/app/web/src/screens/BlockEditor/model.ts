// Pure edits on a v3 block body (app/blocks.py is the source of truth for rules; the server
// re-checks every change). Link reasons mirror blocks.link_reason / edge_reason so a red line
// shows while dragging, before the server answers.
import type { Block, Body, CatalogItem, Edge, ExecId, Row, StageId } from '../../api/v2';
import { blockEditor } from '../../copy/blockEditor';

export const STAGES: StageId[] = [
  'universe',
  'signal',
  'filter',
  'select',
  'buy',
  'sell',
  'weight',
];
export const ONCE: StageId[] = ['universe', 'select', 'buy', 'weight'];
export const TOGGLE: StageId[] = ['signal', 'filter', 'sell'];
export const CARD_W = 256;
export const BLOCK_MAX = 20;
export const ROW_MAX = 10;

export const R = blockEditor.links;

const NEXT_ID = (blocks: Block[], stage: StageId) => {
  const prefix = {
    universe: 'u',
    signal: 's',
    filter: 'f',
    select: 'k',
    buy: 'b',
    sell: 'x',
    weight: 'w',
  }[stage];
  let n = 1;
  const ids = new Set(blocks.map((b) => b.id));
  while (ids.has(`${prefix}${String(n)}`)) n += 1;
  return `${prefix}${String(n)}`;
};

export function newRow(item: CatalogItem, op?: string): Row {
  const o = op ?? item.ops[0] ?? 'fixed';
  const params: Row['params'] = {};
  for (const p of item.params) {
    if (p.when_op.length && !p.when_op.includes(o)) continue;
    params[p.key] = null;
  }
  if (item.id === 'top_n') {
    params.by = 'strength';
    params.order = 'desc';
    delete params.n;
  }
  let exec: ExecId | null = null;
  if (item.execs.length)
    exec = item.execs.includes('intraday') ? 'intraday' : (item.execs[0] ?? null);
  return { item: item.id, op: o, params, value: null, value2: null, exec };
}

export function newBlock(blocks: Block[], stage: StageId, x = 0, y = 0): Block {
  const match = stage === 'sell' ? 'any' : 'all';
  const rows: Row[] = [];
  if (stage === 'buy')
    rows.push({ item: 'next_open', op: 'fixed', params: {}, value: 1, value2: null, exec: null });
  if (stage === 'weight')
    rows.push({ item: 'equal', op: 'fixed', params: {}, value: null, value2: null, exec: null });
  return { id: NEXT_ID(blocks, stage), stage, match, rows, x, y };
}

/** 새 전략(그림 V2-23 빈 캔버스): ① 종목 직접 지정 → ④ 신호 강도 → ⑤ ← ⑦ 동일 비중. */
export function blankBody(name: string = blockEditor.newName): Body {
  const blocks: Block[] = [];
  const u: Block = { ...newBlock(blocks, 'universe', 0, 0) };
  u.rows = [{ item: 'manual_list', op: 'pick', params: {}, value: null, value2: null, exec: null }];
  blocks.push(u);
  const k = newBlock(blocks, 'select', 304, 0);
  k.rows = [
    {
      item: 'top_n',
      op: 'top_n',
      params: { by: 'strength', order: 'desc' },
      value: null,
      value2: null,
      exec: null,
    },
  ];
  blocks.push(k);
  blocks.push(newBlock(blocks, 'buy', 608, 0));
  blocks.push(newBlock(blocks, 'weight', 304, 316));
  return {
    name,
    graph: {
      blocks,
      edges: [
        { from: 'u1', to: 'k1' },
        { from: 'k1', to: 'b1' },
        { from: 'w1', to: 'b1' },
      ],
    },
  };
}

export function addBlockReason(blocks: Block[], stage: StageId, stageName: string): string | null {
  if (blocks.length >= BLOCK_MAX) return blockEditor.blockMax(BLOCK_MAX);
  if (ONCE.includes(stage) && blocks.some((b) => b.stage === stage))
    return blockEditor.stageOnce(stageName);
  return null;
}

export function linkReason(src: StageId, dst: StageId, hasSelect: boolean): string | null {
  if (dst === 'universe') return R.universeIn;
  if (src === 'weight' || dst === 'weight')
    return src === 'weight' && dst === 'buy' ? null : R.weight;
  if (dst === 'sell') return src === 'buy' || src === 'sell' ? null : R.sell;
  if (src === 'sell') return R.sell;
  if (src === 'buy') return dst === 'buy' ? R.buyOnce : R.entry;
  if (src === 'select') return dst === 'buy' ? null : R.select;
  if (dst === 'buy' && hasSelect) return R.select;
  return null;
}

function reaches(edges: Edge[], a: string, b: string): boolean {
  const seen = new Set([a]);
  const stack = [a];
  while (stack.length) {
    const cur = stack.pop();
    if (cur === undefined) break;
    if (cur === b) return true;
    for (const e of edges)
      if (e.from === cur && !seen.has(e.to)) {
        seen.add(e.to);
        stack.push(e.to);
      }
  }
  return false;
}

export function edgeReason(body: Body, src: string, dst: string): string | null {
  const by = new Map(body.graph.blocks.map((b) => [b.id, b]));
  const a = by.get(src);
  const b = by.get(dst);
  if (!a || !b) return blockEditor.noBlock;
  if (src === dst) return R.cycle;
  const r = linkReason(
    a.stage,
    b.stage,
    body.graph.blocks.some((x) => x.stage === 'select'),
  );
  if (r) return r;
  if (body.graph.edges.some((e) => e.from === src && e.to === dst)) return R.dup;
  if (reaches(body.graph.edges, dst, src)) return R.cycle;
  return null;
}

export const isSellChain = (body: Body, src: string, dst: string) => {
  const by = new Map(body.graph.blocks.map((b) => [b.id, b.stage]));
  return by.get(src) === 'sell' && by.get(dst) === 'sell';
};

// ── 바꾸기(새 본문을 돌려줘요) ────────────────────────────────────────────────

const clone = (body: Body): Body => JSON.parse(JSON.stringify(body)) as Body;

export function withBlock(body: Body, block: Block): Body {
  const next = clone(body);
  next.graph.blocks.push(block);
  return next;
}

export function removeBlock(body: Body, id: string): Body {
  const next = clone(body);
  next.graph.blocks = next.graph.blocks.filter((b) => b.id !== id);
  next.graph.edges = next.graph.edges.filter((e) => e.from !== id && e.to !== id);
  return next;
}

export function updateBlock(body: Body, id: string, fn: (b: Block) => void): Body {
  const next = clone(body);
  const b = next.graph.blocks.find((x) => x.id === id);
  if (b) fn(b);
  return next;
}

export function connect(body: Body, src: string, dst: string): Body {
  const next = clone(body);
  next.graph.edges.push({ from: src, to: dst });
  return next;
}

export function disconnect(body: Body, src: string, dst: string): Body {
  const next = clone(body);
  next.graph.edges = next.graph.edges.filter((e) => !(e.from === src && e.to === dst));
  return next;
}

/** ⑥ → ⑥ 확인 창의 '같은 단계로 옮기기': dst의 줄을 src 블록으로 옮기고 dst를 지워요. */
export function mergeSell(body: Body, src: string, dst: string): Body {
  const next = clone(body);
  const a = next.graph.blocks.find((b) => b.id === src);
  const b = next.graph.blocks.find((x) => x.id === dst);
  if (!a || !b) return next;
  a.rows.push(...b.rows);
  return removeBlock(next, dst);
}

/** 블록 높이(대략): 머리 44 + 줄마다 40 + '+ 조건 추가' 40. */
export const blockHeight = (b: Block) => 44 + 16 + Math.max(b.rows.length, 0) * 40 + 40;

/** 자동 정렬: 진입 단계는 위 줄(① ② ③), ④ ⑤ ⑥은 아래 줄, ⑦은 ④ 밑. 같은 단계는 아래로 쌓아요. */
export function autoLayout(body: Body): Body {
  const next = clone(body);
  const col: Record<StageId, [number, number]> = {
    universe: [0, 0],
    signal: [1, 0],
    filter: [2, 0],
    select: [0, 1],
    buy: [1, 1],
    sell: [2, 1],
    weight: [0, 2],
  };
  const rowTop = [0, 0, 0];
  const stacks = new Map<string, number>();
  const heights: number[][] = [[], [], []];
  for (const b of next.graph.blocks) {
    const [c, r] = col[b.stage];
    const key = `${String(c)}:${String(r)}`;
    const k = stacks.get(key) ?? 0;
    stacks.set(key, k + 1);
    (heights[r] ??= []).push(blockHeight(b) * (k + 1) + 24 * k);
  }
  rowTop[1] = Math.max(0, ...(heights[0] ?? [0])) + 64;
  rowTop[2] = rowTop[1] + Math.max(0, ...(heights[1] ?? [0])) + 24;
  const used = new Map<string, number>();
  for (const b of next.graph.blocks) {
    const [c, r] = col[b.stage];
    const key = `${String(c)}:${String(r)}`;
    const y0 = used.get(key) ?? rowTop[r] ?? 0;
    b.x = c * (CARD_W + 48);
    b.y = y0;
    used.set(key, y0 + blockHeight(b) + 24);
  }
  return next;
}

export class History {
  private past: Body[] = [];
  private future: Body[] = [];
  push(prev: Body): void {
    this.past.push(prev);
    if (this.past.length > 100) this.past.shift();
    this.future = [];
  }
  undo(current: Body): Body | null {
    const prev = this.past.pop();
    if (!prev) return null;
    this.future.push(current);
    return prev;
  }
  redo(current: Body): Body | null {
    const next = this.future.pop();
    if (!next) return null;
    this.past.push(current);
    return next;
  }
  get canUndo(): boolean {
    return this.past.length > 0;
  }
  get canRedo(): boolean {
    return this.future.length > 0;
  }
}

export function stageCount(body: Body, stage: StageId): number {
  return body.graph.blocks.filter((b) => b.stage === stage).length;
}

export function josaRo(n: number): string {
  // '버전 1로' · '버전 3으로' · '버전 10으로'(GLOSSARY 1절): 끝자리 3 · 6 · 0은 받침이 있어요
  return [0, 3, 6].includes(n % 10) ? blockEditor.josa.euro : blockEditor.josa.ro;
}
