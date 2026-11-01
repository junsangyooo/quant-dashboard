// 경로 · 문제 요약 글(편집 오른쪽 패널 · 전략 상세 · 예시 상세 · 가져오기 확인이 같이 쓴다).
import type { Analysis, Graph, GraphNode, Problem, ProblemKind } from '../api/mvp';
import { editorCopy as t } from '../copy/editor';
import { kindNames } from '../copy/graph';
import { KIND_ORDER, pieceTitle, slotCircle, slotLabel, stageOf, type RuleCatalog } from './rules';

function node(g: Graph, id: string): GraphNode | undefined {
  return g.nodes.find((n) => n.id === id);
}

/** 경로 한 줄의 조건 하나: '① 종목 직접 지정' · '② 20일 최고가 돌파' · '⑤ 매수'. compact면 ① · ④ · ⑤는 번호만. */
export function stepText(cat: RuleCatalog, g: Graph, id: string, compact = false): string {
  const n = node(g, id);
  if (!n) return id;
  const s = stageOf(cat, n.piece);
  const circle = slotCircle(cat, s);
  if (s === 'buy') return compact ? circle : t.paths.buy;
  if (s === 'universe') return compact ? circle : `${circle} ${cat.pieces[n.piece]?.name ?? ''}`;
  if (s === 'select' && compact) return circle;
  return `${circle} ${pieceTitle(cat, n)}`;
}

export function pathText(
  cat: RuleCatalog,
  g: Graph,
  ids: readonly string[],
  compact = false,
): string {
  return ids.map((id) => stepText(cat, g, id, compact)).join(' → ');
}

/** 경로 위 ② · ③ 조건 수. */
export function condCount(cat: RuleCatalog, g: Graph, ids: readonly string[]): number {
  return ids.filter((id) => {
    const n = node(g, id);
    const s = n ? stageOf(cat, n.piece) : '';
    return s === 'signal' || s === 'filter';
  }).length;
}

export function problemParts(a: Analysis): string {
  return KIND_ORDER.filter((k) => (a.counts[k] ?? 0) > 0)
    .map((k) => t.status.part(kindNames[k], a.counts[k] ?? 0))
    .join(' · ');
}

/** 노랑(빈칸 · 필요한 조건만) 또는 빨강(그 밖의 문제). */
export function problemTone(a: Analysis): 'ok' | 'warn' | 'error' {
  if (a.problems.length === 0) return 'ok';
  return a.problems.every((p) => p.kind === 'blank' || p.kind === 'required') ? 'warn' : 'error';
}

export function requiredTitle(cat: RuleCatalog, a: Analysis): string | null {
  const req = a.problems.filter((p) => p.kind === 'required');
  if (req.length === 0) return null;
  const labels: string[] = [];
  for (const p of req) {
    if (!p.slot) continue;
    const l = slotLabel(cat, p.slot);
    if (!labels.includes(l)) labels.push(l);
  }
  return t.paths.required(req.length, labels.join(' · '));
}

export function nodeProblems(a: Analysis, id: string): Problem[] {
  return a.problems.filter((p) => p.node === id);
}

export function nodeKinds(a: Analysis, id: string): Set<ProblemKind> {
  return new Set(nodeProblems(a, id).map((p) => p.kind));
}

/** 경로에 들어 있는 빈칸 · 범위 밖 수. */
export function pathProblemCount(a: Analysis, ids: readonly string[], kind: ProblemKind): number {
  return a.problems.filter((p) => p.kind === kind && ids.includes(p.node)).length;
}

/** 진입 경로 k가 신호 없음 문제인가. */
export function noSignalPaths(a: Analysis): Set<number> {
  const out = new Set<number>();
  for (const p of a.problems) {
    if (p.kind !== 'required' || p.slot !== 'signal') continue;
    const m = /(\d+)/.exec(p.short);
    if (m) out.add(Number(m[1]));
  }
  return out;
}

export function circleOf(cat: RuleCatalog, g: Graph, id: string): string {
  const n = node(g, id);
  return n ? slotCircle(cat, stageOf(cat, n.piece)) : '';
}
