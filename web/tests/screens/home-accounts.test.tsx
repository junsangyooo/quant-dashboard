// SCR-HOME 계좌별 보기 (the owner, 2026-10-12): 전체 · 한국 ₩ · 미국 $. 전체 is the ledger in won with
// the two account tiles and 환율 효과; an account shows its value, P&L, line and rows in its own
// money. Numbers are the 예시-값표 world split as the engine splits it (fixtures/parts/accounts.ts).
import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it } from 'vitest';
import type { Breakdown, HomeResponse } from '../../src/api/types';
import homeBeforeFill from '../../src/fixtures/bundles/home.before-fill';
import homePaper from '../../src/fixtures/bundles/home.paper';
import homeUsCash from '../../src/fixtures/bundles/home.us-cash';
import homeUsEmpty from '../../src/fixtures/bundles/home.us-empty';
import { paperAccounts } from '../../src/fixtures/parts/accounts';
import { homePaper as paperHome } from '../../src/fixtures/parts/home';
import type { FixtureBundle } from '../../src/fixtures/types';
import { viewOf } from '../../src/screens/Home/HomeScreen';
import { moneyTick } from '../../src/screens/Home/money';
import { breakdownSteps, singlePointAxis } from '../../src/screens/Home/TrendCard';
import { findTotal, renderState, stubScroll, textOf } from './home-plan.routes';

beforeAll(stubScroll);
beforeEach(() => {
  window.localStorage.clear();
});

const switcher = () => screen.getByRole('radiogroup', { name: '계좌' });
const radio = (name: string) => within(switcher()).getByRole('radio', { name });
const composition = () => screen.getByRole('region', { name: '구성' });

function figures(pattern: RegExp): string[] {
  return within(composition())
    .getAllByText(pattern, { selector: '.t-figure' })
    .map((el) => el.textContent);
}

describe('전체 (the ledger in won)', () => {
  it('puts the switch on top with 전체 chosen, then the total, 환율 효과 and the two tiles', async () => {
    renderState(homePaper);
    expect(await findTotal('10,243,800원')).toBeInTheDocument();
    expect(radio('전체')).toHaveAttribute('aria-checked', 'true');
    expect(radio('한국 ₩')).toHaveAttribute('aria-checked', 'false');
    expect(radio('미국 $')).toHaveAttribute('aria-checked', 'false');
    // Today's view stays: the P&L, the untouched line and the plan.
    expect(screen.getByText('▲ +243,800원 · +2.44%')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '손대지 않았을 때 +3.59%' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: '계획' })).toBeInTheDocument();
    // Each account in its own money; a tile opens that account's view.
    const kr = screen.getByRole('link', { name: /한국 계좌/ });
    const us = screen.getByRole('link', { name: /미국 계좌/ });
    expect(textOf(kr)).toBe('한국 계좌+9.41%5,368,683원▲ +484,683원');
    expect(textOf(us)).toBe('미국 계좌−4.30%$3,526.56▼ −$149.95');
    expect(kr).toHaveAttribute('href', '/?account=kr');
    expect(us).toHaveAttribute('href', '/?account=us');
  });

  it('환율 효과 opens 손익 나눠 보기: 한국 + 미국 in won + 환율 효과 = 전체 손익, to the won', async () => {
    renderState(homePaper);
    await findTotal('10,243,800원');
    const line = screen.getByRole('button', { name: /환율 효과/ });
    expect(textOf(line)).toBe('환율 효과−33,592원');
    fireEvent.click(line);
    const sheet = await screen.findByRole('dialog', { name: '손익 나눠 보기' });
    const rows = within(within(sheet).getByRole('table'))
      .getAllByRole('row')
      .slice(1)
      .map((r) => textOf(r));
    expect(rows).toEqual([
      '한국 계좌+484,683원',
      '미국 계좌−207,291원',
      '환율 효과−33,592원',
      '전체 손익+243,800원',
    ]);
    expect(484_683 - 207_291 - 33_592).toBe(243_800);
    // How the dollars became won, and what 환율 효과 is.
    expect(within(sheet).getByText('미국 계좌 −$149.95 × 1,382.4원')).toBeInTheDocument();
    expect(
      within(sheet).getByText('환율 효과 · 달러로 바꾼 돈이 지금 환율로 늘거나 준 몫이에요'),
    ).toBeInTheDocument();
  });
});

