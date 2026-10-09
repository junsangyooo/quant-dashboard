// 자산 and 계획 inside the real AppShell (header, banner, mode chip), without the other screens:
// tests of these two screens do not depend on how far the other screens have come.
import { screen } from '@testing-library/react';
import type { RouteObject } from 'react-router';
import { vi, type Mock } from 'vitest';
import { HomeScreen } from '../../src/screens/Home/HomeScreen';
import { PlanScreen } from '../../src/screens/Plan/PlanScreen';
import { AppShell } from '../../src/shell/AppShell';
import type { FixtureBundle } from '../../src/fixtures/types';
import { answerFrom, renderRoutes } from '../helpers';

function Placeholder({ name }: { name: string }) {
  return <h1>{name}</h1>;
}

export const homePlanRoutes: RouteObject[] = [
  { path: '/pin', element: <Placeholder name="pin" /> },
  {
    element: <AppShell />,
    children: [
      { index: true, element: <HomeScreen />, handle: { page: 'home', kind: 'tab', tab: 'home' } },
      { path: 'plan', element: <PlanScreen />, handle: { page: 'plan', kind: 'tab', tab: 'plan' } },
      {
        path: 'day/:date',
        element: <Placeholder name="day" />,
        handle: { page: 'day', kind: 'sheet' },
      },
      {
        path: 'health',
        element: <Placeholder name="health" />,
        handle: { page: 'health', kind: 'sub' },
      },
      {
        path: 'rules/:ruleId?',
        element: <Placeholder name="rules" />,
        handle: { page: 'rules', kind: 'tab', tab: 'rules' },
      },
    ],
  },
];

/** Render a path of the two screens answering from `bundle`; resolves once data is on screen. */
export function renderState(bundle: FixtureBundle, path = '/') {
  answerFrom(bundle);
  return renderRoutes(homePlanRoutes, path);
}

/** jsdom has no scrollIntoView; this records the calls. */
export const scrollSpy: Mock<(arg?: boolean | ScrollIntoViewOptions) => void> = vi.fn();

export function stubScroll() {
  Element.prototype.scrollIntoView = scrollSpy;
}

/** The value, or a thrown error naming what is missing. */
export function must<T>(value: T | null | undefined, what = 'element'): T {
  if (value === null || value === undefined) throw new Error(`missing ${what}`);
  return value;
}

/** An element as HTMLElement (for `within`). */
export function html(el: Element | null | undefined): HTMLElement {
  if (!(el instanceof HTMLElement)) throw new Error('missing element');
  return el;
}

/** Text of an element with whitespace collapsed. */
export function textOf(el: Element | null): string {
  return (el?.textContent ?? '').replace(/\s+/g, ' ').trim();
}

/** Wait for the main figure of the 자산 hero. */
export async function findTotal(text: string) {
  return screen.findByText(text, { selector: '.t-display' });
}
