// SCR-PLAN · 모의투자 기본 (기획 §5 완료 조건, 예시-값표 §1.3·§1.4).
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeAll, describe, expect, it } from 'vitest';
import planPaper from '../../src/fixtures/bundles/plan.paper';
import planDiscovery from '../../src/fixtures/bundles/plan.discovery';
import { html, renderState, scrollSpy, stubScroll, textOf } from './home-plan.routes';

beforeAll(stubScroll);

const card = (name: string) => screen.getByRole('article', { name });

async function open() {
  renderState(planPaper, '/plan');
  return screen.findByRole('article', { name: '지수 반반' });
}

/** Last row of a card's (or the page's) sr-only drift table, as cells. */
function lastDriftRow(scope: HTMLElement, caption: RegExp): string[] {
  const table = within(scope).getByRole('table', { name: caption });
  const rows = within(table).getAllByRole('row');
  return within(html(rows.at(-1)))
    .getAllByRole('cell')
    .map((c) => textOf(c));
}

describe('SCR-PLAN 모의투자 기본', () => {
  it('지수 반반: 81.1% · 목표 80%, 리밸런싱 중 · 오늘 22:30 미국 매수 2주, needle KOSPI200 ETF +0.2%p, rows 50.2 / 49.8, 1.8%p', async () => {
    const index = await open();
    expect(textOf(within(index).getByRole('heading', { level: 2 }).parentElement)).toBe(
      '지수 반반자산의81.1%· 목표 80%',
    );
    expect(within(index).getByText('리밸런싱 중')).toBeVisible();
    expect(within(index).getByRole('button', { name: '오늘 22:30 미국 매수 2주' })).toBeVisible();
    expect(
      within(index).getByRole('img', { name: 'KOSPI200 ETF +0.2%p · 리밸런싱까지 1.8%p' }),
    ).toBeVisible();
    expect(within(index).getByText('+0.2%p')).toBeVisible();
    expect(within(index).getByText('50.2% · 목표 50%')).toBeVisible();
    expect(within(index).getByText('49.8% · 목표 50%')).toBeVisible();
    expect(within(index).getAllByText('리밸런싱까지 1.8%p')).toHaveLength(3);
    expect(
      within(index).getByText(
        '규칙 안 비중 · 원화 기준 · 매수 대기 달러 포함 · 환율 1,382.4원 16:00',
      ),
    ).toBeVisible();
  });

  it('모멘텀: 목표 범위 안, needle NVDA −1.0%p, 리밸런싱까지 1.0%p', async () => {
    await open();
    const m = card('[예시] 종목 모멘텀');
    expect(within(m).getByText('목표 범위 안')).toBeVisible();
    expect(within(m).getByText('다음 확인 10/8 08:30')).toBeVisible();
    expect(within(m).getByRole('img', { name: 'NVDA −1.0%p · 리밸런싱까지 1.0%p' })).toBeVisible();
    expect(within(m).getByText('39.0% · 목표 40%')).toBeVisible();
    expect(within(m).getAllByText('리밸런싱까지 1.0%p')).toHaveLength(2);
  });

  it('needle = row numbers = last point of the drift line', async () => {
    await open();
    // 지수 반반: +0.2 = 50.2 − 50; 모멘텀: −1.0 = 39.0 − 40; the lines end at 0.2 and 1.0.
    const drift = screen.getByRole('region', { name: '벗어남 흐름' });
    expect(lastDriftRow(drift, /벗어남 흐름/)).toEqual(['0.2%p', '1.0%p']);
    expect(within(card('지수 반반')).getByText('+0.2%p')).toBeVisible();
    expect(within(card('[예시] 종목 모멘텀')).getByText('−1.0%p')).toBeVisible();
  });

  it("예정 '지금' stage cards carry the 10/7 numbers; filled cards say 모의 체결, the pending one nothing", async () => {
    await open();
    const now = screen.getByText('지금 · 리밸런싱 중').closest('li') as HTMLElement;
    expect(within(now).getByText('KOSPI200 ETF 매도 5주 · 181,900원')).toBeVisible();
    expect(within(now).getByText('173,000원 → $125.30 · 1,380.6원')).toBeVisible();
    expect(within(now).getByText('S&P 500 ETF 매수 2주 · 약 $124.80')).toBeVisible();
    expect(within(now).getAllByText('모의 체결')).toHaveLength(2);
    expect(within(now).queryByText('실제 체결')).not.toBeInTheDocument();
    const links = within(now).getAllByRole('link');
    expect(links.map((l) => l.getAttribute('href'))).toEqual([
      '/day/2026-10-07',
      '/day/2026-10-07',
      '/day/2026-10-07',
    ]);
  });

  it('예정 lists 다음 확인 · 휴장 · 1주 미만 대기 with the 예시 chip, then 규칙 그림 보기', async () => {
    await open();
    const schedule = screen.getByRole('region', { name: '예정' });
    expect(within(schedule).getByText('예시')).toBeVisible();
    const items = within(schedule)
      .getAllByRole('listitem')
      .filter((li) => li.parentElement?.tagName === 'OL' && li.querySelector('[class*=rail]'));
    expect(items.map((li) => textOf(li))).toEqual([
      expect.stringContaining('지금 · 리밸런싱 중'),
      '10/8 08:30다음 확인',
      '10/9한국 휴장 · 거래 없음',
      '원화 현금1주 미만 대기56,548원',
    ]);
    expect(within(schedule).getByRole('link', { name: '규칙 그림 보기' })).toHaveAttribute(
      'href',
      '/rules',
    );
  });

  it('the next action of a rule with a 지금 item scrolls there', async () => {
    await open();
    fireEvent.click(screen.getByRole('button', { name: '오늘 22:30 미국 매수 2주' }));
    expect(document.activeElement?.id).toBe('plan-now');
    expect(scrollSpy).toHaveBeenCalled();
  });

  it('rule share bar: 81.1 · 18.3, a segment scrolls to its card', async () => {
    await open();
    const shares = screen.getByRole('region', { name: '규칙별 자산 비중' });
    const seg = within(shares).getByRole('button', { name: '[예시] 종목 모멘텀 18.3%' });
    expect(within(shares).getByRole('button', { name: '지수 반반 81.1%' })).toBeVisible();
    fireEvent.click(seg);
    expect(document.activeElement).toBe(card('[예시] 종목 모멘텀'));
  });

  it('drift: period chips 3개월 · 1년 · 전체; ⇄ markers open the day', async () => {
    await open();
    const drift = screen.getByRole('region', { name: '벗어남 흐름' });
    const chips = within(drift).getByRole('group', { name: '흐름 기간' });
    expect(within(chips).getByRole('button', { name: '3개월' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(within(drift).getByRole('link', { name: '8/21(금) 리밸런싱' })).toHaveAttribute(
      'href',
      '/day/2026-08-21',
    );
    expect(within(drift).getByRole('link', { name: '9/14(월) 일부 실패' })).toBeVisible();
    fireEvent.click(within(chips).getByRole('button', { name: '1년' }));
    await waitFor(() => {
      expect(within(chips).getByRole('button', { name: '1년' })).toHaveAttribute(
        'aria-pressed',
        'true',
      );
    });
    const table = within(drift).getByRole('table', { name: /벗어남 흐름 · 1년/ });
    expect(textOf(within(table).getAllByRole('row')[1] ?? null)).toBe('7/10.2%p0.4%p');
  });
});

describe('AI 규칙 카드 (Figma 탐색 17:7108, plan.discovery)', () => {
  it('sell-condition gauge, rows of 팔 조건까지, basis line and next check with 점검', async () => {
    renderState(planDiscovery, '/plan');
    const ai = await screen.findByRole('article', { name: '3년 발굴' });
    expect(textOf(within(ai).getByRole('heading', { level: 2 }).parentElement)).toBe(
      '3년 발굴자산의18.5%· 목표 20%',
    );
    expect(within(ai).getByText('유지')).toBeVisible();
    expect(within(ai).getByText('다음 확인 10/8 08:30 · 점검 11/1')).toBeVisible();
    expect(within(ai).getByText('팔 조건에 가장 가까운 종목')).toBeVisible();
    expect(within(ai).getByText('54%')).toBeVisible();
    expect(within(ai).getByText('팔 조건까지 이익률 2.3%p')).toBeVisible();
    expect(
      within(ai).getByRole('img', { name: 'HD현대일렉트릭 54% · 팔 조건까지 이익률 2.3%p' }),
    ).toBeVisible();
    const rows: [string, string][] = [
      ['54% · 이익률', '여유 2.3%p'],
      ['41% · 수주잔고', '여유 3.1조'],
      ['12% · AI 매출', '여유 2분기'],
    ];
    for (const [first, second] of rows) {
      expect(within(ai).getByText(first)).toBeVisible();
      expect(within(ai).getByText(second)).toBeVisible();
    }
    expect(
      within(ai).getByText('팔 조건까지 = 고른 날 지표 → 팔 조건 · 지표 표 10/8'),
    ).toBeVisible();
    expect(within(ai).getByText('지수 대비 · 7/1부터 (%p)')).toBeVisible();
    expect(within(ai).getByRole('link', { name: '7/1(수) 시작' })).toHaveAttribute(
      'href',
      '/day/2026-07-01',
    );
    // The gauge runs 0 → 100 with the 80~100 확인 구간 as its band.
    const svg = within(ai).getByRole('img', { name: /HD현대일렉트릭/ });
    expect([...svg.querySelectorAll('text')].map((t) => t.textContent)).toEqual(['0', '50', '100']);
    // The AI rule draws no drift line of its own.
    const drift = screen.getByRole('region', { name: '벗어남 흐름' });
    expect(within(drift).queryByText('3년 발굴')).not.toBeInTheDocument();
  });

  it('예정 adds 실적 발표 · 다음 월 점검 · 다음 발굴', async () => {
    renderState(planDiscovery, '/plan');
    const schedule = await screen.findByRole('region', { name: '예정' });
    expect(within(schedule).getByText('HD현대일렉트릭 실적 발표')).toBeVisible();
    expect(within(schedule).getByText('다음 월 점검')).toBeVisible();
    expect(within(schedule).getByText('다음 발굴')).toBeVisible();
  });
});
