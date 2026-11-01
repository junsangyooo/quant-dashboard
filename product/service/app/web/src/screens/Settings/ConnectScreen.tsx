// MVP-06 설정 › 연결: 키 없음 · 저장됨 · 확인 중 · 연결됨 · 실패 셋(API 키 · 허용 IP · 응답 없음)
// · API 키 변경 · API 키 삭제 확인. 1440: the card on the left, 'API 키 받는 법' on the right.
import clsx from 'clsx';
import { useEffect, useState } from 'react';
import { CircleCheck, CircleX, Clock, Hourglass, Circle, Info } from 'lucide-react';
import { api, isApiError } from '../../api/client';
import {
  usePost,
  useConnect,
  type CheckResult,
  type CheckStep,
  type ConnectView,
} from '../../api/mvp';
import { Box } from '../../components/Box';
import { Button, ExpandButton, CollapseButton } from '../../components/Buttons';
import { Card, KeyValue } from '../../components/Card';
import { TextField } from '../../components/Field';
import { Sheet } from '../../components/Sheet';
import { StepNo } from '../../components/Tags';
import { copy } from '../../copy';
import { settingsCopy } from '../../copy/settings';
import { formatKrw } from '../../lib/format';
import { useMediaQuery } from '../../lib/useMedia';
import { dayTime } from '../../lib/when';
import { BackLink, Page, Split } from '../../shell/Layout';
import { useDocumentTitle } from '../../shell/page';
import styles from './Connect.module.css';

const t = settingsCopy.connect;
const WIDE = '(min-width: 900px)';

function usePublicIp() {
  const [ip, setIp] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ask = async () => {
    setBusy(true);
    setError(null);
    try {
      setIp((await api.post<{ ip: string }>('/api/public-ip')).ip);
    } catch (e) {
      setError(isApiError(e) ? e.message : copy.common.noConnection);
    } finally {
      setBusy(false);
    }
  };
  return { ip, busy, error, ask };
}

type Ip = ReturnType<typeof usePublicIp>;

function IpBlock({ ip }: { ip: Ip }) {
  const [copied, setCopied] = useState(false);
  if (ip.ip) {
    return (
      <div className="stack-tight">
        <div className={styles.ipRow}>
          <span className={clsx('t-caption c-muted', styles.ipLabel)}>{t.ipLabel}</span>
          <span className={clsx('t-body-strong', styles.ipValue)}>{ip.ip}</span>
          <Button
            kind="default"
            onClick={() => {
              void navigator.clipboard.writeText(ip.ip ?? '').then(() => {
                setCopied(true);
              });
            }}
          >
            {copied ? copy.common.copied : copy.common.copy}
          </Button>
        </div>
        <p className="t-caption c-muted">{t.ipNote}</p>
      </div>
    );
  }
  return (
    <div className="stack-tight">
      <Button
        kind="default"
        className={styles.ipButton}
        disabled={ip.busy}
        onClick={() => void ip.ask()}
      >
        {ip.busy ? t.ipLoading : t.ipButton}
      </Button>
      {ip.error ? (
        <p className="t-caption c-error">{ip.error}</p>
      ) : (
        <p className="t-caption c-muted">{t.ipNote}</p>
      )}
    </div>
  );
}

function HowTo({ ip, outline }: { ip: Ip; outline: boolean }) {
  return (
    <Card tone={outline ? 'outline' : 'white'} className={outline ? undefined : styles.howInner}>
      <h2 className="t-heading-1">{t.howTitle}</h2>
      <ol className="stack-row">
        {t.how.map((line, i) => (
          <li key={line} className={styles.howStep}>
            <StepNo n={i + 1} />
            <div className="stack-row">
              <span className="t-body">{line}</span>
              {i === 2 ? <IpBlock ip={ip} /> : null}
            </div>
          </li>
        ))}
      </ol>
      <Box tone="warn">{t.ownKey}</Box>
    </Card>
  );
}

function StatusLine({ icon, children }: { icon: 'clock' | 'ok' | 'fail'; children: string }) {
  const Icon = icon === 'clock' ? Clock : icon === 'ok' ? CircleCheck : CircleX;
  return (
    <p className={clsx('t-body', styles.status)}>
      <Icon size={20} className={styles[`status-${icon}`]} aria-hidden />
      {children}
    </p>
  );
}

function Tails({ toss }: { toss: ConnectView['toss'] }) {
  return (
    <div className="stack-inline">
      <KeyValue label={t.clientId}>{`····${toss.client_id_tail ?? ''}`}</KeyValue>
      <KeyValue label={t.clientSecret}>{`····${toss.secret_tail ?? ''}`}</KeyValue>
      {toss.account_tail ? (
        <KeyValue label={t.accountShort}>{`····${toss.account_tail}`}</KeyValue>
      ) : null}
    </div>
  );
}

