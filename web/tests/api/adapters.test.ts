import { describe, expect, it } from 'vitest';
import { bannerLink, bannerText, markerKind, ruleStatusChip } from '../../src/api/adapters';
import type { Banner } from '../../src/api/types';

const stale: Banner = {
  kind: 'stale',
  market: 'US',
  basisDate: '2026-10-02',
  tradingDays: 2,
  link: 'health',
};
const partial = (retryAt: string): Banner => ({
  kind: 'partial-retry',
  date: '2026-10-07',
  market: 'US',
  side: 'buy',
  retryAt,
  link: 'plan',
});

describe('banner', () => {
  it.each<[Banner, string]>([
    [stale, '미국 시세 10/2 기준 · 2거래일째 갱신 없음'],
    [{ ...stale, market: 'FX' }, '환율 10/2 기준 · 2거래일째 갱신 없음'],
    [partial('2026-10-07T23:30:00+09:00'), '10/7 미국 매수 실패 · 23:30 다시 시도'],
    [partial('2026-10-08T22:30:00+09:00'), '10/7 미국 매수 실패 · 10/8 22:30 다시 시도'],
    [
      {
        kind: 'partial-todo',
        date: '2026-09-14',
        market: 'US',
        side: 'buy',
        reason: 'broker-rejected',
        link: 'health',
      },
      '9/14 미국 매수 실패 · 토스 주문 거부 · 직접 할 일',
    ],
    [
      {
        kind: 'partial-todo',
        date: '2026-09-14',
        market: 'US',
        side: 'buy',
        reason: 'retry-failed',
        link: 'health',
      },
      '9/14 미국 매수 실패 · 다시 시도도 실패 · 직접 할 일',
    ],
    [
      {
        kind: 'check-failed',
        at: '2026-10-07T08:30:00+09:00',
        retryAt: '2026-10-07T09:30:00+09:00',
        link: 'health',
      },
      '10/7 08:30 확인 실패 · 09:30 자동 재시도',
    ],
    [
      { kind: 'check-failed', at: '2026-10-07T08:30:00+09:00', retryAt: null, link: 'health' },
      '10/7 08:30 확인 실패',
    ],
    [
      { kind: 'cancel-failed', market: 'US', side: 'buy', link: 'mode' },
      '모의투자로 바뀜 · 미국 매수 주문 취소 안 됨',
    ],
    [{ kind: 'push-undelivered', days: 3, link: 'account' }, '알림이 3일째 기기에 안 닿아요'],
  ])('%o', (banner, text) => {
    expect(bannerText(banner, 'paper')).toBe(text);
  });

  it('says 모의투자로 바뀜 for a failed cancel only once live is off (3단계)', () => {
    const cancel: Banner = { kind: 'cancel-failed', market: 'US', side: 'buy', link: 'mode' };
    expect(bannerText(cancel, 'paper')).toBe('모의투자로 바뀜 · 미국 매수 주문 취소 안 됨');
    // A cancel the tick asked for while live is still on: nothing switched.
    expect(bannerText(cancel, 'live')).toBe('미국 매수 주문 취소 안 됨');
    // Either way the link is the mode screen's 취소 다시 시도 (hidden on that screen).
    expect(bannerLink(cancel, '/')).toEqual({ to: '/mode', label: '다시 시도' });
    expect(bannerLink(cancel, '/mode')).toBeNull();
    // The other banners read the same in both modes.
    expect(bannerText(stale, 'live')).toBe(bannerText(stale, 'paper'));
  });

  it('never links to the page the user is on', () => {
    expect(bannerLink(stale, '/')).toEqual({ to: '/health', label: '작동 보기' });
    expect(bannerLink(stale, '/health')).toBeNull();
    expect(bannerLink(partial('2026-10-08T22:30:00+09:00'), '/')).toEqual({
      to: '/plan',
      label: '계획 보기',
    });
    // On 계획 the partial-failure banner points at 작동 instead.
    expect(bannerLink(partial('2026-10-08T22:30:00+09:00'), '/plan')).toEqual({
      to: '/health',
      label: '작동 보기',
    });
  });
});

describe('enum mapping', () => {
  it('words AI rule chips differently', () => {
    expect(ruleStatusChip('in-progress')).toEqual({ state: 'inProgress', label: '리밸런싱 중' });
    expect(ruleStatusChip('in-progress', true)).toEqual({ state: 'inProgress', label: '주문 중' });
    expect(ruleStatusChip('buy-scheduled', true)).toEqual({
      state: 'scheduled',
      label: '매수 예정',
    });
  });

  it('has no marker for AI events yet', () => {
    expect(markerKind('partial-failed')).toBe('partialFail');
    expect(markerKind('ai-buy')).toBeNull();
  });
});