describe('한국 ₩ · 미국 $ (one account in its own money)', () => {
  it('한국 ₩: its value and P&L in won, its own line with 들어온 돈, no plan or 손대지 않았을 때', async () => {
    const { router } = renderState(homePaper);
    await findTotal('10,243,800원');
    fireEvent.click(radio('한국 ₩'));
    expect(await findTotal('5,368,683원')).toBeInTheDocument();
    expect(router.state.location.search).toBe('?account=kr');
    expect(radio('한국 ₩')).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByText('한국 계좌 · 7/1부터')).toBeInTheDocument();
    expect(screen.getByText('▲ +484,683원 · +9.41%')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /손대지 않았을 때/ })).toBeNull();
    expect(screen.queryByRole('region', { name: '계획' })).toBeNull();
    expect(screen.queryByRole('button', { name: /환율 효과/ })).toBeNull();
    const trend = screen.getByRole('region', { name: '자산 변동' });
    expect(within(trend).getByText('한국 계좌')).toBeInTheDocument();
    expect(within(trend).getByText('들어온 돈')).toBeInTheDocument();
    // Why the dashed line steps: a conversion moves money in between the two accounts.
    expect(
      within(trend).getByText('들어온 돈은 환전하면 두 계좌 사이로 옮겨가요'),
    ).toBeInTheDocument();
    // Rows in won add up to the account; group % is of the account, no targets.
    const won = figures(/원$/).map((t) => Number(t.replace(/[,원]/g, '')));
    expect(won.reduce((a, b) => a + b, 0)).toBe(5_368_683);
    expect(within(composition()).getByText('계좌의 77.6%')).toBeInTheDocument();
    expect(within(composition()).queryByText(/목표/)).toBeNull();
    expect(within(composition()).queryByText('S&P 500 ETF')).toBeNull();
  });

  it('미국 $: dollars everywhere — value, P&L, rows, and the S&P ETF return without the rate', async () => {
    renderState(homePaper, '/?account=us');
    expect(await findTotal('$3,526.56')).toBeInTheDocument();
    expect(screen.getByText('미국 계좌 · 7/1부터')).toBeInTheDocument();
    expect(screen.getByText('▼ −$149.95 · −4.30%')).toBeInTheDocument();
    expect(figures(/^\$/)).toEqual(['$2,870.40', '$126.96', '$529.20']);
    // −5.4% in dollars (전체 shows −6.0%: the rate is in the won figure).
    expect(within(composition()).getByText('▼ −5.4%')).toBeInTheDocument();
    expect(within(composition()).getByText('매수 대기 · S&P 500 ETF 2주')).toBeInTheDocument();
    expect(within(composition()).queryByText('KOSPI200 ETF')).toBeNull();
    expect(within(composition()).getByText('계좌의 85.0%')).toBeInTheDocument();
  });

  it('미국 $ 변동 분해: start → 환전 → 시세 → 배당 → 수수료 → now, in dollars', async () => {
    renderState(homePaper, '/?account=us');
    await findTotal('$3,526.56');
    const us = paperAccounts('3m').list[1];
    const pnl = us?.trend.periodPnl;
    expect(pnl).not.toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /3개월.*\$/ }));
    const sheet = await screen.findByRole('dialog', { name: '변동 분해 · 3개월' });
    await within(sheet).findByText('7/7~10/7');
    const rows = within(within(sheet).getByRole('table'))
      .getAllByRole('row')
      .slice(1)
      .map((r) => textOf(r));
    expect(rows.map((r) => r.replace(/[+−$\d,.]+$/, ''))).toEqual([
      '기간 시작',
      '환전',
      '시세',
      '배당',
      '수수료',
      '지금',
    ]);
    expect(rows[1]).toBe('환전+$251.23');
    expect(rows[4]).toBe('수수료−$0.13');
    expect(rows[5]).toBe('지금$3,526.56');
  });

  it('a period chip follows the account: 1개월 gives the account its 1-month P&L', async () => {
    renderState(homePaper, '/?account=kr');
    await findTotal('5,368,683원');
    const month = paperAccounts('1m').list[0]?.trend.periodPnl;
    expect(month).toBeTruthy();
    fireEvent.click(
      within(screen.getByRole('group', { name: '기간' })).getByRole('button', { name: '1개월' }),
    );
    const amount = new Intl.NumberFormat('en-US').format(Math.abs(month?.amount ?? 0));
    expect(
      await screen.findByRole('button', { name: new RegExp(`1개월.*${amount}원`) }),
    ).toBeVisible();
    // The switch keeps its place; 전체 shows the ledger's 1-month P&L again.
    fireEvent.click(radio('전체'));
    expect(
      await screen.findByRole('button', { name: /1개월.*\+138,400원 \(\+1\.37%\)/ }),
    ).toBeVisible();
  });

  it('an account opened from 전체 is one entry above it: back and 전체 both return there', async () => {
    const { router } = renderState(homePaper);
    await findTotal('10,243,800원');
    fireEvent.click(radio('한국 ₩'));
    await findTotal('5,368,683원');
    fireEvent.click(radio('미국 $')); // between the accounts the entry is replaced
    await findTotal('$3,526.56');
    await act(() => router.navigate(-1));
    expect(await findTotal('10,243,800원')).toBeInTheDocument();
    expect(router.state.location.search).toBe('');
    // 전체 on the switch steps back as well, so presses never pile up entries.
    fireEvent.click(radio('한국 ₩'));
    await findTotal('5,368,683원');
    fireEvent.click(radio('전체'));
    expect(await findTotal('10,243,800원')).toBeInTheDocument();
    expect(router.state.historyAction).toBe('POP');
    // An address opened as it is (no 전체 under it): 전체 replaces it.
    await act(() => router.navigate('/?account=us'));
    await findTotal('$3,526.56');
    fireEvent.click(radio('전체'));
    expect(await findTotal('10,243,800원')).toBeInTheDocument();
    expect(router.state.historyAction).toBe('REPLACE');
  });

  it('arrow keys move along the switch', async () => {
    renderState(homePaper);
    await findTotal('10,243,800원');
    radio('전체').focus();
    fireEvent.keyDown(radio('전체'), { key: 'ArrowRight' });
    await waitFor(() => {
      expect(radio('한국 ₩')).toHaveAttribute('aria-checked', 'true');
    });
    expect(radio('한국 ₩')).toHaveFocus();
    fireEvent.keyDown(radio('한국 ₩'), { key: 'ArrowLeft' });
    await waitFor(() => {
      expect(radio('전체')).toHaveAttribute('aria-checked', 'true');
    });
  });

  it('a stale market marks only its own account (dollars do not move with the rate)', async () => {
    const accounts = paperAccounts();
    const [kr, us] = accounts.list;
    if (!kr || !us) throw new Error('accounts');
    const stale: HomeResponse = {
      ...paperHome(),
      accounts: { ...accounts, list: [kr, { ...us, stale: true }] },
    };
    const bundle: FixtureBundle = {
      ...homePaper,
      responses: { ...homePaper.responses, '/api/home': stale },
    };
    const { unmount } = renderState(bundle, '/?account=us');
    await findTotal('$3,526.56');
    expect(screen.getAllByText('낡음')).toHaveLength(2); // hero and 구성
    unmount();
    renderState(bundle, '/?account=kr');
    await findTotal('5,368,683원');
    expect(screen.queryByText('낡음')).toBeNull();
  });
});

