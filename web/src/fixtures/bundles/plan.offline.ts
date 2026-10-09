// SCR-PLAN · 불러오기 실패 (spec only): like 자산, header '연결 안 됨' and a top chip
// '16:10 불러온 값 · 연결 안 됨'; values stay.
import type { FixtureBundle } from '../types';
import homeOffline from './home.offline';

const bundle = {
  ...homeOffline,
  id: 'plan.offline',
} satisfies FixtureBundle;

export default bundle;
