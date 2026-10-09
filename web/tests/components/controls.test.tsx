import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { copy } from '../../src/copy';
import { ConfirmModal } from '../../src/components/ConfirmModal';
import { Checkbox, ModeSwitch, Toggle } from '../../src/components/Controls';
import { EventBand } from '../../src/charts/EventBand';
import { timeScale } from '../../src/charts/geometry/scale';
import { paperEvents } from '../../src/fixtures/charts';

function inRouter(ui: React.ReactNode) {
  const router = createMemoryRouter([{ path: '/', element: ui }], { initialEntries: ['/'] });
  return render(<RouterProvider router={router} />);
}

describe('토글', () => {
  it('is a switch that reports its state', async () => {
    function Harness() {
      const [on, setOn] = useState(false);
      return <Toggle checked={on} onChange={setOn} aria-label="toggle" />;
    }
    render(<Harness />);
    const sw = screen.getByRole('switch', { name: 'toggle' });
    expect(sw).toHaveAttribute('aria-checked', 'false');
    await userEvent.click(sw);
    expect(sw).toHaveAttribute('aria-checked', 'true');
  });
});

describe('체크', () => {
  it('is a native checkbox named by its label', async () => {
    const onChange = vi.fn();
    render(
      <Checkbox checked={false} onChange={onChange}>
        label
      </Checkbox>,
    );
    await userEvent.click(screen.getByRole('checkbox', { name: 'label' }));
    expect(onChange).toHaveBeenCalledWith(true);
  });
});

describe('스위치/모드', () => {
  it('is a radio group; arrows move to the other mode', async () => {
    const onSelect = vi.fn();
    render(<ModeSwitch value="paper" onSelect={onSelect} aria-label="mode" />);
    const paper = screen.getByRole('radio', { name: copy.mode.paper });
    expect(paper).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('radio', { name: copy.mode.live })).toHaveAttribute('tabindex', '-1');
    paper.focus();
    await userEvent.keyboard('{ArrowRight}');
    expect(onSelect).toHaveBeenCalledWith('live');
  });
});

describe('모달/확인', () => {
  it('opens as a modal dialog with the safe action focused; Escape cancels', () => {
    const onCancel = vi.fn();
    render(
      <ConfirmModal
        open
        title="title"
        cancelLabel="cancel"
        confirmLabel="confirm"
        onCancel={onCancel}
        onConfirm={() => undefined}
      >
        body
      </ConfirmModal>,
    );
    const dialog = screen.getByRole('dialog', { name: 'title' });
    expect(dialog).toHaveAttribute('open');
    expect(screen.getByRole('button', { name: 'cancel' })).toHaveFocus();
    dialog.dispatchEvent(new Event('cancel', { cancelable: true }));
    expect(onCancel).toHaveBeenCalledOnce();
  });
});

describe('사건 띠', () => {
  it('renders each event as a labelled link and moves with arrow keys', async () => {
    const x = timeScale('2026-07-07', '2026-10-07', 700);
    inRouter(
      <EventBand
        width={752}
        plotW={700}
        x={x}
        events={paperEvents.filter((e) => e.date >= '2026-07-07')}
        hrefFor={(d) => `/day/${d}`}
        onLegend={() => undefined}
      />,
    );
    const first = screen.getByRole('link', { name: '8/21(금) 리밸런싱' });
    expect(first).toHaveAttribute('href', '/day/2026-08-21');
    expect(screen.getByRole('button', { name: copy.chart.markerLegend })).toBeInTheDocument();
    first.focus();
    await userEvent.keyboard('{ArrowRight}');
    expect(screen.getByRole('link', { name: '9/9(수) 확인 실패' })).toHaveFocus();
  });
});
