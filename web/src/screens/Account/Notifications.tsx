// 알림 (Figma 1:65384 · 1:65568): this device's switch → '받을 사건 · 처음부터 n개 켜짐' → one switch
// per event (확인 실패 locked) → 알림에 금액 숨기기 → '[시각] 저장됨' → 시험 알림 보내기 → a result row per
// device. Every switch saves at once; the browser permission is asked only from this device's
// switch. Phase 1 answers the push endpoints with 501: shown as a calm '준비 중', not an error.
// Until the server has web push (`available` false, 1·2단계) the screen shows NotificationsLater —
// one disabled row — instead of this card (the owner, 2026-10-12: ten switches looked live while
// nothing was sent); this card returns as it is when push comes (3단계).
import clsx from 'clsx';
import { useId, useState } from 'react';
import {
  ArrowLeftRight,
  Banknote,
  Bell,
  CalendarX,
  CircleCheck,
  CircleDollarSign,
  CircleMinus,
  CirclePlus,
  CircleX,
  ClipboardCheck,
  ClockAlert,
  EyeOff,
  Laptop,
  LoaderCircle,
  Lock,
  MailCheck,
  Monitor,
  Plug,
  Smartphone,
  UserX,
  type LucideIcon,
} from 'lucide-react';
import { accountCopy as t } from '../../copy/account';
import { isApiError } from '../../api/client';
import {
  usePushSubscribe,
  usePushTest,
  usePushUnsubscribe,
  useSaveNotifications,
} from '../../api/queries';
import type { AccountResponse, NotifyEvent } from '../../api/types';
import { Button } from '../../components/Buttons';
import { Toggle } from '../../components/Controls';
import { formatDateTime } from '../../lib/format';
import { askPermission, browserCanPush, currentSubscription } from './push';
import styles from './Account.module.css';

type Notifications = AccountResponse['notifications'];

/** Spec order (1:39291), then the 2단계 AI events (화면-맞춤 §3). */
export const EVENT_ORDER: readonly NotifyEvent[] = [
  'check-failed',
  'stale',
  'weekly-ok',
  'live-fill',
  'pin-failures',
  'toss-expiring',
  'check-missed',
  'rebalance-notice',
  'cash-moves',
  'ai-sell',
  'ai-buy',
  'ai-review',
];

/** On from the start (D-notify-webpush: 6; 'AI가 팔기로 함' is proposed on too, 화면-맞춤 §3). */
export const ON_BY_DEFAULT: ReadonlySet<NotifyEvent> = new Set<NotifyEvent>([
  'check-failed',
  'stale',
  'weekly-ok',
  'live-fill',
  'pin-failures',
  'toss-expiring',
  'ai-sell',
]);

const EVENT_ICON: Record<NotifyEvent, LucideIcon> = {
  'check-failed': CircleX,
  stale: ClockAlert,
  'weekly-ok': MailCheck,
  'live-fill': CircleDollarSign,
  'pin-failures': UserX,
  'toss-expiring': Plug,
  'check-missed': CalendarX,
  'rebalance-notice': ArrowLeftRight,
  'cash-moves': Banknote,
  'ai-sell': CircleMinus,
  'ai-buy': CirclePlus,
  'ai-review': ClipboardCheck,
};

function deviceIcon(name: string): LucideIcon {
  if (/iphone|android|phone|galaxy/i.test(name)) return Smartphone;
  if (/mac|windows|linux|chromebook|pc/i.test(name)) return Laptop;
  return Monitor;
}

type DeviceNote =
  | { kind: 'hint' }
  | { kind: 'cannot'; reason: 'safari-tab' | 'denied' | 'unsupported' }
  | { kind: 'not-ready' }
  | { kind: 'off-not-ready' }
  | { kind: 'failed' }
  | { kind: 'off-failed' };

interface Saved {
  events: Partial<Record<NotifyEvent, boolean>>;
  hideAmounts?: boolean | undefined;
  savedAt: string | null;
}

/** Before web push: one disabled row — 알림 · what it will do · a switch that cannot be turned on. */
export function NotificationsLater() {
  const titleId = useId();
  return (
    <section
      id="notifications"
      className={clsx(styles.card, styles.notificationsLater)}
      aria-labelledby={titleId}
    >
      <div className={styles.laterRow}>
        <Bell size={20} aria-hidden />
        <div className={styles.switchText}>
          <h2 id={titleId} className="t-body-strong">
            {t.notifications.title}
          </h2>
          <p className={clsx('t-caption', styles.muted)}>{t.notifications.later}</p>
        </div>
        <Toggle checked={false} disabled aria-labelledby={titleId} className={styles.toggleLater} />
      </div>
    </section>
  );
}

