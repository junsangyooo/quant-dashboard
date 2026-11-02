// 설정 v2(그림 V2-50 설정 · V2-52 알림 · V2-53 데이터 · V2-55 사용 조건 · 앱 정보 · V2-56 접속).
import { useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { useQueryClient } from '@tanstack/react-query';
import { api, isApiError } from '../../api/client';
import { keys, useConnect } from '../../api/mvp';
import {
  download,
  restoreBackup,
  setPlace,
  setTelegramEvent,
  settingsKeys,
  useAbout,
  useAccess,
  useDataView,
  useTelegram,
} from '../../api/settingsV2';
import { Box } from '../../components/Box';
import { Button } from '../../components/Buttons';
import { Checkbox } from '../../components/Controls';
import { MenuRow } from '../../components/MenuRow';
import { StatusTag } from '../../components/Tags';
import { copy } from '../../copy';
import { setupV2 } from '../../copy/setupV2';
import { settingsV2 as t } from '../../copy/settingsV2';
import { termsCopy } from '../../copy/terms';
import { formatMonthDay, formatMonthDayWeekday } from '../../lib/format';
import { Page } from '../../shell/Layout';
import { useDocumentTitle } from '../../shell/page';
import {
  HowTo,
  Note,
  Panel,
  Status,
  TextLink,
  WizardPage,
  wizardStyles as s,
} from '../Setup/Wizard';
import { TelegramCard } from '../Setup/SetupSteps';
import authStyles from '../Auth/Auth.module.css';

const back = { to: '/settings', label: t.back };
const errorText = (e: unknown) => (isApiError(e) ? e.message : copy.common.noConnection);

// ── V2-50 설정 ───────────────────────────────────────────────────────────────

export function SettingsV2Screen() {
  useDocumentTitle(copy.pages.settings);
  const conn = useConnect().data as
    (ReturnType<typeof useConnect>['data'] & { dart?: { saved: boolean } }) | undefined;
  const access = useAccess().data;
  const tg = useTelegram().data;
  const data = useDataView().data;
  const about = useAbout().data;
  const navigate = useNavigate();
  const qc = useQueryClient();
  const r = t.rows;
  const toss = conn?.toss;
  const tossLine = toss?.last_check?.ok ? r.tossOk : toss?.saved ? r.tossSaved : r.tossNone;
  const dartLine = conn?.dart?.saved ? r.dartSaved : r.dartNone;
  const place = access?.place ? t.placeShort[access.place] : r.placeNone;
  return (
    <Page width="narrow" gutter="block">
      <h1 className="t-title">{t.title}</h1>
      <div>
        <MenuRow
          to="/settings/connect"
          title={r.connect}
          line={r.connectLine(tossLine, dartLine)}
        />
        <MenuRow
          to="/settings/access"
          title={r.access}
          line={r.accessLine(place, Boolean(access?.tailscale.ok))}
        />
        <MenuRow
          to="/settings/notify"
          title={r.notify}
          line={tg?.saved && tg.chat ? r.notifyOk : r.notifyNone}
        />
        <MenuRow
          to="/settings/data"
          title={r.data}
          line={
            data?.bars.symbols && data.bars.to
              ? r.dataLine(data.bars.symbols, formatMonthDayWeekday(data.bars.to))
              : r.dataNone
          }
        />
        <MenuRow to="/settings/password" title={r.password} line={r.passwordLine} />
        <MenuRow
          to="/settings/about"
          title={r.about}
          line={
            about
              ? r.aboutLine(
                  about.version,
                  place,
                  about.terms_at ? formatMonthDay(about.terms_at) : '—',
                )
              : undefined
          }
        />
      </div>
      <Button
        kind="default"
        className="full"
        onClick={() => {
          void api.post('/api/logout').then(async () => {
            qc.clear();
            await navigate('/login', { replace: true });
          });
        }}
      >
        {t.lock}
      </Button>
      <p className="t-caption c-muted">{t.lockLine}</p>
    </Page>
  );
}

// ── V2-52 알림 ───────────────────────────────────────────────────────────────

export function NotifyScreen() {
  useDocumentTitle(t.notify.title);
  const qc = useQueryClient();
  const v = useTelegram().data;
  const n = t.notify;
  return (
    <WizardPage
      back={back}
      title={n.title}
      main={
        <>
          <TelegramCard settings />
          <Panel title={n.precheckTitle} tone="outline">
            <Note>{n.precheckLine}</Note>
          </Panel>
          <Panel title={n.eventsTitle} tone="outline">
            {(v?.events ?? []).map((e) => (
              <div key={e.key} className={s.switchRow}>
                <span className="t-body">{e.title}</span>
                {e.locked ? (
                  <span className="t-caption c-muted">{n.always}</span>
                ) : (
                  <Checkbox
                    checked={e.on}
                    aria-label={e.title}
                    onChange={(on) => {
                      void setTelegramEvent(e.key, on).then((next) => {
                        qc.setQueryData(settingsKeys.telegram, next);
                      });
                    }}
                  />
                )}
              </div>
            ))}
          </Panel>
        </>
      }
      side={<HowTo title={n.commandsTitle} steps={n.commands} note={n.noSymbols} />}
    />
  );
}

// ── V2-53 데이터 ─────────────────────────────────────────────────────────────

export function DataScreen() {
  useDocumentTitle(t.data.title);
  const q = useDataView();
  const v = q.data;
  const d = t.data;
  const navigate = useNavigate();
  const qc = useQueryClient();
  const file = useRef<HTMLInputElement>(null);
  const [msg, setMsg] = useState<{ tone: 'error' | 'success'; text: string } | null>(null);
  const kv = (k: string, value: string) => (
    <div className={s.kv}>
      <span className="t-caption c-muted">{k}</span>
      <strong className="t-body">{value}</strong>
    </div>
  );
  return (
    <WizardPage
      back={back}
      title={d.title}
      main={
        <>
          <Panel title={d.status}>
            {kv(
              d.bars,
              v?.bars.symbols && v.bars.from && v.bars.to
                ? d.barsValue(v.bars.symbols, v.bars.from, v.bars.to)
                : d.none,
            )}
            {kv(d.dartFin, v ? d.dartValue(v.dart.financials, v.dart.disclosures) : d.none)}
            {kv(d.dartShares, v ? d.sharesValue(v.dart.shares) : d.none)}
          </Panel>
          <Panel title={d.export} tone="outline">
            <div className={s.buttons}>
              <Button
                className={s.grow}
                onClick={() => void download('/api/history/csv', 'history.csv')}
              >
                {d.csv}
              </Button>
              <Button className={s.grow} onClick={() => void navigate('/strategies')}>
                {d.strategyFile}
              </Button>
            </div>
            <p className="t-caption c-muted">{d.strategyFileLine}</p>
          </Panel>
          <Panel title={d.backupTitle} tone="outline">
            <p className="t-body c-muted">{d.backupLine}</p>
            <div className={s.buttons}>
              <Button
                className={s.grow}
                onClick={() => void download('/api/data/backup', 'backup.db')}
              >
                {d.backup}
              </Button>
              <Button className={s.grow} onClick={() => file.current?.click()}>
                {d.restore}
              </Button>
              <input
                ref={file}
                type="file"
                hidden
                aria-label={d.restorePick}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (!f) return;
                  restoreBackup(f)
                    .then(async () => {
                      qc.clear();
                      await navigate('/login', { replace: true });
                    })
                    .catch((err: unknown) => {
                      setMsg({ tone: 'error', text: errorText(err) });
                    });
                }}
              />
            </div>
            <Note>{d.restoreLine}</Note>
            {msg ? <Box tone={msg.tone} title={msg.text} strongTitle /> : null}
          </Panel>
        </>
      }
      side={
        <Panel title={d.deleteTitle} tone="outline">
          <p className="t-body c-muted">{d.deleteLine}</p>
          {v?.live_running ? (
            <Box tone="error" icon="error">
              {d.deleteBlocked}
            </Box>
          ) : null}
          <Button
            kind="dangerOutline"
            className="full"
            disabled={Boolean(v?.live_running)}
            onClick={() => {
              api
                .delete('/api/data')
                .then(async () => {
                  qc.clear();
                  await qc.invalidateQueries({ queryKey: keys.state });
                  await navigate('/setup', { replace: true });
                })
                .catch((err: unknown) => {
                  setMsg({ tone: 'error', text: errorText(err) });
                });
            }}
          >
            {d.delete}
          </Button>
        </Panel>
      }
    />
  );
}

