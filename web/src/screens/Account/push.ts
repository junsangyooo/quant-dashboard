// Browser side of '이 기기에서 알림 받기'. The permission prompt runs only from the switch press
// (기획 §5 SCR-ACCOUNT: '권한 요청은 이 스위치를 누를 때만').
// Phase 1 ships no service worker and no VAPID key (both arrive with web push, phase 3), so a
// device that grants permission sends the subscription it can make — none yet — and the server
// answers 501 not-implemented, which the screen shows as '준비 중'.

/** This browser has the three pieces web push needs. */
export function browserCanPush(): boolean {
  return (
    typeof window !== 'undefined' &&
    'Notification' in window &&
    'PushManager' in window &&
    typeof navigator !== 'undefined' &&
    'serviceWorker' in navigator
  );
}

export type Permission = 'granted' | 'denied' | 'default' | 'unsupported';

/** Asks once; resolves the browser's answer ('default' = dismissed). */
export async function askPermission(): Promise<Permission> {
  if (!browserCanPush()) return 'unsupported';
  if (Notification.permission !== 'default') return Notification.permission;
  try {
    return await Notification.requestPermission();
  } catch {
    return 'denied';
  }
}

/** The existing subscription of this page's worker, or an empty one when there is no worker yet. */
export async function currentSubscription(): Promise<PushSubscriptionJSON> {
  try {
    const registration = await navigator.serviceWorker.getRegistration();
    const subscription = await registration?.pushManager.getSubscription();
    return subscription ? subscription.toJSON() : {};
  } catch {
    return {};
  }
}
