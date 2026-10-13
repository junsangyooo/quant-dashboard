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

const SUGGESTION = '약 1,500,000원을 달러로 바꾸면 50:50';
const MIX = '지금 한국 61.4 : 미국 38.6 · 토스 앱에서 바꾸면 다음 거래일부터 사요';
const NEW_MONEY = '새로 들어온 돈 3,000,000원 · 다음 거래일 08:30부터 써요';

describe('계획 · 실전 (plan.live-mix)', () => {
  it("the rule card says '환전 제안' and how much; 예정 says when today's money is used", async () => {
    renderState(planLiveMix, '/plan');
    const card = await screen.findByRole('article', { name: '지수 반반' });
    expect(within(card).getByText('환전 제안')).toBeVisible();
    expect(within(card).getByText(SUGGESTION)).toBeVisible();
    expect(within(card).getByText(MIX)).toBeVisible();
    // The other rule has nothing to say about the currencies.
    const other = screen.getByRole('article', { name: '[예시] 종목 모멘텀' });
    expect(within(other).queryByText(/바꾸면/)).toBeNull();
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
