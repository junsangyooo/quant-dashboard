// SCR-HOME · 미국 계좌에 달러 현금만 (no drawing): 출시 첫날 (값표 §4, 7/1 16:10) on 미국 $ — the
// $3,568.24 the 09:10 conversion bought waits for the 22:30 buy: no gain, no loss yet, one row, the
// graph from the second day. Same answers as home.first-day.
import type { FixtureBundle } from '../types';
import homeFirstDay from './home.first-day';

const bundle = {
  ...homeFirstDay,
  id: 'home.us-cash',
  search: 'account=us',
} satisfies FixtureBundle;

export default bundle;
