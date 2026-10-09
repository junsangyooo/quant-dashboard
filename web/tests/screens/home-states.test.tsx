// SCR-HOME states (기획 §5 상태 표) — one bundle per state, numbers from 예시-값표.
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeAll, describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import homeCheckFailed from '../../src/fixtures/bundles/home.check-failed';
import homeEmpty from '../../src/fixtures/bundles/home.empty';
import homeFirstDay from '../../src/fixtures/bundles/home.first-day';
import homeHoliday from '../../src/fixtures/bundles/home.holiday';
import homeLive from '../../src/fixtures/bundles/home.live';
import homeLiveFirst from '../../src/fixtures/bundles/home.live-first';
import homeLiveTodo from '../../src/fixtures/bundles/home.live-todo';
import homeLoading from '../../src/fixtures/bundles/home.loading';
import homeOffline from '../../src/fixtures/bundles/home.offline';
import homeOtherDevice from '../../src/fixtures/bundles/home.other-device';
import homePartial from '../../src/fixtures/bundles/home.partial';
import homePermission from '../../src/fixtures/bundles/home.permission';
import homePushUndelivered from '../../src/fixtures/bundles/home.push-undelivered';
import homeStale from '../../src/fixtures/bundles/home.stale';
import homeWithdraw from '../../src/fixtures/bundles/home.withdraw';
import { homePaper } from '../../src/fixtures/parts/home';
import type { Breakdown } from '../../src/api/types';
import { BreakdownBody } from '../../src/screens/Home/TrendCard';
import type { FixtureBundle } from '../../src/fixtures/types';
import { configureClient, pinPath } from '../../src/api/client';
import { findTotal, renderState, stubScroll, textOf } from './home-plan.routes';

beforeAll(stubScroll);

const region = (name: string) => screen.getByRole('region', { name });

function rowValuesSum(): number {
  return within(region('구성'))
    .getAllByText(/^[\d,]+원$/, { selector: '.t-figure' })
    .map((el) => Number(el.textContent.replace(/[,원]/g, '')))
    .reduce((a, b) => a + b, 0);
}

describe('출금 대기 (값표 §2.3)', () => {
  it('PnL counts no cash flow: +104,918원 · +1.05%; rows add up to 10,104,918원', async () => {
    renderState(homeWithdraw);
    expect(await findTotal('10,104,918원')).toBeInTheDocument();
    expect(screen.getByText('▲ +104,918원 · +1.05%')).toBeVisible();
    expect(rowValuesSum()).toBe(10_104_918);
  });

  it('hatched bar end + its line, plan line 출금 대기 · 10/12까지 · 리밸런싱 쉼; no 매수 대기, banner or stages', async () => {
    const { container } = renderState(homeWithdraw);
    await findTotal('10,104,918원');
    expect(screen.getByText('빗금 = 출금 대기 원화 500,425원 · 10/12까지')).toBeVisible();
    expect(container.querySelector('svg path.pending')).not.toBeNull();
    const line = screen.getByRole('link', { name: /10\/12까지 · 리밸런싱 쉼/ });
    expect(textOf(line)).toBe('출금 대기10/12까지 · 리밸런싱 쉼');
    expect(screen.queryByText(/매수 대기/)).not.toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    const card = region('계획');
    expect(within(card).queryByRole('list')).not.toBeInTheDocument();
    expect(within(card).getByText('500,425원 · 10/12까지 · 주문 0건')).toBeVisible();
    expect(within(card).getByText('−0.7%p')).toBeVisible();
    expect(within(card).getByText('리밸런싱까지 1.3%p')).toBeVisible();
    expect(within(region('구성')).getByText('원화 현금 · 출금 대기')).toBeVisible();
    expect(within(region('구성')).getByText('출금 대기 · 10/12까지')).toBeVisible();
  });
});

