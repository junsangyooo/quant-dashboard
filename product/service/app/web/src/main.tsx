import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClientProvider } from '@tanstack/react-query';
import { createBrowserRouter } from 'react-router';
import { RouterProvider } from 'react-router/dom';
import { configureClient } from './api/client';
import { createQueryClient, keys } from './api/query';
import { routes } from './routes';
import './styles/pretendard.css';
import './styles/tokens.css';
import './styles/global.css';
import './styles/mvp.css';

const container = document.getElementById('root');
if (!container) throw new Error('#root is missing from index.html');

const router = createBrowserRouter(routes);
const queryClient = createQueryClient();

// The session is gone (expired, 잠그기 in another tab, or the app restarted) → 로그인.
configureClient({
  onLoginRequired: () => {
    void queryClient.invalidateQueries({ queryKey: keys.state });
    if (!['/login', '/setup', '/recover'].includes(window.location.pathname)) {
      void router.navigate('/login', { replace: true });
    }
  },
});

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
