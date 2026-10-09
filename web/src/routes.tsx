import type { RouteObject } from 'react-router';
import { AppShell } from './shell/AppShell';
import type { PageHandle } from './shell/page';
import { AccountScreen } from './screens/AccountScreen';
import { DayScreen } from './screens/DayScreen';
import { HealthScreen } from './screens/HealthScreen';
import { HistoryScreen } from './screens/HistoryScreen';
import { HomeScreen } from './screens/HomeScreen';
import { ModeScreen } from './screens/ModeScreen';
import { NotFoundScreen } from './screens/NotFoundScreen';
import { PinScreen } from './screens/PinScreen';
import { PlanScreen } from './screens/PlanScreen';
import { RulesScreen } from './screens/RulesScreen';

const handle = (h: PageHandle) => h;

function KitLoading() {
  return null;
}

/** DEV-only component gallery; the import is dropped from production builds. */
const devRoutes: RouteObject[] = import.meta.env.DEV
  ? [
      {
        path: '/_kit',
        // Rendered while the lazy chunk loads on a direct visit.
        HydrateFallback: KitLoading,
        lazy: async () => {
          const { KitGallery } = await import('./kit/KitGallery');
          return { Component: KitGallery };
        },
      },
    ]
  : [];

export const routes: RouteObject[] = [
  { path: '/pin', element: <PinScreen />, handle: handle({ page: 'pin', kind: 'sub' }) },
  {
    element: <AppShell />,
    children: [
      {
        index: true,
        element: <HomeScreen />,
        handle: handle({ page: 'home', kind: 'tab', tab: 'home' }),
      },
      {
        path: 'plan',
        element: <PlanScreen />,
        handle: handle({ page: 'plan', kind: 'tab', tab: 'plan' }),
      },
      {
        path: 'history',
        element: <HistoryScreen />,
        handle: handle({ page: 'history', kind: 'tab', tab: 'history' }),
      },
      { path: 'day/:date', element: <DayScreen />, handle: handle({ page: 'day', kind: 'sheet' }) },
      {
        path: 'rules/:ruleId?',
        element: <RulesScreen />,
        handle: handle({ page: 'rules', kind: 'tab', tab: 'rules' }),
      },
      {
        path: 'health',
        element: <HealthScreen />,
        handle: handle({ page: 'health', kind: 'sub' }),
      },
      { path: 'mode', element: <ModeScreen />, handle: handle({ page: 'mode', kind: 'sub' }) },
      {
        path: 'account',
        element: <AccountScreen />,
        handle: handle({ page: 'account', kind: 'sub' }),
      },
    ],
  },
  ...devRoutes,
  { path: '*', element: <NotFoundScreen /> },
];
