// SCR-PIN 입장 — 기획 §5 완료 조건 (lines 370–376) and the spec's states.
import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { copy } from '../../src/copy';
import { pinCopy } from '../../src/copy/pin';
import pinEntering from '../../src/fixtures/bundles/pin.entering';
import pinError from '../../src/fixtures/bundles/pin.error';
import pinGlobal from '../../src/fixtures/bundles/pin.global-lock';
import pinHold from '../../src/fixtures/bundles/pin.hold';
import pinLoading from '../../src/fixtures/bundles/pin.loading';
import pinLocked from '../../src/fixtures/bundles/pin.locked';
import pinNoPin from '../../src/fixtures/bundles/pin.no-pin';
import healthPermission from '../../src/fixtures/bundles/health.permission';
import { renderApp, serve, writes } from './ops';

const AT_1610 = new Date('2026-10-07T16:10:00+09:00');

function pinInput() {
  return screen.getByLabelText(copy.pin.prompt);
}

async function typeOnKeypad(digits: string) {
  const user = userEvent.setup();
  const pad = screen.getByRole('group', { name: pinCopy.keypad });
  for (const d of digits) await user.click(within(pad).getByRole('button', { name: d }));
}

afterEach(() => {
  vi.useRealTimers();
});

describe('입장 (SCR-PIN)', () => {
  it('shows only the wordmark, PIN 6자리, six cells, the keypad and 잊었을 때 — no figure, no request', () => {
    const calls = serve(pinEntering);
    const { container } = renderApp('/pin');
    expect(screen.getByRole('heading', { level: 1, name: copy.wordmark })).toBeInTheDocument();
    expect(screen.getByText(copy.pin.prompt)).toBeInTheDocument();
    expect(container.querySelectorAll('[class*="pinCell"]')).toHaveLength(6);
    const pad = screen.getByRole('group', { name: pinCopy.keypad });
    for (const d of '0123456789')
      expect(within(pad).getByRole('button', { name: d })).toBeEnabled();
    expect(within(pad).getByRole('button', { name: copy.pin.delete })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: copy.pin.forgot })).toBeInTheDocument();
    // 계좌 숫자 0개: no money, no %, and nothing requested before entry.
    expect(document.body.textContent).not.toMatch(/원|%|\$/);
    expect(calls).toEqual([]);
    expect(screen.queryByRole('banner')).toBeNull();
  });

  it('marks the next cell while entering (3 digits: 3 dots, the 4th outlined)', async () => {
    serve(pinEntering);
    const { container } = renderApp('/pin');
    await typeOnKeypad('123');
    const cells = [...container.querySelectorAll('[class*="pinCell"]')];
    expect(cells.filter((c) => c.querySelector('[class*="pinDot"]'))).toHaveLength(3);
    expect(cells[3]?.className).toContain('pin-focus');
    expect(pinInput()).toHaveValue('123');
  });

  it('submits by itself on the sixth digit and returns to safeNext(next)', async () => {
    const calls = serve(pinEntering);
    const { router } = renderApp(`/pin?next=${encodeURIComponent('/day/2026-08-21?ledger=paper')}`);
    await typeOnKeypad('123456');
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/day/2026-08-21');
    });
    expect(router.state.location.search).toBe('?ledger=paper');
    expect(writes(calls)).toEqual([
      { method: 'POST', path: '/api/auth/pin', body: { pin: '123456' } },
    ]);
  });

  it('accepts typed digits (keyboard) and ignores anything else', async () => {
    const calls = serve(pinEntering);
    const { router } = renderApp('/pin');
    const user = userEvent.setup();
    await user.click(pinInput());
    await user.keyboard('12a3');
    expect(pinInput()).toHaveValue('123');
    await user.keyboard('{Backspace}');
    expect(pinInput()).toHaveValue('12');
    await user.keyboard('3456');
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/');
    });
    expect(writes(calls)[0]?.body).toEqual({ pin: '123456' });
  });

  it.each([
    ['https://evil.example/x', '/'],
    ['//evil.example', '/'],
    ['/pin?next=/pin', '/'],
    ['/health', '/health'],
  ])('returns to safeNext(%s) ?? / → %s', async (next, expected) => {
    serve(pinEntering);
    const { router } = renderApp(`/pin?next=${encodeURIComponent(next)}`);
    await typeOnKeypad('111111');
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(expected);
    });
  });

  it('clears the six cells with red borders and shows the tries left on a wrong PIN', async () => {
    serve(pinError);
    const { container } = renderApp('/pin');
    await typeOnKeypad('000000');
    expect(await screen.findByText('PIN이 맞지 않아요 · 남은 시도 2회')).toBeInTheDocument();
    expect(pinInput()).toHaveValue('');
    expect(pinInput()).toHaveAttribute('aria-invalid', 'true');
    const cells = [...container.querySelectorAll('[class*="pinCell"]')];
    expect(cells.every((c) => c.className.includes('pin-error'))).toBe(true);
    // The keypad still works ('키패드는 그대로 쓸 수 있음').
    expect(screen.getByRole('button', { name: '1' })).toBeEnabled();
  });

  it('counts down and locks at the fifth failure', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(AT_1610);
    serve(pinError);
    renderApp('/pin');
    await typeOnKeypad('000000');
    await screen.findByText(pinCopy.wrong(2));
    await typeOnKeypad('000000');
    await screen.findByText(pinCopy.wrong(1));
    await typeOnKeypad('000000');
    expect(await screen.findByText('16:40까지 잠김 · 이 접속 위치')).toBeInTheDocument();
  });

  it('locks this place: lock line, the note, closed cells and a keypad that cannot be pressed', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(AT_1610);
    serve(pinLocked);
    renderApp('/pin');
    await typeOnKeypad('123456');
    expect(await screen.findByText('16:40까지 잠김 · 이 접속 위치')).toBeInTheDocument();
    expect(
      screen.getByText('이미 열린 기기는 그대로 써요 · 실전 끄기도 그 기기에서 돼요'),
    ).toBeInTheDocument();
    expect(pinInput()).toBeDisabled();
    const pad = screen.getByRole('group', { name: pinCopy.keypad });
    for (const key of within(pad).getAllByRole('button')) expect(key).toBeDisabled();
  });

  it('opens again by itself when the lock time passes', async () => {
    vi.useFakeTimers({
      toFake: ['Date', 'setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'],
    });
    vi.setSystemTime(AT_1610);
    serve(pinLocked);
    renderApp('/pin');
    const pad = screen.getByRole('group', { name: pinCopy.keypad });
    for (const d of '123456') {
      act(() => {
        within(pad).getByRole('button', { name: d }).click();
      });
    }
    // React Query hands results over on a timer; let the 403 locked land first.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    expect(screen.getByText('16:40까지 잠김 · 이 접속 위치')).toBeInTheDocument();
    expect(pinInput()).toBeDisabled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30 * 60_000 + 1_000);
    });
    expect(pinInput()).toBeEnabled();
    expect(screen.queryByText('16:40까지 잠김 · 이 접속 위치')).toBeNull();
  });

  it('shows the global cap with a clock and the minutes left', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(AT_1610);
    serve(pinGlobal);
    renderApp('/pin');
    await typeOnKeypad('123456');
    expect(await screen.findByText('시도가 많아요 · 42분 뒤 다시')).toBeInTheDocument();
    expect(screen.getByText(pinCopy.lockedNote)).toBeInTheDocument();
    expect(pinInput()).toBeDisabled();
  });

  it('closes until the server unlocks it after a day of wrong PINs (scope hold, no end time)', async () => {
    vi.useFakeTimers({
      toFake: ['Date', 'setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'],
    });
    vi.setSystemTime(AT_1610);
    serve(pinHold);
    renderApp('/pin');
    const pad = screen.getByRole('group', { name: pinCopy.keypad });
    for (const d of '123456') {
      act(() => {
        within(pad).getByRole('button', { name: d }).click();
      });
    }
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    expect(screen.getByText(pinCopy.lockedHold)).toBeInTheDocument();
    expect(screen.getByText(pinCopy.lockedHoldHelp)).toBeInTheDocument();
    expect(screen.getByText('python -m autotrade.jobs unlock')).toBeInTheDocument();
    expect(screen.getByText(pinCopy.lockedNote)).toBeInTheDocument();
    expect(pinInput()).toBeDisabled();
    expect(screen.getByRole('button', { name: '1' })).toBeDisabled();
    // No time on it: a day later it is still closed (only the server's unlock opens it).
    await act(async () => {
      await vi.advanceTimersByTimeAsync(24 * 60 * 60_000);
    });
    expect(pinInput()).toBeDisabled();
    expect(screen.getByText(pinCopy.lockedHold)).toBeInTheDocument();
  });

  it('shows a failure, not a silent page, for a lock without its time', async () => {
    serve({
      ...pinHold,
      id: 'pin.hold',
      responses: {
        'POST /api/auth/pin': { $status: 403, $body: { error: 'locked', scope: 'ip' } },
      },
    });
    renderApp('/pin');
    await typeOnKeypad('123456');
    expect(await screen.findByText(pinCopy.failed)).toBeInTheDocument();
    expect(pinInput()).toBeEnabled();
  });

  it('explains that the first PIN is set on the server when there is none (403 no-pin)', async () => {
    serve(pinNoPin);
    renderApp('/pin');
    await typeOnKeypad('123456');
    expect(await screen.findByText(pinCopy.noPin)).toBeInTheDocument();
    expect(screen.getByText(pinCopy.noPinHelp)).toBeInTheDocument();
    expect(screen.getByText(pinCopy.noPinCommand)).toBeInTheDocument();
    expect(pinInput()).toBeDisabled();
    expect(screen.getByRole('button', { name: '1' })).toBeDisabled();
  });

  it('keeps the six dots, closes the field and keypad and spins while the PIN is checked', async () => {
    serve(pinLoading);
    const { container } = renderApp('/pin');
    await typeOnKeypad('123456');
    expect(await screen.findByText(pinCopy.checking)).toBeInTheDocument();
    expect(container.querySelectorAll('[class*="pinDot"]')).toHaveLength(6);
    expect(pinInput()).toBeDisabled();
    expect(screen.getByRole('button', { name: '1' })).toBeDisabled();
  });

  it('folds out the recovery line under 잊었을 때', async () => {
    serve(pinEntering);
    renderApp('/pin');
    const toggle = screen.getByRole('button', { name: copy.pin.forgot });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByText(copy.pin.forgotHelp)).not.toBeVisible();
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('PIN을 잊었다면 서버에서 다시 정해요 · Claude에게 요청')).toBeVisible();
  });

  it('brings a page without a session to /pin?next= and back to it after entry', async () => {
    serve(healthPermission);
    const { router } = renderApp('/health');
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/pin');
    });
    expect(new URLSearchParams(router.state.location.search).get('next')).toBe('/health');
    await typeOnKeypad('123456');
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/health');
    });
    expect(await screen.findByRole('heading', { level: 2, name: '정상' })).toBeInTheDocument();
  });
});
