// SCR-MODE 모의투자·실전 — 기획 §5 완료 조건 (lines 785–798) and the spec's states.
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { copy } from '../../src/copy';
import { modeCopy } from '../../src/copy/mode';
import type { ModeResponse } from '../../src/api/types';
import modeBlocked from '../../src/fixtures/bundles/mode.blocked';
import modeEmpty from '../../src/fixtures/bundles/mode.empty';
import modeLive from '../../src/fixtures/bundles/mode.live';
import modeLiveStale from '../../src/fixtures/bundles/mode.live-stale';
import modeLoading from '../../src/fixtures/bundles/mode.loading';
import modeNotAvailable from '../../src/fixtures/bundles/mode.live-not-available';
import modeOffConfirm from '../../src/fixtures/bundles/mode.off-confirm';
import modeOffFailed from '../../src/fixtures/bundles/mode.off-failed';
import modePaper from '../../src/fixtures/bundles/mode.paper';
import modePreviewChanged from '../../src/fixtures/bundles/mode.preview-changed';
import modeShort from '../../src/fixtures/bundles/mode.short';
import modeTurningOn from '../../src/fixtures/bundles/mode.turning-on';
import {
  LIVE_PENDING_BUY,
  NOW,
  PREFLIGHT_OK,
  TWO_LEDGERS,
  modePaper as paperMode,
  shell,
} from '../../src/fixtures/ops';
import type { FixtureBundle } from '../../src/fixtures/types';
import { renderApp, serve, writes } from './ops';

const TURN_ON = modeCopy.turnOn;

function region(name: string) {
  return screen.getByRole('region', { name });
}

async function openMode(bundle: FixtureBundle) {
  const calls = serve(bundle);
  const view = renderApp('/mode');
  await screen.findByRole('radiogroup', { name: modeCopy.segment });
  return { calls, ...view };
}

async function fillTurnOn(pin = '123456') {
  const user = userEvent.setup();
  const card = region(TURN_ON.title);
  await user.click(within(card).getByRole('checkbox', { name: TURN_ON.confirm }));
  await user.type(within(card).getByLabelText(TURN_ON.pin), pin);
  return { user, card };
}

function sectionOrder(): string[] {
  const names: string[] = [
    modeCopy.twoLedgers.title,
    modeCopy.performance.title,
    modeCopy.preflight.title,
    modeCopy.preview.title,
    TURN_ON.title,
  ];
  return [...document.querySelectorAll('main h2')]
    .map((h) => h.textContent)
    .filter((t) => names.includes(t));
}

