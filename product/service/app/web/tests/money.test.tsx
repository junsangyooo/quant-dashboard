// 검토 2차: y축은 1억부터 '억'(잘림 0), 해를 넘는 x축은 연도를 붙인다.
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { LineChart } from '../src/charts/LineChart';
import { LINE_HOME_390 } from '../src/charts/geometry/lineChart';
import { formatYearDate } from '../src/lib/format';
import { axisTick, manTick } from '../src/lib/money';

describe('y축 단위', () => {
  it('1억 아래는 만, 1억부터 억', () => {
    expect(manTick(10_500_000)).toBe('1,050만');
    expect(manTick(99_000_000)).toBe('9,900만');
    expect(manTick(120_000_000)).toBe('1.2억');
    expect(manTick(300_000_000)).toBe('3억');
    expect(manTick(5_000_000_000)).toBe('50억');
    expect(manTick(302_500_000)).toBe('3.025억');
    expect(axisTick(5e10)(0)).toBe('0억');
    expect(axisTick(5e7)(0)).toBe('0만');
    // 좁은 눈금 칸(52px)에 들어가는 길이
    for (const v of [1e8, 2.95e8, 5e9, 1e10, 3.025e8])
      expect(manTick(v).length).toBeLessThanOrEqual(6);
  });
});

describe('해를 넘는 x축', () => {
  it('첫 눈금과 해가 바뀌는 눈금에 연도', () => {
    expect(formatYearDate('2025-05-30')).toBe('2025.5/30');
    const pts = [
      { date: '2025-05-30', value: 1 },
      { date: '2026-10-28', value: 2 },
    ];
    const { container } = render(
      <LineChart
        layout={LINE_HOME_390}
        start="2025-05-30"
        end="2026-10-28"
        axis={{ domain: [0, 3], ticks: [0, 1, 2] }}
        mine={{ key: 'm', points: pts }}
        label="x"
        width={350}
      />,
    );
    const labels = [...container.querySelectorAll('span')].map((s) => s.textContent);
    expect(labels[0]).toBe('2025.5/30');
    expect(labels.some((l) => l.startsWith('2026.'))).toBe(true);
  });

  it('한 해 안이면 연도를 붙이지 않는다', () => {
    const { container } = render(
      <LineChart
        layout={LINE_HOME_390}
        start="2026-09-28"
        end="2026-10-28"
        axis={{ domain: [0, 3], ticks: [0, 1, 2] }}
        mine={{
          key: 'm',
          points: [
            { date: '2026-09-28', value: 1 },
            { date: '2026-10-28', value: 2 },
          ],
        }}
        label="x"
        width={350}
      />,
    );
    const labels = [...container.querySelectorAll('span')].map((s) => s.textContent);
    expect(labels.every((l) => !l.includes('.'))).toBe(true);
  });
});
