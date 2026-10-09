// SCR-ACCOUNT · 1·2단계 (CONTRACT.md: notifications.available false, 푸시 501, thisDevice
// supported:false · 'unsupported', devices []): every device reads '알림은 준비 중이에요'.
import type { AccountResponse } from '../../api/types';
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import { NOW, events, shell } from '../ops';

const phase1: AccountResponse = {
  thisDevice: { name: 'Mac · Chrome', kind: 'mac', enteredAt: kst('2026-10-07', '16:02') },
  notifications: {
    available: false,
    thisDevice: { supported: false, reason: 'unsupported', subscribed: false },
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
  id: 'account.push-not-ready',
  now: NOW,
  responses: {
    '/api/shell': shell(),
    '/api/account': phase1,
    'PUT /api/account/notifications': { savedAt: NOW },
    'POST /api/account/push': notImplemented,
    'POST /api/account/push/test': notImplemented,
  },
} satisfies FixtureBundle;

export default bundle;
