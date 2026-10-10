// SCR-PIN 입장: wordmark → 'PIN 6자리' → 6 cells → keypad (390) → '잊었을 때'. The sixth digit
// submits by itself; after entry the page goes back to where the user was going
// (safeNext(next) ?? '/'). No account figure is ever shown or requested here.
// 1440 has no drawing: the same column, 360 wide, typed on the keyboard instead of the keypad.
import clsx from 'clsx';
import { useEffect, useId, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import {
  ChevronDown,
  ChevronUp,
  Clock,
  KeyRound,
  LoaderCircle,
  Lock,
  ShieldAlert,
} from 'lucide-react';
import { copy } from '../../copy';
import { pinCopy } from '../../copy/pin';
import { isApiError, safeNext } from '../../api/client';
import { useLogin } from '../../api/queries';
import { KeypadKey } from '../../components/Controls';
import { formatTime } from '../../lib/format';
import { pageTitle, useDocumentTitle } from '../../shell/page';
import { PIN_LENGTH, PinField } from './PinField';
import { useMediaQuery } from './useMediaQuery';
import styles from './PinScreen.module.css';

/** The keypad is drawn for 390 only; from 900px the keyboard types (기획 §5 레이아웃 의도). */
const WIDE = '(min-width: 900px)';

/** ip · global end at `until`; hold (new logins closed until the server's unlock) has no end. */
type Lock = { until: number; scope: 'ip' | 'global' } | { until: null; scope: 'hold' };

type Notice = { kind: 'wrong'; remaining: number } | { kind: 'failed' } | null;

/** A top-level field of a contract error body (`remaining`, `until`, `scope`). */
function errorField(error: unknown, key: string): unknown {
  if (!isApiError(error) || !error.body) return undefined;
  return (error.body as unknown as Record<string, unknown>)[key];
}

/** Minutes until `until`, at least 1 while it lasts. */
function minutesLeft(until: number, now: number): number {
  return Math.max(1, Math.ceil((until - now) / 60_000));
}

export function PinScreen() {
  useDocumentTitle(pageTitle('pin'));
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const target = safeNext(params.get('next')) ?? '/';
  const login = useLogin();
  const wide = useMediaQuery(WIDE);
  const promptId = useId();
  const messageId = useId();
  const helpId = useId();

  const [pin, setPin] = useState('');
  const [redCells, setRedCells] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const [lock, setLock] = useState<Lock | null>(null);
  const [noPin, setNoPin] = useState(false);
  const [forgotOpen, setForgotOpen] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  // A lock ends by itself at its time ('표시 시각이 지나면 자동 해제'); the global one also counts
  // its minutes down. The hold has no time: it stays until the page is opened again.
  useEffect(() => {
    const until = lock?.until ?? null;
    if (until === null) return;
    const tick = () => {
      const t = Date.now();
      setNow(t);
      if (t >= until) setLock(null);
    };
    tick();
    const timer = setInterval(tick, 15_000);
    const end = setTimeout(tick, Math.min(Math.max(0, until - Date.now()), 2 ** 31 - 1));
    return () => {
      clearInterval(timer);
      clearTimeout(end);
    };
  }, [lock]);

  const checking = login.isPending;
  const closed = lock !== null || noPin;

  const submit = (value: string) => {
    if (closed || checking) return;
    setNotice(null);
    login.mutate(value, {
      onSuccess: () => {
        void navigate(target, { replace: true });
      },
      onError: (error) => {
        setPin('');
        if (isApiError(error, 'pin')) {
          setRedCells(true);
          const remaining = errorField(error, 'remaining');
          setNotice({ kind: 'wrong', remaining: typeof remaining === 'number' ? remaining : 0 });
        } else if (isApiError(error, 'locked')) {
          const raw = errorField(error, 'until');
          const until = typeof raw === 'string' ? Date.parse(raw) : Number.NaN;
          const scope = errorField(error, 'scope');
          setRedCells(false);
          if (scope === 'hold') setLock({ until: null, scope: 'hold' });
          else if (Number.isFinite(until))
            setLock({ until, scope: scope === 'global' ? 'global' : 'ip' });
          else setNotice({ kind: 'failed' });
        } else if (isApiError(error, 'no-pin')) {
          setRedCells(false);
          setNoPin(true);
        } else {
          setRedCells(true);
          setNotice({ kind: 'failed' });
        }
      },
    });
  };

  const enter = (next: string) => {
    if (closed || checking) return;
    setRedCells(false);
    setPin(next);
    if (next.length === PIN_LENGTH) submit(next);
  };

  const fieldState = closed ? 'disabled' : checking ? 'busy' : redCells ? 'error' : 'normal';
  const keypadOff = closed || checking;

  return (
    <main id="main" className={styles.page}>
      <h1 className={clsx('t-title', styles.wordmark)}>{copy.wordmark}</h1>
      <label id={promptId} htmlFor={`${promptId}-input`} className={clsx('t-body', styles.prompt)}>
        {copy.pin.prompt}
      </label>
      <PinField
        id={`${promptId}-input`}
        value={pin}
        onChange={enter}
        state={fieldState}
        cursor="always"
        labelledBy={promptId}
        describedBy={notice || lock || noPin ? messageId : undefined}
        focusOnMount
        inputMode={wide ? 'numeric' : 'none'}
      />

      <div id={messageId} className={styles.messages} aria-live="polite">
        {checking ? (
          <span className={styles.checking}>
            <LoaderCircle size={20} className={styles.spinner} aria-hidden />
            <span className="sr-only">{pinCopy.checking}</span>
          </span>
        ) : null}
        {notice ? (
          <p className={clsx('t-body-strong', styles.error)}>
            {notice.kind === 'wrong' ? pinCopy.wrong(notice.remaining) : pinCopy.failed}
          </p>
        ) : null}
        {lock?.scope === 'hold' ? (
          <>
            <ShieldAlert size={24} className={styles.error} aria-hidden />
            <p className={clsx('t-body-strong', styles.error)}>{pinCopy.lockedHold}</p>
            <p className={clsx('t-caption', styles.note)}>{pinCopy.lockedHoldHelp}</p>
            <code className={clsx('t-caption', styles.code)}>{pinCopy.unlockCommand}</code>
            <p className={clsx('t-caption', styles.note)}>{pinCopy.lockedNote}</p>
          </>
        ) : lock ? (
          <>
            {lock.scope === 'ip' ? (
              <Lock size={24} className={styles.error} aria-hidden />
            ) : (
              <Clock size={24} className={styles.error} aria-hidden />
            )}
            <p className={clsx('t-body-strong', styles.error)}>
              {lock.scope === 'ip'
                ? pinCopy.lockedHere(formatTime(new Date(lock.until)))
                : pinCopy.lockedEverywhere(minutesLeft(lock.until, now))}
            </p>
            <p className={clsx('t-caption', styles.note)}>{pinCopy.lockedNote}</p>
          </>
        ) : null}
        {noPin ? (
          <>
            <KeyRound size={24} className={styles.note} aria-hidden />
            <p className="t-body-strong">{pinCopy.noPin}</p>
            <p className={clsx('t-caption', styles.note)}>{pinCopy.noPinHelp}</p>
            <code className={clsx('t-caption', styles.code)}>{pinCopy.noPinCommand}</code>
          </>
        ) : null}
      </div>

      {wide ? null : (
        <div
          role="group"
          aria-label={pinCopy.keypad}
          className={clsx(styles.keypad, keypadOff && styles.keypadOff)}
        >
          {['1', '2', '3', '4', '5', '6', '7', '8', '9'].map((d) => (
            <KeypadKey
              key={d}
              kind="digit"
              digit={d}
              disabled={keypadOff}
              onPress={() => {
                enter(`${pin}${d}`.slice(0, PIN_LENGTH));
              }}
            />
          ))}
          <KeypadKey kind="blank" />
          <KeypadKey
            kind="digit"
            digit="0"
            disabled={keypadOff}
            onPress={() => {
              enter(`${pin}0`.slice(0, PIN_LENGTH));
            }}
          />
          <KeypadKey
            kind="delete"
            disabled={keypadOff}
            onPress={() => {
              enter(pin.slice(0, -1));
            }}
          />
        </div>
      )}

      <div className={styles.forgot}>
        <button
          type="button"
          className={clsx('t-label', styles.forgotToggle)}
          aria-expanded={forgotOpen}
          aria-controls={helpId}
          onClick={() => {
            setForgotOpen((open) => !open);
          }}
        >
          {copy.pin.forgot}
          {forgotOpen ? <ChevronUp size={16} aria-hidden /> : <ChevronDown size={16} aria-hidden />}
        </button>
        <p id={helpId} className={clsx('t-caption', styles.note)} hidden={!forgotOpen}>
          {copy.pin.forgotHelp}
        </p>
      </div>
    </main>
  );
}
