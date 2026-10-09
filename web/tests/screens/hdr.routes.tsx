// 기록 · 그날 · 규칙 inside the real AppShell (header, banner), without the other screens: these
// tests do not depend on how far the other screens have come.
import { screen } from '@testing-library/react';
import type { RouteObject } from 'react-router';
import { vi } from 'vitest';
import { DayScreen } from '../../src/screens/Day/DayScreen';
import { HistoryScreen } from '../../src/screens/History/HistoryScreen';
import { RulesScreen } from '../../src/screens/Rules/RulesScreen';
import { AppShell } from '../../src/shell/AppShell';
import type { FixtureBundle } from '../../src/fixtures/types';
import { answerFrom, renderRoutes } from '../helpers';

function Placeholder({ name }: { name: string }) {
  return <h1>{name}</h1>;
}

export const hdrRoutes: RouteObject[] = [
  { path: '/pin', element: <Placeholder name="pin" /> },
  {
    element: <AppShell />,
    children: [
      {
        index: true,
        element: <Placeholder name="home" />,
        handle: { page: 'home', kind: 'tab', tab: 'home' },
      },
      {
        path: 'plan',
        element: <Placeholder name="plan" />,
        handle: { page: 'plan', kind: 'tab', tab: 'plan' },
      },
      {
        path: 'history',
        element: <HistoryScreen />,
        handle: { page: 'history', kind: 'tab', tab: 'history' },
      },
      {
        path: 'day/:date',
        element: <DayScreen />,
        handle: { page: 'day', kind: 'tab', tab: 'history' },
      },
      {
        path: 'rules/:ruleId?',
        element: <RulesScreen />,
        handle: { page: 'rules', kind: 'tab', tab: 'rules' },
      },
      {
        path: 'health',
        element: <Placeholder name="health" />,
        handle: { page: 'health', kind: 'sub' },
      },
    ],
  },
];

export function renderState(bundle: FixtureBundle, path: string) {
  answerFrom(bundle);
  return renderRoutes(hdrRoutes, path);
}

/** A matchMedia that answers like a viewport `width` px wide (jsdom has none). */
export function viewport(width: number) {
  const match = (query: string) => {
    const m = /min-width:\s*(\d+)px/.exec(query);
    return m ? width >= Number(m[1]) : false;
  };
  vi.stubGlobal(
    'matchMedia',
    (query: string): MediaQueryList =>
      ({
        matches: match(query),
        media: query,
        onchange: null,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
        addListener: () => undefined,
        removeListener: () => undefined,
        dispatchEvent: () => false,
      }) as MediaQueryList,
  );
}

/** Text of an element with whitespace collapsed (several spans read as one line). */
export function textOf(el: Element | null): string {
  return (el?.textContent ?? '').replace(/\s+/g, ' ').trim();
}

export async function findText(text: string | RegExp) {
  return screen.findByText(text, undefined, { timeout: 3000 });
}

/** The big total of a card (type/title), e.g. 자산 변동 or 그날 자산. */
export async function findTotal(text: string) {
  return screen.findByText(text, { selector: '.t-title' }, { timeout: 3000 });
}