describe('the edges: before the first fill, dollars only, an empty account', () => {
  it('before the first fill there is no switch and no tile (손익 · 첫 체결 뒤)', async () => {
    renderState(homeBeforeFill);
    expect(await findTotal('10,000,000원')).toBeInTheDocument();
    expect(screen.getByText('손익 · 첫 체결 뒤')).toBeInTheDocument();
    expect(screen.queryByRole('radiogroup', { name: '계좌' })).toBeNull();
    expect(screen.queryByRole('link', { name: /한국 계좌/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /환율 효과/ })).toBeNull();
    // Won waiting to buy keeps the name: it is for either market.
    expect(within(composition()).getByText('매수 대기 · KOSPI200 ETF 156주')).toBeVisible();
    expect(within(composition()).getByText('매수 대기 · S&P 500 ETF 54주')).toBeVisible();
  });

  it('a ?account= address before the first fill shows 전체', async () => {
    renderState(homeBeforeFill, '/?account=us');
    expect(await findTotal('10,000,000원')).toBeInTheDocument();
    expect(screen.getByText('모의투자 자산 · 7/1부터')).toBeInTheDocument();
  });

  it('미국 계좌 with dollars only: $3,568.24, no gain or loss yet, one row, the graph from day two', async () => {
    renderState(homeUsCash, '/?account=us');
    expect(await findTotal('$3,568.24')).toBeInTheDocument();
    expect(screen.getByText('$0.00 · 0.00%')).toBeInTheDocument();
    expect(screen.getByText('그래프는 둘째 날부터')).toBeInTheDocument();
    expect(figures(/^\$/)).toEqual(['$3,568.24']);
    expect(within(composition()).getByText('매수 대기 · 54주')).toBeVisible();
    expect(within(composition()).getByText('100.0%')).toBeVisible();
  });

  it('an empty 미국 계좌: $0.00 and why, no graph or rows; its tile says 비어 있음', async () => {
    renderState(homeUsEmpty, '/?account=us');
    expect(await findTotal('$0.00')).toBeInTheDocument();
    expect(screen.getByText('미국 계좌는 비어 있어요')).toBeInTheDocument();
    expect(screen.getByText('환전하면 채워져요')).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: '구성' })).toBeNull();
    expect(screen.queryByRole('region', { name: '자산 변동' })).toBeNull();
    fireEvent.click(radio('전체'));
    expect(await findTotal('9,999,252원')).toBeInTheDocument();
    expect(textOf(screen.getByRole('link', { name: /미국 계좌/ }))).toBe('미국 계좌$0.00비어 있음');
    expect(textOf(screen.getByRole('link', { name: /한국 계좌/ }))).toBe(
      '한국 계좌−0.01%9,999,252원▼ −748원',
    );
  });
});

