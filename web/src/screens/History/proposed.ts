// Values the 기록 screen needs that autotrade/CONTRACT.md does not carry yet. They are contract
// gaps (reported, not added to the contract): fixtures model them on typed constants, so every
// bundle still satisfies the contract types, and the screen reads them through these helpers.
// When the contract adds them, these helpers become plain field reads.
import type { HistoryEvent, Side } from '../../api/types';

export interface HistoryEventProposal {
  /**
   * 리밸런싱 중: the stage still waiting and its time, for '매수 22:30' (기획 §5 사건 목록
   * '리밸런싱 중 · 매수 22:30'). `stagesMini` only carries statuses.
   */
  pending?: { side: Side; at: string } | undefined;
  /** Target weights for the mini before/after bars (the target tick, Figma 1:59344 '목표 50'). */
  weightsMini?: { before: number[]; after: number[]; target?: number[] | undefined } | undefined;
}

export type ProposedHistoryEvent = HistoryEvent & HistoryEventProposal;

export function pendingOf(event: HistoryEvent): HistoryEventProposal['pending'] {
  return (event as ProposedHistoryEvent).pending;
}

export function miniTargetsOf(event: HistoryEvent): number[] | undefined {
  return (event as ProposedHistoryEvent).weightsMini?.target;
}
