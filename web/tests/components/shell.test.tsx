import { render, screen, within } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { describe, expect, it } from 'vitest';
import { copy } from '../../src/copy';
import { routes } from '../../src/routes';

function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(<RouterProvider router={router} />);
}

describe('app shell', () => {
  it('starts with a skip link to the main region', () => {
    renderAt('/');
    const skip = screen.getByRole('link', { name: copy.skipLink });
    expect(skip).toHaveAttribute('href', '#main');
    expect(document.getElementById('main')?.tagName).toBe('MAIN');
  });

  it('shows the header: wordmark, mode badge → 모드, status chip → 작동, gear → 설정', () => {
    renderAt('/');
    const header = screen.getByRole('banner');
    expect(within(header).getByText(copy.wordmark)).toBeInTheDocument();
    expect(within(header).getByRole('link', { name: copy.mode.paper })).toHaveAttribute(
      'href',
      '/mode',
    );
    expect(
      within(header).getByRole('link', { name: copy.headerStatus.ok('08:30') }),
    ).toHaveAttribute('href', '/health');
    expect(within(header).getByRole('link', { name: copy.settings })).toHaveAttribute(
      'href',
      '/account',
    );
  });

  it.each([
    ['/', copy.nav.home],
    ['/plan', copy.nav.plan],
    ['/history', copy.nav.history],
    ['/rules', copy.nav.rules],
    ['/rules/index-half', copy.nav.rules],
  ])('marks the current tab on %s', (path, label) => {
    renderAt(path);
    const current = screen.getAllByRole('link', { current: 'page' });
    expect(current.length).toBeGreaterThan(0);
    for (const link of current) expect(link).toHaveTextContent(label);
    expect(screen.getByRole('heading', { level: 1, name: label })).toBeInTheDocument();
  });

  it('renders the four bottom tabs on tab pages', () => {
    renderAt('/plan');
    const navs = screen.getAllByRole('navigation');
    const bottom = navs.find(
      (n) => within(n).queryAllByRole('link').length === 4 && n.querySelector('svg'),
    );
    expect(bottom).toBeDefined();
  });

  it.each([
    ['/health', copy.pages.health],
    ['/mode', copy.pages.mode],
    ['/account', copy.pages.account],
  ])('renders %s as a sub-page: ‹ title, no bottom tabs', (path, title) => {
    renderAt(path);
    expect(screen.getByRole('heading', { level: 1, name: title })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: copy.back })).toHaveAttribute('href', '/');
    // Only the header nav remains (bottom tab bar is not rendered).
    expect(screen.getAllByRole('navigation')).toHaveLength(1);
  });

  it('renders the day panel with the date as its title and × back to 기록', () => {
    renderAt('/day/2026-08-21');
    expect(screen.getByRole('heading', { level: 1, name: '8/21(금)' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: copy.close })).toHaveAttribute('href', '/history');
    expect(screen.getAllByRole('navigation')).toHaveLength(1);
  });

  it('renders the PIN page without the shell', () => {
    renderAt('/pin');
    expect(screen.queryByRole('banner')).toBeNull();
    expect(screen.getByRole('heading', { level: 1, name: copy.wordmark })).toBeInTheDocument();
    expect(screen.getByText(copy.pin.prompt)).toBeInTheDocument();
  });

  it('answers unknown paths with the wordmark only', () => {
    renderAt('/nope');
    expect(screen.getByRole('heading', { level: 1, name: copy.wordmark })).toBeInTheDocument();
    expect(screen.queryAllByRole('link')).toHaveLength(0);
  });
});
