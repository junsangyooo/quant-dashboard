// 실전으로 켜기 (Figma 1:64094 · 1:64451 · 1:64956): three points → one check → PIN 6자리 → 실전 켜기.
// Closed (grey + red line) when the server says it cannot be turned on; '바꾸는 중' while the
// request runs; a changed preview (409 preview-changed) replaces the numbers and unchecks.
import clsx from 'clsx';
import { useId, useState, type Ref } from 'react';
import { Banknote, Repeat, Send, type LucideIcon } from 'lucide-react';
import { modeCopy as t } from '../../copy/mode';
import { pinCopy } from '../../copy/pin';
import { isApiError, NetworkError, type ApiError } from '../../api/client';
import { useTurnLiveOn } from '../../api/queries';
import type { ModeResponse } from '../../api/types';
import { Button } from '../../components/Buttons';
import { Checkbox } from '../../components/Controls';
import { formatTime } from '../../lib/format';
import { PIN_LENGTH, PinField } from '../Pin/PinField';
import { blockedLine, type OkPreview, type Preview } from './text';
import styles from './Mode.module.css';

const POINT_ICONS: readonly LucideIcon[] = [Send, Repeat, Banknote];

/** A field of a contract error body, at the top level (`remaining`, `preview`) or in `detail`. */
function bodyField(error: ApiError, key: string): unknown {
  const body = error.body as unknown as Record<string, unknown> | null;
  if (!body) return undefined;
  if (key in body) return body[key];
  const detail = body.detail as Record<string, unknown> | undefined;
  return detail?.[key];
}

/** '켜지 않았어요 · [이유]' (or the PIN form's own words for PIN errors). */
function failureLine(error: unknown): { text: string; pin: boolean } {
  if (isApiError(error, 'pin')) {
    const remaining = bodyField(error, 'remaining');
    return { text: pinCopy.wrong(typeof remaining === 'number' ? remaining : 0), pin: true };
  }
  if (isApiError(error, 'locked')) {
    const raw = bodyField(error, 'until');
    const until = typeof raw === 'string' ? Date.parse(raw) : Number.NaN;
    const global = bodyField(error, 'scope') === 'global';
    const text = Number.isFinite(until)
      ? global
        ? pinCopy.lockedEverywhere(Math.max(1, Math.ceil((until - Date.now()) / 60_000)))
        : pinCopy.lockedHere(formatTime(new Date(until)))
      : t.turnOn.failed(t.turnOn.reasons.server);
    return { text, pin: true };
  }
  if (isApiError(error, 'invalid-pin'))
    return { text: t.turnOn.failed(t.turnOn.reasons.pinFormat), pin: true };
  if (isApiError(error, 'blocked')) {
    const cause = bodyField(error, 'cause');
    const reason =
      cause === 'live-not-available'
        ? t.turnOn.reasons.notAvailable
        : cause === 'preview'
          ? t.turnOn.reasons.preview
          : cause === 'cancel-pending'
            ? t.turnOn.reasons.cancelPending
            : t.turnOn.reasons.checks;
    return { text: t.turnOn.failed(reason), pin: false };
  }
  if (isApiError(error, 'in-progress'))
    return { text: t.turnOn.failed(t.turnOn.reasons.inProgress), pin: false };
  if (error instanceof NetworkError)
    return { text: t.turnOn.failed(t.turnOn.reasons.network), pin: false };
  return { text: t.turnOn.failed(t.turnOn.reasons.server), pin: false };
}

export interface TurnOnCardProps {
  mode: ModeResponse;
  /** The preview on screen (the server's, or the one a 409 preview-changed brought). */
  preview: Preview | null;
  onPreviewChanged: (preview: OkPreview, at: string) => void;
  /** The 실전 cell of the segment scrolls here. */
  ref?: Ref<HTMLElement> | undefined;
}

export function TurnOnCard({ mode, preview, onPreviewChanged, ref }: TurnOnCardProps) {
  const titleId = useId();
  const pinLabelId = useId();
  const lineId = useId();
  const turnOn = useTurnLiveOn();
  const [checked, setChecked] = useState(false);
  const [pin, setPin] = useState('');
  const [failure, setFailure] = useState<{ text: string; pin: boolean } | null>(null);
  const [redPin, setRedPin] = useState(false);

  const blocked = blockedLine(mode);
  const hash = preview?.kind === 'ok' ? preview.hash : null;
  const closed = blocked !== null || hash === null;
  const busy = turnOn.isPending;
  const ready = !closed && !busy && checked && pin.length === PIN_LENGTH;

  const submit = () => {
    if (!ready) return;
    setFailure(null);
    const sent = pin;
    setPin('');
    turnOn.mutate(
      { pin: sent, previewHash: hash },
      {
        onError: (error) => {
          if (isApiError(error, 'preview-changed')) {
            const next = bodyField(error, 'preview') as Preview | undefined;
            if (next?.kind === 'ok') onPreviewChanged(next, next.computedAt);
            setChecked(false);
            return;
          }
          const f = failureLine(error);
          setFailure(f);
          setRedPin(f.pin);
        },
      },
    );
  };

  const lineText = busy ? t.turnOn.busyNote : (failure?.text ?? blocked);
  const lineTone = busy ? 'muted' : 'error';

  return (
    <section
      ref={ref}
      className={clsx(styles.card, styles.outlined, styles.turnOn)}
      aria-labelledby={titleId}
    >
      <h2 id={titleId} className="t-heading-1">
        {t.turnOn.title}
      </h2>
      <ul className={styles.points}>
        {t.turnOn.points.map((point, i) => {
          const Icon = POINT_ICONS[i] ?? Send;
          return (
            <li key={point} className={styles.point}>
              <Icon size={20} aria-hidden />
              <span className="t-body">{point}</span>
            </li>
          );
        })}
      </ul>
      <Checkbox
        checked={checked}
        disabled={closed || busy}
        onChange={setChecked}
        className={clsx(styles.confirm, (closed || busy) && !checked && styles.confirmOff)}
      >
        <span className="t-body-strong">{t.turnOn.confirm}</span>
      </Checkbox>
      <form
        className={styles.pinForm}
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <span id={pinLabelId} className={clsx('t-label', styles.muted)}>
          {t.turnOn.pin}
        </span>
        <PinField
          value={pin}
          onChange={(v) => {
            setRedPin(false);
            setPin(v);
          }}
          state={closed || busy ? 'disabled' : redPin ? 'error' : 'normal'}
          labelledBy={pinLabelId}
          describedBy={lineText ? lineId : undefined}
        />
        <Button type="submit" kind="primary" block className={styles.wide} disabled={!ready}>
          {busy ? t.turnOn.busy : t.turnOn.button}
        </Button>
      </form>
      {lineText ? (
        <p
          id={lineId}
          className={clsx('t-caption', styles[lineTone])}
          role={failure ? 'alert' : undefined}
        >
          {lineText}
        </p>
      ) : null}
    </section>
  );
}
