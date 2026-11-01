// 서버 app/graph.py의 검사를 화면에서 미리 돌리는 거울(잇는 중 맞는 곳/안 되는 곳 · 삭제하면 바뀌는 것 ·
// 상태 상자). 결과가 서버와 같은지는 web/tests/graphMirror.test.ts가 서버가 만든 대조 파일로 본다.
// 화면에 보이는 상태는 서버의 검사 결과(/api/strategies/{id}/check)를 그대로 쓰고, 이 계산은 그 답이
// 오기 전과 미리 보기에만 쓴다.
import type {
  Analysis,
  EntryPath,
  Graph,
  GraphNode,
  ModeId,
  ParamSpec,
  ParamValue,
  PieceSpec,
  Problem,
  ProblemKind,
  SlotInfo,
  SlotKey,
} from '../api/mvp';
import { graphRules as R, graphText as T, howNames, kindNames, modeNames } from '../copy/graph';
import { J, type JosaPair } from '../copy/particles';

export const NODE_MAX = 40;
export const PATH_MAX = 20;

export interface RuleCatalog {
  pieces: Record<string, PieceSpec>;
  slots: SlotInfo[];
  /** 종목 이름(조건 제목 '종목 직접 지정 · 삼성전자 외 9'). */
  names: Record<string, string>;
}

const ONCE_STAGES: ReadonlySet<SlotKey> = new Set(['universe', 'select', 'buy']);
const ONCE_PIECES: ReadonlySet<string> = new Set(['equal', 'max_per_stock', 'rebalance_every']);
export const KIND_ORDER: readonly ProblemKind[] = [
  'blank',
  'range',
  'required',
  'unusable',
  'loose',
  'dead',
  'rule',
  'many',
];

// ── 글 꼴(app/pieces.py와 같다) ───────────────────────────────────────────────

/** 끝의 괄호는 건너뛴다('… (3)'은 3). */
function lastChar(word: string): string {
  return word
    .trim()
    .replace(/[\s)\]]+$/, '')
    .slice(-1);
}

export function hasBatchim(word: string): boolean {
  const last = lastChar(word) || 'a';
  if (last >= '0' && last <= '9') return '013678'.includes(last);
  const code = last.charCodeAt(0);
  if (code >= 0xac00 && code <= 0xd7a3) return (code - 0xac00) % 28 !== 0;
  return 'lmnr'.includes(last.toLowerCase());
}

export function josa(word: string, pair: JosaPair): string {
  const [a, b] = pair.split('/') as [string, string];
  if (pair === J.ro) {
    const last = lastChar(word);
    const code = last ? last.charCodeAt(0) : 0;
    const rieul =
      (code >= 0xac00 && code <= 0xd7a3 && (code - 0xac00) % 28 === 8) || '178'.includes(last);
    return word + (hasBatchim(word) && !rieul ? a : b);
  }
  return word + (hasBatchim(word) ? a : b);
}

function commas(intText: string): string {
  const neg = intText.startsWith('-');
  const digits = neg ? intText.slice(1) : intText;
  const out = digits.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return neg ? `-${out}` : out;
}

/** Python num_text: 정수면 쉼표, 아니면 소수 6자리까지(끝 0 빼고). */
export function numText(v: ParamValue | number): string {
  if (typeof v !== 'number') return String(v);
  if (Number.isInteger(v)) return commas(BigInt(v).toString());
  const fixed = v.toFixed(6).replace(/0+$/, '').replace(/\.$/, '');
  const [i = '', f] = fixed.split('.');
  return f === undefined ? commas(i) : `${commas(i)}.${f}`;
}

export function rangeText(p: ParamSpec): string {
  return `${numText(p.min)}~${numText(p.max)}${p.unit ?? ''}`;
}

export function symbolsShort(syms: readonly string[], names: Record<string, string>): string {
  if (syms.length === 0) return '';
  const first = names[syms[0] ?? ''] ?? syms[0] ?? '';
  return syms.length === 1 ? first : T.more(first, syms.length - 1);
}

export function stageOf(cat: RuleCatalog, piece: string): SlotKey {
  return cat.pieces[piece]?.slot ?? 'filter';
}

export function slotLabel(cat: RuleCatalog, slot: SlotKey): string {
  return cat.slots.find((s) => s.key === slot)?.label ?? slot;
}

export function slotCircle(cat: RuleCatalog, slot: SlotKey): string {
  return cat.slots.find((s) => s.key === slot)?.circle ?? '';
}

