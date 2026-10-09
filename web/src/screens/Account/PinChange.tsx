// PIN 바꾸기 (Figma 1:65384 row; the open form is not drawn): key icon · 'PIN 바꾸기' · ⌄ and a grey
// line; open, three PIN fields (현재 · 새 · 새 다시) and 바꾸기. Wrong current PIN → '현재 PIN이 맞지
// 않아요' (that field clears); the two new ones differ → '두 PIN이 달라요'. Done → '바꿨어요 · 다른 기기
// 로그아웃됨' (the server ends every other session).
import clsx from 'clsx';
import { useId, useState } from 'react';
import { ChevronDown, ChevronUp, KeyRound, LoaderCircle } from 'lucide-react';
import { accountCopy as t } from '../../copy/account';
import { pinCopy } from '../../copy/pin';
import { isApiError } from '../../api/client';
import { useChangePin } from '../../api/queries';
import { Button } from '../../components/Buttons';
import { formatTime } from '../../lib/format';
import { PIN_LENGTH, PinField } from '../Pin/PinField';
import styles from './Account.module.css';

type Field = 'current' | 'next' | 'again';

function bodyField(error: unknown, key: string): unknown {
  if (!isApiError(error) || !error.body) return undefined;
  return (error.body as unknown as Record<string, unknown>)[key];
}

export function PinChangeCard() {
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState<Record<Field, string>>({ current: '', next: '', again: '' });
  const [error, setError] = useState<{ text: string; field: Field | null } | null>(null);
  const [done, setDone] = useState(false);
  const change = useChangePin();
  const formId = useId();
  const ids = { current: useId(), next: useId(), again: useId() };
  const messageId = useId();
  const busy = change.isPending;
  const ready = !busy && Object.values(values).every((v) => v.length === PIN_LENGTH);

  const set = (field: Field) => (value: string) => {
    setDone(false);
    if (error?.field === field) setError(null);
    setValues((v) => ({ ...v, [field]: value }));
  };

  const submit = () => {
    if (!ready) return;
    if (values.next !== values.again) {
      setError({ text: t.pin.mismatch, field: 'again' });
      setValues((v) => ({ ...v, again: '' }));
      return;
    }
    setError(null);
    change.mutate(
      { current: values.current, next: values.next },
      {
        onSuccess: () => {
          setDone(true);
          setValues({ current: '', next: '', again: '' });
        },
        onError: (e) => {
          if (isApiError(e, 'current-pin')) {
            setError({ text: t.pin.wrongCurrent, field: 'current' });
            setValues((v) => ({ ...v, current: '' }));
          } else if (isApiError(e, 'locked')) {
            const raw = bodyField(e, 'until');
            const until = typeof raw === 'string' ? Date.parse(raw) : Number.NaN;
            const global = bodyField(e, 'scope') === 'global';
            setError({
              text: Number.isFinite(until)
                ? global
                  ? pinCopy.lockedEverywhere(Math.max(1, Math.ceil((until - Date.now()) / 60_000)))
                  : pinCopy.lockedHere(formatTime(new Date(until)))
                : t.pin.failed,
              field: null,
            });
            setValues({ current: '', next: '', again: '' });
          } else if (isApiError(e, 'invalid-pin')) {
            setError({ text: t.pin.invalid, field: 'next' });
            setValues((v) => ({ ...v, next: '', again: '' }));
          } else {
            setError({ text: t.pin.failed, field: null });
          }
        },
      },
    );
  };

  const fields: { key: Field; label: string; auto: 'current-password' | 'new-password' }[] = [
    { key: 'current', label: t.pin.current, auto: 'current-password' },
    { key: 'next', label: t.pin.next, auto: 'new-password' },
    { key: 'again', label: t.pin.again, auto: 'new-password' },
  ];

  return (
    <section className={clsx(styles.card, styles.pinCard)} aria-label={t.pin.title}>
      <button
        type="button"
        className={styles.pinToggle}
        aria-expanded={open}
        aria-controls={open ? formId : undefined}
        onClick={() => {
          setOpen((o) => !o);
        }}
      >
        <KeyRound size={20} aria-hidden />
        <span className={clsx('t-body-strong', styles.grow)}>{t.pin.title}</span>
        {open ? <ChevronUp size={16} aria-hidden /> : <ChevronDown size={16} aria-hidden />}
      </button>
      <p className={clsx('t-caption', styles.muted)}>{t.pin.note}</p>
      {open ? (
        <form
          id={formId}
          className={styles.pinForm}
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          {fields.map((f) => (
            <div key={f.key} className={styles.pinRow}>
              <span id={ids[f.key]} className={clsx('t-label', styles.muted)}>
                {f.label}
              </span>
              <PinField
                value={values[f.key]}
                onChange={set(f.key)}
                state={busy ? 'busy' : error?.field === f.key ? 'error' : 'normal'}
                labelledBy={ids[f.key]}
                describedBy={error ? messageId : undefined}
                autoComplete={f.auto}
                focusOnMount={f.key === 'current'}
              />
            </div>
          ))}
          <Button type="submit" kind="primary" className={styles.wide} disabled={!ready}>
            {busy ? (
              <>
                <LoaderCircle size={18} className={styles.spinner} aria-hidden />
                {t.pin.busy}
              </>
            ) : (
              t.pin.submit
            )}
          </Button>
          <div id={messageId} className={styles.contents} aria-live="polite">
            {error ? <p className={clsx('t-caption', styles.error)}>{error.text}</p> : null}
            {done ? <p className={clsx('t-caption', styles.success)}>{t.pin.done}</p> : null}
          </div>
        </form>
      ) : done ? (
        <p className={clsx('t-caption', styles.success)} role="status">
          {t.pin.done}
        </p>
      ) : null}
    </section>
  );
}
