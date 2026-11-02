// V2-33 비밀번호 확인 창. api/client가 403 need_confirm을 받으면 여기로 물어요: 맞는 비밀번호면
// 서버가 내준 1회용 토큰으로 같은 요청을 한 번 더 보내요. 틀린 횟수 · 잠금 글은 서버 글 그대로.
import { useEffect, useState } from 'react';
import { api, configureClient, isApiError, type ConfirmAsk } from '../api/client';
import { confirmCopy as t } from '../copy/confirm';
import { Button } from './Buttons';
import { TextField } from './Field';
import { Sheet } from './Sheet';

interface Pending extends ConfirmAsk {
  resolve: (token: string | null) => void;
}

export function ConfirmHost() {
  const [pending, setPending] = useState<Pending | null>(null);
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    configureClient({
      onConfirmRequired: (ask) =>
        new Promise<string | null>((resolve) => {
          setPassword('');
          setError('');
          setPending({ ...ask, resolve });
        }),
    });
    return () => {
      configureClient({ onConfirmRequired: () => Promise.resolve(null) });
    };
  }, []);

  if (!pending) return null;
  const close = (token: string | null) => {
    pending.resolve(token);
    setPending(null);
  };
  return (
    <Sheet
      title={pending.title || t.fallbackTitle}
      onClose={() => {
        close(null);
      }}
    >
      <form
        className="stack-block"
        onSubmit={(e) => {
          e.preventDefault();
          if (!password || busy) return;
          setBusy(true);
          api
            .post<{ token: string }>('/api/confirm', { password, action: pending.action })
            .then((r) => {
              close(r.token);
            })
            .catch((err: unknown) => {
              setError(isApiError(err) ? err.message : String(err));
            })
            .finally(() => {
              setBusy(false);
            });
        }}
      >
        <p className="t-body">{t.line}</p>
        <TextField
          label={t.password}
          type="password"
          autoComplete="current-password"
          value={password}
          error={error || undefined}
          onChange={(e) => {
            setPassword(e.target.value);
          }}
        />
        <div className="buttons">
          <Button
            block
            type="button"
            onClick={() => {
              close(null);
            }}
          >
            {t.cancel}
          </Button>
          <Button kind="primary" block type="submit" disabled={!password || busy}>
            {busy ? t.checking : t.ok}
          </Button>
        </div>
      </form>
    </Sheet>
  );
}