describe('입출금이 있는 기간의 변동 분해', () => {
  it('cash-flow bars are grey and all bars add up to the change', () => {
    const b: Breakdown = {
      from: '2026-07-07',
      to: '2026-10-07',
      start: 10_021_000,
      deposit: 500_000,
      withdrawal: -300_000,
      market: 6_825,
      dividend: 16_243,
      fees: -268,
      end: 10_243_800,
    };
    expect(b.deposit + b.withdrawal + b.market + b.dividend + b.fees).toBe(b.end - b.start);
    const { container } = render(<BreakdownBody breakdown={b} />);
    const rects = [...container.querySelectorAll('svg rect')].map((r) => r.getAttribute('class'));
    expect(rects.filter((c) => c === 'wf-cash')).toHaveLength(2);
    expect(rects).toContain('wf-gain');
    expect(rects).toContain('wf-loss');
    const rows = within(screen.getByRole('table'))
      .getAllByRole('row')
      .slice(1)
      .map((r) => textOf(r));
    expect(rows).toEqual([
      '기간 시작10,021,000원',
      '입금+500,000원',
      '출금−300,000원',
      '시세·환율+6,825원',
      '배당+16,243원',
      '수수료−268원',
      '지금10,243,800원',
    ]);
  });
});

describe('시세 대기 (값표 §3)', () => {
  it('one banner, one 낡음 per section, plan 시세 대기, card weight —, no 목표 범위 안', async () => {
    renderState(homeStale);
    expect(await findTotal('10,217,664원')).toBeInTheDocument();
    const banner = screen.getByRole('status');
    expect(textOf(banner)).toBe('미국 시세 10/2 기준 · 2거래일째 갱신 없음작동 보기');
    expect(within(banner).getByRole('link', { name: '작동 보기' })).toHaveAttribute(
      'href',
      '/health',
    );
    expect(screen.getAllByText('낡음')).toHaveLength(3);
    expect(within(region('계획')).getByText('낡음')).toBeVisible();
    expect(within(region('구성')).getByText('낡음')).toBeVisible();
    const line = screen.getByRole('link', { name: /미국 시세 10\/2 기준 · 주문 0건/ });
    expect(textOf(line)).toBe('시세 대기미국 시세 10/2 기준 · 주문 0건');
    const card = region('계획');
    expect(within(card).getByText('—')).toBeVisible();
    expect(within(card).getByText('미국 시세 10/2 기준')).toBeVisible();
    expect(card.querySelector('line.needle')).toBeNull();
    expect(card.querySelector('circle.hubEmpty')).not.toBeNull();
    expect(screen.queryByText('목표 범위 안')).not.toBeInTheDocument();
    expect(screen.getByText('▲ +217,664원 · +2.18%')).toBeVisible();
    expect(screen.getByText('손대지 않았을 때 +3.36%')).toBeVisible();
    expect(rowValuesSum()).toBe(10_217_664);
  });
});

describe('일부 실패 (값표 §3, 10/8 08:40)', () => {
  it('banner, plan line and the ✕ stage show the same retry time (10/8 22:30)', async () => {
    renderState(homePartial);
    expect(await findTotal('10,243,800원')).toBeInTheDocument();
    const banner = screen.getByRole('status');
    expect(textOf(banner)).toContain('10/7 미국 매수 실패 · 10/8 22:30 다시 시도');
    expect(within(banner).getByRole('link', { name: '계획 보기' })).toHaveAttribute(
      'href',
      '/plan',
    );
    expect(screen.getByRole('button', { name: '08:30 기준' })).toBeVisible();
    const line = screen.getByRole('link', { name: /다시 시도/ });
    expect(textOf(line)).toBe('일부 실패10/8 22:30 미국 매수 다시 시도');
    const card = region('계획');
    expect(textOf(within(card).getByRole('list'))).toBe(
      '체결매도09:05체결환전09:10실패매수다시 10/8 22:30',
    );
    expect(within(card).getByText('다음 확인 10/9 08:30')).toBeVisible();
  });
});

