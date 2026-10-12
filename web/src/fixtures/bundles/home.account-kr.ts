// SCR-HOME · 계좌별 보기 · 한국 ₩ (no drawing; the owner's plan of 2026-10-12): the 모의투자 world
// (값표 §1, 10/7 16:10) with the switch on 한국 계좌 — 5,368,683원, ▲ +484,683원 · +9.92%, its own
// line and rows in won (BTC is bought in won, so it is here). Same answers as home.paper.
import type { FixtureBundle } from '../types';
import homePaper from './home.paper';

const bundle = {
  ...homePaper,
  id: 'home.account-kr',
  search: 'account=kr',
} satisfies FixtureBundle;

export default bundle;