// ── V2-56 접속 ───────────────────────────────────────────────────────────────

export function AccessScreen() {
  useDocumentTitle(t.access.title);
  const q = useAccess();
  const qc = useQueryClient();
  const a = q.data;
  const x = t.access;
  const [error, setError] = useState<string | null>(null);
  const other = a?.place === 'pc' ? 'server' : 'pc';
  return (
    <WizardPage
      back={back}
      title={x.title}
      lead={x.lead}
      main={
        <>
          <Panel
            title={x.place}
            action={
              <TextLink
                onClick={() => {
                  setPlace(other)
                    .then((next) => {
                      qc.setQueryData(settingsKeys.access, next);
                    })
                    .catch((err: unknown) => {
                      setError(errorText(err));
                    });
                }}
              >
                {x.change}
              </TextLink>
            }
          >
            <div className={s.kv}>
              <span className="t-caption c-muted">{x.now}</span>
              <strong className="t-body">{a?.place_name ?? t.rows.placeNone}</strong>
            </div>
            <p className="t-caption c-muted">{x.placeLine}</p>
            {error ? <Box tone="error" title={error} strongTitle /> : null}
          </Panel>
          <Panel title={x.tailscale}>
            {a?.tailscale.ok ? (
              <>
                <Status kind="ok">{x.ok}</Status>
                <div className={s.kv}>
                  <span className="t-caption c-muted">{x.address}</span>
                  <strong className="t-body">{a.tailscale.address}</strong>
                </div>
              </>
            ) : (
              <>
                <Status kind="bad">{x.missing}</Status>
                <Note>{x.missingHelp}</Note>
                <Button className="full" onClick={() => void q.refetch()}>
                  {x.recheck}
                </Button>
              </>
            )}
          </Panel>
          <Note>{x.noPublic}</Note>
        </>
      }
      side={<HowTo title={x.howTitle} steps={setupV2.tailscale.how} />}
    />
  );
}

