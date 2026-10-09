// Values the 계획 screens need that autotrade/CONTRACT.md does not carry yet. They are contract
// gaps (reported, not added to the contract): fixtures model them on typed constants, so every
// bundle still satisfies the contract types, and the screens read them through these helpers.
// When the contract adds them, these helpers become plain field reads.
import type { NextAction, PlanCard, RuleCard } from '../../api/types';

/** One point of a line chart; null breaks the line. */
export interface ProposedPoint {
  date: string;
  value: number | null;
}

/**
 * AI rule (gauge kind 'sell-condition', 화면-맞춤.md ②, Figma 탐색 17:7108):
 * - `vsIndex`: the '지수 대비 · [고른 날]부터 (%p)' line that takes the drift chart's place.
 * - `basisLine.metricTableAt`: date of the metric table behind the gauge ('지표 표 10/8').
 */
export interface RuleCardProposal {
  vsIndex?: { since: string; points: readonly ProposedPoint[] } | undefined;
  basisLine: RuleCard['basisLine'] & { metricTableAt?: string | undefined };
}

/** AI rule: the next monthly review rides on the next check ('다음 확인 10/8 08:30 · 점검 11/1'). */
export type NextCheckProposal = Extract<NextAction, { kind: 'next-check' }> & {
  reviewAt?: string | undefined;
};

export function vsIndexOf(card: RuleCard): RuleCardProposal['vsIndex'] {
  return (card as RuleCard & RuleCardProposal).vsIndex;
}

export function metricTableAtOf(card: RuleCard | PlanCard): string | null {
  if (!('basisLine' in card)) return null;
  return (card as RuleCard & RuleCardProposal).basisLine.metricTableAt ?? null;
}

export function reviewAtOf(next: NextAction): string | null {
  return next.kind === 'next-check' ? ((next as NextCheckProposal).reviewAt ?? null) : null;
}
