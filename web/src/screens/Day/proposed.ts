// Values the 그날 panel needs that autotrade/CONTRACT.md does not carry yet (contract gaps,
// reported). Fixtures model them on typed constants that still satisfy the contract types; the
// panel reads them through these helpers and shows nothing extra when they are absent.
import type { DayResponse, HistoryEvent, Order } from '../../api/types';

export interface OrderProposal {
  /**
   * A failed order that was sent again later: '9/15 다시 · 체결' on the failed card
   * (기획 §5 SCR-DAY.partial '다시 시도해 체결된 경우 그 날짜 칩'). `failure.retryAt` only says when.
   */
  retried?: { at: string; status: 'filled' | 'failed' } | undefined;
}

export type ProposedOrder = Order & OrderProposal;

export function retriedOf(order: Order): OrderProposal['retried'] {
  return (order as ProposedOrder).retried;
}

export interface CheckProposal {
  /** 확인 실패 days: why and when it was normal again ('시세 응답 없음 · 9/10 정상'). */
  failure?:
    { reason: NonNullable<HistoryEvent['failureReason']>; recoveredOn?: string } | undefined;
}

export type ProposedCheck = DayResponse['check'] & CheckProposal;

export function checkFailureOf(check: DayResponse['check']): CheckProposal['failure'] {
  return (check as ProposedCheck).failure;
}
