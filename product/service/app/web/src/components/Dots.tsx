// '·'로 이은 묶음: 묶음 하나(금액 + 단위, '매도 16', '평균 149,022원')는 줄을 바꾸지 않고, 넘치면
// 묶음 단위로 다음 줄로 내린다.
import { Fragment, type ReactNode } from 'react';

export function Dots({ parts }: { parts: readonly ReactNode[] }) {
  const shown = parts.filter((p) => p !== null && p !== undefined && p !== '' && p !== false);
  return (
    <>
      {shown.map((p, i) => (
        <Fragment key={i}>
          {i > 0 ? ' · ' : null}
          <span className="nw">{p}</span>
        </Fragment>
      ))}
    </>
  );
}
