// SCR-ACCOUNT 설정 — 기획 §5 완료 조건 (lines 839–848) and the spec's states.
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { copy } from '../../src/copy';
import { accountCopy } from '../../src/copy/account';
import type { AccountResponse, NotifyEvent } from '../../src/api/types';
import accountDefault from '../../src/fixtures/bundles/account.default';
import accountEmpty from '../../src/fixtures/bundles/account.empty';
import accountError from '../../src/fixtures/bundles/account.error';
import accountLoading from '../../src/fixtures/bundles/account.loading';
import accountNoPush from '../../src/fixtures/bundles/account.no-push';
import accountPinError from '../../src/fixtures/bundles/account.pin-error';
import accountPushNotReady from '../../src/fixtures/bundles/account.push-not-ready';
import { account } from '../../src/fixtures/ops';
import type { FixtureBundle } from '../../src/fixtures/types';
import { renderApp, serve, writes } from './ops';

const N = accountCopy.notifications;

function notifications() {
  return screen.getByRole('region', { name: N.title });
}

function eventSwitch(name: string) {
  return within(notifications()).getByRole('switch', { name });
}

async function open(bundle: FixtureBundle) {
  const calls = serve(bundle);
  const view = renderApp('/account');
  await screen.findByRole('region', { name: N.title });
  return { calls, ...view };
}

/** A browser with web push (Notification · PushManager · service worker) and no worker yet. */
function stubPushBrowser(answer: NotificationPermission = 'granted') {
  const requestPermission = vi.fn(() => Promise.resolve(answer));
  vi.stubGlobal(
    'Notification',
    Object.assign(vi.fn(), { permission: 'default', requestPermission }),
  );
  vi.stubGlobal('PushManager', vi.fn());
  Object.defineProperty(navigator, 'serviceWorker', {
    configurable: true,
    value: { getRegistration: () => Promise.resolve(undefined) },
  });
  return requestPermission;
}

afterEach(() => {
  vi.unstubAllGlobals();
  Reflect.deleteProperty(navigator, 'serviceWorker');
});

