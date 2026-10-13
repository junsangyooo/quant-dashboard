import { lazy, type ComponentType, type LazyExoticComponent } from 'react';
import type { RouteObject } from 'react-router';
import { AppShell } from './shell/AppShell';
import type { PageHandle } from './shell/page';
import { NotFoundScreen } from './screens/NotFoundScreen';
import { PinScreen } from './screens/Pin/PinScreen';

const handle = (h: PageHandle) => h;

/**
 * The signed-in screens are a chunk each; the entry keeps the shell, the PIN page and 404.
 * main.tsx loads the screen of the address before the first render (createRoutes(loaded)), so the
 * shell and that screen paint together as with one bundle, and the screen's reads start with the
 * shell's. The others are lazy: a move keeps the old screen up until the new one is ready (the
 * router's transition), and their chunks load in the background once the page has loaded.
 */
const load = {
  home: () => import('./screens/Home/HomeScreen').then((m) => m.HomeScreen),
  plan: () => import('./screens/Plan/PlanScreen').then((m) => m.PlanScreen),
  // /history and /day/:date render this one component (Day/DayScreen.tsx): one entry keeps it
  // the same component across the two, so the page keeps its scroll and state.
  history: () => import('./screens/History/HistoryScreen').then((m) => m.HistoryScreen),
  rules: () => import('./screens/Rules/RulesScreen').then((m) => m.RulesScreen),
  health: () => import('./screens/Health/HealthScreen').then((m) => m.HealthScreen),
  mode: () => import('./screens/Mode/ModeScreen').then((m) => m.ModeScreen),
  account: () => import('./screens/Account/AccountScreen').then((m) => m.AccountScreen),
} satisfies Record<string, () => Promise<ComponentType>>;

export type ScreenKey = keyof typeof load;
export type LoadedScreens = Partial<Record<ScreenKey, ComponentType>>;

const KEYS = Object.keys(load) as ScreenKey[];

// One lazy component per screen for the life of the page (a stable component type).
const lazyOf = (key: ScreenKey): LazyExoticComponent<ComponentType> =>
  lazy(() => load[key]().then((c) => ({ default: c })));
const lazyScreens: Record<ScreenKey, LazyExoticComponent<ComponentType>> = {
  home: lazyOf('home'),
  plan: lazyOf('plan'),
  history: lazyOf('history'),
  rules: lazyOf('rules'),
  health: lazyOf('health'),
  mode: lazyOf('mode'),
  account: lazyOf('account'),
};

/** The screen an address opens (its first segment), or null (PIN, 404). */
export function screenOf(pathname: string): ScreenKey | null {
  const first = pathname.split('/')[1] ?? '';
  if (first === '') return 'home';
  if (first === 'day') return 'history';
  return KEYS.find((key) => key === first) ?? null;
}

/** Loads these screens' chunks; the components, for createRoutes. */
export async function loadScreens(keys: readonly ScreenKey[]): Promise<LoadedScreens> {
  const loaded = await Promise.all(keys.map(async (key) => [key, await load[key]()] as const));
  return Object.fromEntries(loaded) as LoadedScreens;
}

/** Loads every screen's chunk (once the page has loaded), so a later move opens at once. */
export function prefetchScreens(): Promise<LoadedScreens> {
  return loadScreens(KEYS);
}

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

/** The route table: a loaded screen renders at once, the others are lazy (AppShell's Suspense). */
export function createRoutes(loaded: LoadedScreens = {}): RouteObject[] {
  const screen = (key: ScreenKey) => {
    const Component = loaded[key] ?? lazyScreens[key];
    return <Component />;
  };
  return [
    { path: '/pin', element: <PinScreen />, handle: handle({ page: 'pin', kind: 'sub' }) },
    {
      element: <AppShell />,
      children: [
        {
          index: true,
          element: screen('home'),
          handle: handle({ page: 'home', kind: 'tab', tab: 'home' }),
        },
        {
          path: 'plan',
          element: screen('plan'),
          handle: handle({ page: 'plan', kind: 'tab', tab: 'plan' }),
        },
        {
          path: 'history',
          element: screen('history'),
          handle: handle({ page: 'history', kind: 'tab', tab: 'history' }),
        },
        // Same component as 기록: from 1100px the panel opens over the 기록 page (frame and tab of
        // 기록); below that a full-height modal sheet covers the frame.
        {
          path: 'day/:date',
          element: screen('history'),
          handle: handle({ page: 'day', kind: 'tab', tab: 'history' }),
        },
        {
          path: 'rules/:ruleId?',
          element: screen('rules'),
          handle: handle({ page: 'rules', kind: 'tab', tab: 'rules' }),
        },
        {
          path: 'health',
          element: screen('health'),
          handle: handle({ page: 'health', kind: 'sub' }),
        },
        { path: 'mode', element: screen('mode'), handle: handle({ page: 'mode', kind: 'sub' }) },
        {
          path: 'account',
          element: screen('account'),
          handle: handle({ page: 'account', kind: 'sub' }),
        },
      ],
    },
    ...devRoutes,
    { path: '*', element: <NotFoundScreen /> },
  ];
}

/** Every screen lazy (the tests' table; main.tsx passes the screen it loaded first). */
export const routes: RouteObject[] = createRoutes();
