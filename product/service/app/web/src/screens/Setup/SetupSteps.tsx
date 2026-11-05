// 처음 실행 마법사(그림 V2-01 비밀번호 만들기 · V2-02 복구 코드 · V2-05 설치 위치 · V2-06 Tailscale ·
// V2-07 토스 연결 · V2-08 텔레그램 · V2-09 DART). 1 · 2는 로그인 전, 3부터는 방금 만든 세션으로.
import clsx from 'clsx';
import { useState } from 'react';
import { useNavigate } from 'react-router';
import { useQueryClient } from '@tanstack/react-query';
import { Monitor, Server } from 'lucide-react';
import { api, isApiError } from '../../api/client';
import { useConnect } from '../../api/connect';
import { keys } from '../../api/query';
import type { RecoveryOut } from '../../api/state';
import {
  findTelegramChat,
  saveDartKey,
  saveTelegramToken,
  sendTelegramTest,
  setPlace,
  settingsKeys,
  useAccess,
  useTelegram,
  type TelegramView,
} from '../../api/settingsV2';
import { Box } from '../../components/Box';
import { Button } from '../../components/Buttons';
import { Checkbox } from '../../components/Controls';
import { TextField } from '../../components/Field';
import { Sheet } from '../../components/Sheet';
import { copy } from '../../copy';
import { authCopy } from '../../copy/auth';
import { setupV2 as t } from '../../copy/setupV2';
import { settingsCopy } from '../../copy/settings';
import { termsCopy } from '../../copy/terms';
import { useDocumentTitle } from '../../shell/page';
import { formatMonthDayWeekday } from '../../lib/format';
import { dayTime } from '../../lib/when';
import { HowTo, Note, Panel, Status, TextLink, WizardPage, wizardStyles as s } from './Wizard';
import authStyles from '../Auth/Auth.module.css';

const errorText = (e: unknown) => (isApiError(e) ? e.message : copy.common.noConnection);

// ── 1 · 2 비밀번호 만들기 → 복구 코드 ─────────────────────────────────────────

export function SetupScreen() {
  useDocumentTitle(copy.pages.setup);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [pw, setPw] = useState('');
  const [pw2, setPw2] = useState('');
  const [adult, setAdult] = useState(false);
  const [terms, setTerms] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [code, setCode] = useState<string | null>(null);
  const [full, setFull] = useState(false);
  const a = authCopy.setup;

  const mismatch = pw2.length > 0 && pw !== pw2;
  const ready = pw.length >= 8 && pw === pw2 && adult && terms && !busy;

  if (code) return <RecoveryStep code={code} onNext={() => void navigate('/setup/place')} />;

  return (
    <WizardPage
      step={1}
      title={t.password.title}
      lead={t.password.lead}
      main={
        <form
          className="stack-block"
          onSubmit={(e) => {
            e.preventDefault();
            if (!ready) return;
            setBusy(true);
            setError(null);
            api
              .post<RecoveryOut>('/api/setup', {
                password: pw,
                password2: pw2,
                adult,
                terms,
              })
              .then(async (r) => {
                setCode(r.recovery_code);
                setPw('');
                setPw2('');
                await qc.invalidateQueries({ queryKey: keys.state });
              })
              .catch((err: unknown) => {
                setError(errorText(err));
              })
              .finally(() => {
                setBusy(false);
              });
          }}
        >
          <TextField
            label={a.password}
            type="password"
            autoComplete="new-password"
            value={pw}
            onChange={(e) => {
              setPw(e.target.value);
            }}
            hint={a.passwordHint}
          />
          <TextField
            label={a.password2}
            type="password"
            autoComplete="new-password"
            value={pw2}
            onChange={(e) => {
              setPw2(e.target.value);
            }}
            error={mismatch ? a.mismatch : undefined}
          />
          <Checkbox checked={adult} onChange={setAdult}>
            {a.adult}
          </Checkbox>
          <Checkbox checked={terms} onChange={setTerms}>
            {a.agree}
          </Checkbox>
          {error ? <Box tone="error" title={error} strongTitle /> : null}
          <Button kind="primary" type="submit" className="full" disabled={!ready}>
            {t.next}
          </Button>
        </form>
      }
      side={
        <Panel
          title={t.password.termsTitle}
          action={
            <TextLink
              onClick={() => {
                setFull(true);
              }}
            >
              {t.password.full}
            </TextLink>
          }
        >
          <ul className={authStyles.terms}>
            {t.password.terms.map((line) => (
              <li key={line} className={`t-body ${authStyles.termItem}`}>
                {line}
              </li>
            ))}
          </ul>
          {full ? (
            <Sheet
              title={`${t.password.termsTitle} · ${termsCopy.draft}`}
              onClose={() => {
                setFull(false);
              }}
            >
              {termsCopy.sections.map((sec) => (
                <section key={sec.title} className="stack-tight">
                  <h3 className="t-body-strong">{sec.title}</h3>
                  {sec.lines.map((l) => (
                    <p key={l} className="t-body">
                      {l}
                    </p>
                  ))}
                </section>
              ))}
            </Sheet>
          ) : null}
        </Panel>
      }
    />
  );
}

