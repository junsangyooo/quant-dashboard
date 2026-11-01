import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Box } from '../../src/components/Box';
import { Checkbox } from '../../src/components/Controls';
import { TextField } from '../../src/components/Field';
import { Sheet } from '../../src/components/Sheet';
import { SideTag, VersionTag } from '../../src/components/Tags';

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

describe('입력 칸', () => {
  it('names the input by its label and shows the error instead of the hint', () => {
    render(<TextField label="name" hint="hint" error="bad" value="" onChange={() => undefined} />);
    const input = screen.getByLabelText('name');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText('bad')).toBeInTheDocument();
    expect(screen.queryByText('hint')).toBeNull();
  });
});

describe('시트', () => {
  it('closes on Escape and on its × button', async () => {
    const onClose = vi.fn();
    render(
      <Sheet title="t" onClose={onClose}>
        body
      </Sheet>,
    );
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole('button'));
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});

describe('칩', () => {
  it('shows the version state in order: 모의투자 중 > 백테스트 가능 > 문제', () => {
    const { rerender } = render(<VersionTag paper problems={3} />);
    expect(screen.getByText('모의투자 중')).toBeInTheDocument();
    rerender(<VersionTag paper={false} problems={0} />);
    expect(screen.getByText('백테스트 가능')).toBeInTheDocument();
    rerender(<VersionTag paper={false} problems={4} />);
    expect(screen.getByText('문제 4개')).toBeInTheDocument();
  });

  it('labels buy and sell', () => {
    render(
      <>
        <SideTag side="buy" />
        <SideTag side="sell" />
      </>,
    );
    expect(screen.getByText('매수')).toBeInTheDocument();
    expect(screen.getByText('매도')).toBeInTheDocument();
  });

  it('box shows its title and lines', () => {
    render(
      <Box tone="warn" title="title">
        line
      </Box>,
    );
    expect(screen.getByText('title')).toBeInTheDocument();
    expect(screen.getByText('line')).toBeInTheDocument();
  });
});
