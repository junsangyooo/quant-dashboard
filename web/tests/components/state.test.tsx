import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ShellResponse } from '../../src/api/types';
import {
  ErrorBlock,
  ExampleChip,
  ShellBanner,
  Skeleton,
  SkeletonBlock,
  StaleMark,
} from '../../src/components/State';
import homePaper from '../../src/fixtures/bundles/home.paper';
import type { FixtureBundle } from '../../src/fixtures/types';
import { answerFrom, renderWithData } from '../helpers';

const paperShell: ShellResponse = homePaper.responses['/api/shell'];

function withBanner(banner: ShellResponse['banner']): FixtureBundle {
  return {
    id: 'home.stale',
    now: paperShell.now,
    responses: { '/api/shell': { ...paperShell, banner } },
  };
}

describe('ShellBanner', () => {
  it('shows the server banner with its move link', async () => {
    answerFrom(
      withBanner({
        kind: 'stale',
        market: 'US',
        basisDate: '2026-10-02',
        tradingDays: 2,
        link: 'health',
      }),
    );
    renderWithData(<ShellBanner />, '/');
    expect(
      await screen.findByText('미국 시세 10/2 기준 · 2거래일째 갱신 없음'),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '작동 보기' })).toHaveAttribute('href', '/health');
  });

  it('drops the link on the page it points to', async () => {
    answerFrom(
      withBanner({
        kind: 'stale',
        market: 'US',
        basisDate: '2026-10-02',
        tradingDays: 2,
        link: 'health',
      }),
    );
    renderWithData(<ShellBanner />, '/health');
    expect(
      await screen.findByText('미국 시세 10/2 기준 · 2거래일째 갱신 없음'),
    ).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('renders nothing without a banner', async () => {
    answerFrom(homePaper);
    const { container, client } = renderWithData(<ShellBanner />);
    await vi.waitFor(() => {
      expect(client.getQueryData(['shell'])).toBeDefined();
    });
    expect(container).toBeEmptyDOMElement();
  });
});

describe('small states', () => {
  it('hides skeletons from assistive tech', () => {
    const { container } = render(
      <>
        <Skeleton text="display" width={120} />
        <SkeletonBlock height={160} />
      </>,
    );
    for (const el of Array.from(container.children))
      expect(el).toHaveAttribute('aria-hidden', 'true');
  });

  it('shows 예시 only for example data', () => {
    const { rerender } = render(<ExampleChip show />);
    expect(screen.getByText('예시')).toBeInTheDocument();
    rerender(<ExampleChip show={false} />);
    expect(screen.queryByText('예시')).not.toBeInTheDocument();
  });

  it('puts one 낡음 tag on a stale section', () => {
    render(
      <>
        <StaleMark stale={['plan']} section="hero" />
        <StaleMark stale={['plan']} section="plan" />
      </>,
    );
    expect(screen.getAllByText('낡음')).toHaveLength(1);
  });

  it('retries from the error block', () => {
    const onRetry = vi.fn();
    const { rerender } = render(<ErrorBlock message="기록을 못 불러왔어요" onRetry={onRetry} />);
    fireEvent.click(screen.getByRole('button', { name: '다시 불러오기' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
    rerender(<ErrorBlock message="기록을 못 불러왔어요" onRetry={onRetry} retrying />);
    expect(screen.getByRole('button', { name: '다시 불러오기' })).toBeDisabled();
  });
});