function RecoveryStep({ code, onNext }: { code: string; onNext: () => void }) {
  const [copied, setCopied] = useState(false);
  const [wrote, setWrote] = useState(false);
  const r = authCopy.recovery;
  return (
    <WizardPage
      step={2}
      title={t.recovery.title}
      lead={t.recovery.lead}
      main={
        <>
          <Panel tone="outline">
            <p className="t-caption c-muted">{r.codeLabel}</p>
            <div className={s.kv}>
              <p className={clsx('t-heading-1', authStyles.code)}>{code}</p>
              <Button
                onClick={() => {
                  void navigator.clipboard.writeText(code).then(() => {
                    setCopied(true);
                  });
                }}
              >
                {copied ? copy.common.copied : copy.common.copy}
              </Button>
            </div>
          </Panel>
          <Box tone="warn">{r.once}</Box>
          <Checkbox checked={wrote} onChange={setWrote}>
            {r.wrote}
          </Checkbox>
          <Button kind="primary" className="full" disabled={!wrote} onClick={onNext}>
            {t.next}
          </Button>
        </>
      }
      side={<HowTo title={t.recovery.useTitle} steps={t.recovery.uses} />}
    />
  );
}

// ── 3 설치 위치 ───────────────────────────────────────────────────────────────

export function PlaceStep() {
  useDocumentTitle(t.place.title);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const access = useAccess().data;
  const [picked, setPicked] = useState<'server' | 'pc' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const place = picked ?? access?.place ?? null;
  const p = t.place;
  const choice = (
    key: 'server' | 'pc',
    Icon: typeof Server,
    title: string,
    line: string,
    notes: readonly string[],
  ) => (
    <button
      type="button"
      className={clsx(s.choice, place === key && s.choiceOn)}
      aria-pressed={place === key}
      onClick={() => {
        setPicked(key);
      }}
    >
      <span className={s.cardHead}>
        <span className={clsx(s.status, 't-heading-1')}>
          <Icon size={22} aria-hidden />
          {title}
        </span>
        <input type="radio" readOnly checked={place === key} tabIndex={-1} aria-hidden />
      </span>
      <span className="t-body">{line}</span>
      <ul className={clsx(s.notes, 't-caption')}>
        {notes.map((n) => (
          <li key={n}>· {n}</li>
        ))}
      </ul>
    </button>
  );
  return (
    <WizardPage
      step={3}
      back={{ to: '/setup', label: t.prev }}
      title={p.title}
      lead={p.lead}
      main={
        <>
          <div className={s.choices}>
            {choice('server', Server, p.server, p.serverLine, p.serverNotes)}
            {choice('pc', Monitor, p.pc, p.pcLine, p.pcNotes)}
          </div>
          <Box tone="warn" icon="warn">
            {p.laptop}
          </Box>
          <p className="t-caption c-muted">{p.later}</p>
          {error ? <Box tone="error" title={error} strongTitle /> : null}
          <Button
            kind="primary"
            className="full"
            disabled={!place}
            onClick={() => {
              if (!place) return;
              setPlace(place)
                .then(async () => {
                  await qc.invalidateQueries({ queryKey: settingsKeys.access });
                  await navigate('/setup/tailscale');
                })
                .catch((err: unknown) => {
                  setError(errorText(err));
                });
            }}
          >
            {t.next}
          </Button>
        </>
      }
      side={
        <Panel title={p.docTitle} tone="outline">
          <p className="t-body c-muted">{p.docLine}</p>
        </Panel>
      }
    />
  );
}

// ── 4 Tailscale ───────────────────────────────────────────────────────────────