function Steps({ steps, running }: { steps: CheckStep[]; running?: boolean }) {
  return (
    <ul className="stack-inline">
      {steps.map((s, i) => {
        const now = running && i === 0;
        const Icon = now
          ? Hourglass
          : s.state === 'done'
            ? CircleCheck
            : s.state === 'failed'
              ? CircleX
              : Circle;
        const label = now ? t.steps.running : t.steps[s.state];
        return (
          <li
            key={s.key}
            className={clsx(styles.step, styles[`step-${now ? 'running' : s.state}`])}
          >
            <Icon size={18} aria-hidden />
            <span className="t-body">{s.name}</span>
            <span className={clsx('t-caption', styles.stepState)}>{label}</span>
          </li>
        );
      })}
    </ul>
  );
}

const PENDING_STEPS: CheckStep[] = [
  { key: 'token', name: t.stepNames.token, state: 'waiting' },
  { key: 'account', name: t.stepNames.account, state: 'waiting' },
  { key: 'price', name: t.stepNames.price, state: 'waiting' },
];

function KeyForm({
  changing,
  onDone,
  onClose,
  onTyped,
}: {
  changing: boolean;
  onDone: () => void;
  onClose?: (() => void) | undefined;
  /** 키를 입력하기 시작했는가(저장 전 상태 줄). */
  onTyped?: ((typed: boolean) => void) | undefined;
}) {
  const [cid, setCid] = useState('');
  const [sec, setSec] = useState('');
  const typed = cid.trim() !== '' || sec.trim() !== '';
  useEffect(() => {
    onTyped?.(typed);
  }, [typed, onTyped]);
  const [acc, setAcc] = useState('');
  const save = usePost<
    { client_id: string; client_secret: string; account_no: string },
    ConnectView
  >('/api/connect/toss', 'PUT');
  const ready = cid.trim() !== '' && sec.trim() !== '' && !save.isPending;
  return (
    <form
      className="stack-block"
      onSubmit={(e) => {
        e.preventDefault();
        if (!ready) return;
        save.mutate(
          { client_id: cid, client_secret: sec, account_no: acc },
          {
            onSuccess: () => {
              setCid('');
              setSec('');
              setAcc('');
              onDone();
            },
          },
        );
      }}
    >
      <TextField
        label={t.clientId}
        value={cid}
        autoComplete="off"
        spellCheck={false}
        placeholder={changing ? t.newIdPlaceholder : t.idPlaceholder}
        onChange={(e) => {
          setCid(e.target.value);
        }}
      />
      <TextField
        label={t.clientSecret}
        type="password"
        value={sec}
        autoComplete="off"
        placeholder={changing ? t.newSecretPlaceholder : t.secretPlaceholder}
        hint={t.tailOnly}
        onChange={(e) => {
          setSec(e.target.value);
        }}
      />
      <TextField
        label={t.account}
        value={acc}
        inputMode="numeric"
        autoComplete="off"
        placeholder={t.accountPlaceholder}
        hint={t.accountHint}
        onChange={(e) => {
          setAcc(e.target.value);
        }}
      />
      {save.error ? (
        <p className="t-caption c-error">
          {isApiError(save.error) ? save.error.message : copy.common.noConnection}
        </p>
      ) : null}
      {changing ? (
        <>
          <div className="buttons">
            <Button kind="default" onClick={onClose}>
              {copy.common.dismiss}
            </Button>
            <Button kind="primary" type="submit" disabled={!ready}>
              {t.save}
            </Button>
          </div>
          <p className="t-caption c-muted">{t.afterChange}</p>
        </>
      ) : (
        <Button kind="primary" type="submit" className="full" disabled={!ready}>
          {t.save}
        </Button>
      )}
    </form>
  );
}

function Failure({ result, ip }: { result: Extract<CheckResult, { ok: false }>; ip: Ip }) {
  return (
    <div className={styles.failBox} role="alert">
      <p className="t-label c-error">{t.cause}</p>
      <p className="t-body">{result.cause}</p>
      <p className="t-label c-error">{t.next}</p>
      <p className="t-body">{result.next}</p>
      {result.kind === 'ip' ? (
        <div className={styles.failIp}>
          <IpBlock ip={ip} />
        </div>
      ) : null}
    </div>
  );
}

