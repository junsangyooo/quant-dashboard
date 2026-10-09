// SCR-RULES 규칙 — 기획 §5 완료 조건 (one block per bullet); values from 예시-값표 §1 · §4.
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { PlanResponse } from '../../src/api/types';
import planPaper from '../../src/fixtures/bundles/plan.paper';
import rulesDaily from '../../src/fixtures/bundles/rules.discovery-daily';
import rulesError from '../../src/fixtures/bundles/rules.error';
import rulesFirstDay from '../../src/fixtures/bundles/rules.first-day';
import rulesIndexHalf from '../../src/fixtures/bundles/rules.index-half';
import rulesLoading from '../../src/fixtures/bundles/rules.loading';
import rulesMomentum from '../../src/fixtures/bundles/rules.momentum';
import rulesStale from '../../src/fixtures/bundles/rules.stale';
import { ruleIndexHalf, ruleMomentum } from '../../src/fixtures/parts/rules';
import { findText, renderState, textOf, viewport } from './hdr.routes';

afterEach(() => {
  vi.unstubAllGlobals();
});

function tile(name: string) {
  return screen.getByRole('region', { name });
}

async function indexHalf(path = '/rules') {
  const r = renderState(rulesIndexHalf, path);
  await screen.findByRole('heading', { level: 1, name: '지수 반반' });
  return r;
}

async function momentum() {
  const r = renderState(rulesMomentum, '/rules/momentum');
  await screen.findByRole('heading', { level: 1, name: '[예시] 종목 모멘텀' });
  return r;
}

