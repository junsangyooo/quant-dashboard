// 원화 · 달러 (D47·D48, 2026-10-13): the live ledger runs on the money as deposited. The plan card
// says '환전 제안' and how much to convert for 50:50, the 예정 list says when the money of today is
// used, and the mode and health screens show the same as an information card beside the to-dos —
// never a to-do, never counted, never closing anything.
import { screen, within } from '@testing-library/react';
import { beforeAll, describe, expect, it } from 'vitest';
import { modeCopy } from '../../src/copy/mode';
import healthLive from '../../src/fixtures/bundles/health.live';
import modeLive from '../../src/fixtures/bundles/mode.live';
import modeLiveCash from '../../src/fixtures/bundles/mode.live-cash';
import planLiveMix from '../../src/fixtures/bundles/plan.live-mix';
import { renderState, stubScroll } from './home-plan.routes';
import { renderApp, serve } from './ops';

beforeAll(stubScroll);

const SUGGESTION = '약 1,552,000원을 달러로 바꾸면 50:50';
const MIX = '지금 한국 61.8 : 미국 38.2 · 토스 앱에서 바꾸면 다음 거래일부터 사요';
const NEW_MONEY = '새로 들어온 돈 3,000,000원 · 다음 거래일 08:30부터 써요';

describe('계획 · 실전 (plan.live-mix)', () => {
  it("the rule card says '환전 제안' and how much; 예정 says when today's money is used", async () => {
    renderState(planLiveMix, '/plan');
    const card = await screen.findByRole('article', { name: '지수 반반' });
    expect(within(card).getByText('환전 제안')).toBeVisible();
    expect(within(card).getByText(SUGGESTION)).toBeVisible();
    expect(within(card).getByText(MIX)).toBeVisible();
    // 실전 runs 지수 반반 alone (실전 몫 100 · 3년 발굴 0): no other rule card, no share bar.
    expect(screen.getAllByRole('article')).toHaveLength(1);
    expect(screen.queryByText('규칙별 자산 비중')).toBeNull();
    // The gauge is the same mix, its band the suggestion's: no rebalance between the currencies.
    expect(within(card).getByText('원화 · 달러 비율')).toBeVisible();
    expect(within(card).getByText('한국 61.8 : 미국 38.2')).toBeVisible();
    expect(within(card).getByText('+11.8%p')).toBeVisible();
    expect(within(card).getByText('환전 제안까지 0.0%p')).toBeVisible();
    expect(within(card).queryByText(/리밸런싱/)).toBeNull();
    expect(screen.getByText(NEW_MONEY)).toBeVisible();
    // Only the money that is not today's would be '새 현금 · 다음 확인에 목표대로'.
    expect(screen.queryByText(/^새 현금/)).toBeNull();
  });
});

describe('모의투자·실전 · 실전 (mode.live-cash)', () => {
  it('shows the 원화 · 달러 card while live is on; the header stays 정상', async () => {
    serve(modeLiveCash);
    renderApp('/mode');
    await screen.findByRole('radiogroup', { name: modeCopy.segment });
    const card = await screen.findByRole('region', { name: '원화 · 달러' });
    expect(within(card).getByText(SUGGESTION)).toBeInTheDocument();
    expect(within(card).getByText(MIX)).toBeInTheDocument();
    expect(within(card).getByText(NEW_MONEY)).toBeInTheDocument();
    expect(screen.getByRole('banner')).not.toHaveTextContent('직접 할 일');
  });

  it('draws no card when there is nothing to say', async () => {
    serve(modeLive);
    renderApp('/mode');
    await screen.findByRole('radiogroup', { name: modeCopy.segment });
    expect(screen.queryByRole('region', { name: '원화 · 달러' })).toBeNull();
  });
});

describe('작동 · 실전 (health.live)', () => {
  it('puts the card beside the to-dos, not among them; no 토스 앱 환전 to-do', async () => {
    serve(healthLive);
    renderApp('/health');
    const card = await screen.findByRole('region', { name: '원화 · 달러' });
    expect(within(card).getByText(SUGGESTION)).toBeInTheDocument();
    expect(within(card).getByText(NEW_MONEY)).toBeInTheDocument();
    const todos = screen.getAllByRole('article');
    expect(todos).toHaveLength(2); // the mismatch and the link
    for (const todo of todos) expect(todo).not.toHaveTextContent(/환전/);
    expect(card.closest('article')).toBeNull();
  });
});