export function NotificationsCard({ notifications: n }: { notifications: Notifications }) {
  const titleId = useId();
  const save = useSaveNotifications();
  const subscribe = usePushSubscribe();
  const unsubscribe = usePushUnsubscribe();
  const test = usePushTest();
  // Saved changes since this page opened: the switches show them at once and keep them.
  const [saved, setSaved] = useState<Saved>({ events: {}, savedAt: null });
  const [saveFailed, setSaveFailed] = useState(false);
  const [deviceNote, setDeviceNote] = useState<DeviceNote | null>(null);
  const [asking, setAsking] = useState(false);

  const events = EVENT_ORDER.flatMap((id) => {
    const e = n.events.find((x) => x.id === id);
    return e ? [{ ...e, on: saved.events[id] ?? e.on }] : [];
  });
  const defaultsOn = events.filter((e) => ON_BY_DEFAULT.has(e.id)).length;
  const hideAmounts = saved.hideAmounts ?? n.hideAmounts;
  const savedAt = [saved.savedAt, n.savedAt]
    .filter((v): v is string => v !== null)
    .sort((a, b) => Date.parse(b) - Date.parse(a))[0];

  const persist = (change: {
    events?: Partial<Record<NotifyEvent, boolean>>;
    hideAmounts?: boolean;
  }) => {
    setSaveFailed(false);
    const before = saved;
    setSaved((s) => ({
      events: { ...s.events, ...change.events },
      hideAmounts: change.hideAmounts ?? s.hideAmounts,
      savedAt: s.savedAt,
    }));
    save.mutate(change, {
      onSuccess: (res) => {
        setSaved((s) => ({ ...s, savedAt: res.savedAt }));
      },
      onError: () => {
        setSaved(before);
        setSaveFailed(true);
      },
    });
  };

  // This device. While the server has no web push (`available` false, 1·2단계) every device
  // reads 'not built yet' (준비 중); so does a capable browser the server calls 'unsupported'.
  const thisDevice = n.thisDevice;
  const serverNote: DeviceNote | null = !n.available
    ? { kind: 'not-ready' }
    : thisDevice.supported
      ? null
      : thisDevice.reason === 'unsupported' && browserCanPush()
        ? { kind: 'not-ready' }
        : { kind: 'cannot', reason: thisDevice.reason ?? 'unsupported' };
  const note = deviceNote ?? serverNote ?? { kind: 'hint' };
  const switchOn = thisDevice.supported && thisDevice.subscribed;
  const switchDisabled =
    !n.available || !thisDevice.supported || asking || subscribe.isPending || unsubscribe.isPending;

  const onDevice = async () => {
    if (switchOn) {
      setDeviceNote(null);
      unsubscribe.mutate(undefined, {
        onError: (error) => {
          setDeviceNote(
            isApiError(error, 'not-implemented')
              ? { kind: 'off-not-ready' }
              : { kind: 'off-failed' },
          );
        },
      });
      return;
    }
    setDeviceNote(null);
    setAsking(true);
    const permission = await askPermission();
    setAsking(false);
    if (permission === 'denied' || permission === 'unsupported') {
      setDeviceNote({ kind: 'cannot', reason: permission });
      return;
    }
    if (permission === 'default') return;
    const subscription = await currentSubscription();
    subscribe.mutate(subscription, {
      onError: (error) => {
        setDeviceNote(
          isApiError(error, 'not-implemented') ? { kind: 'not-ready' } : { kind: 'failed' },
        );
      },
    });
  };

  const results = test.data?.results ?? n.testResults ?? [];
  const testState: 'idle' | 'not-ready' | 'failed' = test.isError
    ? isApiError(test.error, 'not-implemented')
      ? 'not-ready'
      : 'failed'
    : 'idle';
  const noDevices = n.devices.length === 0;

  return (
    <section
      id="notifications"
      className={clsx(styles.card, styles.notifications)}
      aria-labelledby={titleId}
    >
      <h2 id={titleId} className="t-heading-1">
        {t.notifications.title}
      </h2>

      {noDevices && n.available && thisDevice.supported && !switchOn ? (
        <p className={clsx('t-caption', styles.muted)}>{t.notifications.start}</p>
      ) : null}
      <div className={styles.switchRow}>
        <Bell size={20} aria-hidden />
        <div className={styles.switchText}>
          <span id={`${titleId}-device`} className="t-body">
            {t.notifications.thisDevice}
          </span>
          <span
            className={clsx(
              't-caption',
              note.kind === 'cannot' || note.kind === 'failed' || note.kind === 'off-failed'
                ? styles.warning
                : styles.muted,
            )}
          >
            {note.kind === 'hint'
              ? t.notifications.iphoneOnly
              : note.kind === 'cannot'
                ? t.notifications.cannot(t.notifications.reasons[note.reason])
                : note.kind === 'not-ready'
                  ? t.notifications.notReady
                  : note.kind === 'off-not-ready'
                    ? t.notifications.offNotReady
                    : note.kind === 'off-failed'
                      ? t.notifications.unsubscribeFailed
                      : t.notifications.subscribeFailed}
          </span>
        </div>
        <Toggle
          checked={switchOn}
          disabled={switchDisabled}
          aria-labelledby={`${titleId}-device`}
          onChange={() => {
            void onDevice();
          }}
        />
      </div>
      {note.kind === 'cannot' && note.reason !== 'unsupported' ? (
        <p className={clsx('t-caption', styles.muted)}>{t.notifications.fix[note.reason]}</p>
      ) : null}

      <hr className={styles.divider} />
      <p className={clsx('t-label', styles.muted)}>{t.notifications.eventsTitle(defaultsOn)}</p>
      <ul className={styles.switchList}>
        {events.map((e) => {
          const copy = t.events[e.id];
          const Icon = EVENT_ICON[e.id];
          const labelId = `${titleId}-${e.id}`;
          const sub = 'note' in copy ? copy.note : undefined;
          return (
            <li key={e.id} className={styles.switchRow}>
              <Icon size={20} aria-hidden />
              <div className={styles.switchText}>
                <span id={labelId} className="t-body">
                  {copy.name}
                </span>
                {sub !== undefined ? (
                  <span className={clsx('t-caption', styles.muted)}>{sub}</span>
                ) : null}
              </div>
              {e.locked ? (
                <span className={styles.lock}>
                  <Lock size={16} aria-hidden />
                  <span className="sr-only">{t.notifications.locked}</span>
                </span>
              ) : null}
              <Toggle
                checked={e.locked ? true : e.on}
                disabled={e.locked}
                aria-labelledby={labelId}
                onChange={(next) => {
                  persist({ events: { [e.id]: next } });
                }}
              />
            </li>
          );
        })}
      </ul>
      <hr className={styles.divider} />
      <div className={styles.switchRow}>
        <EyeOff size={20} aria-hidden />
        <div className={styles.switchText}>
          <span id={`${titleId}-hide`} className="t-body">
            {t.notifications.hideAmounts}
          </span>
        </div>
        <Toggle
          checked={hideAmounts}
          aria-labelledby={`${titleId}-hide`}
          onChange={(next) => {
            persist({ hideAmounts: next });
          }}
        />
      </div>
      <div className={styles.contents} aria-live="polite">
        {saveFailed ? (
          <p className={clsx('t-caption', styles.error)}>{t.notifications.saveFailed}</p>
        ) : savedAt ? (
          <p className={clsx('t-caption', styles.muted)}>
            {t.notifications.saved(formatDateTime(savedAt))}
          </p>
        ) : null}
      </div>
      <hr className={styles.divider} />
      <Button
        kind="default"
        className={styles.wide}
        disabled={noDevices || test.isPending}
        onClick={() => {
          test.mutate();
        }}
      >
        {test.isPending ? <LoaderCircle size={18} className={styles.spinner} aria-hidden /> : null}
        {test.isPending ? t.notifications.testing : t.notifications.test}
      </Button>
      <div className={styles.contents} aria-live="polite">
        {testState === 'not-ready' ? (
          <p className={clsx('t-caption', styles.muted)}>{t.notifications.testNotReady}</p>
        ) : testState === 'failed' ? (
          <p className={clsx('t-caption', styles.error)}>{t.notifications.testFailed}</p>
        ) : null}
        {!noDevices && results.length > 0 ? (
          <ul className={styles.results}>
            {results.map((r) => {
              const Icon = deviceIcon(r.device);
              return (
                <li key={r.device} className={styles.result}>
                  <Icon size={18} aria-hidden />
                  <span className={clsx('t-caption', styles.grow)}>{r.device}</span>
                  {r.ok ? (
                    <CircleCheck size={16} className={styles.success} aria-hidden />
                  ) : (
                    <CircleX size={16} className={styles.error} aria-hidden />
                  )}
                  <span className={clsx('t-caption', styles.muted)}>
                    {r.ok
                      ? t.notifications.received(formatDateTime(r.at))
                      : t.notifications.resultFailed}
                  </span>
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>
    </section>
  );
}