describe('SCR-RULES · 지수 반반 (1:60971 · 1:61916)', () => {
  it('완료 조건: six tiles — 50 : 50 · 매일 08:30 · ±2%p 넘으면 · 리밸런싱 주문 · +9.5% · 지금·결과 ✓✓⏳', async () => {
    await indexHalf();
    expect(textOf(tile('무엇 · 비중'))).toContain('50 : 50원화 기준 · ETF 2개');
    expect(textOf(tile('언제 · 시작'))).toContain('매일 08:30한국 시간 · 평일');
    expect(textOf(tile('조건'))).toContain('±2%p 넘으면목표 50% 기준');
    expect(textOf(tile('행동'))).toContain('리밸런싱 주문목표 비중까지');
    expect(textOf(tile('과거 1년 수익 · 측정'))).toContain('+9.5%중간값 · 세후 · 2015–25');
    const now = tile('지금 · 결과');
    expect(textOf(now)).toContain('매도09:05환전09:10매수22:30');
    expect(now.querySelectorAll('.lucide-circle-check')).toHaveLength(2);
    expect(now.querySelectorAll('.lucide-hourglass')).toHaveLength(1);
    expect(textOf(now)).toContain('리밸런싱 중다음 확인 10/8 08:30');
  });

  it('완료 조건: 과거 1년 수익 — no 기대, 2015–25 · 세후 · 중간값, a neutral big number, ⌄ opens the source', async () => {
    await indexHalf();
    expect(screen.queryByText(/기대/)).toBeNull();
    const t = tile('과거 1년 수익 · 측정');
    const value = within(t).getByText('+9.5%', { selector: '.t-heading-1' });
    expect(value.className).not.toMatch(/gain|loss/);
    const toggle = within(t).getByRole('button', { name: '출처' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(textOf(t.querySelector('dl'))).toBe(
      '출처T09기간2015–25중간값+9.5%나쁜 해−13.6%최악−33.5%세후세후',
    );
  });

  it('완료 조건: a measurement that is not there is not drawn (5 tiles)', async () => {
    const detail = ruleIndexHalf();
    const bundle = {
      ...rulesIndexHalf,
      responses: {
        ...rulesIndexHalf.responses,
        '/api/rules/index_half': {
          ...detail,
          display:
            detail.display.kind === 'tiles'
              ? { ...detail.display, measured: null }
              : detail.display,
        },
      },
    };
    renderState(bundle, '/rules/index_half');
    await screen.findByRole('heading', { level: 1, name: '지수 반반' });
    expect(screen.queryByRole('region', { name: '과거 1년 수익 · 측정' })).toBeNull();
    expect(screen.getByRole('region', { name: '지금 · 결과' })).toBeInTheDocument();
  });

  it('완료 조건: 자산의 81.1% · 목표 80% and the status chip equal the 계획 card head', async () => {
    await indexHalf();
    expect(textOf(screen.getByText('자산의').parentElement)).toBe('자산의81.1%· 목표 80%');
    const plan = planPaper.responses['/api/plan'] as PlanResponse;
    const card = plan.rules.find((r) => r.rule.id === 'index_half');
    expect(card?.share).toEqual({ pct: 81.1, target: 80 });
    expect(card?.status).toBe(ruleIndexHalf().status);
    const m = plan.rules.find((r) => r.rule.id === 'momentum');
    expect(m?.share).toEqual(ruleMomentum().share);
    expect(m?.status).toBe(ruleMomentum().status);
  });

  it('완료 조건: AI chip is AI 없음 or AI 판단 포함; 계획에서 지금 위치 보기 links to the rule card', async () => {
    await indexHalf();
    expect(screen.getAllByText('AI 없음').length).toBeGreaterThan(0);
    expect(screen.getByRole('link', { name: '계획에서 지금 위치 보기' })).toHaveAttribute(
      'href',
      '/plan#rule-index_half',
    );
  });

  it('완료 조건: no input, edit or save controls (view only)', async () => {
    const { container } = await indexHalf();
    expect(container.querySelectorAll('input, textarea, select, [contenteditable]')).toHaveLength(
      0,
    );
    expect(screen.queryByRole('button', { name: /저장|편집|수정/ })).toBeNull();
  });
});

describe('rule selection', () => {
  it('완료 조건 390: one rule at a time, chips switch and put the id in the address', async () => {
    const { router } = await indexHalf();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: 'AI 판단 포함 [예시] 종목 모멘텀 18.3%' }));
    expect(
      await screen.findByRole('heading', { level: 1, name: '[예시] 종목 모멘텀' }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/rules/momentum');
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
  });

  it('완료 조건 1440: the list cards switch rules, with 보기 전용 under them', async () => {
    viewport(1440);
    const { router } = await indexHalf();
    expect(screen.getByText('규칙 2개')).toBeInTheDocument();
    expect(screen.getByText('보기 전용')).toBeInTheDocument();
    const current = screen.getByRole('link', { current: 'page', name: /지수 반반/ });
    expect(current).toHaveAttribute('href', '/rules/index_half');
    fireEvent.click(screen.getByRole('link', { name: /\[예시\] 종목 모멘텀/ }));
    expect(
      await screen.findByRole('heading', { level: 1, name: '[예시] 종목 모멘텀' }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/rules/momentum');
  });

  it('완료 조건: with one rule there is no selector, the same six tiles (1:61661)', async () => {
    renderState(rulesFirstDay, '/rules');
    await screen.findByRole('heading', { level: 1, name: '지수 반반' });
    expect(screen.queryByRole('group', { name: '규칙' })).toBeNull();
    expect(screen.queryByText('보기 전용')).toBeNull();
    expect(textOf(screen.getByText('자산의').parentElement)).toBe('자산의99.6%· 목표 100%');
    const now = tile('지금 · 결과');
    expect(textOf(now)).toContain('환전09:10매수22:30');
    expect(textOf(now)).not.toContain('매도');
    expect(textOf(now)).toContain('다음 확인 7/2 08:30');
  });
});

describe('SCR-RULES · [예시] 종목 모멘텀 (1:61226 · 1:62197)', () => {
  it('완료 조건: nine node cards (시작 … 결과), each with a 지금 box', async () => {
    await momentum();
    const canvas = screen.getByRole('group', { name: '[예시] 종목 모멘텀 흐름' });
    const cards = within(canvas).getAllByRole('article');
    expect(cards).toHaveLength(9);
    for (const card of cards) expect(within(card).getByText('지금')).toBeInTheDocument();
    const kinds = cards.map((c) => c.querySelector('p span.t-label')?.textContent);
    expect(kinds).toEqual([
      '시작',
      '종목',
      '데이터',
      'AI 판단',
      '비중',
      '조건',
      '행동',
      '예외',
      '결과',
    ]);
  });

  it('완료 조건: the AI card shows 입력 · AI · 출력 and 마지막 판단 10/7 08:30', async () => {
    await momentum();
    const ai = screen.getByText('상위 3 고르고 비중 정하기').closest('article');
    if (!ai) throw new Error('no AI card');
    expect(textOf(ai)).toContain('입력8종목 · 30일 수익률');
    expect(textOf(ai)).toContain('AI상위 3 고르고 비중');
    expect(textOf(ai)).toContain('출력3종목 · 비중');
    expect(textOf(ai)).toContain('· 마지막 판단 10/7 08:30');
    expect(textOf(ai)).toContain('3종목 고름지난번과 같은 3종목');
  });

  it('cards read like the drawing (지금 values)', async () => {
    await momentum();
    const card = (title: string) => textOf(screen.getByText(title).closest('article'));
    expect(card('매일 08:30')).toContain('다음 10/8 08:30');
    expect(card('후보군 8종목')).toContain('외 5');
    expect(card('후보군 8종목')).toContain('· 규칙 안 비중 · 손익');
    expect(card('후보군 8종목')).toContain('삼성전자42.0%+1.4%');
    expect(card('30일 수익률')).toContain('· 8종목 중 상위 3');
    expect(card('42 · 40 · 18')).toContain('42.0 · 39.0 · 18.9목표 42 · 40 · 18');
    expect(card('2%p 넘게 벗어났나요?')).toContain('BTC +1.0%p리밸런싱까지 1.0%p');
    expect(card('리밸런싱 주문')).toContain('· 마지막 9/14~9/15');
    expect(card('리밸런싱 주문')).toContain('매도 1 · 삼성전자9/14 체결');
    expect(card('리밸런싱 주문')).toContain('매수 1 · BTC9/15 다시 · 체결');
    expect(card('다음 확인으로 미룸')).toContain('지금 해당 없음');
    expect(card('리밸런싱 상태')).toContain('목표 범위 안마지막 확인 10/7 08:30');
  });

  it('screen readers get where each card leads (예 → 행동, 아니오 · 그대로 → 결과)', async () => {
    await momentum();
    const condition = screen.getByText('2%p 넘게 벗어났나요?').closest('article');
    expect(textOf(condition)).toContain(
      '예 → 행동 리밸런싱 주문 · 아니오 · 그대로 → 결과 리밸런싱 상태',
    );
  });

  it('예외 칩 show their one-line help in place', async () => {
    await momentum();
    const holiday = screen.getByRole('button', { name: '휴장' });
    fireEvent.click(holiday);
    expect(holiday).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('휴장 → 다음 개장일 확인')).toBeInTheDocument();
  });

  it('line legend: 이번에 지난 길 · 안 지난 갈래 · 예외 갈래', async () => {
    await momentum();
    for (const t of ['이번에 지난 길', '안 지난 갈래', '예외 갈래']) {
      expect(screen.getByText(t)).toBeInTheDocument();
    }
  });
});

describe('3년 발굴 lanes (탐색 17:5855 · 17:6432 · 17:7193 · 17:7808)', () => {
  it('shows 흐름 chips when a rule has several start lanes and switches lanes in place', async () => {
    const { router } = renderState(rulesDaily, '/rules/discovery_3y');
    await screen.findByRole('heading', { level: 1, name: '3년 발굴' });
    const lanes = screen.getByRole('group', { name: '흐름' });
    expect(
      within(lanes)
        .getAllByRole('button')
        .map((b) => b.textContent),
    ).toEqual(['매일 08:30', '실적 공시', '매달 1일', '4·6·9·12월 1일']);
    expect(within(lanes).getByRole('button', { name: '매일 08:30' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    fireEvent.click(within(lanes).getByRole('button', { name: '4·6·9·12월 1일' }));
    expect(await findText('흐름과 기업 고르기')).toBeInTheDocument();
    expect(router.state.location.search).toBe('?lane=quarterly');
    expect(
      textOf(screen.getByText('4·6·9·12월 1일', { selector: 'p' }).closest('article')),
    ).toContain('다음 12/1');
    const lane = (name: string) =>
      within(screen.getByRole('group', { name: '흐름' })).getByRole('button', { name });
    fireEvent.click(lane('실적 공시'));
    expect(await findText('실적 지표 뽑기')).toBeInTheDocument();
    expect(lane('실적 공시')).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(lane('매달 1일'));
    expect(await findText('반증이면 매일 흐름의 두 번 확인으로')).toBeInTheDocument();
  });

  it('no lane chips for a rule with one lane', async () => {
    await momentum();
    expect(screen.queryByRole('group', { name: '흐름' })).toBeNull();
  });
});

describe('SCR-RULES states', () => {
  it('stale: status chip 시세 대기 and 낡음 on 지금·결과 and every 지금 box', async () => {
    renderState(rulesStale, '/rules');
    await screen.findByRole('heading', { level: 1, name: '지수 반반' });
    expect(screen.getAllByText('시세 대기').length).toBeGreaterThan(0);
    expect(within(tile('지금 · 결과')).getByText('낡음')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'AI 판단 포함 [예시] 종목 모멘텀 18.3%' }));
    await screen.findByRole('heading', { level: 1, name: '[예시] 종목 모멘텀' });
    const cards = within(
      screen.getByRole('group', { name: '[예시] 종목 모멘텀 흐름' }),
    ).getAllByRole('article');
    for (const card of cards) expect(within(card).getByText('낡음')).toBeInTheDocument();
  });

  it('loading keeps the frames; error shows 규칙을 못 불러왔어요 + 다시 불러오기', async () => {
    const loading = renderState(rulesLoading, '/rules');
    await waitFor(() => {
      expect(loading.container.querySelector('[aria-busy="true"]')).not.toBeNull();
    });
    loading.unmount();
    renderState(rulesError, '/rules');
    expect(await findText('규칙을 못 불러왔어요')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '다시 불러오기' })).toBeEnabled();
  });
});
