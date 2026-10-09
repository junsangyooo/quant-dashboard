// SCR-PLAN · 첫 확인 전 (spec only, 그림 없음): hollow gauges, weights '— · 목표 50%', first
// item '첫 확인 7/1 08:30 · 목표대로 매수', '벗어남 흐름은 둘째 날부터'.
import type { FixtureBundle } from '../types';
import homeEmpty from './home.empty';

const bundle = {
  ...homeEmpty,
  id: 'plan.empty',
} satisfies FixtureBundle;

export default bundle;