describe('실전 평상 (값표 §2.2)', () => {
  it('no period chips or period PnL under 30 trading days; 금액 | 수익률 stays', async () => {
    renderState(homeLive);
    expect(await findTotal('10,112,670원')).toBeInTheDocument();
    expect(screen.getByText('실전 자산 · 9/1부터')).toBeVisible();
    expect(screen.getByText('▲ +112,670원 · +1.13%')).toBeVisible();
    expect(screen.getByText('손대지 않았을 때 +1.75%')).toBeVisible();
    expect(screen.queryByRole('group', { name: '기간' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /3개월/ })).not.toBeInTheDocument();
    expect(screen.getByRole('group', { name: '금액 | 수익률' })).toBeVisible();
    expect(screen.getByRole('link', { name: '9/1(화) 실전 켬' })).toHaveAttribute(
      'href',
      '/day/2026-09-01',
    );
    expect(within(region('구성')).getByText('자산의 80.6% · 목표 80%')).toBeVisible();
    expect(within(region('구성')).getByText('자산의 18.5% · 목표 20%')).toBeVisible();
    expect(rowValuesSum()).toBe(10_112_670);
  });
});

describe('실전 첫 체결 전 (값표 §2.1)', () => {
  it('손익 · 첫 체결 뒤, one point with ⏻, no 모의투자 numbers', async () => {
    const { container } = renderState(homeLiveFirst);
    expect(await findTotal('10,000,000원')).toBeInTheDocument();
    expect(screen.getByText('실전 자산 · 9/1 시작')).toBeVisible();
    expect(screen.getByText('손익 · 첫 체결 뒤')).toBeVisible();
    expect(screen.queryByText(/손대지 않았을 때 \+/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '08:30 기준' })).toBeVisible();
    const line = screen.getByRole('link', { name: /첫 주문/ });
    expect(textOf(line)).toBe('리밸런싱 예정오늘 09:05 첫 주문 · 한국 매수 2건');
    expect(screen.getByText('첫 체결 뒤 그래프가 그려져요')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '9/1(화) 실전 켬' })).toBeVisible();
    expect(screen.queryByText('손대지 않았을 때')).not.toBeInTheDocument();
    const card = region('계획');
    expect(within(card).getByText('목표 80%')).toBeVisible();
    expect(within(card).queryByRole('img', { name: /%p/ })).not.toBeInTheDocument();
    expect(textOf(within(card).getByRole('list'))).toBe('대기환전09:10대기매수22:30');
    expect(within(region('구성')).getByText('09:05부터 매수')).toBeVisible();
    expect(within(region('구성')).getByText('자산의 100.0%')).toBeVisible();
    const text = container.textContent;
    for (const paper of ['10,243,800', '243,800', '2.44%', '3.59%', '81.1%']) {
      expect(text).not.toContain(paper);
    }
  });
});

describe('출시 첫날 (값표 §4)', () => {
  it('one point + 시작 marker + 그래프는 둘째 날부터, no period chips, one rule', async () => {
    renderState(homeFirstDay);
    expect(await findTotal('10,005,258원')).toBeInTheDocument();
    expect(screen.getByText('▲ +5,258원 · +0.05%')).toBeVisible();
    expect(screen.getByText('손대지 않았을 때 +0.05%')).toBeVisible();
    expect(screen.getByText('그래프는 둘째 날부터')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '7/1(수) 시작' })).toBeVisible();
    expect(screen.queryByRole('group', { name: '기간' })).not.toBeInTheDocument();
    const card = region('계획');
    expect(within(card).getByText('오늘 22:30 미국 매수 54주')).toBeVisible();
    expect(textOf(within(card).getByRole('list'))).toBe('체결환전09:10대기매수22:30');
    expect(within(card).getByText('다음 확인 7/2 08:30')).toBeVisible();
    expect(within(card).queryByText(/외 \d개 규칙/)).not.toBeInTheDocument();
    const chips = screen.getByRole('group', { name: '묶어 보기' });
    expect(
      within(chips)
        .getAllByRole('button')
        .map((b) => b.textContent),
    ).toEqual(['나라', '통화']);
    expect(within(region('구성')).getByText('매수 대기 · 54주')).toBeVisible();
    expect(within(region('구성')).getByText('자산의 99.6% · 목표 100%')).toBeVisible();
    expect(rowValuesSum()).toBe(10_005_258);
  });
});

