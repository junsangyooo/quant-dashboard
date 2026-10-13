import { focusManager } from '@tanstack/react-query';
import { act, fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { configureClient } from '../../src/api/client';
import {
  MODE_WAIT_POLL_MS,
  headerStatusView,
  modeWaitsForSnapshot,
  queryKeys,
  useHeaderStatus,
  useHome,
  useMode,
  useTurnLiveOn,
} from '../../src/api/queries';
import type { HomeResponse, ShellResponse } from '../../src/api/types';
import { ModeChangedChip, OfflineChip } from '../../src/components/State';
import homePaper from '../../src/fixtures/bundles/home.paper';
import modeCancelPending from '../../src/fixtures/bundles/mode.cancel-pending';
import modeLinkOff from '../../src/fixtures/bundles/mode.link-off';
import modeLiveBundle from '../../src/fixtures/bundles/mode.live';
import modePaperBundle from '../../src/fixtures/bundles/mode.paper';
import { fixtureFetch } from '../../src/fixtures/runtime';
import type { FixtureBundle } from '../../src/fixtures/types';
import { answerFrom, renderWithData } from '../helpers';

const paperShell: ShellResponse = homePaper.responses['/api/shell'];
const paperHome: HomeResponse = homePaper.responses['/api/home'];
const liveShell: ShellResponse = {
  ...paperShell,
  mode: 'live',
  liveSince: '2026-09-01T09:00:00+09:00',
};
const liveHome: HomeResponse = { ...paperHome, ledger: 'live', example: false, total: 10_500_000 };

/** Header label, the two chips, and one number slot of SCR-HOME. */
function Probe() {
  const home = useHome();
  const status = useHeaderStatus();
  return (
    <>
      <ModeChangedChip />
      <OfflineChip />
      <p data-testid="status">{status?.label ?? 'skeleton'}</p>
      <p data-testid="total">
        {home.data ? `${home.data.ledger} ${String(home.data.total)}` : 'skeleton'}
      </p>
    </>
  );
}

/** Wraps the bundle's answers so a test can count calls or hold one back. */
function answerVia(
  bundle: FixtureBundle,
  shellPollMs: number,
  hook: (url: string) => Promise<void> | void,
) {
  const base = fixtureFetch(bundle);
  configureClient({
    shellPollMs,
    fetch: async (input, init) => {
      await hook(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url);
      return base(input, init);
    },
  });
}

describe('/api/shell', () => {
  it('polls every 60 s and not in a hidden tab', async () => {
    answerFrom(homePaper);
    const { client } = renderWithData(<Probe />);
    expect(await screen.findByText('paper 10243800')).toBeInTheDocument();
    const observers = client.getQueryCache().find({ queryKey: ['shell'] })?.observers ?? [];
    expect(observers.length).toBeGreaterThan(0);
    for (const observer of observers) {
      expect(observer.options.refetchInterval).toBe(60_000);
      expect(observer.options.refetchIntervalInBackground).toBe(false);
    }
  });

  it('stops polling while hidden and reads again on return', async () => {
    const shellCalls = vi.fn();
    answerVia(homePaper, 20, (url) => {
      if (url === '/api/shell') shellCalls();
    });
    renderWithData(<Probe />);
    await screen.findByText('paper 10243800');
    try {
      act(() => {
        focusManager.setFocused(false);
      });
      const before = shellCalls.mock.calls.length;
      await new Promise((resolve) => setTimeout(resolve, 120));
      expect(shellCalls).toHaveBeenCalledTimes(before);
      act(() => {
        focusManager.setFocused(true);
      });
      await waitFor(() => {
        expect(shellCalls.mock.calls.length).toBeGreaterThan(before);
      });
    } finally {
      focusManager.setFocused(undefined);
    }
  });
});

function ModeProbe() {
  const mode = useMode();
  return <p data-testid="mode">{mode.data?.mode ?? 'skeleton'}</p>;
}

describe('/api/mode', () => {
  it('asks again each minute only while turning on waits on a fresh account picture', async () => {
    expect(modeWaitsForSnapshot(modeLinkOff.responses['/api/mode'])).toBe(true);
    expect(modeWaitsForSnapshot(modeCancelPending.responses['/api/mode'])).toBe(true);
    expect(modeWaitsForSnapshot(modePaperBundle.responses['/api/mode'])).toBe(false);
    expect(modeWaitsForSnapshot(modeLiveBundle.responses['/api/mode'])).toBe(false);
    answerFrom(modeLinkOff);
    const { client } = renderWithData(<ModeProbe />);
    expect(await screen.findByText('paper')).toBeInTheDocument();
    const query = client.getQueryCache().find({ queryKey: queryKeys.mode });
    if (!query) throw new Error('no mode query');
    const options = query.observers[0]?.options;
    const interval = options?.refetchInterval;
    expect(typeof interval === 'function' ? interval(query) : interval).toBe(MODE_WAIT_POLL_MS);
    expect(options?.refetchIntervalInBackground).toBe(false);
  });
});

describe('mode switched on another device', () => {
  it('shows the chip and a skeleton until the new ledger loads', async () => {
    const switched: ShellResponse = {
      ...paperShell,
      now: '2026-10-07T16:11:30+09:00',
      modeChangedAt: '2026-10-07T16:11:00+09:00',
    };
    const bundle: FixtureBundle = {
      id: 'home.other-device',
      now: switched.now,
      responses: {
        '/api/shell': [liveShell, switched],
        '/api/home?ledger=live': liveHome,
        '/api/home?ledger=paper': paperHome,
      },
    };
    let release: () => void = () => undefined;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    answerVia(bundle, 100, (url) => (url.startsWith('/api/home?ledger=paper') ? held : undefined));

    renderWithData(<Probe />);
    expect(await screen.findByText('live 10500000')).toBeInTheDocument();
    expect(
      await screen.findByText('16:11 다른 기기에서 실전 → 모의투자로 바뀜'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('total')).toHaveTextContent('skeleton');

    release();
    expect(await screen.findByText('paper 10243800')).toBeInTheDocument();
    expect(screen.getByText('16:11 다른 기기에서 실전 → 모의투자로 바뀜')).toBeInTheDocument();
  });

  it('does not flag our own switch', async () => {
    const turnedOn: ShellResponse = { ...liveShell, modeChangedAt: paperShell.now };
    const bundle: FixtureBundle = {
      id: 'mode.turning-on',
      now: paperShell.now,
      responses: {
        '/api/shell': [paperShell, turnedOn],
        '/api/home?ledger=paper': paperHome,
        '/api/home?ledger=live': liveHome,
        'POST /api/mode/live': { mode: 'live' },
      },
    };
    const base = fixtureFetch(bundle);
    const sent: unknown[] = [];
    configureClient({
      fetch: (input, init) => {
        if (init?.method === 'POST' && typeof init.body === 'string')
          sent.push(JSON.parse(init.body));
        return base(input, init);
      },
    });
    function TurnOn() {
      const turnOn = useTurnLiveOn();
      return (
        <button
          type="button"
          onClick={() => {
            turnOn.mutate({ pin: '123456', previewHash: 'h1' });
          }}
        >
          켜기
        </button>
      );
    }

    renderWithData(
      <>
        <Probe />
        <TurnOn />
      </>,
    );
    expect(await screen.findByText('paper 10243800')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '켜기' }));
    expect(await screen.findByText('live 10500000')).toBeInTheDocument();
    expect(sent).toEqual([{ pin: '123456', previewHash: 'h1', confirm: true }]);
    expect(screen.queryByText(/다른 기기에서/)).not.toBeInTheDocument();
  });
});

