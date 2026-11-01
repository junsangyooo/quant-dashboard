// 시작하기 4단계(API 키 연결(선택) · 전략 만들기 · 백테스트 · 모의투자 시작)와 예시 전략 카드 4개.
// 자산(모의투자 전) · 전략 목록(빈 상태)이 같이 쓴다.
import clsx from 'clsx';
import { Link } from 'react-router';
import { ChevronRight, Circle, CircleCheck } from 'lucide-react';
import type { ExampleView, Steps } from '../../api/mvp';
import { LinkButton } from '../../components/Buttons';
import { strategyCopy } from '../../copy/strategy';
import styles from './Start.module.css';

const s = strategyCopy.steps;
const e = strategyCopy.examples;

export function StartSteps({
  steps,
  layout,
  onCreate,
}: {
  steps: Steps;
  layout: 'column' | 'row';
  /** '전략 만들기 ›'(전략 목록에서는 새 전략 시트, 자산에서는 전략 목록으로). */
  onCreate?: (() => void) | undefined;
}) {
  const done = [steps.connected, steps.strategies > 0, steps.backtested, steps.papered];
  const count = done.filter(Boolean).length;
  const current = [1, 2, 3].find((i) => !done[i]) ?? -1;
  const latest = steps.latest_strategy;
  const links: (string | null)[] = [
    '/settings/connect',
    '/strategies',
    latest !== null ? `/strategies/${String(latest)}/backtest` : '/strategies',
    latest !== null ? `/strategies/${String(latest)}` : '/strategies',
  ];
  return (
    <section className={styles.steps} aria-label={s.title}>
      <div className={styles.stepsHead}>
        <h2 className="t-heading-1">{s.title}</h2>
        <span className="t-caption">{s.done(count)}</span>
      </div>
      {layout === 'column' ? <p className="t-caption c-muted">{s.lead}</p> : null}
      <ol className={clsx(styles.stepList, layout === 'row' && styles.stepRow)}>
        {s.rows.map((row, i) => {
          const isDone = done[i] ?? false;
          const isCur = i === current;
          const showLink = isCur || (i === 0 && !isDone);
          return (
            <li key={row.title} className={clsx(styles.step, isCur && styles.stepCur)}>
              {isDone ? (
                <CircleCheck size={20} className="c-success" aria-hidden />
              ) : (
                <Circle size={20} className={isCur ? 'c-accent' : 'c-muted'} aria-hidden />
              )}
              <div className="stack-tight">
                <span className="t-body-strong">{row.title}</span>
                <span className="t-caption c-muted">{isDone ? row.done : row.todo}</span>
                {showLink && !isDone ? (
                  i === 1 && onCreate ? (
                    <LinkButton onClick={onCreate}>{row.link}</LinkButton>
                  ) : (
                    <LinkButton to={links[i] ?? '/strategies'}>{row.link}</LinkButton>
                  )
                ) : null}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

export function ExampleCards({ examples, columns }: { examples: ExampleView[]; columns: 1 | 2 }) {
  return (
    <section className="stack-row" aria-label={e.title}>
      <div className="stack-tight">
        <h2 className="t-heading-1">{e.title}</h2>
        <p className="t-caption c-muted">{e.lead}</p>
      </div>
      <ul className={clsx(styles.cards, columns === 2 && styles.cards2)}>
        {examples.map((x) => (
          <li key={x.id}>
            <Link to={`/examples/${x.id}`} className={styles.card}>
              <span className={styles.cardHead}>
                <span className={clsx('t-caption', styles.exChip)}>{e.chip}</span>
                <span className="t-heading-1">{x.name}</span>
                <ChevronRight size={20} className={clsx('c-muted', styles.cardChev)} aria-hidden />
              </span>
              <span className="t-label c-accent">{x.summary.mode_name}</span>
              <span className="t-caption">{x.line}</span>
              <span className="t-caption c-muted">
                {e.meta(x.summary.nodes, x.summary.entry, x.summary.sell)}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function ExampleChip() {
  return <span className={clsx('t-caption', styles.exChip)}>{e.chip}</span>;
}