describe('빈 상태 · 첫 확인 전', () => {
  it('start amount, 첫 확인 line without a chip, empty grid, target outline bar', async () => {
    const { container } = renderState(homeEmpty);
    expect(await findTotal('10,000,000원')).toBeInTheDocument();
    expect(screen.getByText('모의투자 시작 금액')).toBeVisible();
    expect(screen.getByText('손익 · 첫 확인 뒤')).toBeVisible();
    const line = screen.getByRole('link', { name: /첫 확인 7\/1\(수\)/ });
    expect(textOf(line)).toBe('첫 확인 7/1(수) 08:30 · 목표대로 매수');
    expect(screen.getByText('첫 확인 뒤 그래프가 그려져요')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /기준$/ })).not.toBeInTheDocument();
    const card = region('계획');
    expect(within(card).getByText('첫 확인 7/1 08:30 · 목표대로 매수')).toBeVisible();
    expect(within(card).getByText('외 1개 규칙 · 첫 확인 전')).toBeVisible();
    expect(
      screen.getAllByText('점선 = 목표 비중 · 지수 반반 80% · [예시] 종목 모멘텀 20%').length,
    ).toBeGreaterThan(0);
    expect(
      container.querySelectorAll('rect.outline-strategy-1, rect.outline-strategy-2'),
    ).toHaveLength(2);
    expect(within(region('구성')).getByText('첫 확인 때 매수')).toBeVisible();
    expect(screen.getByRole('banner')).toHaveTextContent('첫 확인 전');
  });
});

describe('휴장 (명세, 그림 없음)', () => {
  it("plan line '휴장 · 한국 휴장 · 거래 없음 ›', card chip 휴장, no stages, 다음 확인, no banner", async () => {
    renderState(homeHoliday);
    expect(await findTotal('10,243,633원')).toBeInTheDocument();
    const line = screen.getByRole('link', { name: /휴장/ });
    expect(textOf(line)).toBe('휴장한국 휴장 · 거래 없음');
    const card = region('계획');
    expect(within(card).getByText('휴장')).toBeVisible();
    expect(within(card).queryByRole('list')).not.toBeInTheDocument();
    expect(within(card).getByText('다음 확인 10/12 08:30')).toBeVisible();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(rowValuesSum()).toBe(10_243_633);
  });
});

describe('확인 실패 (명세, 그림 없음)', () => {
  it("header 확인 실패, banner '10/7 08:30 확인 실패 · 09:30 자동 재시도 · 작동 보기'", async () => {
    renderState(homeCheckFailed);
    expect(await findTotal('10,228,000원')).toBeInTheDocument();
    expect(screen.getByRole('banner')).toHaveTextContent('확인 실패');
    const banner = screen.getByRole('status');
    expect(textOf(banner)).toBe('10/7 08:30 확인 실패 · 09:30 자동 재시도작동 보기');
    expect(rowValuesSum()).toBe(10_228_000);
  });
});

describe('실전 일부 실패 · 직접 할 일', () => {
  it("header 직접 할 일 1, banner with 토스 주문 거부, plan line '직접 할 일 · 토스 앱에서 주문 확인'", async () => {
    renderState(homeLiveTodo);
    expect(await findTotal('10,112,670원')).toBeInTheDocument();
    expect(screen.getByRole('banner')).toHaveTextContent('직접 할 일 1');
    expect(textOf(screen.getByRole('status'))).toBe(
      '10/7 미국 매수 실패 · 토스 주문 거부 · 직접 할 일작동 보기',
    );
    const line = screen.getByRole('link', { name: /토스 앱에서 주문 확인/ });
    expect(textOf(line)).toBe('일부 실패직접 할 일 · 토스 앱에서 주문 확인');
    expect(textOf(within(region('계획')).getByRole('list'))).toContain('실패매수직접 할 일');
  });
});

