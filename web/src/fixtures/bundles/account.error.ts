// SCR-ACCOUNT · 못 불러옴 (그림 없음): '설정을 못 불러왔어요' + 다시 불러오기, which then loads.
import type { FixtureBundle } from '../types';
import { NOW, account, shell } from '../ops';

const bundle = {
  id: 'account.error',
  now: NOW,
  responses: {
    '/api/shell': shell(),
    '/api/account': [{ $status: 500, $body: { error: 'internal' } }, account()],
  },
} satisfies FixtureBundle;

export default bundle;
