// 처음 실행 마법사 틀(그림 V2-01 ~ V2-09): '이전' · 단계 막대 n/7 · '처음 실행' · 제목 · 설명 · 두 칸.
// 설정 v2 화면(V2-52 · V2-53 · V2-55 · V2-56)도 같은 두 칸(왼쪽 776 · 오른쪽 400)을 써요.
import clsx from 'clsx';
import type { ReactNode } from 'react';
import { ChevronRight, CircleCheck, CircleX, Clock, Info } from 'lucide-react';
import { setupV2 as t } from '../../copy/setupV2';
import { BackLink } from '../../shell/Layout';
import styles from './Wizard.module.css';

export { styles as wizardStyles };

export function StepBar({ step }: { step: number }) {
  return (
    <div className={styles.steps}>
      <p className={clsx(styles.stepLabel, 't-label')}>
        <span className={styles.stepNo}>{t.stepOf(step)}</span>
        <span>{t.steps[step - 1]}</span>
      </p>
      <div className={styles.bar} aria-hidden>
        {t.steps.map((name, i) => (
          <span key={name} className={clsx(styles.seg, i < step && styles.segOn)} />
        ))}
      </div>
    </div>
  );
}

export function WizardPage({
  step,
  back,
  title,
  lead,
  main,
  side,
}: {
  step?: number | undefined;
  back?: { to: string; label: string } | undefined;
  title: ReactNode;
  lead?: ReactNode;
  main: ReactNode;
  side?: ReactNode;
}) {
  return (
    <div className={styles.page}>
      {back ? <BackLink to={back.to}>{back.label}</BackLink> : null}
      {step ? <StepBar step={step} /> : null}
      <div className={styles.head}>
        {step ? <p className={clsx(styles.eyebrow, 't-label')}>{t.eyebrow}</p> : null}
        <h1 className="t-title">{title}</h1>
        {lead ? <p className={clsx(styles.lead, 't-body')}>{lead}</p> : null}
      </div>
      <div className={styles.cols}>
        <div className={styles.main}>{main}</div>
        {side ? <div className={styles.side}>{side}</div> : null}
      </div>
    </div>
  );
}

export function Panel({
  title,
  action,
  tone = 'subtle',
  children,
}: {
  title?: ReactNode;
  action?: ReactNode;
  tone?: 'subtle' | 'outline';
  children?: ReactNode;
}) {
  return (
    <section className={tone === 'subtle' ? styles.card : styles.outline}>
      {title !== undefined || action ? (
        <div className={styles.cardHead}>
          {title !== undefined ? <h2 className="t-heading-1">{title}</h2> : <span />}
          {action}
        </div>
      ) : null}
      {children}
    </section>
  );
}

export function HowTo({
  title,
  steps,
  note,
}: {
  title: string;
  steps: readonly string[];
  note?: ReactNode;
}) {
  return (
    <Panel title={title} tone="outline">
      <ol className={styles.howList}>
        {steps.map((s, i) => (
          <li key={s} className={clsx(styles.howItem, 't-body')}>
            <span className={clsx(styles.num, 't-caption')}>{i + 1}</span>
            <span>{s}</span>
          </li>
        ))}
      </ol>
      {note ? <Note>{note}</Note> : null}
    </Panel>
  );
}

export function Note({ children }: { children: ReactNode }) {
  return (
    <p className={clsx(styles.status, styles.muted, 't-caption')}>
      <Info size={16} aria-hidden />
      <span>{children}</span>
    </p>
  );
}

export function Status({ kind, children }: { kind: 'ok' | 'bad' | 'wait'; children: ReactNode }) {
  const Icon = kind === 'ok' ? CircleCheck : kind === 'bad' ? CircleX : Clock;
  return (
    <p className={clsx(styles.status, 't-body')}>
      <Icon
        size={20}
        aria-hidden
        className={kind === 'ok' ? styles.statusOk : kind === 'bad' ? styles.statusBad : undefined}
      />
      <span>{children}</span>
    </p>
  );
}

export function TextLink({
  href,
  onClick,
  children,
}: {
  href?: string;
  onClick?: () => void;
  children: ReactNode;
}) {
  if (href)
    return (
      <a className={clsx(styles.link, 't-label')} href={href} target="_blank" rel="noreferrer">
        {children}
        <ChevronRight size={16} aria-hidden />
      </a>
    );
  return (
    <button type="button" className={clsx(styles.link, 't-label')} onClick={onClick}>
      {children}
      <ChevronRight size={16} aria-hidden />
    </button>
  );
}