describe('알림 안 닿음 (명세, 그림 없음)', () => {
  it("banner '알림이 9일째 기기에 안 닿아요 · 시험 알림 ›'", async () => {
    renderState(homePushUndelivered);
    await findTotal('10,243,800원');
    const banner = screen.getByRole('status');
    expect(textOf(banner)).toBe('알림이 9일째 기기에 안 닿아요시험 알림');
  });
});

describe('연결 끊김', () => {
  it("numbers stay; '16:10 불러온 값 · 연결 안 됨' and header 연결 안 됨", async () => {
    renderState({ ...homeOffline, shellPollMs: 30 } satisfies FixtureBundle);
    expect(await findTotal('10,243,800원')).toBeInTheDocument();
    expect(await screen.findByText('16:10 불러온 값 · 연결 안 됨')).toBeVisible();
    expect(screen.getByRole('banner')).toHaveTextContent('연결 안 됨');
    expect(screen.getByText('10,243,800원', { selector: '.t-display' })).toBeVisible();
  });
});

describe('다른 기기에서 바뀜', () => {
  it('badge and chip within a poll, numbers turn to skeleton, then the new ledger', async () => {
    const quick: FixtureBundle = {
      ...homeOtherDevice,
      shellPollMs: 40,
      responses: {
        ...homeOtherDevice.responses,
        '/api/home?ledger=paper': { $delayMs: 150, $then: homePaper() },
      },
    };
    renderState(quick);
    expect(await findTotal('10,112,670원')).toBeInTheDocument();
    expect(await screen.findByText('16:11 다른 기기에서 실전 → 모의투자로 바뀜')).toBeVisible();
    expect(
      within(screen.getByRole('banner')).getByRole('link', { name: '모의투자' }),
    ).toBeVisible();
    expect(screen.queryByText('10,112,670원')).not.toBeInTheDocument();
    expect(document.querySelector('[aria-busy="true"]')).not.toBeNull();
    expect(await findTotal('10,243,800원')).toBeInTheDocument();
  });
});

describe('첫 로드', () => {
  it('card frames, titles and tabs with skeleton bars; no numbers', async () => {
    const { container } = renderState(homeLoading);
    expect(await screen.findByRole('region', { name: '계획' })).toBeVisible();
    expect(screen.getByRole('region', { name: '구성' })).toBeVisible();
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull();
    expect(screen.getByRole('link', { name: '계획 보기' })).toBeVisible();
    expect(container.textContent).not.toMatch(/\d{1,3}(,\d{3})+원/);
  });
});

describe('세션 없음', () => {
  it('goes to the PIN page and remembers the way back', async () => {
    const { router } = renderState(homePermission);
    // main.tsx sends the client's 403 'session' to the router; do the same here.
    configureClient({
      onAuthRequired: (next) => {
        void router.navigate(pinPath(next));
      },
    });
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/pin');
    });
    expect(router.state.location.search).toContain('next=');
  });
});

describe('group-by of the 실전 world', () => {
  it('나라 regroups the rows', async () => {
    renderState(homeLive);
    await findTotal('10,112,670원');
    fireEvent.click(
      within(screen.getByRole('group', { name: '묶어 보기' })).getByRole('button', {
        name: '나라',
      }),
    );
    const card = region('구성');
    expect(within(card).getByRole('heading', { level: 3, name: '한국' })).toBeVisible();
    expect(within(card).getByRole('heading', { level: 3, name: '미국' })).toBeVisible();
    expect(within(card).getByRole('heading', { level: 3, name: '코인' })).toBeVisible();
    expect(within(card).getByRole('heading', { level: 3, name: '현금' })).toBeVisible();
  });
});
