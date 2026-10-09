// Values the 규칙 screen needs that autotrade/CONTRACT.md does not carry yet (contract gaps,
// reported). Fixtures model them on typed constants that still satisfy the contract types; the
// screen reads them through these helpers and draws nothing extra when they are absent.
import type { FlowDisplay, Instrument, NowBlock, TilesDisplay } from '../../api/types';

export type FlowNode = FlowDisplay['nodes'][number];
export type FlowEdge = FlowDisplay['edges'][number];
export type NowRow = NowBlock['rows'][number];

export interface FlowNodeProposal {
  /**
   * 종목 card: how many more instruments than the logos shown ('외 5' after 삼 · NV · B, Figma
   * 1:62197; '외 12' in 3년 발굴). The logos, flags and kind badges come from the 지금 rows.
   */
  more?: number | undefined;
  /** 비중 card: target weight per instrument ('삼 42 · NV 40 · B 18' under '42 · 40 · 18'). */
  targets?: { instrument: Instrument; weight: number }[] | undefined;
}

export interface NowBlockProposal {
  /**
   * Engine words after '지금 ·' that `headKey` cannot say: '8종목 중 상위 3', '기준 전날',
   * '15종목', '종목당 약 6천 토큰', '10/7 발굴 뒤' (data text, like `kv`).
   */
  note?: string | undefined;
  /** 'now-last' over a span: '마지막 9/14~9/15' (`at` = first day). */
  until?: string | undefined;
}

export interface KvRowProposal {
  /** Right-hand column of a kv row: '정상', '새 1', '갱신', '40여', '15'. */
  note?: string | undefined;
}

export interface OrderRowProposal {
  /** The order failed once and was sent again: '9/15 다시 · 체결'. */
  retried?: boolean | undefined;
}

export interface TilesConditionProposal {
  /** 조건 tile points (인계 '그림에 남은 작은 불일치' 2): 빈 점 = now, 주황 점 = at the 08:30 check. */
  deviation?: { now: number | null; atCheck: number | null } | undefined;
}

export type ProposedNode = FlowNode & FlowNodeProposal;
export type ProposedNow = NowBlock & NowBlockProposal;

export function moreOf(node: FlowNode): number | undefined {
  return (node as ProposedNode).more;
}

export function targetsOf(node: FlowNode): FlowNodeProposal['targets'] {
  return (node as ProposedNode).targets;
}

export function nowNoteOf(now: NowBlock): string | undefined {
  return (now as ProposedNow).note;
}

export function nowUntilOf(now: NowBlock): string | undefined {
  return (now as ProposedNow).until;
}

export function kvNoteOf(row: Extract<NowRow, { kind: 'kv' }>): string | undefined {
  return (row as Extract<NowRow, { kind: 'kv' }> & KvRowProposal).note;
}

export function retriedOf(row: Extract<NowRow, { kind: 'order' }>): boolean {
  return (row as Extract<NowRow, { kind: 'order' }> & OrderRowProposal).retried === true;
}

export function conditionDeviationOf(
  condition: TilesDisplay['condition'],
): TilesConditionProposal['deviation'] {
  return (condition as TilesDisplay['condition'] & TilesConditionProposal).deviation;
}

export interface EdgeProposal {
  /** Branch words the contract's `label` enum lacks: '아니오 · 대기' (3년 발굴 분기 발굴, 17:6432). */
  labelKey?: 'no-wait' | undefined;
}

export type EdgeLabel = NonNullable<FlowEdge['label']> | 'no-wait';

export function edgeLabelOf(edge: FlowEdge): EdgeLabel | null {
  return (edge as FlowEdge & EdgeProposal).labelKey ?? edge.label ?? null;
}
