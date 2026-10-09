import type { RouteObject } from 'react-router';
import { AppShell } from './shell/AppShell';
import type { PageHandle } from './shell/page';
import { AccountScreen } from './screens/Account/AccountScreen';
import { DayScreen } from './screens/Day/DayScreen';
import { HealthScreen } from './screens/Health/HealthScreen';
import { HistoryScreen } from './screens/History/HistoryScreen';
import { HomeScreen } from './screens/Home/HomeScreen';
import { ModeScreen } from './screens/Mode/ModeScreen';
import { NotFoundScreen } from './screens/NotFoundScreen';
import { PinScreen } from './screens/Pin/PinScreen';
import { PlanScreen } from './screens/Plan/PlanScreen';
import { RulesScreen } from './screens/Rules/RulesScreen';

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
      // Same component as 기록: from 1100px the panel opens over the 기록 page (frame and tab of
      // 기록); below that a full-height modal sheet covers the frame.
      {
        path: 'day/:date',
        element: <DayScreen />,
        handle: handle({ page: 'day', kind: 'tab', tab: 'history' }),
      },
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