describe('no connection', () => {
  it('says 연결 안 됨 and keeps the last numbers', async () => {
    const bundle: FixtureBundle = {
      id: 'home.offline',
      now: paperShell.now,
      shellPollMs: 50,
      responses: { '/api/shell': [paperShell, { $network: 'down' }], '/api/home': paperHome },
    };
    answerFrom(bundle);
    renderWithData(<Probe />);
    expect(await screen.findByText('paper 10243800')).toBeInTheDocument();
    expect(screen.getByTestId('status')).toHaveTextContent('정상 · 08:30 확인');

    expect(await screen.findByText('16:10 불러온 값 · 연결 안 됨')).toBeInTheDocument();
    expect(screen.getByTestId('status')).toHaveTextContent('연결 안 됨');
    expect(screen.getByTestId('total')).toHaveTextContent('paper 10243800');
  });
});

describe('header status', () => {
  const at = '2026-10-07T08:30:00+09:00';
  const shell = (status: ShellResponse['status']): ShellResponse => ({ ...paperShell, status });

  it.each([
    [{ kind: 'ok', lastCheckAt: at }, 'ok', '정상 · 08:30 확인'],
    [{ kind: 'before-first', firstCheckAt: at }, 'ok', '첫 확인 전'],
    [{ kind: 'check', count: 2 }, 'check', '점검 2'],
    [{ kind: 'check-failed', at }, 'error', '확인 실패'],
    [{ kind: 'todo', count: 1 }, 'error', '직접 할 일 1'],
    [{ kind: 'cancel-failed', count: 1 }, 'error', '취소 안 됨 1'],
  ] as const)('%o → %s %s', (status, chip, label) => {
    expect(headerStatusView(shell(status), 'online')).toEqual({ status: chip, label });
  });

  it('marks the cases with no answer', () => {
    expect(headerStatusView(paperShell, 'offline')).toEqual({
      status: 'unknown',
      label: '연결 안 됨',
    });
    expect(headerStatusView(paperShell, 'unknown')).toEqual({
      status: 'unknown',
      label: '확인 불가',
    });
    expect(headerStatusView(undefined, 'online')).toBeNull();
  });
});
