// MVP-03 로그인: 기본 · 맞지 않음(남은 횟수) · 잠금(남은 시간) · 다시 켠 뒤.
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { useQueryClient } from '@tanstack/react-query';
import { api, isApiError } from '../../api/client';
import { useAppState } from '../../api/state';
import { Box } from '../../components/Box';
import { Button, LinkButton } from '../../components/Buttons';
import { TextField } from '../../components/Field';
import { copy } from '../../copy';
import { authCopy } from '../../copy/auth';
import { setupV2 } from '../../copy/setupV2';
import { Page } from '../../shell/Layout';
import { useDocumentTitle } from '../../shell/page';

/** Seconds left of a lock that ends at `until` (ms since epoch). */
function useCountdown(until: number | null): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (until === null) return;
    const id = window.setInterval(() => {
      setNow(Date.now());
    }, 1000);
    return () => {
      window.clearInterval(id);
    };
  }, [until]);
  // 서버 남은 초처럼 내림 · 5분 0초를 넘지 않게
  return until === null ? 0 : Math.min(300, Math.max(0, Math.floor((until - now) / 1000)));
}

export function LoginScreen() {
  useDocumentTitle(copy.pages.login);
  const t = authCopy.login;
  const v2 = setupV2.login;
  const state = useAppState();
  const navigate = useNavigate();
  const qc = useQueryClient();
  // 서버가 다시 켜진 뒤 첫 로그인 전에만(잠그기 뒤에는 기본 로그인 화면)
  const restarted = state.data?.restarted ?? false;
  const [pw, setPw] = useState('');
  const [busy, setBusy] = useState(false);
  const [triesLeft, setTriesLeft] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lockUntil, setLockUntil] = useState<number | null>(() => {
    const initial = state.data?.locked_for ?? 0;
    return initial > 0 ? Date.now() + (initial + 0.999) * 1000 : null;
  });
  const left = useCountdown(lockUntil);
  const locked = left > 0;

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.post('/api/login', { password: pw });
      await qc.invalidateQueries();
      void navigate('/', { replace: true });
    } catch (e) {
      if (isApiError(e) && e.status === 429) {
        setPw('');
        setLockUntil(Date.now() + ((e.body?.locked_for ?? 300) + 0.999) * 1000);
        setTriesLeft(null);
      } else if (isApiError(e) && e.status === 401 && typeof e.body?.tries_left === 'number') {
        setTriesLeft(e.body.tries_left);
      } else {
        setError(isApiError(e) ? e.message : copy.common.noConnection);
      }
    } finally {
      setBusy(false);
    }
  };

  const time = t.time(left);
  return (
    <Page width="login">
      <h1 className="t-title">{copy.pages.login}</h1>
      {locked ? (
        <Box tone="error" icon="lock" title={t.lockedTitle(time)} strongTitle role="alert">
          {t.lockedBody}
        </Box>
      ) : restarted && triesLeft === null ? (
        <Box tone="info" icon="info" title={v2.restartedTitle}>
          {v2.restartedBody}
        </Box>
      ) : null}
      <form
        className="stack-block"
        onSubmit={(e) => {
          e.preventDefault();
          if (pw && !locked && !busy) void submit();
        }}
      >
        <div className="stack-inline">
          <TextField
            label={t.password}
            type="password"
            autoComplete="current-password"
            value={pw}
            disabled={locked}
            placeholder={locked ? t.lockedPlaceholder(time) : t.placeholder}
            onChange={(e) => {
              setPw(e.target.value);
            }}
            error={!locked && triesLeft !== null ? t.wrong(triesLeft) : undefined}
          />
          {!locked && triesLeft !== null ? <p className="t-caption c-muted">{t.rule}</p> : null}
        </div>
        {error ? <Box tone="error" title={error} strongTitle /> : null}
        <Button kind="primary" type="submit" className="full" disabled={!pw || locked || busy}>
          {t.submit}
        </Button>
      </form>
      {locked ? (
        <p className="t-caption c-muted">{t.forgotLocked}</p>
      ) : (
        <LinkButton to="/recover">{t.forgot}</LinkButton>
      )}
      <p className="t-caption c-muted">{v2.onlyTailscale}</p>
    </Page>
  );
}
