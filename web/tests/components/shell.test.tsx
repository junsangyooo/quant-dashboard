import { screen, within } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { copy } from '../../src/copy';
import homePaper from '../../src/fixtures/bundles/home.paper';
import { prefetchScreens, routes } from '../../src/routes';
import { answerFrom, renderRoutes } from '../helpers';

function renderAt(path: string) {
  return renderRoutes(routes, path);
}

// The screens are lazy chunks: load their modules once, so each test waits for a render only.
beforeAll(async () => {
  await prefetchScreens();
});

beforeEach(() => {
  answerFrom(homePaper);
});

describe('app shell', () => {
  it('starts with a skip link to the main region', () => {
    renderAt('/');
    const skip = screen.getByRole('link', { name: copy.skipLink });
    expect(skip).toHaveAttribute('href', '#main');
    expect(document.getElementById('main')?.tagName).toBe('MAIN');
  });

  it('shows the header: wordmark, mode badge → 모드, status chip → 작동, gear → 설정', async () => {
    renderAt('/');
    const header = screen.getByRole('banner');
    expect(within(header).getByText(copy.wordmark)).toBeInTheDocument();
    // Mode and status come from /api/shell (fixture home.paper: 모의투자, checked 08:30).
    expect(await within(header).findByRole('link', { name: copy.mode.paper })).toHaveAttribute(
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
  ])('marks the current tab on %s', async (path, label) => {
    renderAt(path);
    const current = screen.getAllByRole('link', { current: 'page' });
    expect(current.length).toBeGreaterThan(0);
    for (const link of current) expect(link).toHaveTextContent(label);
    // The screen is a lazy chunk (routes.tsx): its title comes when the chunk is in, by when the
    // fixture's data may be there too ('모의투자 기록 · 2026' on 기록).
    expect(
      await screen.findByRole('heading', { level: 1, name: new RegExp(label) }),
    ).toBeInTheDocument();
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
  ])('renders %s as a sub-page: ‹ title, no bottom tabs', async (path, title) => {
    renderAt(path);
    expect(await screen.findByRole('heading', { level: 1, name: title })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: copy.back })).toHaveAttribute('href', '/');
    // Only the header nav remains (bottom tab bar is not rendered).
    expect(screen.getAllByRole('navigation')).toHaveLength(1);
  });

  it('renders the day panel with the date as its title and × back to 기록', async () => {
    renderAt('/day/2026-08-21');
    expect(await screen.findByRole('heading', { level: 1, name: '8/21(금)' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: copy.close })).toHaveAttribute('href', '/history');
    // 그날 opens over 기록 (1440 panel; below 1100px a modal sheet over the frame), so the frame
    // stays that of the 기록 tab.
    const current = screen.getAllByRole('link', { current: 'page' });
    expect(current.length).toBeGreaterThan(0);
    for (const link of current) expect(link).toHaveTextContent(copy.nav.history);
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