describe('모의투자·실전 (SCR-MODE)', () => {
  it('shows the paper segment and line, then 성적 → 점검 → 미리보기 → 켜기', async () => {
    await openMode(modePaper);
    expect(screen.getByRole('heading', { level: 1, name: copy.pages.mode })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: '모의투자' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByText('모의투자 · 실제 돈은 안 움직여요')).toBeInTheDocument();
    expect(sectionOrder()).toEqual([
      modeCopy.performance.title,
      modeCopy.preflight.title,
      modeCopy.preview.title,
      TURN_ON.title,
    ]);
  });

  it('shows the first order stage by stage with markets, quantities, 약 amounts, times and the basis chips', async () => {
    await openMode(modePaper);
    const preview = region(modeCopy.preview.title);
    expect(within(preview).getByText('실계좌')).toBeInTheDocument();
    expect(within(preview).getByText('지금 · 원화 현금 10,000,000원')).toBeInTheDocument();
    expect(within(preview).getByText('목표 · 규칙대로')).toBeInTheDocument();
    for (const name of ['KOSPI200', 'S&P 500', '삼성전자', 'NVDA', 'BTC']) {
      expect(within(preview).getByText(name)).toBeInTheDocument();
    }
    const legs = within(preview)
      .getAllByRole('listitem')
      .filter((li) => li.classList.contains('leg'));
    expect(legs).toHaveLength(2); // 매도 0건 → hidden
    const [fx, buy] = legs;
    expect(fx).toHaveTextContent('환전 · 원→달러');
    expect(fx).toHaveTextContent('10/8 09:10 예상');
    expect(fx).toHaveTextContent('약 4,705,000원');
    expect(fx).toHaveTextContent('→ 약 $3,403');
    expect(fx).toHaveTextContent('환율 1,382.4원');
    expect(buy).toHaveTextContent('매수 · 4건');
    expect(buy).toHaveTextContent('한국 09:05 · 미국 22:30');
    expect(buy).toHaveTextContent('한국 · KOSPI200 ETF 110주 · 삼성전자 14주');
    expect(buy).toHaveTextContent('미국 · S&P 500 ETF 46주 · NVDA 3주');
    expect(buy).toHaveTextContent('약 4,775,700원 · 약 $3,400');
    expect(within(preview).queryByText(/매도 ·/)).toBeNull();
    for (const chip of ['잔고 08:30', '현재가 16:00', '환율 1,382.4원 16:00']) {
      expect(within(preview).getByText(chip)).toBeInTheDocument();
    }
  });

  it('leaves the outside-Toss coin out of the preview with its own line', async () => {
    await openMode(modePaper);
    const preview = region(modeCopy.preview.title);
    expect(
      within(preview).getByText('BTC 0.0027 · 약 355,000원 · 토스 밖 계좌라 이 미리보기에 없어요'),
    ).toBeInTheDocument();
    const legs = within(preview)
      .getAllByRole('listitem')
      .filter((li) => li.classList.contains('leg'));
    expect(legs.length).toBeGreaterThan(0);
    for (const leg of legs) expect(leg.textContent).not.toContain('BTC');
  });

  it('keeps 실전 켜기 disabled until the box is checked and six digits are in', async () => {
    await openMode(modePaper);
    const user = userEvent.setup();
    const card = region(TURN_ON.title);
    const button = within(card).getByRole('button', { name: TURN_ON.button });
    expect(button).toBeDisabled();
    await user.type(within(card).getByLabelText(TURN_ON.pin), '123456');
    expect(button).toBeDisabled();
    await user.clear(within(card).getByLabelText(TURN_ON.pin));
    await user.click(within(card).getByRole('checkbox', { name: TURN_ON.confirm }));
    expect(button).toBeDisabled();
    await user.type(within(card).getByLabelText(TURN_ON.pin), '12345');
    expect(button).toBeDisabled();
    await user.type(within(card).getByLabelText(TURN_ON.pin), '6');
    expect(button).toBeEnabled();
  });

  it('closes the whole 켜기 card when a check fails, counting one cause once', async () => {
    await openMode(modeBlocked);
    expect(sectionOrder()).toEqual([
      modeCopy.preflight.title,
      modeCopy.preview.title,
      TURN_ON.title,
      modeCopy.performance.title,
    ]);
    const checks = region(modeCopy.preflight.title);
    const health = within(checks).getByRole('link', { name: /작동/ });
    expect(health).toHaveAttribute('href', '/health');
    expect(health).toHaveTextContent('점검 1 · 미국 시세 낡음');
    const fresh = within(checks).getByRole('link', { name: /자료 최신/ });
    expect(fresh).toHaveTextContent('미국 시세 10/2 기준 · 위 점검과 같은 원인');
    expect(
      within(region(modeCopy.preview.title)).getByText('첫 주문 계산 안 됨 · 10/7 16:00 조회'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('미국 시세가 다시 들어오면 자동으로 다시 계산해요'),
    ).toBeInTheDocument();
    const card = region(TURN_ON.title);
    expect(within(card).getByRole('checkbox')).toBeDisabled();
    expect(within(card).getByLabelText(TURN_ON.pin)).toBeDisabled();
    expect(within(card).getByRole('button', { name: TURN_ON.button })).toBeDisabled();
    expect(within(card).getByText('점검 1개(미국 시세) 해결 뒤 켤 수 있어요')).toBeInTheDocument();
  });

  it('turns live off without a PIN from a modal whose order is the plan’s buy card', async () => {
    const { calls } = await openMode(modeOffConfirm);
    expect(screen.getByRole('radio', { name: '실전' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByText('실전 9/1부터 · 27일째')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: modeCopy.turnOff.button }));
    const dialog = await screen.findByRole('dialog', { name: modeCopy.turnOff.title });
    expect(within(dialog).getByText(modeCopy.turnOff.cancelOrders)).toBeInTheDocument();
    expect(await within(dialog).findByText('매수 · 미국 · 22:30 대기')).toBeInTheDocument();
    // The same numbers as the plan's pending buy (예시-값표 §2.2).
    expect(LIVE_PENDING_BUY.qty).toBe(2);
    expect(LIVE_PENDING_BUY.amountUsd).toBe(124.8);
    expect(within(dialog).getByText('S&P 500 ETF 2주 · 약 $124.80')).toBeInTheDocument();
    expect(
      await within(dialog).findByText('달러 현금 $125.67은 계좌에 남아요'),
    ).toBeInTheDocument();
    // /api/mode offPreview lists every positive balance; the modal keeps the drawn single line,
    // the currency of the cancelled buy (원화 현금 85,964원 stays unmentioned).
    expect(within(dialog).queryByText(/원화 현금/)).toBeNull();
    expect(within(dialog).getByText('보유 종목은 그대로')).toBeInTheDocument();
    expect(within(dialog).getByText('모의투자는 계속')).toBeInTheDocument();
    expect(within(dialog).queryByLabelText(/PIN/)).toBeNull();
    await userEvent.click(within(dialog).getByRole('button', { name: modeCopy.turnOff.confirm }));
    expect(await screen.findByText('모의투자 · 실계좌 주문은 멈췄어요')).toBeInTheDocument();
    expect(screen.getByText('실전 9/1~10/7 · 16:12에 끔')).toBeInTheDocument();
    expect(writes(calls)).toEqual([{ method: 'POST', path: '/api/mode/paper', body: undefined }]);
  });

  // Focus inside the open modal is checked in the browser (e2e/mode.spec.ts): jsdom's dialog has
  // no focus handling of its own.
  it('cancels the modal with 취소 or Escape', async () => {
    await openMode(modeOffConfirm);
    const user = userEvent.setup();
    const opener = screen.getByRole('button', { name: modeCopy.turnOff.button });
    await user.click(opener);
    const dialog = await screen.findByRole('dialog', { name: modeCopy.turnOff.title });
    await user.click(within(dialog).getByRole('button', { name: modeCopy.turnOff.cancel }));
    expect(dialog).not.toHaveAttribute('open');
    await user.click(opener);
    expect(dialog).toHaveAttribute('open');
    dialog.dispatchEvent(new Event('cancel', { cancelable: true }));
    await waitFor(() => {
      expect(dialog).not.toHaveAttribute('open');
    });
    expect(screen.getByRole('radio', { name: '실전' })).toHaveAttribute('aria-checked', 'true');
  });

  it('shows 바꾸는 중 on the modal button while turning off', async () => {
    await openMode(modeLive);
    await userEvent.click(screen.getByRole('button', { name: modeCopy.turnOff.button }));
    const dialog = await screen.findByRole('dialog', { name: modeCopy.turnOff.title });
    await userEvent.click(within(dialog).getByRole('button', { name: modeCopy.turnOff.confirm }));
    expect(
      await within(dialog).findByRole('button', { name: modeCopy.turnOff.busy }),
    ).toBeInTheDocument();
  });

  it('tells the facts when cancelling failed: 취소 안 됨 1, banner, 모의투자 segment, red card', async () => {
    const { calls } = await openMode(modeOffFailed);
    const header = screen.getByRole('banner');
    expect(await within(header).findByText('취소 안 됨 1')).toBeInTheDocument();
    expect(screen.getByText('모의투자로 바뀜 · 미국 매수 주문 취소 안 됨')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: '모의투자' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByText('모의투자 · 실계좌 주문은 멈췄어요')).toBeInTheDocument();
    const card = region(modeCopy.cancelFailed.title);
    expect(within(card).getByText('매수·미국 S&P 500 ETF 2주 · 약 $124.80')).toBeInTheDocument();
    expect(within(card).getByText('22:30 대기')).toBeInTheDocument();
    expect(within(card).getByText('그대로 두면 22:30에 체결될 수 있어요')).toBeInTheDocument();
    // The red card comes first; no 켜기 card while an order is left.
    expect(document.querySelector('main h2')?.textContent).toBe(modeCopy.cancelFailed.title);
    expect(screen.queryByRole('region', { name: TURN_ON.title })).toBeNull();
    await userEvent.click(within(card).getByRole('button', { name: modeCopy.cancelFailed.retry }));
    await waitFor(() => {
      expect(screen.queryByRole('region', { name: modeCopy.cancelFailed.title })).toBeNull();
    });
    expect(writes(calls)).toEqual([
      { method: 'POST', path: '/api/mode/cancel-retry', body: undefined },
    ]);
    await waitFor(() => {
      expect(within(header).queryByText('취소 안 됨 1')).toBeNull();
    });
  });

  it('breaks the gap down into three lines that add up to the end difference', async () => {
    await openMode(modeLive);
    const card = region(modeCopy.twoLedgers.title);
    // The heading carries the valuation time the contract now sends (breakdown.valuedAt).
    expect(within(card).getByText('차이 분해 · 9/1부터 · 10/7 16:00')).toBeInTheDocument();
    const b = TWO_LEDGERS.breakdown;
    expect(Math.round((b.fills + b.fees + b.other) * 100)).toBe(Math.round(b.total * 100));
    expect(Math.round((TWO_LEDGERS.endRet.live - TWO_LEDGERS.endRet.paper) * 100)).toBe(
      Math.round(b.total * 100),
    );
    for (const [label, value] of [
      ['체결가', '−0.02%p'],
      ['실제 수수료', '−0.06%p'],
      ['기타 · 1주 단위·시작 시점', '−0.07%p'],
      ['합', '−0.15%p'],
    ] as const) {
      const row = within(card).getByText(label).closest('div');
      expect(row).toHaveTextContent(value);
    }
    for (const text of ['실전 +1.13%', '모의투자 +1.28%', '손대지 않았을 때 +1.75%']) {
      expect(within(card).getByRole('button', { name: text })).toHaveAttribute(
        'aria-pressed',
        'true',
      );
    }
    expect(within(card).getByRole('link', { name: '실전 기록' })).toHaveAttribute(
      'href',
      '/history?ledger=live',
    );
    expect(within(card).getByRole('link', { name: '모의투자 기록' })).toHaveAttribute(
      'href',
      '/history?ledger=paper',
    );
  });

  it('switches lines with the legend chips and units with 금액 | 수익률', async () => {
    await openMode(modeLive);
    const card = region(modeCopy.twoLedgers.title);
    const svg = () => card.querySelector('svg[role="img"]');
    expect(svg()?.querySelectorAll('path')).toHaveLength(3);
    expect(within(card).getByText('+1.5%')).toBeInTheDocument();
    expect(within(card).getByText('0%')).toBeInTheDocument();
    const paper = within(card).getByRole('button', { name: '모의투자 +1.28%' });
    await userEvent.click(paper);
    expect(paper).toHaveAttribute('aria-pressed', 'false');
    expect(svg()?.querySelectorAll('path')).toHaveLength(2);
    await userEvent.click(within(card).getByRole('button', { name: modeCopy.twoLedgers.amount }));
    expect(within(card).getByRole('button', { name: modeCopy.twoLedgers.amount })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(within(card).queryByText('+1.5%')).toBeNull();
    expect(within(card).getAllByText(/만$/).length).toBeGreaterThan(0);
    await userEvent.click(within(card).getByRole('button', { name: copy.chart.tableView }));
    const table = within(card).getByRole('table');
    expect(within(table).getAllByRole('row')).toHaveLength(TWO_LEDGERS.series.length + 1);
    expect(within(table).getByText('10,112,670원')).toBeInTheDocument();
  });

  it('shows the performance tiles like the 기록 summary (71 · 3 · 1 · 13) with the return', async () => {
    await openMode(modePaper);
    const card = region(modeCopy.performance.title);
    expect(within(card).getByText('7/1부터')).toBeInTheDocument();
    const tiles = within(card)
      .getAllByRole('listitem')
      .map((li) => li.textContent);
    expect(tiles).toEqual(['71회확인', '3회리밸런싱', '1회실패', '13건모의 체결']);
    expect(within(card).getByText('+2.44%')).toBeInTheDocument();
    expect(within(card).getByText('+243,800원')).toBeInTheDocument();
    expect(within(card).getByText('손대지 않았을 때 +3.59%')).toBeInTheDocument();
    expect(within(card).getByText('수수료 반영 · 세금 미포함')).toBeInTheDocument();
    expect(within(card).getByRole('link', { name: '모의투자 기록' })).toHaveAttribute(
      'href',
      '/history?ledger=paper',
    );
  });

  it('shows 기간 짧음 · 30거래일부터 수익률 instead of a return before 30 trading days, without blocking', async () => {
    await openMode(modeShort);
    const card = region(modeCopy.performance.title);
    expect(
      within(card)
        .getAllByRole('listitem')
        .map((li) => li.textContent),
    ).toEqual(['12회확인', '0회리밸런싱', '0회실패', '6건모의 체결']);
    expect(within(card).getByText('기간 짧음 · 30거래일부터 수익률')).toBeInTheDocument();
    expect(
      within(card).getByText('확인 12회 · 수익률은 30거래일이 지나면 보여요'),
    ).toBeInTheDocument();
    expect(within(card).queryByText(/%$/)).toBeNull();
  });

  it('does not block turning on for a short record', async () => {
    const short = {
      ...modePaper,
      responses: {
        ...modePaper.responses,
        '/api/mode': paperMode({ performance: modeShort.responses['/api/mode'].performance }),
      },
    } satisfies FixtureBundle;
    await openMode(short);
    await fillTurnOn();
    expect(
      within(region(TURN_ON.title)).getByRole('button', { name: TURN_ON.button }),
    ).toBeEnabled();
  });

  it('warns but does not block when no device receives push', async () => {
    const preflight: NonNullable<ModeResponse['preflight']> = PREFLIGHT_OK.map((row) =>
      row.id === 'push' ? { id: 'push', ok: true, warn: true, facts: { devices: 0 } } : row,
    );
    const bundle = {
      ...modePaper,
      responses: { ...modePaper.responses, '/api/mode': paperMode({ preflight }) },
    } satisfies FixtureBundle;
    await openMode(bundle);
    const row = within(region(modeCopy.preflight.title)).getByRole('link', {
      name: /알림 받을 기기/,
    });
    expect(row).toHaveTextContent('0대 · 알림을 받을 기기가 없어요');
    expect(row.querySelector('[class*="tone-warn"]')).not.toBeNull();
    await fillTurnOn();
    expect(
      within(region(TURN_ON.title)).getByRole('button', { name: TURN_ON.button }),
    ).toBeEnabled();
  });

  it('turns on with the PIN, confirm and the preview hash; shows 바꾸는 중 while it runs', async () => {
    const { calls } = await openMode(modeTurningOn);
    const { user, card } = await fillTurnOn('482915');
    await user.click(within(card).getByRole('button', { name: TURN_ON.button }));
    expect(await within(card).findByRole('button', { name: TURN_ON.busy })).toBeDisabled();
    expect(within(card).getByText(TURN_ON.busyNote)).toBeInTheDocument();
    expect(within(card).getByRole('checkbox')).toBeChecked();
    expect(within(card).getByLabelText(TURN_ON.pin)).toHaveValue('');
    expect(writes(calls)).toEqual([
      {
        method: 'POST',
        path: '/api/mode/live',
        body: { pin: '482915', previewHash: 'preview-20261007-1600', confirm: true },
      },
    ]);
  });

  it('shows the 1단계 refusal (409 blocked · live-not-available) under the button', async () => {
    await openMode(modePaper);
    const { user, card } = await fillTurnOn();
    await user.click(within(card).getByRole('button', { name: TURN_ON.button }));
    expect(await within(card).findByText('켜지 않았어요 · 토스 주문 연결 전')).toBeInTheDocument();
    expect(within(card).getByLabelText(TURN_ON.pin)).toHaveValue('');
    expect(screen.getByRole('radio', { name: '모의투자' })).toHaveAttribute('aria-checked', 'true');
  });

  it('closes the 켜기 card in phase 1 (canTurnOn live-not-available)', async () => {
    await openMode(modeNotAvailable);
    const card = region(TURN_ON.title);
    expect(within(card).getByText('토스 주문 연결 뒤 켤 수 있어요')).toBeInTheDocument();
    expect(within(card).getByRole('button', { name: TURN_ON.button })).toBeDisabled();
    expect(screen.queryByRole('region', { name: modeCopy.preflight.title })).toBeNull();
    expect(screen.queryByRole('region', { name: modeCopy.preview.title })).toBeNull();
  });

  it('replaces the preview and unchecks when the recomputed amount moved (409 preview-changed)', async () => {
    await openMode(modePreviewChanged);
    const { user, card } = await fillTurnOn();
    await user.click(within(card).getByRole('button', { name: TURN_ON.button }));
    const preview = region(modeCopy.preview.title);
    expect(await within(preview).findByText('16:10 다시 계산 · 금액 바뀜')).toBeInTheDocument();
    expect(within(preview).getByText('→ 약 $3,341')).toBeInTheDocument();
    expect(within(preview).getByText('환율 1,401.2원 16:10')).toBeInTheDocument();
    expect(preview).toHaveTextContent('미국 · S&P 500 ETF 45주 · NVDA 3주');
    expect(within(card).getByRole('checkbox')).not.toBeChecked();
    expect(within(card).getByLabelText(TURN_ON.pin)).toHaveValue('');
  });

  it('scrolls to the 켜기 card when the 실전 cell is chosen in paper mode, without switching', async () => {
    await openMode(modePaper);
    await userEvent.click(screen.getByRole('radio', { name: '실전' }));
    expect(screen.getByRole('radio', { name: '모의투자' })).toHaveAttribute('aria-checked', 'true');
    expect(within(region(TURN_ON.title)).getByRole('checkbox')).toHaveFocus();
  });

  it('shows the live layout: period chip, two ledgers, 성적, the red 실전 끄기 and no 켜기 parts', async () => {
    await openMode(modeLive);
    expect(screen.getByText('실전 · 규칙이 내는 주문이 실계좌로 나가요')).toBeInTheDocument();
    expect(sectionOrder()).toEqual([modeCopy.twoLedgers.title, modeCopy.performance.title]);
    expect(screen.getByRole('button', { name: modeCopy.turnOff.button })).toBeInTheDocument();
    expect(screen.getByText(modeCopy.turnOff.note)).toBeInTheDocument();
    // The two-ledger card carries the links; 성적 has none.
    expect(within(region(modeCopy.performance.title)).queryByRole('link')).toBeNull();
  });

  it('shows only the shared banner when data goes stale while live (no 점검 section)', async () => {
    await openMode(modeLiveStale);
    expect(
      await screen.findByText('미국 시세 10/2 기준 · 2거래일째 갱신 없음'),
    ).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: modeCopy.preflight.title })).toBeNull();
  });

  it('shows the empty record before the first paper check', async () => {
    await openMode(modeEmpty);
    expect(
      await screen.findByText('아직 모의투자 기록 없음 · 첫 확인 7/1(수) 08:30'),
    ).toBeInTheDocument();
  });

  it('shows skeletons while the mode loads', () => {
    serve(modeLoading);
    renderApp('/mode');
    expect(document.querySelector('[aria-busy="true"]')).not.toBeNull();
    expect(screen.queryByRole('radiogroup')).toBeNull();
  });

  it('has no subtraction sentence and no 모의와 비교 wording', async () => {
    for (const bundle of [modePaper, modeLive, modeOffFailed, modeBlocked]) {
      serve(bundle);
      const view = renderApp('/mode');
      await screen.findByRole('radiogroup', { name: modeCopy.segment });
      const text = document.querySelector('main')?.textContent ?? '';
      expect(text).not.toContain('모의와 비교');
      expect(text).not.toMatch(/실전\s*[−-]\s*모의|모의투자\s*[−-]\s*실전|빼면|뺀 값/);
      view.unmount();
    }
  });

  it('answers from the fixture clock (shell now)', () => {
    expect(shell().now).toBe(NOW);
  });
});