export function pieceTitle(cat: RuleCatalog, n: Pick<GraphNode, 'piece' | 'params'>): string {
  const spec = cat.pieces[n.piece];
  if (!spec) return n.piece;
  const params = n.params;
  if (n.piece === 'manual_list') {
    const syms = Array.isArray(params.symbols) ? params.symbols : [];
    if (syms.length === 0) return spec.title;
    return `${spec.title} · ${symbolsShort(syms, cat.names)}`;
  }
  let out = spec.title;
  if (n.piece === 'rsi_below' && (params.level === null || params.level === undefined))
    out = out.replace(' {level}', '');
  for (const p of spec.params) {
    if (p.kind === 'choice') continue;
    const v = params[p.key];
    const text = v === null || v === undefined ? 'n' : numText(v);
    out = out.replace(`{${p.key}}`, text);
  }
  if (n.piece === 'rebalance_every') {
    const how = params.how;
    if (how === 'target' || how === 'rank') out = `${out} · ${howNames[how]}`;
  }
  return out;
}

export function labelOf(cat: RuleCatalog, n: Pick<GraphNode, 'piece' | 'params'>): string {
  return `${slotCircle(cat, stageOf(cat, n.piece))} ${pieceTitle(cat, n)}`;
}

// ── 조건 · 선 ────────────────────────────────────────────────────────────────

export function onceReason(cat: RuleCatalog, piece: string): string {
  const stage = stageOf(cat, piece);
  if (stage === 'universe') return R.universeOnce;
  if (stage === 'buy') return R.buyOnce;
  if (stage === 'select') return R.select;
  return R.onceNamed(josa(cat.pieces[piece]?.name ?? piece, J.eun));
}

export function addReason(cat: RuleCatalog, g: Graph, piece: string): string | null {
  if (g.nodes.length >= NODE_MAX) return R.nodeMax(NODE_MAX);
  const stage = stageOf(cat, piece);
  if (ONCE_STAGES.has(stage) && g.nodes.some((n) => stageOf(cat, n.piece) === stage))
    return onceReason(cat, piece);
  if (ONCE_PIECES.has(piece) && g.nodes.some((n) => n.piece === piece))
    return onceReason(cat, piece);
  return null;
}

