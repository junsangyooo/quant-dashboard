// 08 전략 목록(전략 있음 · 빈 상태: 시작하기 4단계 + 예시 카드)과 09 새 전략 시트(빈 캔버스 · 예시에서 시작 ·
// 복사한 전략 붙여 넣기). 새 전략은 저장하지 않고 편집을 연다(저장하면 버전 1).
import clsx from 'clsx';
import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { ChevronRight, CircleCheck, Circle } from 'lucide-react';
import { useExamples, useStrategies } from '../../api/mvp';
import { Button, LinkButton } from '../../components/Buttons';
import { Card } from '../../components/Card';
import { TextField } from '../../components/Field';
import { Sheet } from '../../components/Sheet';
import { VersionTag } from '../../components/Tags';
import { copy } from '../../copy';
import { strategyCopy as t } from '../../copy/strategy';
import { formatMonthDay } from '../../lib/format';
import { Page } from '../../shell/Layout';
import { useDocumentTitle } from '../../shell/page';
import { LoadError } from '../LoadError';
import { ExampleCards, StartSteps } from '../Start/StartParts';
import styles from './Strategies.module.css';

type From = 'blank' | 'example';

export function NewStrategySheet({ onClose }: { onClose: () => void }) {
  const examples = useExamples().data?.examples ?? [];
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [from, setFrom] = useState<From>('example');
  const [ex, setEx] = useState('breakout');
  const s = t.sheet;
  const go = () => {
    const q = new URLSearchParams();
    q.set('start', from);
    if (from === 'example') q.set('example', ex);
    if (name.trim()) q.set('name', name.trim());
    onClose();
    void navigate(`/strategies/new?${q.toString()}`);
  };
  return (
    <Sheet title={s.title} onClose={onClose}>
      <TextField
        label={s.name}
        value={name}
        maxLength={60}
        placeholder={s.namePlaceholder}
        hint={s.nameHint}
        onChange={(e) => {
          setName(e.target.value);
        }}
      />
      <fieldset className={styles.templates}>
        <legend className="t-label">{s.from}</legend>
        <button
          type="button"
          aria-pressed={from === 'blank'}
          className={clsx(styles.template, from === 'blank' && styles.templateOn)}
          onClick={() => {
            setFrom('blank');
          }}
        >
          <span className={styles.templateText}>
            <span className="t-body-strong">{s.blank}</span>
            <span className="t-caption c-muted">{s.blankLine}</span>
          </span>
          {from === 'blank' ? <CircleCheck size={22} className="c-accent" aria-hidden /> : null}
        </button>
        <div className={clsx(styles.template, from === 'example' && styles.templateOn)}>
          <button
            type="button"
            aria-pressed={from === 'example'}
            className={styles.templateHead}
            onClick={() => {
              setFrom('example');
            }}
          >
            <span className={styles.templateText}>
              <span className="t-body-strong">{s.example}</span>
              <span className="t-caption c-muted">{s.exampleLine}</span>
            </span>
            {from === 'example' ? <CircleCheck size={22} className="c-accent" aria-hidden /> : null}
          </button>
          <div className={styles.exList} role="radiogroup" aria-label={s.example}>
            {examples.map((x) => {
              const on = from === 'example' && ex === x.id;
              return (
                <button
                  key={x.id}
                  type="button"
                  role="radio"
                  aria-checked={on}
                  className={clsx(styles.exItem, on && styles.exOn)}
                  onClick={() => {
                    setFrom('example');
                    setEx(x.id);
                  }}
                >
                  {on ? (
                    <CircleCheck size={18} className="c-accent" aria-hidden />
                  ) : (
                    <Circle size={18} className="c-muted" aria-hidden />
                  )}
                  <span className="stack-tight">
                    <span className="t-label">{x.name}</span>
                    <span className="t-caption c-muted">
                      {t.examples.pick(x.summary.mode_name, x.summary.nodes)}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>
        <Link to="/strategies/import" className={styles.template} onClick={onClose}>
          <span className={styles.templateText}>
            <span className="t-body-strong">{s.paste}</span>
            <span className="t-caption c-muted">{s.pasteLine}</span>
          </span>
          <ChevronRight size={20} className="c-muted" aria-hidden />
        </Link>
      </fieldset>
      <Button kind="primary" className="full" onClick={go}>
        {s.create}
      </Button>
      <p className="t-caption c-muted">{s.note}</p>
    </Sheet>
  );
}

export function StrategiesScreen() {
  useDocumentTitle(copy.pages.strategies);
  const q = useStrategies();
  const examples = useExamples().data?.examples ?? [];
  const [search, setSearch] = useSearchParams();
  const [sheet, setSheet] = useState(search.get('new') === '1');
  const navigate = useNavigate();
  if (q.isError) return <LoadError onRetry={() => void q.refetch()} />;
  if (!q.data) return null;
  const list = q.data.strategies;
  const open = () => {
    setSheet(true);
  };
  const close = () => {
    setSheet(false);
    if (search.get('new')) setSearch({}, { replace: true });
  };

  return (
    <Page width="wide">
      <div className={styles.head}>
        <h1 className="t-title">{t.title}</h1>
        {list.length > 0 ? (
          <Button kind="primary" onClick={open}>
            {t.new}
          </Button>
        ) : null}
      </div>
      {list.length === 0 ? (
        <>
          <Card>
            <h2 className="t-heading-1">{t.emptyTitle}</h2>
            <p className="t-body c-muted">{t.emptyBody}</p>
            <div className={styles.emptyButtons}>
              <Button kind="primary" onClick={open}>
                {t.new}
              </Button>
              <Button kind="default" onClick={() => void navigate('/strategies/import')}>
                {t.importLink}
              </Button>
            </div>
          </Card>
          <StartSteps steps={q.data.steps} layout="row" onCreate={open} />
          <ExampleCards examples={examples} columns={2} />
        </>
      ) : (
        <>
          <ul className={styles.list}>
            {list.map((s) => (
              <li key={s.id}>
                <Link to={`/strategies/${String(s.id)}`} className={styles.row}>
                  <span className={styles.rowText}>
                    <span className="t-heading-1">{s.name}</span>
                    {s.latest ? (
                      <span className="t-caption c-muted">
                        {t.rowLine(s.latest.no, s.mode_name, formatMonthDay(s.latest.created_at))}
                      </span>
                    ) : null}
                  </span>
                  {s.latest ? (
                    <VersionTag paper={s.paper !== null} problems={s.latest.problems} />
                  ) : null}
                  <ChevronRight size={20} className="c-muted" aria-hidden />
                </Link>
              </li>
            ))}
          </ul>
          <LinkButton to="/strategies/import">{t.importLink}</LinkButton>
        </>
      )}
      {sheet ? <NewStrategySheet onClose={close} /> : null}
    </Page>
  );
}