export function ConnectScreen() {
  useDocumentTitle(copy.pages.connect);
  const q = useConnect();
  const wide = useMediaQuery(WIDE);
  const ip = usePublicIp();
  const [changing, setChanging] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [howOpen, setHowOpen] = useState(false);
  const [typed, setTyped] = useState(false);
  const check = usePost<undefined, { result: CheckResult } & ConnectView>(
    '/api/connect/toss/check',
  );
  const remove = usePost<undefined, ConnectView>('/api/connect/toss', 'DELETE');
  const view = q.data;
  const toss = view?.toss;
  const result = check.isPending ? null : (toss?.last_check ?? null);

  let body: React.ReactNode = null;
  if (toss && !toss.saved) {
    body = (
      <>
        <StatusLine icon="clock">{typed ? t.typed : t.none}</StatusLine>
        <KeyForm changing={false} onDone={() => void q.refetch()} onTyped={setTyped} />
      </>
    );
  } else if (toss && changing) {
    body = (
      <>
        <StatusLine icon="clock">{t.changing}</StatusLine>
        <KeyForm
          changing
          onDone={() => {
            setChanging(false);
          }}
          onClose={() => {
            setChanging(false);
          }}
        />
      </>
    );
  } else if (toss) {
    const failed = result && !result.ok ? result : null;
    const okResult = result?.ok ? result : null;
    const actions = (
      <div className="buttons">
        <Button
          kind="default"
          disabled={check.isPending}
          onClick={() => {
            setChanging(true);
          }}
        >
          {t.change}
        </Button>
        <Button
          kind="dangerOutline"
          disabled={check.isPending}
          onClick={() => {
            setDeleting(true);
          }}
        >
          {t.remove}
        </Button>
      </div>
    );
    body = (
      <>
        {check.isPending ? (
          <StatusLine icon="clock">{t.checking}</StatusLine>
        ) : okResult ? (
          <StatusLine icon="ok">{t.ok(dayTime(okResult.at))}</StatusLine>
        ) : failed ? (
          <StatusLine icon="fail">{failed.title}</StatusLine>
        ) : (
          <StatusLine icon="clock">{t.saved}</StatusLine>
        )}
        {okResult ? (
          <>
            <KeyValue label={t.price}>{formatKrw(okResult.price)}</KeyValue>
            <p className={clsx('t-caption', styles.readOnly)}>
              <Info size={16} aria-hidden />
              {t.readOnly}
            </p>
            <hr className={styles.rule} />
          </>
        ) : null}
        <Tails toss={toss} />
        {check.isPending ? (
          <Steps running steps={PENDING_STEPS} />
        ) : failed ? (
          <Steps steps={failed.steps} />
        ) : null}
        {failed ? <Failure result={failed} ip={ip} /> : null}
        {failed?.kind === 'auth' ? (
          <>
            <Button
              kind="primary"
              className="full"
              onClick={() => {
                setChanging(true);
              }}
            >
              {t.change}
            </Button>
            <div className="buttons">
              <Button
                kind="default"
                onClick={() => {
                  check.mutate(undefined);
                }}
              >
                {t.recheck}
              </Button>
              <Button
                kind="dangerOutline"
                onClick={() => {
                  setDeleting(true);
                }}
              >
                {t.remove}
              </Button>
            </div>
          </>
        ) : (
          <>
            {actions}
            <Button
              kind={okResult ? 'default' : 'primary'}
              className="full"
              disabled={check.isPending}
              onClick={() => {
                check.mutate(undefined);
              }}
            >
              {check.isPending ? t.checkingButton : result ? t.recheck : t.check}
            </Button>
          </>
        )}
        {!result && !check.isPending ? <p className="t-caption c-muted">{t.checkNote}</p> : null}
        {check.error ? (
          <p className="t-caption c-error">
            {isApiError(check.error) ? check.error.message : copy.common.noConnection}
          </p>
        ) : null}
      </>
    );
  }

  const failedNow = !check.isPending && toss?.saved && !changing && result && !result.ok;
  const showHowInline = !wide && toss && (!toss.saved || changing || failedNow);
  const inlineHow =
    showHowInline && toss.saved ? (
      howOpen ? (
        <>
          <CollapseButton
            onClick={() => {
              setHowOpen(false);
            }}
          >
            {t.howTitle}
          </CollapseButton>
          <HowTo ip={ip} outline={false} />
        </>
      ) : (
        <ExpandButton
          onClick={() => {
            setHowOpen(true);
          }}
        >
          {t.howTitle}
        </ExpandButton>
      )
    ) : showHowInline ? (
      <HowTo ip={ip} outline />
    ) : null;

  return (
    <Page width="split" gutter="block">
      <BackLink to="/settings">{settingsCopy.back}</BackLink>
      <h1 className="t-title">{t.title}</h1>
      <Split
        main={
          <Card>
            <h2 className="t-heading-1">{t.card}</h2>
            {body}
            {inlineHow}
          </Card>
        }
        side={wide ? <HowTo ip={ip} outline /> : null}
      />
      {deleting ? (
        <Sheet
          title={t.deleteTitle}
          onClose={() => {
            setDeleting(false);
          }}
        >
          <p className="t-body">{t.deleteBody}</p>
          <p className="t-caption c-muted">{t.deleteNote}</p>
          <div className="buttons">
            <Button
              kind="default"
              onClick={() => {
                setDeleting(false);
              }}
            >
              {copy.common.dismiss}
            </Button>
            <Button
              kind="danger"
              disabled={remove.isPending}
              onClick={() => {
                remove.mutate(undefined, {
                  onSuccess: () => {
                    setDeleting(false);
                  },
                });
              }}
            >
              {t.remove}
            </Button>
          </div>
        </Sheet>
      ) : null}
    </Page>
  );
}