export function TailscaleStep() {
  useDocumentTitle(t.tailscale.title);
  const navigate = useNavigate();
  const q = useAccess();
  const a = q.data;
  const ts = t.tailscale;
  const server = a?.place !== 'pc';
  const ok = Boolean(a?.tailscale.ok);
  return (
    <WizardPage
      step={4}
      back={{ to: '/setup/place', label: t.prev }}
      title={ts.title}
      lead={ts.lead}
      main={
        <>
          <Panel title={server ? ts.hereServer : ts.herePc}>
            {ok ? (
              <>
                <Status kind="ok">{ts.ok(a?.tailscale.name ?? '')}</Status>
                <div className={s.kv}>
                  <span className="t-caption c-muted">{ts.address}</span>
                  <strong className="t-body">{a?.tailscale.address}</strong>
                </div>
              </>
            ) : (
              <>
                <Status kind="bad">{server ? ts.missingServer : ts.missingPc}</Status>
                <Note>{ts.missingHelp}</Note>
              </>
            )}
          </Panel>
          <div className={s.buttons}>
            {ok ? null : <Button onClick={() => void q.refetch()}>{ts.recheck}</Button>}
            {!ok && !server ? (
              <Button onClick={() => void navigate('/setup/toss')}>{t.skip}</Button>
            ) : null}
            <Button
              kind="primary"
              className={s.grow}
              disabled={!ok}
              onClick={() => void navigate('/setup/toss')}
            >
              {t.next}
            </Button>
          </div>
        </>
      }
      side={<HowTo title={ts.howTitle} steps={ts.how} note={ts.noPublic} />}
    />
  );
}

// ── 5 토스 연결 ───────────────────────────────────────────────────────────────

export function TossStep() {
  useDocumentTitle(t.toss.title);
  const navigate = useNavigate();
  const conn = useConnect();
  const [cid, setCid] = useState('');
  const [sec, setSec] = useState('');
  const [acc, setAcc] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const toss = conn.data?.toss;
  const check = toss?.last_check;
  const k = settingsCopy.connect;
  return (
    <WizardPage
      step={5}
      back={{ to: '/setup/tailscale', label: t.prev }}
      title={t.toss.title}
      lead={t.toss.lead}
      main={
        <>
          <Panel title={k.card}>
            {toss?.saved ? (
              <Status kind={check?.ok ? 'ok' : check ? 'bad' : 'wait'}>
                {check?.ok ? k.ok(dayTime(check.at)) : check ? check.title : k.saved}
              </Status>
            ) : null}
            <TextField
              label={k.clientId}
              placeholder={k.idPlaceholder}
              value={cid}
              autoComplete="off"
              onChange={(e) => {
                setCid(e.target.value);
              }}
            />
            <TextField
              label={k.clientSecret}
              placeholder={k.secretPlaceholder}
              type="password"
              value={sec}
              autoComplete="off"
              onChange={(e) => {
                setSec(e.target.value);
              }}
            />
            <TextField
              label={k.account}
              placeholder={k.accountPlaceholder}
              hint={k.accountHint}
              value={acc}
              inputMode="numeric"
              onChange={(e) => {
                setAcc(e.target.value);
              }}
            />
          </Panel>
          {error ? <Box tone="error" title={error} strongTitle /> : null}
          <div className={s.buttons}>
            <Button onClick={() => void navigate('/setup/telegram')}>{t.toss.later}</Button>
            <Button
              kind="primary"
              className={s.grow}
              disabled={busy || (!toss?.saved && (!cid || !sec))}
              onClick={() => {
                setBusy(true);
                setError(null);
                const save =
                  cid && sec
                    ? api.put('/api/connect/toss', {
                        client_id: cid,
                        client_secret: sec,
                        account_no: acc,
                      })
                    : Promise.resolve();
                save
                  .then(() => api.post('/api/connect/toss/check'))
                  .then(async () => {
                    await conn.refetch();
                    await navigate('/setup/telegram');
                  })
                  .catch((err: unknown) => {
                    setError(errorText(err));
                  })
                  .finally(() => {
                    setBusy(false);
                  });
              }}
            >
              {t.next}
            </Button>
          </div>
        </>
      }
    />
  );
}

// ── 6 텔레그램 ─────────────────────────────────────────────────────────────────

