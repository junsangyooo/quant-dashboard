// Daily series of the 실전 world and the extra lines of SCR-PLAN, read back from the Figma
// line paths on the 디자인 page the same way fixtures/charts.ts reads the 모의투자 world:
// - 실전 자산 / 손대지 않았을 때: SCR-HOME · 실전 평상 · 1440 (1:55222), 700px = 9/1→10/7,
//   1000만 at y 223.06, 81.175px per 10만. Ends on 예시-값표 §2.2 (10,112,670 · +1.75%).
// - 실전 벗어남 흐름: SCR-PLAN · 실전 평상 · 390 (1:56152), 316px = 9/1→10/7, 28px per %p
//   (값표 §2.2: 지수 반반 10/6 2.5 → 10/7 0.2, 모멘텀 1.0).
// - 3년 발굴 지수 대비: Figma 탐색 17:7108, 344px = 7/1→10/7, 7.334px per %p.
import type { LinePoint } from '../../charts/geometry/lineChart';
import { driftIndex, driftMomentum } from '../charts';

/** 실전 자산 9/1–10/7 (27 trading days). */
export const liveDaily: readonly LinePoint[] = [
  { date: '2026-09-01', value: 9994400 },
  { date: '2026-09-02', value: 10006500 },
  { date: '2026-09-03', value: 10005400 },
  { date: '2026-09-04', value: 10012000 },
  { date: '2026-09-07', value: 9998100 },
  { date: '2026-09-08', value: 9987700 },
  { date: '2026-09-09', value: 9985000 },
  { date: '2026-09-10', value: 9984900 },
  { date: '2026-09-11', value: 9984100 },
  { date: '2026-09-14', value: 9976000 },
  { date: '2026-09-15', value: 9986100 },
  { date: '2026-09-16', value: 9995200 },
  { date: '2026-09-17', value: 9994200 },
  { date: '2026-09-18', value: 10004000 },
  { date: '2026-09-21', value: 10019000 },
  { date: '2026-09-22', value: 10018900 },
  { date: '2026-09-23', value: 10022200 },
  { date: '2026-09-24', value: 10031000 },
  { date: '2026-09-25', value: 10039400 },
  { date: '2026-09-28', value: 10048800 },
  { date: '2026-09-29', value: 10058000 },
  { date: '2026-09-30', value: 10060000 },
  { date: '2026-10-01', value: 10064600 },
  { date: '2026-10-02', value: 10079000 },
  { date: '2026-10-05', value: 10095100 },
  { date: '2026-10-06', value: 10098000 },
  { date: '2026-10-07', value: 10112670 },
];

/** 실전 손대지 않았을 때 (9/1 두 ETF 50:50), same dates. */
export const liveUntouchedDaily: readonly LinePoint[] = [
  { date: '2026-09-01', value: 10000000 },
  { date: '2026-09-02', value: 10013300 },
  { date: '2026-09-03', value: 10013200 },
  { date: '2026-09-04', value: 10021000 },
  { date: '2026-09-07', value: 10009500 },
  { date: '2026-09-08', value: 9999900 },
  { date: '2026-09-09', value: 9998000 },
  { date: '2026-09-10', value: 9999100 },
  { date: '2026-09-11', value: 9999500 },
  { date: '2026-09-14', value: 9995000 },
  { date: '2026-09-15', value: 10006800 },
  { date: '2026-09-16', value: 10017700 },
  { date: '2026-09-17', value: 10018400 },
  { date: '2026-09-18', value: 10030000 },
  { date: '2026-09-21', value: 10047000 },
  { date: '2026-09-22', value: 10047600 },
  { date: '2026-09-23', value: 10051500 },
  { date: '2026-09-24', value: 10061000 },
  { date: '2026-09-25', value: 10070700 },
  { date: '2026-09-28', value: 10084100 },
  { date: '2026-09-29', value: 10094600 },
  { date: '2026-09-30', value: 10098000 },
  { date: '2026-10-01', value: 10104600 },
  { date: '2026-10-02', value: 10121000 },
  { date: '2026-10-05', value: 10150600 },
  { date: '2026-10-06', value: 10158000 },
  { date: '2026-10-07', value: 10175000 },
];

/**
 * 실전 · 지수 반반 (D47): how far its won and dollars were from 50 : 50 (|한국 − 목표|, %p). 10/6 is
 * past the band ('환전 제안'), the owner converts that day, and 10/7 is back at 50 : 50 (the 08:30
 * check buys S&P 500 ETF with those dollars at 22:30).
 */
export const liveDriftIndex: readonly LinePoint[] = [
  { date: '2026-09-01', value: 0.3 },
  { date: '2026-09-04', value: 0.6 },
  { date: '2026-09-09', value: 0.9 },
  { date: '2026-09-14', value: 1.1 },
  { date: '2026-09-18', value: 1.0 },
  { date: '2026-09-24', value: 1.6 },
  { date: '2026-09-30', value: 1.9 },
  { date: '2026-10-02', value: 2.0 },
  { date: '2026-10-06', value: 2.5 },
  { date: '2026-10-07', value: 0.0 },
];

/**
 * 출금 대기 variant: the hand sale on 10/2 (KOSPI200 ETF 14주) leaves 한국 at 49.7% of the rule's
 * money (the waiting cash leaves it, 값표 §2.3), and nothing is bought. Not drawn in Figma.
 */
export const withdrawDriftIndex: readonly LinePoint[] = [
  ...liveDriftIndex.filter((p) => p.date <= '2026-10-02'),
  { date: '2026-10-05', value: 0.3 },
  { date: '2026-10-06', value: 0.3 },
  { date: '2026-10-07', value: 0.3 },
];

/**
 * 시세 대기 (1:56437): the lines stop after the last good US close (10/2) and break from
 * 10/5 ('10/5부터 시세 대기').
 */
export function staleDrift(points: readonly LinePoint[]): LinePoint[] {
  return [
    ...points.filter((p) => p.date <= '2026-10-02'),
    { date: '2026-10-05', value: null },
    { date: '2026-10-06', value: null },
    { date: '2026-10-07', value: null },
  ];
}

export const staleDriftIndex = staleDrift([
  ...driftIndex.filter((p) => p.date <= '2026-10-01'),
  { date: '2026-10-02', value: 1.9 },
]);
export const staleDriftMomentum = staleDrift(driftMomentum);

/** 3년 발굴 · 지수 대비 (%p) since the pick date 7/1 (Figma 탐색 17:7108). */
export const discoveryVsIndex: readonly LinePoint[] = [
  { date: '2026-07-01', value: 0.5 },
  { date: '2026-07-09', value: 0.9 },
  { date: '2026-07-23', value: 1.5 },
  { date: '2026-08-05', value: 1.9 },
  { date: '2026-08-17', value: 1.4 },
  { date: '2026-09-02', value: 1.0 },
  { date: '2026-09-18', value: 1.5 },
  { date: '2026-10-05', value: 1.3 },
  { date: '2026-10-07', value: 1.3 },
];
