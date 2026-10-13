// SCR-HOME · 모의투자 기본 (기획 §5 완료 조건, 예시-값표 §1). Numbers are the table's. Last, the
// line the live ledger's 손대지 않았을 때 sheet adds (D47).
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { homeCopy } from '../../src/copy/home';
import homeLive from '../../src/fixtures/bundles/home.live';
import homePaper from '../../src/fixtures/bundles/home.paper';
import { PAPER_COMPOSITION } from '../../src/fixtures/parts/home';
import { barSegments, viewGroups } from '../../src/screens/Home/CompositionCard';
import { toneMap } from '../../src/screens/Plan/words';
import { findTotal, html, renderState, stubScroll, textOf } from './home-plan.routes';

beforeAll(stubScroll);
beforeEach(() => {
  window.localStorage.clear();
});

function composition() {
  return screen.getByRole('region', { name: '구성' });
}

function group(name: string) {
  const head = within(composition()).getByRole('heading', { level: 3, name });
  const box = head.closest('div')?.parentElement;
  if (!box) throw new Error(`no group ${name}`);
  return box;
}

describe('SCR-HOME 모의투자 기본', () => {
  it('shows the hero: ledger, start, 예시, 기준, total, PnL and the untouched line', async () => {
    renderState(homePaper);
    expect(await findTotal('10,243,800원')).toBeInTheDocument();
    expect(screen.getByText('모의투자 자산 · 7/1부터')).toBeInTheDocument();
    expect(screen.getAllByText('예시').length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: '16:00 기준' })).toBeInTheDocument();
    expect(screen.getByText('▲ +243,800원 · +2.44%')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '손대지 않았을 때 +3.59%' })).toBeInTheDocument();
  });

  it('plan line: status chip + next action, linking to 계획', async () => {
    renderState(homePaper);
    await findTotal('10,243,800원');
    const line = screen.getByRole('link', { name: /오늘 22:30 미국 매수 2주/ });
    expect(line).toHaveAttribute('href', '/plan');
    expect(textOf(line)).toBe('리밸런싱 중오늘 22:30 미국 매수 2주');
  });

  it('기간 손익 3개월 ▲ +222,800원 (+2.22%) opens the 변동 분해 sheet (bars add up)', async () => {
    renderState(homePaper);
    await findTotal('10,243,800원');
    const pnl = screen.getByRole('button', { name: /3개월.*\+222,800원 \(\+2\.22%\)/ });
    expect(textOf(pnl)).toBe('3개월▲ +222,800원 (+2.22%)');
    fireEvent.click(pnl);
    const sheet = await screen.findByRole('dialog', { name: '변동 분해 · 3개월' });
    expect(await within(sheet).findByText('7/7~10/7')).toBeInTheDocument();
    // start + bars = end: 10,021,000 + 206,825 + 16,243 − 268 = 10,243,800.
    const table = within(sheet).getByRole('table');
    const cells = within(table)
      .getAllByRole('row')
      .slice(1)
      .map((r) => textOf(r));
    expect(cells).toEqual([
      '기간 시작10,021,000원',
      '입금0원',
      '출금0원',
      '시세·환율+206,825원',
      '배당+16,243원',
      '수수료−268원',
      '지금10,243,800원',
    ]);
    fireEvent.click(within(sheet).getByRole('button', { name: '닫기' }));
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });

  it('기준 sheet: 한국 10/7 종가 · 미국 10/6 종가(ET) · 환율 1,382.4원 16:00', async () => {
    renderState(homePaper);
    await findTotal('10,243,800원');
    fireEvent.click(screen.getByRole('button', { name: '16:00 기준' }));
    const sheet = await screen.findByRole('dialog', { name: '16:00 기준' });
    expect(within(sheet).getByText('한국 10/7 종가')).toBeInTheDocument();
    expect(within(sheet).getByText('미국 10/6 종가(ET)')).toBeInTheDocument();
    expect(within(sheet).getByText('환율 1,382.4원 16:00')).toBeInTheDocument();
  });

  it('손대지 않았을 때 sheet explains the half-and-half line', async () => {
    renderState(homePaper);
    await findTotal('10,243,800원');
    fireEvent.click(screen.getByRole('button', { name: '손대지 않았을 때 +3.59%' }));
    const sheet = await screen.findByRole('dialog', { name: '손대지 않았을 때' });
    expect(within(sheet).getByText('시작일에 두 ETF를 반반 사서 그대로 둔 경우예요')).toBeVisible();
    expect(within(sheet).getByText('입출금은 같은 날 같은 금액으로 넣고 빼요')).toBeVisible();
    // The live ledger's line about the won · dollar mix is not the paper ledger's.
    expect(within(sheet).getAllByRole('listitem')).toHaveLength(2);
    expect(within(sheet).queryByText(homeCopy.baselineSheet.live)).toBeNull();
  });

  it('period chips change the graph and its PnL; 전체 hides the period PnL', async () => {
    renderState(homePaper);
    await findTotal('10,243,800원');
    const chips = screen.getByRole('group', { name: '기간' });
    expect(within(chips).getByRole('button', { name: '3개월' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    fireEvent.click(within(chips).getByRole('button', { name: '1개월' }));
    expect(
      await screen.findByRole('button', { name: /1개월.*\+138,400원 \(\+1\.37%\)/ }),
    ).toBeInTheDocument();
    fireEvent.click(within(chips).getByRole('button', { name: '전체' }));
    await waitFor(() => {
      expect(within(chips).getByRole('button', { name: '전체' })).toHaveAttribute(
        'aria-pressed',
        'true',
      );
    });
    expect(screen.queryByRole('button', { name: /전체.*원 \(/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/\+222,800원/)).not.toBeInTheDocument();
  });

  it('금액 | 수익률 switches the line between won and return', async () => {
    renderState(homePaper);
    await findTotal('10,243,800원');
    const modes = screen.getByRole('group', { name: '금액 | 수익률' });
    fireEvent.click(within(modes).getByRole('button', { name: '수익률' }));
    expect(within(modes).getByRole('button', { name: '수익률' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    fireEvent.click(screen.getByRole('button', { name: '표로 보기' }));
    const table = screen.getByRole('table', { name: '표로 보기' });
    // 10/7: 10,243,800 → +2.44% · untouched 10,358,700 → +3.59%.
    expect(textOf(within(table).getAllByRole('row').at(-1) ?? null)).toBe('10/7+2.44%+3.59%');
  });

  it('표로 보기 reads the same values as the graph (접근성 대체)', async () => {
    renderState(homePaper);
    await findTotal('10,243,800원');
    const toggle = screen.getByRole('button', { name: '표로 보기' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(toggle);
    const table = screen.getByRole('table', { name: '표로 보기' });
    const rows = within(table).getAllByRole('row');
    expect(textOf(rows[0] ?? null)).toBe('날짜내 자산손대지 않았을 때');
    expect(textOf(rows[1] ?? null)).toBe('7/710,021,000원9,960,100원');
    expect(textOf(rows.at(-1) ?? null)).toBe('10/710,243,800원10,358,700원');
    expect(screen.getByRole('button', { name: '접기' })).toHaveAttribute('aria-expanded', 'true');
  });

  it('event markers link to the day panel; ⓘ opens the legend sheet', async () => {
    renderState(homePaper);
    await findTotal('10,243,800원');
    const marker = screen.getByRole('link', { name: '8/21(금) 리밸런싱' });
    expect(marker).toHaveAttribute('href', '/day/2026-08-21');
    expect(screen.getByRole('link', { name: '9/14(월) 일부 실패' })).toHaveAttribute(
      'href',
      '/day/2026-09-14',
    );
    fireEvent.click(screen.getByRole('button', { name: '표식 범례' }));
    const legend = await screen.findByRole('dialog', { name: '표식 범례' });
    for (const word of [
      '시작',
      '리밸런싱',
      '일부 실패',
      '진행 중',
      '배당',
      '입금',
      '출금',
      '실전 켬/끔',
    ]) {
      expect(within(legend).getByRole('img', { name: word })).toBeInTheDocument();
    }
    fireEvent.click(marker);
    expect(await screen.findByRole('heading', { level: 1, name: 'day' })).toBeInTheDocument();
  });

  it('구성: group % = sum of its rows = bar segment (40.7 + 38.7 + 1.7 = 81.1)', async () => {
    renderState(homePaper);
    await findTotal('10,243,800원');
    const index = group('지수 반반');
    expect(within(index).getByText('자산의 81.1% · 목표 80%')).toBeInTheDocument();
    expect(within(index).getByText('40.7%')).toBeInTheDocument();
    expect(within(index).getByText('38.7%')).toBeInTheDocument();
    expect(within(index).getByText('1.7%')).toBeInTheDocument();
    expect(within(group('[예시] 종목 모멘텀')).getByText('자산의 18.3% · 목표 20%')).toBeVisible();
    expect(within(group('현금')).getByText('자산의 0.6%')).toBeVisible();
    // The bar draws the same three numbers.
    const segs = barSegments(viewGroups(PAPER_COMPOSITION, 'rule', toneMap([])));
    expect(segs.map((s) => s.value)).toEqual([81.1, 18.3, 0.6]);
    expect(
      within(composition()).getByRole('img', {
        name: '지수 반반 81.1% · [예시] 종목 모멘텀 18.3% · 현금 0.6%',
      }),
    ).toBeInTheDocument();
  });

  it('row values add up to the total (10,243,800원)', async () => {
    renderState(homePaper);
    await findTotal('10,243,800원');
    const values = within(composition())
      .getAllByText(/^[\d,]+원$/, { selector: '.t-figure' })
      .map((el) => Number(el.textContent.replace(/[,원]/g, '')));
    expect(values).toHaveLength(7);
    expect(values.reduce((a, b) => a + b, 0)).toBe(10_243_800);
  });

  it('매수 대기 달러 sits in 지수 반반, the 1주 미만 won in 현금', async () => {
    renderState(homePaper);
    await findTotal('10,243,800원');
    const dollar = html(within(group('지수 반반')).getByText('달러 현금').parentElement);
    expect(within(dollar).getByText('매수 대기 · S&P 500 ETF 2주')).toBeVisible();
    expect(within(dollar).getByText('$126.96')).toBeVisible();
    const won = html(within(group('현금')).getByText('원화 현금').parentElement);
    expect(within(won).getByText('1주 미만 대기')).toBeVisible();
  });

  it('ETF · 주식 · 코인 rows: initials, flag (coin icon) and kind badge', async () => {
    renderState(homePaper);
    await findTotal('10,243,800원');
    const card = composition();
    for (const initials of ['K2', 'SP', '삼', 'NV', 'B']) {
      expect(within(card).getByText(initials)).toBeInTheDocument();
    }
    expect(within(card).getAllByRole('img', { name: '한국' })).toHaveLength(2);
    expect(within(card).getAllByRole('img', { name: '미국' })).toHaveLength(2);
    expect(within(card).getAllByRole('img', { name: '코인' })).toHaveLength(1);
    expect(within(card).getAllByText('ETF')).toHaveLength(2);
    expect(within(card).getAllByText('주식')).toHaveLength(2);
    expect(within(card).getAllByText('코인')).toHaveLength(1);
  });

  it('390: a row opens its second line (115주 · 평균 32,005원)', async () => {
    renderState(homePaper);
    await findTotal('10,243,800원');
    const row = screen.getByRole('button', { name: /KOSPI200 ETF.*4,168,750원/ });
    expect(row).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('115주 · 평균 32,005원')).not.toBeInTheDocument();
    fireEvent.click(row);
    expect(row).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('115주 · 평균 32,005원')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: /BTC/ }));
    expect(screen.getByText('0.0027 BTC · 평균 1억 5,493만원')).toBeVisible();
  });

  it('묶어 보기: every criterion regroups bar and rows; the choice stays on this device', async () => {
    const { unmount } = renderState(homePaper);
    await findTotal('10,243,800원');
    const chips = screen.getByRole('group', { name: '묶어 보기' });
    expect(
      within(chips)
        .getAllByRole('button')
        .map((b) => b.textContent),
    ).toEqual(['종목', '종류', '나라', '통화', '규칙']);
    expect(within(chips).getByRole('button', { name: '규칙' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    fireEvent.click(within(chips).getByRole('button', { name: '종류' }));
    expect(within(composition()).getByRole('heading', { level: 3, name: 'ETF' })).toBeVisible();
    expect(within(group('ETF')).getByText('자산의 79.4%')).toBeVisible();
    expect(within(group('주식')).getByText('자산의 14.8%')).toBeVisible();
    expect(within(group('코인')).getByText('자산의 3.5%')).toBeVisible();
    expect(within(group('현금')).getByText('자산의 2.3%')).toBeVisible();
    expect(window.localStorage.getItem('quant.home.groupBy')).toBe('kind');
    unmount();
    renderState(homePaper);
    await findTotal('10,243,800원');
    expect(
      within(screen.getByRole('group', { name: '묶어 보기' })).getByRole('button', {
        name: '종류',
      }),
    ).toHaveAttribute('aria-pressed', 'true');
  });

  it('계획 card: rule head, the same gauge as 계획, stages, next check, other rules', async () => {
    renderState(homePaper);
    await findTotal('10,243,800원');
    const card = screen.getByRole('region', { name: '계획' });
    expect(within(card).getByRole('link', { name: '계획 보기' })).toHaveAttribute('href', '/plan');
    expect(textOf(within(card).getByRole('heading', { level: 3 }).parentElement)).toBe(
      '지수 반반자산의81.1%· 목표 80%',
    );
    expect(within(card).getByText('오늘 22:30 미국 매수 2주')).toBeVisible();
    expect(within(card).getByText('가장 많이 벗어난 종목')).toBeVisible();
    expect(within(card).getByText('+0.2%p')).toBeVisible();
    expect(within(card).getByText('리밸런싱까지 1.8%p')).toBeVisible();
    const stages = within(card).getByRole('list');
    expect(textOf(stages)).toBe('체결매도09:05체결환전09:10대기매수22:30');
    expect(within(card).getByText('다음 확인 10/8 08:30')).toBeVisible();
    expect(within(card).getByText('외 1개 규칙 · 목표 범위 안')).toBeVisible();
  });

  it('the 계획 card gauge equals the first rule card of 계획 (needle, instrument, numbers)', async () => {
    const { container, router } = renderState(homePaper);
    await findTotal('10,243,800원');
    const homeCard = screen.getByRole('region', { name: '계획' });
    const homeGauge = within(homeCard).getByRole('img', { name: /KOSPI200 ETF/ });
    const needle = (svg: Element) => {
      const line = svg.querySelector('line.needle');
      return [line?.getAttribute('x2'), line?.getAttribute('y2')];
    };
    const atHome = { label: homeGauge.getAttribute('aria-label'), needle: needle(homeGauge) };
    expect(atHome.label).toBe('KOSPI200 ETF +0.2%p · 리밸런싱까지 1.8%p');

    await router.navigate('/plan');
    const first = await screen.findByRole('article', { name: '지수 반반' });
    const planGauge = within(first).getByRole('img', { name: /KOSPI200 ETF/ });
    expect(planGauge.getAttribute('aria-label')).toBe(atHome.label);
    expect(needle(planGauge)).toEqual(atHome.needle);
    expect(container).toBeTruthy();
  });

  it('no 다 sentences and no 모의와 비교 / 실계좌 − 모의 wording', async () => {
    const { container } = renderState(homePaper);
    await findTotal('10,243,800원');
    const text = container.textContent;
    expect(text).not.toMatch(/다\.|니다|었다|한다|된다|이다(?![가-힣])/);
    expect(text).not.toContain('모의와 비교');
    expect(text).not.toContain('실계좌 − 모의');
  });
});

describe('SCR-HOME · 실전 손대지 않았을 때 (D47)', () => {
  it('the sheet adds that most of the gap to the line is the won · dollar mix', async () => {
    renderState(homeLive);
    fireEvent.click(await screen.findByRole('button', { name: '손대지 않았을 때 +1.75%' }));
    const sheet = await screen.findByRole('dialog', { name: '손대지 않았을 때' });
    expect(
      within(sheet)
        .getAllByRole('listitem')
        .map((li) => li.textContent),
    ).toEqual([
      '시작일에 두 ETF를 반반 사서 그대로 둔 경우예요',
      '입출금은 같은 날 같은 금액으로 넣고 빼요',
      '실전에서는 이 선과의 차이가 대부분 원화·달러 비율에서 나와요',
    ]);
  });
});