describe('pieces', () => {
  it('reads the view from the address only when the ledger has accounts', () => {
    const home = paperHome();
    expect(viewOf('kr', home)).toBe('kr');
    expect(viewOf('us', home)).toBe('us');
    expect(viewOf('jp', home)).toBe('all');
    expect(viewOf(null, home)).toBe('all');
    expect(viewOf('us', { ...home, accounts: null })).toBe('all');
    expect(viewOf('us', null)).toBe('all');
  });

  it('미국 계좌 shows 입금 · 출금 only when dollars came in or went out that way', () => {
    const us: Breakdown = {
      from: '2026-07-01',
      to: '2026-10-07',
      currency: 'USD',
      start: 0,
      deposit: 0,
      withdrawal: 0,
      transfer: 3568.24,
      market: 10,
      dividend: 1,
      fees: -3.56,
      end: 3575.68,
    };
    const keys = (b: Breakdown) => breakdownSteps(b).map((s) => s.key);
    expect(keys(us)).toEqual(['start', 'transfer', 'market', 'dividend', 'fee', 'end']);
    expect(keys({ ...us, deposit: 100, end: 3675.68 })).toEqual([
      'start',
      'deposit',
      'transfer',
      'market',
      'dividend',
      'fee',
      'end',
    ]);
    // 한국 계좌 and 전체 keep both rows, even at 0.
    expect(keys({ ...us, currency: 'KRW', transfer: -10, end: 0 })).toContain('withdraw');
  });

  it('draws dollar ticks without cents unless the step needs them', () => {
    const tick = moneyTick('USD');
    expect(tick(3500)).toBe('$3,500');
    expect(tick(3502.5)).toBe('$3,502.50');
    expect(moneyTick('KRW')(5_200_000)).toBe('520만');
  });

  it('puts one dollar point on an axis of about 2% steps', () => {
    expect(singlePointAxis(3568.24, 'amount', 'USD')).toEqual({
      domain: [3500, 3687.5],
      ticks: [3550, 3600, 3650],
    });
    expect(singlePointAxis(5_040_052, 'amount', 'KRW').ticks).toEqual([
      5_000_000, 5_100_000, 5_200_000,
    ]);
  });
});