export function linkReason(src: SlotKey, dst: SlotKey, hasSelect: boolean): string | null {
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

function index(g: Graph): Map<string, GraphNode> {
  return new Map(g.nodes.map((n) => [n.id, n]));
}

export function outgoing(g: Graph): Map<string, string[]> {
  const by = index(g);
  const out = new Map<string, { k: [number, number, number]; d: string }[]>();
  for (const n of g.nodes) out.set(n.id, []);
  g.edges.forEach((e, i) => {
    const to = by.get(e.to);
    if (by.has(e.from) && to) out.get(e.from)?.push({ k: [to.y ?? 0, to.x ?? 0, i], d: e.to });
  });
  const res = new Map<string, string[]>();
  for (const [id, list] of out) {
    list.sort((a, b) => a.k[0] - b.k[0] || a.k[1] - b.k[1] || a.k[2] - b.k[2]);
    res.set(
      id,
      list.map((x) => x.d),
    );
  }
  return res;
}

function reaches(out: Map<string, string[]>, a: string, b: string): boolean {
  const seen = new Set([a]);
  const stack = [a];
  while (stack.length > 0) {
    const cur = stack.pop() ?? '';
    if (cur === b) return true;
    for (const nxt of out.get(cur) ?? []) {
      if (!seen.has(nxt)) {
        seen.add(nxt);
        stack.push(nxt);
      }
    }
  }
  return false;
}

export function edgeReason(cat: RuleCatalog, g: Graph, src: string, dst: string): string | null {
  const by = index(g);
  const a = by.get(src);
  const b = by.get(dst);
  if (!a || !b) return R.noNode;
  if (src === dst) return R.cycle;
  const hasSelect = g.nodes.some((n) => stageOf(cat, n.piece) === 'select');
  const r = linkReason(stageOf(cat, a.piece), stageOf(cat, b.piece), hasSelect);
  if (r) return r;
  if (g.edges.some((e) => e.from === src && e.to === dst)) return R.dup;
  if (reaches(outgoing(g), dst, src)) return R.cycle;
  const g2: Graph = { nodes: g.nodes, edges: [...g.edges, { from: src, to: dst }] };
  if (entryPaths(cat, g2).length > PATH_MAX) return R.many(PATH_MAX);
  if (sellPaths(cat, g2).length > PATH_MAX) return R.manySell(PATH_MAX);
  return null;
}

// ── 경로 ─────────────────────────────────────────────────────────────────────

const ENTRY_NEXT: ReadonlySet<SlotKey> = new Set(['signal', 'filter', 'select', 'buy']);

export function entryPaths(cat: RuleCatalog, g: Graph, limit = PATH_MAX + 1): EntryPath[] {
  const by = index(g);
  const uni = g.nodes.filter((n) => stageOf(cat, n.piece) === 'universe').map((n) => n.id);
  if (uni.length === 0) return [];
  const out = outgoing(g);
  const paths: EntryPath[] = [];
  const walk = (path: string[]) => {
    if (paths.length >= limit) return;
    const last = path[path.length - 1] ?? '';
    const lastNode = by.get(last);
    if (lastNode && stageOf(cat, lastNode.piece) === 'buy') {
      paths.push({ nodes: [...path], complete: true });
      return;
    }
    const nexts = (out.get(last) ?? []).filter((d) => {
      const n = by.get(d);
      return !path.includes(d) && n !== undefined && ENTRY_NEXT.has(stageOf(cat, n.piece));
    });
    if (nexts.length === 0) {
      paths.push({ nodes: [...path], complete: false });
      return;
    }
    for (const d of nexts) {
      walk([...path, d]);
      if (paths.length >= limit) return;
    }
  };
  walk([uni[0] ?? '']);
  return paths;
}

export function sellPaths(cat: RuleCatalog, g: Graph, limit = PATH_MAX + 1): { nodes: string[] }[] {
  const by = index(g);
  const buys = g.nodes.filter((n) => stageOf(cat, n.piece) === 'buy').map((n) => n.id);
  if (buys.length === 0) return [];
  const out = outgoing(g);
  const paths: { nodes: string[] }[] = [];
  const walk = (path: string[]) => {
    if (paths.length >= limit) return;
    const nexts = (out.get(path[path.length - 1] ?? '') ?? []).filter((d) => {
      const n = by.get(d);
      return !path.includes(d) && n !== undefined && stageOf(cat, n.piece) === 'sell';
    });
    if (nexts.length === 0) {
      if (path.length > 1) paths.push({ nodes: [...path] });
      return;
    }
    for (const d of nexts) {
      walk([...path, d]);
      if (paths.length >= limit) return;
    }
  };
  walk([buys[0] ?? '']);
  return paths;
}

export function linkedWeights(cat: RuleCatalog, g: Graph): string[] {
  const buys = new Set(g.nodes.filter((n) => stageOf(cat, n.piece) === 'buy').map((n) => n.id));
  return g.nodes
    .filter(
      (n) =>
        stageOf(cat, n.piece) === 'weight' &&
        g.edges.some((e) => e.from === n.id && buys.has(e.to)),
    )
    .map((n) => n.id);
}

export function modeOf(cat: RuleCatalog, g: Graph): ModeId | null {
  const by = index(g);
  for (const id of linkedWeights(cat, g)) {
    const n = by.get(id);
    if (n?.piece === 'rebalance_every') {
      const how = n.params.how;
      return how === 'target' || how === 'rank' ? how : null;
    }
  }
  return 'event';
}

// ── 검사 ─────────────────────────────────────────────────────────────────────

export function fieldProblem(
  p: ParamSpec,
  value: ParamValue | undefined,
): [ProblemKind, string] | null {
  if (p.kind === 'choice') {
    if (typeof value !== 'string' || !(p.options ?? []).includes(value))
      return ['blank', T.choose(josa(p.label, J.eul))];
    return null;
  }
  if (p.kind === 'symbols') {
    const syms = Array.isArray(value) ? value : [];
    if (syms.length === 0) return ['blank', T.enter(josa(p.label, J.eul))];
    const bad = syms.filter((s) => !/^[0-9]{6}$/.test(s));
    if (bad.length > 0) return ['range', T.notSymbol(bad.slice(0, 5).map(String).join(', '))];
    if (syms.length > p.max) return ['range', T.tooManySymbols(p.max)];
    return null;
  }
  const rng = rangeText(p);
  if (value === null || value === undefined) return ['blank', T.enter(josa(p.label, J.eul))];
  if (typeof value !== 'number' || !Number.isFinite(value))
    return ['range', T.notNumber(p.label, rng)];
  if (!(p.min <= value && value <= p.max)) return ['range', T.between(josa(p.label, J.eun), rng)];
  if (p.integer && !Number.isInteger(value)) return ['range', T.integer(josa(p.label, J.eun))];
  return null;
}

function problem(
  cat: RuleCatalog,
  kind: ProblemKind,
  node: string,
  field: string,
  slot: SlotKey | '',
  title: string,
  short: string,
  detail?: string,
  hint = '',
): Problem {
  return {
    kind,
    node,
    field,
    slot,
    title,
    short,
    detail: detail ?? (slot ? `${slotLabel(cat, slot)} · ${short}` : short),
    hint,
  };
}

export function analyze(cat: RuleCatalog, g: Graph): Analysis {
  const nodes = g.nodes;
  const by = index(g);
  const stage = (id: string): SlotKey => stageOf(cat, by.get(id)?.piece ?? '');
  let entry = entryPaths(cat, g);
  let sells = sellPaths(cat, g);
  const tooMany = entry.length > PATH_MAX || sells.length > PATH_MAX;
  entry = entry.slice(0, PATH_MAX);
  sells = sells.slice(0, PATH_MAX);
  const weights = linkedWeights(cat, g);
  const mode = modeOf(cat, g);
  const problems: Problem[] = [];

  for (const n of nodes) {
    const spec = cat.pieces[n.piece];
    if (!spec) continue;
    const slot = stage(n.id);
    for (const p of spec.params) {
      const found = fieldProblem(p, n.params[p.key]);
      if (!found) continue;
      const [kind, short] = found;
      const title = kind === 'blank' ? T.blankTitle(spec.name) : T.rangeTitle(pieceTitle(cat, n));
      problems.push(problem(cat, kind, n.id, p.key, slot, title, short));
    }
  }

  const hasStage = (s: SlotKey) => nodes.some((n) => stageOf(cat, n.piece) === s);
  const required = (slot: SlotKey, short: string, hint = '') => {
    problems.push(
      problem(
        cat,
        'required',
        '',
        '',
        slot,
        T.requiredTitle(slotLabel(cat, slot)),
        short,
        short,
        hint,
      ),
    );
  };
  if (!hasStage('universe')) required('universe', T.needUniverse);
  if (!hasStage('buy')) required('buy', T.needBuy);
  if (!nodes.some((n) => n.piece === 'equal')) required('weight', T.needEqual);
  if (mode === 'event' || mode === 'rank') {
    const mname = modeNames[mode];
    if (!hasStage('select')) required('select', T.needSelect(mname), T.needSelectHint);
    entry.forEach((path, i) => {
      if (!path.complete) return;
      if (path.nodes.some((id) => stage(id) === 'signal')) return;
      const nxt = path.nodes.length > 1 ? (path.nodes[1] ?? '') : (path.nodes[0] ?? '');
      required('signal', T.noSignal(i + 1), T.noSignalHint(slotCircle(cat, stage(nxt))));
    });
  }
  if (mode === 'event' && sells.length === 0)
    required('sell', T.needSell(modeNames.event), T.needSellHint);

  const onSell = new Set(sells.flatMap((p) => p.nodes.slice(1)));
  if (mode !== null) {
    for (const n of nodes) {
      if (onSell.has(n.id) && !(cat.pieces[n.piece]?.modes ?? []).includes(mode)) {
        const slot = stage(n.id);
        problems.push(
          problem(
            cat,
            'unusable',
            n.id,
            '',
            slot,
            T.unusableTitle(pieceTitle(cat, n)),
            T.unusable(modeNames[mode], slotLabel(cat, slot)),
          ),
        );
      }
    }
  }

  const on = new Set([
    ...entry.flatMap((p) => p.nodes),
    ...sells.flatMap((p) => p.nodes),
    ...weights,
  ]);
  for (const n of nodes) {
    if (!on.has(n.id))
      problems.push(
        problem(cat, 'loose', n.id, '', stage(n.id), T.looseTitle(pieceTitle(cat, n)), T.loose),
      );
  }

  const sel = nodes.find((n) => stageOf(cat, n.piece) === 'select');
  const target = sel ? labelOf(cat, sel) : T.buyTarget;
  entry.forEach((path, i) => {
    if (path.complete) return;
    const last = by.get(path.nodes[path.nodes.length - 1] ?? '');
    if (!last) return;
    const short = T.dead(i + 1, labelOf(cat, last), target);
    problems.push(problem(cat, 'dead', last.id, '', '', T.deadTitle, short, short));
  });

  const hasSelect = sel !== undefined;
  for (const e of g.edges) {
    const a = by.get(e.from);
    const b = by.get(e.to);
    if (!a || !b) continue;
    const r = linkReason(stageOf(cat, a.piece), stageOf(cat, b.piece), hasSelect);
    if (r)
      problems.push(
        problem(
          cat,
          'rule',
          b.id,
          '',
          stageOf(cat, b.piece),
          T.ruleTitle(labelOf(cat, a), labelOf(cat, b)),
          r,
          r,
        ),
      );
  }

  if (tooMany) {
    const short = T.manyShort(PATH_MAX);
    problems.push(problem(cat, 'many', '', '', '', kindNames.many, short, short));
  }

  const counts: Partial<Record<ProblemKind, number>> = {};
  for (const kind of KIND_ORDER) {
    const c = problems.filter((p) => p.kind === kind).length;
    if (c) counts[kind] = c;
  }
  return { mode, entry, sell: sells, weights, problems, counts, too_many: tooMany };
}