describe('설정 (SCR-ACCOUNT)', () => {
  it('has ‹ 설정 and the PIN, 기기 and 알림 cards in that order', async () => {
    await open(accountDefault);
    expect(screen.getByRole('heading', { level: 1, name: copy.pages.account })).toBeInTheDocument();
    const order = [...document.querySelectorAll('main section')].map(
      (s) => s.getAttribute('aria-label') ?? s.querySelector('h2')?.textContent,
    );
    expect(order).toEqual([accountCopy.pin.title, accountCopy.devices.title, N.title]);
  });

  it('starts with six events on and 확인 누락 · 리밸런싱 예고 · 입출금·직접 매매 off', async () => {
    await open(accountDefault);
    expect(within(notifications()).getByText('받을 사건 · 처음부터 6개 켜짐')).toBeInTheDocument();
    for (const name of [
      '확인 실패',
      '자료 낡음',
      '주간 정상 요약',
      '실전 체결',
      'PIN 실패 급증',
      '토스 연결 만료 예정',
    ]) {
      expect(eventSwitch(name)).toHaveAttribute('aria-checked', 'true');
    }
    for (const name of ['확인 누락', '리밸런싱 예고', '입출금·직접 매매']) {
      expect(eventSwitch(name)).toHaveAttribute('aria-checked', 'false');
    }
  });

  it('locks 확인 실패 with a lock and 일부 실패 포함 · 끌 수 없어요', async () => {
    const { calls } = await open(accountDefault);
    const s = eventSwitch('확인 실패');
    expect(s).toBeDisabled();
    expect(s).toHaveAttribute('aria-checked', 'true');
    const row = s.closest('li');
    expect(row).toHaveTextContent('일부 실패 포함 · 끌 수 없어요');
    expect(within(row as HTMLElement).getByText(N.locked)).toBeInTheDocument();
    await userEvent.click(s);
    expect(writes(calls)).toEqual([]);
  });

  it('keeps 알림에 금액 숨기기 off by default and saves it at once', async () => {
    const { calls } = await open(accountDefault);
    const hide = within(notifications()).getByRole('switch', { name: N.hideAmounts });
    expect(hide).toHaveAttribute('aria-checked', 'false');
    await userEvent.click(hide);
    expect(hide).toHaveAttribute('aria-checked', 'true');
    expect(writes(calls)).toEqual([
      { method: 'PUT', path: '/api/account/notifications', body: { hideAmounts: true } },
    ]);
  });

  it('saves a switch at once and shows [시각] 저장됨', async () => {
    const { calls } = await open(accountDefault);
    expect(within(notifications()).getByText('10/7 15:38 저장됨')).toBeInTheDocument();
    await userEvent.click(eventSwitch('확인 누락'));
    expect(eventSwitch('확인 누락')).toHaveAttribute('aria-checked', 'true');
    expect(await within(notifications()).findByText('10/7 16:10 저장됨')).toBeInTheDocument();
    expect(writes(calls)).toEqual([
      {
        method: 'PUT',
        path: '/api/account/notifications',
        body: { events: { 'check-missed': true } },
      },
    ]);
  });

  it('puts a switch back and says so when saving fails', async () => {
    const bundle = {
      ...accountDefault,
      responses: {
        ...accountDefault.responses,
        'PUT /api/account/notifications': { $status: 500, $body: { error: 'internal' } },
      },
    } satisfies FixtureBundle;
    await open(bundle);
    await userEvent.click(eventSwitch('리밸런싱 예고'));
    expect(await within(notifications()).findByText(N.saveFailed)).toBeInTheDocument();
    expect(eventSwitch('리밸런싱 예고')).toHaveAttribute('aria-checked', 'false');
  });

  it('shows a result row per device after a test push', async () => {
    const { calls } = await open(accountDefault);
    const rows = () =>
      within(notifications())
        .getAllByText(/받음$/)
        .map((el) => el.closest('li')?.textContent);
    expect(rows()).toEqual(['iPhone10/7 15:40 받음', 'MacBook · Chrome10/7 15:40 받음']);
    await userEvent.click(within(notifications()).getByRole('button', { name: N.test }));
    await waitFor(() => {
      expect(rows()).toEqual(['iPhone10/7 16:10 받음', 'MacBook · Chrome10/7 16:10 받음']);
    });
    expect(writes(calls)).toEqual([
      { method: 'POST', path: '/api/account/push/test', body: undefined },
    ]);
  });

  it('says why an iPhone Safari tab cannot receive and how to fix it', async () => {
    await open(accountNoPush);
    const device = within(notifications()).getByRole('switch', { name: N.thisDevice });
    expect(device).toHaveAttribute('aria-checked', 'false');
    expect(
      within(notifications()).getByText('이 기기는 알림을 못 받아요 · Safari 탭'),
    ).toBeInTheDocument();
    expect(
      within(notifications()).getByText('공유 → 홈 화면에 추가 → 앱에서 다시 켜기'),
    ).toBeInTheDocument();
    // Events and the test push stay (other devices).
    expect(eventSwitch('자료 낡음')).toBeEnabled();
    expect(within(notifications()).getByRole('button', { name: N.test })).toBeEnabled();
  });

  it('notes on 주간 정상 요약 that turning it off hides a stopped server', async () => {
    await open(accountDefault);
    expect(eventSwitch('주간 정상 요약').closest('li')).toHaveTextContent(
      '끄면 서버가 멈춰도 알 수 없게 돼요',
    );
  });

  it('shows the this-device switch on with the iPhone line', async () => {
    await open(accountDefault);
    expect(within(notifications()).getByRole('switch', { name: N.thisDevice })).toHaveAttribute(
      'aria-checked',
      'true',
    );
    expect(
      within(notifications()).getByText('iPhone은 홈 화면 앱에서만 받아요'),
    ).toBeInTheDocument();
  });

  it('asks for the browser permission only when the switch is pressed; 501 reads 준비 중', async () => {
    const requestPermission = stubPushBrowser('granted');
    const { calls } = await open(accountEmpty);
    expect(within(notifications()).getByText(N.start)).toBeInTheDocument();
    expect(requestPermission).not.toHaveBeenCalled();
    await userEvent.click(within(notifications()).getByRole('switch', { name: N.thisDevice }));
    expect(requestPermission).toHaveBeenCalledTimes(1);
    expect(await within(notifications()).findByText(N.notReady)).toBeInTheDocument();
    expect(writes(calls)).toEqual([
      { method: 'POST', path: '/api/account/push', body: { subscription: {} } },
    ]);
    expect(within(notifications()).queryByText(N.subscribeFailed)).toBeNull();
  });

  it('turns this device off with DELETE /api/account/push; 501 reads 끄기 준비 중', async () => {
    const notImplemented = {
      $status: 501,
      $body: { error: 'not-implemented', detail: { feature: 'push' } },
    } as const;
    const bundle: FixtureBundle = {
      ...accountDefault,
      responses: { ...accountDefault.responses, 'DELETE /api/account/push': notImplemented },
    };
    const { calls } = await open(bundle);
    await userEvent.click(within(notifications()).getByRole('switch', { name: N.thisDevice }));
    expect(await within(notifications()).findByText(N.offNotReady)).toBeInTheDocument();
    expect(writes(calls)).toEqual([
      { method: 'DELETE', path: '/api/account/push', body: undefined },
    ]);
  });

  it('reads 준비 중 and keeps the switch shut while the server has no web push (available false)', async () => {
    stubPushBrowser();
    const base = account();
    const phase2: FixtureBundle = {
      ...accountEmpty,
      responses: {
        ...accountEmpty.responses,
        '/api/account': {
          ...base,
          notifications: {
            ...base.notifications,
            available: false,
            thisDevice: { supported: true, subscribed: false },
            devices: [],
            testResults: null,
          },
        },
      },
    };
    await open(phase2);
    expect(within(notifications()).getByText(N.notReady)).toBeInTheDocument();
    expect(within(notifications()).getByRole('switch', { name: N.thisDevice })).toBeDisabled();
    expect(within(notifications()).queryByText(N.start)).toBeNull();
  });

  it('says the device cannot receive when the permission is denied', async () => {
    stubPushBrowser('denied');
    const { calls } = await open(accountEmpty);
    await userEvent.click(within(notifications()).getByRole('switch', { name: N.thisDevice }));
    expect(
      await within(notifications()).findByText('이 기기는 알림을 못 받아요 · 알림 차단됨'),
    ).toBeInTheDocument();
    expect(within(notifications()).getByText(N.fix.denied)).toBeInTheDocument();
    expect(writes(calls)).toEqual([]);
  });

  it('shows the 1단계 server (push not built) as 준비 중 on a capable browser', async () => {
    stubPushBrowser();
    await open(accountPushNotReady);
    expect(within(notifications()).getByText(N.notReady)).toBeInTheDocument();
    expect(within(notifications()).getByRole('switch', { name: N.thisDevice })).toBeDisabled();
    expect(within(notifications()).queryByText(/못 받아요/)).toBeNull();
  });

  it('starts from 0 devices: the start line, a disabled test button and no result rows', async () => {
    await open(accountEmpty);
    expect(within(notifications()).getByText(N.start)).toBeInTheDocument();
    expect(within(notifications()).getByRole('button', { name: N.test })).toBeDisabled();
    expect(within(notifications()).queryByText(/받음$/)).toBeNull();
    expect(within(notifications()).queryByText(/저장됨$/)).toBeNull();
  });

  it('adds the AI events in the same pattern when the server lists them', async () => {
    const base = account();
    const ai: AccountResponse = {
      ...base,
      notifications: {
        ...base.notifications,
        events: [
          ...base.notifications.events,
          { id: 'ai-sell', on: true },
          { id: 'ai-buy', on: false },
          { id: 'ai-review', on: false },
        ] satisfies { id: NotifyEvent; on: boolean }[],
      },
    };
    await open({
      ...accountDefault,
      responses: { ...accountDefault.responses, '/api/account': ai },
    });
    expect(within(notifications()).getByText('받을 사건 · 처음부터 7개 켜짐')).toBeInTheDocument();
    expect(eventSwitch('AI 매도 결정')).toHaveAttribute('aria-checked', 'true');
    expect(eventSwitch('AI 매도 결정').closest('li')).toHaveTextContent(
      '실전이면 실제 돈이 움직여요',
    );
    expect(eventSwitch('AI 새 종목 매수')).toHaveAttribute('aria-checked', 'false');
    expect(eventSwitch('AI 점검·발굴 결과')).toHaveAttribute('aria-checked', 'false');
  });

  it('shows this device, its entry time and 이 기기; logout goes to 입장', async () => {
    const { calls, router } = await open(accountDefault);
    const devices = screen.getByRole('region', { name: accountCopy.devices.title });
    expect(within(devices).getByText('iPhone · 홈 화면 앱')).toBeInTheDocument();
    expect(within(devices).getByText('들어온 시각 10/1 08:12')).toBeInTheDocument();
    expect(within(devices).getByText('이 기기')).toBeInTheDocument();
    expect(within(devices).getByText('휴대폰을 잃어버렸을 때')).toBeInTheDocument();
    await userEvent.click(
      within(devices).getByRole('button', { name: accountCopy.devices.logout }),
    );
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/pin');
    });
    expect(writes(calls)).toEqual([{ method: 'POST', path: '/api/auth/logout', body: undefined }]);
  });

  it('logs the other devices out after a confirm modal', async () => {
    const { calls } = await open(accountDefault);
    const devices = screen.getByRole('region', { name: accountCopy.devices.title });
    await userEvent.click(
      within(devices).getByRole('button', { name: accountCopy.devices.logoutOthers }),
    );
    const dialog = screen.getByRole('dialog', { name: accountCopy.devices.confirmTitle });
    expect(writes(calls)).toEqual([]);
    await userEvent.click(
      within(dialog).getByRole('button', { name: accountCopy.devices.confirm }),
    );
    expect(await within(devices).findByText(accountCopy.devices.othersDone)).toBeInTheDocument();
    expect(writes(calls)).toEqual([
      { method: 'POST', path: '/api/auth/logout-others', body: undefined },
    ]);
  });

  it('changes the PIN through three fields and says the others are logged out', async () => {
    const { calls } = await open(accountDefault);
    const user = userEvent.setup();
    const card = screen.getByRole('region', { name: accountCopy.pin.title });
    const toggle = within(card).getByRole('button', { name: accountCopy.pin.title });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(within(card).getByText('바꾸면 다른 기기는 다시 들어와야 해요')).toBeInTheDocument();
    await user.click(toggle);
    await user.type(within(card).getByLabelText(accountCopy.pin.current), '111111');
    await user.type(within(card).getByLabelText(accountCopy.pin.next), '222222');
    await user.type(within(card).getByLabelText(accountCopy.pin.again), '222222');
    await user.click(within(card).getByRole('button', { name: accountCopy.pin.submit }));
    expect(await within(card).findByText('바꿨어요 · 다른 기기 로그아웃됨')).toBeInTheDocument();
    expect(writes(calls)).toEqual([
      { method: 'POST', path: '/api/account/pin', body: { current: '111111', next: '222222' } },
    ]);
  });

  it('says 두 PIN이 달라요 and clears the second field without sending', async () => {
    const { calls } = await open(accountDefault);
    const user = userEvent.setup();
    const card = screen.getByRole('region', { name: accountCopy.pin.title });
    await user.click(within(card).getByRole('button', { name: accountCopy.pin.title }));
    await user.type(within(card).getByLabelText(accountCopy.pin.current), '111111');
    await user.type(within(card).getByLabelText(accountCopy.pin.next), '222222');
    await user.type(within(card).getByLabelText(accountCopy.pin.again), '333333');
    await user.click(within(card).getByRole('button', { name: accountCopy.pin.submit }));
    expect(within(card).getByText('두 PIN이 달라요')).toBeInTheDocument();
    expect(within(card).getByLabelText(accountCopy.pin.again)).toHaveValue('');
    expect(within(card).getByLabelText(accountCopy.pin.next)).toHaveValue('222222');
    expect(writes(calls)).toEqual([]);
  });

  it('says 현재 PIN이 맞지 않아요 and clears that field on 403 current-pin', async () => {
    await open(accountPinError);
    const user = userEvent.setup();
    const card = screen.getByRole('region', { name: accountCopy.pin.title });
    await user.click(within(card).getByRole('button', { name: accountCopy.pin.title }));
    await user.type(within(card).getByLabelText(accountCopy.pin.current), '999999');
    await user.type(within(card).getByLabelText(accountCopy.pin.next), '222222');
    await user.type(within(card).getByLabelText(accountCopy.pin.again), '222222');
    await user.click(within(card).getByRole('button', { name: accountCopy.pin.submit }));
    expect(await within(card).findByText('현재 PIN이 맞지 않아요')).toBeInTheDocument();
    expect(within(card).getByLabelText(accountCopy.pin.current)).toHaveValue('');
    expect(within(card).getByLabelText(accountCopy.pin.current)).toHaveAttribute(
      'aria-invalid',
      'true',
    );
  });

  it('shows skeletons while loading', () => {
    serve(accountLoading);
    renderApp('/account');
    expect(document.querySelector('[aria-busy="true"]')).not.toBeNull();
    expect(screen.queryByRole('region', { name: N.title })).toBeNull();
  });

  it('shows the load error with 다시 불러오기, which then loads', async () => {
    serve(accountError);
    renderApp('/account');
    expect(await screen.findByText(accountCopy.error)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: copy.state.retry }));
    expect(await screen.findByRole('region', { name: N.title })).toBeInTheDocument();
  });
});