// ── V2-55 사용 조건 · 앱 정보 ────────────────────────────────────────────────

export function AboutV2Screen() {
  useDocumentTitle(t.about.title);
  const about = useAbout().data;
  const access = useAccess().data;
  const b = t.about;
  const place = access?.place ? t.placeShort[access.place] : '—';
  return (
    <WizardPage
      back={back}
      title={b.title}
      main={
        <Panel
          title={b.terms}
          tone="outline"
          action={
            about?.terms_at ? (
              <span className="t-caption c-muted">
                {b.agreed(formatMonthDayWeekday(about.terms_at))}
              </span>
            ) : undefined
          }
        >
          <p className="stack-inline">
            <StatusTag kind="plain" className={authStyles.draftTag}>
              {termsCopy.draft}
            </StatusTag>
            <span className="t-caption c-muted">{termsCopy.draftLine}</span>
          </p>
          {termsCopy.sections.map((sec) => (
            <section key={sec.title} className="stack-tight">
              <h2 className="t-body-strong">{sec.title}</h2>
              {sec.lines.map((l) => (
                <p key={l} className="t-body c-muted">
                  {l}
                </p>
              ))}
            </section>
          ))}
        </Panel>
      }
      side={
        <Panel title={b.app}>
          <div className={s.kv}>
            <span className="t-caption c-muted">{b.version}</span>
            <strong className="t-body">{about?.version ?? '—'}</strong>
          </div>
          <div className={s.kv}>
            <span className="t-caption c-muted">{b.place}</span>
            <strong className="t-body">{place}</strong>
          </div>
          <div className={s.kv}>
            <span className="t-caption c-muted">{b.access}</span>
            <strong className="t-body">
              {access?.tailscale.ok ? 'Tailscale' : (access?.local ?? '')}
            </strong>
          </div>
          <p className="t-caption c-muted">{b.line(about?.version ?? '', place)}</p>
        </Panel>
      }
    />
  );
}
