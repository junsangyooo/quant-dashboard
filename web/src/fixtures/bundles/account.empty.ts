// SCR-ACCOUNT · 구독 기기 0대 (명세 empty, 그림 없음): 스위치 위 '이 기기에서 알림 받기를 눌러 시작해요',
// 시험 알림 비활성, 결과 행 없음. A server with web push (`available`, 3단계) and no device yet; the
// subscribe call still answers 501 not-implemented here, which the screen shows as a calm '준비 중'.
import type { AccountResponse } from '../../api/types';
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import { NOW, events, shell } from '../ops';

const empty: AccountResponse = {
  thisDevice: { name: 'Mac · Chrome', kind: 'mac', enteredAt: kst('2026-10-07', '16:02') },
  notifications: {
    available: true,
    vapidPublicKey: 'BFixtureVapidPublicKey',
    thisDevice: { supported: true, subscribed: false },
    events: events(),
    hideAmounts: false,
    savedAt: null,
    devices: [],
    testResults: null,
  },
};

const notImplemented = {
  $status: 501,
  $body: { error: 'not-implemented', detail: { feature: 'push' } },
} as const;

const bundle = {
  id: 'account.empty',
  now: NOW,
  responses: {
    '/api/shell': shell(),
    '/api/account': empty,
    'PUT /api/account/notifications': { savedAt: NOW },
    'POST /api/account/push': notImplemented,
    'POST /api/account/push/test': notImplemented,
  },
} satisfies FixtureBundle;

export default bundle;
