// SCR-PLAN · 휴장 (spec only): 10/9 한국 휴장 — chip '휴장' + '한국 휴장 · 거래 없음 · 다음
// 확인 10/12 08:30'. Same moment as home.holiday.
import type { FixtureBundle } from '../types';
import homeHoliday from './home.holiday';

const bundle = {
  ...homeHoliday,
  id: 'plan.holiday',
} satisfies FixtureBundle;

export default bundle;