export function TelegramCard({ settings = false }: { settings?: boolean }) {
  const qc = useQueryClient();
  const q = useTelegram();
  const v = q.data;
  const [token, setToken] = useState('');
  const [started, setStarted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const g = t.telegram;
  const done = (next: TelegramView) => {
    qc.setQueryData(settingsKeys.telegram, next);
  };
  const run = (fn: () => Promise<TelegramView>) => {
    setBusy(true);
    setError(null);
    fn()
      .then(done)
      .catch((err: unknown) => {
        setError(errorText(err));
      })
      .finally(() => {
        setBusy(false);
      });
  };
  if (v?.saved && v.chat) {
    return (
      <Panel title={g.card}>
        <Status kind={v.last_error ? 'bad' : 'ok'}>
          {v.last_error ?? g.connected(v.bot ?? '')}
        </Status>
        <div className={s.kv}>
          <span className="t-caption c-muted">{g.chat}</span>
          <strong className="t-body">{v.chat_name ?? '—'}</strong>
        </div>
        {v.last_sent ? (
          <p className="t-caption c-muted">{g.lastSent(formatMonthDayWeekday(v.last_sent))}</p>
        ) : null}
        {error ? <Box tone="error" title={error} strongTitle /> : null}
        <Button
          disabled={busy}
          onClick={() => {
            run(sendTelegramTest);
          }}
        >
          {g.test}
        </Button>
      </Panel>
    );
  }
  return (
    <Panel title={g.card}>
      <Status kind="wait">{settings ? g.noneSettings : g.none}</Status>
      <TextField
        label={g.token}
        placeholder={g.token}
        hint={g.tokenHint}
        value={token}
        autoComplete="off"
        onChange={(e) => {
          setToken(e.target.value);
        }}
      />
      <Checkbox checked={started} onChange={setStarted}>
        {g.started}
      </Checkbox>
      {error ? <Box tone="error" title={error} strongTitle /> : null}
      {settings ? (
        <Button
          kind="primary"
          className="full"
          disabled={busy || !started || (!token && !v?.saved)}
          onClick={() => {
            run(async () => {
              if (token) await saveTelegramToken(token);
              return findTelegramChat();
            });
          }}
        >
          {busy ? g.finding : g.find}
        </Button>
      ) : (
        <FindButton
          busy={busy}
          disabled={!started || (!token && !v?.saved)}
          onClick={() => {
            run(async () => {
              if (token) await saveTelegramToken(token);
              return findTelegramChat();
            });
          }}
        />
      )}
    </Panel>
  );
}

function FindButton({
  busy,
  disabled,
  onClick,
}: {
  busy: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <Button kind="primary" className="full" disabled={busy || disabled} onClick={onClick}>
      {busy ? t.telegram.finding : t.telegram.find}
    </Button>
  );
}

export function TelegramStep() {
  useDocumentTitle(t.telegram.title);
  const navigate = useNavigate();
  const v = useTelegram().data;
  const g = t.telegram;
  return (
    <WizardPage
      step={6}
      back={{ to: '/setup/toss', label: t.prev }}
      title={g.title}
      lead={g.lead}
      main={
        <>
          <TelegramCard />
          <div className={s.buttons}>
            <Button onClick={() => void navigate('/setup/dart')}>{t.skip}</Button>
            <Button
              kind="primary"
              className={s.grow}
              disabled={!(v?.saved && v.chat)}
              onClick={() => void navigate('/setup/dart')}
            >
              {t.next}
            </Button>
          </div>
          <p className="t-caption c-muted">{g.skipLine}</p>
        </>
      }
      side={<HowTo title={g.howTitle} steps={g.how} note={g.commands} />}
    />
  );
}

// ── 7 DART ───────────────────────────────────────────────────────────────────

export function DartStep() {
  useDocumentTitle(t.dart.title);
  const navigate = useNavigate();
  const conn = useConnect();
  const [key, setKey] = useState('');
  const [error, setError] = useState<string | null>(null);
  const d = t.dart;
  const saved = Boolean((conn.data as { dart?: { saved: boolean } } | undefined)?.dart?.saved);
  return (
    <WizardPage
      step={7}
      back={{ to: '/setup/telegram', label: t.prev }}
      title={d.title}
      lead={d.lead}
      main={
        <>
          <Panel title={d.card}>
            <Status kind={saved ? 'ok' : 'wait'}>{saved ? d.saved : d.none}</Status>
            {saved ? (
              <Note>{d.note}</Note>
            ) : (
              <TextField
                label={d.key}
                placeholder={d.keyPlaceholder}
                value={key}
                autoComplete="off"
                onChange={(e) => {
                  setKey(e.target.value);
                }}
              />
            )}
          </Panel>
          {error ? <Box tone="error" title={error} strongTitle /> : null}
          <div className={s.buttons}>
            <Button onClick={() => void navigate('/')}>{t.skip}</Button>
            {saved ? (
              <Button kind="primary" className={s.grow} onClick={() => void navigate('/')}>
                {d.done}
              </Button>
            ) : (
              <Button
                kind="primary"
                className={s.grow}
                disabled={!key}
                onClick={() => {
                  saveDartKey(key)
                    .then(() => conn.refetch())
                    .catch((err: unknown) => {
                      setError(errorText(err));
                    });
                }}
              >
                {d.check}
              </Button>
            )}
          </div>
        </>
      }
      side={<HowTo title={d.howTitle} steps={d.how} />}
    />
  );
}
