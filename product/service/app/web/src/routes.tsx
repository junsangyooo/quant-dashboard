import type { RouteObject } from 'react-router';
import { AppShell } from './shell/AppShell';
import type { PageHandle } from './shell/page';
import { SetupScreen } from './screens/Auth/SetupScreen';
import { LoginScreen } from './screens/Auth/LoginScreen';
import { RecoverScreen } from './screens/Auth/RecoverScreen';
import { HomeScreen } from './screens/Home/HomeScreen';
import { PlanScreen } from './screens/Plan/PlanScreen';
import { HistoryScreen } from './screens/History/HistoryScreen';
import { BlockEditorScreen } from './screens/BlockEditor/BlockEditorScreen';
import { BacktestV2Screen } from './screens/BacktestV2/BacktestV2Screen';
import {
  PasteScreen,
  StrategiesListScreen,
  StrategyDetailScreen,
} from './screens/StrategiesV2/StrategiesV2';
import { PaperDetailScreen, PaperListScreen, PaperStartScreen } from './screens/PaperV2/PaperV2';
import { SettingsScreen } from './screens/Settings/SettingsScreen';
import { ConnectScreen } from './screens/Settings/ConnectScreen';
import { PasswordScreen } from './screens/Settings/PasswordScreen';
import { AboutScreen, TermsScreen } from './screens/Settings/InfoScreens';
import { NotFoundScreen } from './screens/NotFoundScreen';

const handle = (h: PageHandle) => h;

export const routes: RouteObject[] = [
  {
    element: <AppShell />,
    children: [
      { path: 'setup', element: <SetupScreen />, handle: handle({ page: 'setup', kind: 'auth' }) },
      { path: 'login', element: <LoginScreen />, handle: handle({ page: 'login', kind: 'auth' }) },
      {
        path: 'recover',
        element: <RecoverScreen />,
        handle: handle({ page: 'recover', kind: 'auth' }),
      },
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
      {
        path: 'strategies',
        element: <StrategiesListScreen />,
        handle: handle({ page: 'strategies', kind: 'tab', tab: 'strategies' }),
      },
      {
        path: 'strategies/import',
        element: <PasteScreen />,
        handle: handle({ page: 'import', kind: 'sub', tab: 'strategies' }),
      },
      {
        path: 'strategies/new',
        element: <BlockEditorScreen />,
        handle: handle({ page: 'editor', kind: 'tab', tab: 'strategies' }),
      },
      {
        path: 'strategies/:id',
        element: <StrategyDetailScreen />,
        handle: handle({ page: 'strategy', kind: 'sub', tab: 'strategies' }),
      },
      {
        path: 'strategies/:id/edit',
        element: <BlockEditorScreen />,
        handle: handle({ page: 'editor', kind: 'tab', tab: 'strategies' }),
      },
      {
        path: 'strategies/:id/backtest',
        element: <BacktestV2Screen />,
        handle: handle({ page: 'backtest', kind: 'sub', tab: 'strategies' }),
      },
      {
        path: 'paper',
        element: <PaperListScreen />,
        handle: handle({ page: 'paper', kind: 'tab', tab: 'paper' }),
      },
      {
        path: 'paper/start',
        element: <PaperStartScreen />,
        handle: handle({ page: 'paperStart', kind: 'sub', tab: 'paper' }),
      },
      {
        path: 'paper/:id',
        element: <PaperDetailScreen />,
        handle: handle({ page: 'paperRun', kind: 'sub', tab: 'paper' }),
      },
      {
        path: 'settings',
        element: <SettingsScreen />,
        handle: handle({ page: 'settings', kind: 'sub' }),
      },
      {
        path: 'settings/connect',
        element: <ConnectScreen />,
        handle: handle({ page: 'connect', kind: 'sub' }),
      },
      {
        path: 'settings/password',
        element: <PasswordScreen />,
        handle: handle({ page: 'password', kind: 'sub' }),
      },
      {
        path: 'settings/terms',
        element: <TermsScreen />,
        handle: handle({ page: 'terms', kind: 'sub' }),
      },
      {
        path: 'settings/about',
        element: <AboutScreen />,
        handle: handle({ page: 'about', kind: 'sub' }),
      },
      { path: '*', element: <NotFoundScreen />, handle: handle({ page: 'notFound', kind: 'sub' }) },
    ],
  },
];
