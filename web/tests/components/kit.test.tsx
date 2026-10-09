// Every Figma component variant (153 minus the 27 노드 A/B/C explorations) is rendered in /_kit.
import { render } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { describe, expect, it } from 'vitest';
import { KitGallery } from '../../src/kit/KitGallery';

const FIGMA_COMPONENTS = [
  '1:1282',
  '1:1286',
  '1:1291',
  '1:1294',
  '1:1298',
  '1:1302',
  '1:1306',
  '1:1308',
  '1:1311',
  '1:1322',
  '1:1328',
  '1:1335',
  '1:1342',
  '1:1349',
  '1:1354',
  '1:2448',
  '1:2449',
  '1:2451',
  '1:2452',
  '1:2453',
  '1:2455',
  '1:2457',
  '1:2459',
  '1:2461',
  '1:2463',
  '1:2465',
  '1:2468',
  '1:2470',
  '1:2473',
  '1:2476',
  '1:2478',
  '1:2484',
  '1:2491',
  '1:2971',
  '1:4747',
  '1:4749',
  '1:4752',
  '1:4755',
  '1:4759',
  '1:4761',
  '1:4764',
  '1:4767',
  '1:4770',
  '1:4773',
  '1:4776',
  '1:4779',
  '1:4783',
  '1:4785',
  '1:4806',
  '1:4813',
  '1:4817',
  '1:4823',
  '1:4829',
  '1:4836',
  '1:4841',
  '1:4846',
  '1:4852',
  '1:4857',
  '1:4861',
  '1:4866',
  '1:4872',
  '1:4880',
  '1:4888',
  '1:4890',
  '1:4914',
  '1:4938',
  '1:4962',
  '1:4987',
  '1:4999',
  '1:5025',
  '1:5051',
  '1:5077',
  '1:16571',
  '1:16646',
  '1:16655',
  '1:16664',
  '1:16674',
  '1:16682',
  '1:16692',
  '1:16701',
  '1:16707',
  '1:16715',
  '1:16718',
  '1:16721',
  '1:16727',
  '1:16735',
  '1:16743',
  '1:16769',
  '1:19626',
  '1:19709',
  '1:19737',
  '1:19774',
  '1:19806',
  '1:19835',
  '1:19894',
  '1:19940',
  '1:19962',
  '1:24067',
  '1:24071',
  '1:24072',
  '1:24078',
  '1:24084',
  '1:24090',
  '1:24094',
  '1:24098',
  '1:24100',
  '1:24101',
  '1:24103',
  '1:24111',
  '1:28615',
  '1:28618',
  '1:28621',
  '1:28624',
  '1:28628',
  '1:28636',
  '1:28645',
  '1:28652',
  '1:28662',
  '1:28673',
  '1:28675',
  '1:28680',
  '1:39577',
  '1:41983',
  '1:42662',
  '1:42665',
  '1:42668',
];

function renderKit(path = '/_kit') {
  const router = createMemoryRouter([{ path: '/_kit', element: <KitGallery /> }], {
    initialEntries: [path],
  });
  return render(<RouterProvider router={router} />);
}

describe('/_kit gallery', () => {
  it('lists 126 Figma components', () => {
    expect(new Set(FIGMA_COMPONENTS).size).toBe(126);
  });

  it('renders a box for every Figma component and variant', () => {
    const { container } = renderKit();
    const ids = new Set(
      [...container.querySelectorAll('[data-figma-id]')].map((el) =>
        el.getAttribute('data-figma-id'),
      ),
    );
    const missing = FIGMA_COMPONENTS.filter((id) => !ids.has(id));
    expect(missing).toEqual([]);
  });

  it('renders every box with content', () => {
    const { container } = renderKit();
    for (const box of container.querySelectorAll('[data-figma-id]')) {
      expect(box.childElementCount, box.getAttribute('data-figma-id') ?? '').toBeGreaterThan(0);
    }
  });

  it('isolates one variant with ?only=', () => {
    const { container } = renderKit('/_kit?only=1:4747');
    const boxes = container.querySelectorAll('[data-figma-id]');
    expect(boxes).toHaveLength(1);
    expect(boxes[0]?.getAttribute('data-figma-id')).toBe('1:4747');
  });
});
