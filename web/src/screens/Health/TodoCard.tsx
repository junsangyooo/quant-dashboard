// 할 일 카드 (1:38782 · 1:46904 · 1:47501): red = 실패·낡음, yellow = 만료 예정. Head icon + what ·
// when → chip (자동 재시도 [시각] / 직접 할 일) → two 해요체 lines → a small result line.
import clsx from 'clsx';
import { Fragment } from 'react';
import {
  ArrowLeftRight,
  BellOff,
  Bot,
  CircleX,
  ClockAlert,
  FileText,
  Scale,
  TriangleAlert,
  Unplug,
  UserX,
  type LucideIcon,
} from 'lucide-react';
import { SignalChip } from '../../components/Chips';
import { todoView, type Todo, type TodoView } from './text';
import styles from './Health.module.css';

const ICON: Record<TodoView['icon'], LucideIcon> = {
  stale: TriangleAlert,
  failed: CircleX,
  expiring: ClockAlert,
  push: BellOff,
  ai: Bot,
  filings: FileText,
  pin: UserX, // the 'PIN 실패 급증' icon of the notification settings
  link: Unplug, // 토스 연결 (3단계)
  mismatch: Scale, // 토스 잔고 불일치
  fx: ArrowLeftRight, // 토스 앱에서 환전 (the preview's 환전 icon)
};

export function TodoCard({ todo, now }: { todo: Todo; now: string | null }) {
  const view = todoView(todo, now);
  const Icon = ICON[view.icon];
  const titleId = `todo-${todo.id}`;
  return (
    <article
      id={`todo-${encodeURIComponent(todo.id)}`}
      className={clsx(styles.todo, styles[`todo-${view.tone}`])}
      aria-labelledby={`${titleId}-title`}
    >
      <div className={styles.todoHead}>
        <Icon size={20} className={styles[`tone-${view.tone}`]} aria-hidden />
        <h3 id={`${titleId}-title`} className="t-body-strong">
          {view.title}
        </h3>
      </div>
      <SignalChip kind={view.tone}>{view.chip}</SignalChip>
      <p className="t-body">
        {view.lines.map((line, i) => (
          <Fragment key={line}>
            {i > 0 ? <br /> : null}
            {line}
          </Fragment>
        ))}
      </p>
      {view.result ? <p className={clsx('t-caption', styles.muted)}>{view.result}</p> : null}
    </article>
  );
}
