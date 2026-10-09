// 자료별 (1:62685): title + legend (제때 · 늦음 · 낡음) + '막대 = 갱신 주기 대비 나이', then a row per
// source the API lists: state dot · name · chip, second line (기준 · 받은 시각 · 주기), and the
// age bar over three zones. The push row opens the device list (from /api/account).
import clsx from 'clsx';
import { useId, useState, type ReactNode } from 'react';
import { ChevronDown, ChevronUp, Laptop, Monitor, Smartphone, type LucideIcon } from 'lucide-react';
import { healthCopy as t } from '../../copy/health';
import { useAccount } from '../../api/queries';
import { LinkButton } from '../../components/Buttons';
import { SignalChip, type SignalKind } from '../../components/Chips';
import { Skeleton } from '../../components/State';
import { formatDateTime } from '../../lib/format';
import { sortSources, sourceView, type Source, type SourceView } from './text';
import styles from './Health.module.css';

/** Placeholder rows while the status is unknown: the 1단계 sources, values '—'. */
const UNKNOWN_IDS: readonly Source['id'][] = ['kr-quotes', 'us-quotes', 'fx'];

/** 8 days without a delivery is a warning (기획 §5 알림 기기 행). */
const STALE_DELIVERY_MS = 8 * 24 * 60 * 60 * 1000;

function AgeBar({ fill, tone }: { fill: number; tone: SignalKind }) {
  return (
    <span className={styles.ageBar} aria-hidden>
      <span className={styles.zones}>
        <span className={styles.zoneFresh} />
        <span className={styles.zoneLate} />
        <span className={styles.zoneStale} />
      </span>
      {fill > 0 ? (
        <>
          <span
            className={clsx(styles.ageFill, styles[`fill-${tone}`])}
            style={{ width: `${String(fill * 100)}%` }}
          />
          <span className={styles.ageNow} style={{ left: `calc(${String(fill * 100)}% - 1px)` }} />
        </>
      ) : null}
    </span>
  );
}

function RowBody({
  view,
  unknown,
  after,
}: {
  view: SourceView;
  unknown: boolean;
  after?: ReactNode;
}) {
  const tone = unknown ? 'unknown' : view.tone;
  return (
    <>
      <span className={styles.rowHead}>
        <span className={clsx(styles.dot, styles[`dot-${tone}`])} aria-hidden />
        <span className={clsx('t-body-strong', styles.rowName)}>{view.name}</span>
        <SignalChip kind={tone}>{unknown ? t.sources.state.unknown : view.chip}</SignalChip>
        {after}
      </span>
      <span className={clsx('t-caption', styles.muted, styles.rowLine)}>
        {unknown ? t.sources.noValue : view.line}
      </span>
      <AgeBar fill={unknown ? 0 : view.fill} tone={tone} />
    </>
  );
}

function deviceIcon(name: string): LucideIcon {
  if (/iphone|android|phone|galaxy/i.test(name)) return Smartphone;
  if (/mac|windows|linux|chromebook|pc/i.test(name)) return Laptop;
  return Monitor;
}

function DeviceList({ id, now }: { id: string; now: string | null }) {
  const q = useAccount();
  // Server time of the shell; without it the 8-day check waits.
  const nowMs = now === null ? null : Date.parse(now);
  if (q.isPending) {
    return (
      <div id={id} className={styles.devices}>
        <Skeleton text="body" width={180} />
        <Skeleton text="body" width={160} />
      </div>
    );
  }
  if (q.isError) {
    return (
      <div id={id} className={styles.devices}>
        <p className={clsx('t-caption', styles.muted)}>{t.devices.error}</p>
      </div>
    );
  }
  const devices = q.data.notifications.devices;
  const warn = (d: (typeof devices)[number]) =>
    !d.ok ||
    d.lastDelivery === null ||
    (nowMs !== null && nowMs - Date.parse(d.lastDelivery) > STALE_DELIVERY_MS);
  const needsSettings = devices.length === 0 || devices.some(warn);
  return (
    <div id={id} className={styles.devices}>
      {devices.length === 0 ? (
        <p className={clsx('t-caption', styles.muted)}>{t.devices.none}</p>
      ) : null}
      <ul className={styles.deviceList}>
        {devices.map((d) => {
          const Icon = deviceIcon(d.name);
          const bad = warn(d);
          return (
            <li key={d.name} className={styles.device}>
              <Icon size={24} aria-hidden />
              <span className={styles.deviceText}>
                <span className="t-body-strong">{d.name}</span>
                <span className={clsx('t-caption', styles.muted)}>
                  {d.lastDelivery
                    ? t.sources.lastDelivery(formatDateTime(d.lastDelivery))
                    : t.devices.never}
                </span>
              </span>
              <span
                className={clsx(styles.deviceDot, bad ? styles['dot-warn'] : styles['dot-ok'])}
                aria-hidden
              />
              <span className="sr-only">{bad ? t.devices.warn : t.devices.ok}</span>
            </li>
          );
        })}
      </ul>
      <LinkButton to="/account#notifications">
        {needsSettings ? t.devices.enable : t.devices.settings}
      </LinkButton>
    </div>
  );
}

export function SourcesCard({
  sources,
  now,
  unknown = false,
}: {
  sources: readonly Source[] | null;
  now: string | null;
  unknown?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const listId = useId();
  const rows: Source[] =
    sources !== null
      ? sortSources(sources)
      : UNKNOWN_IDS.map((id) => ({
          id,
          state: 'unknown',
          basis: null,
          receivedAt: null,
          cadence: 'daily',
          age: 0,
        }));

  return (
    <section
      className={clsx(styles.card, styles.sources, styles.areaSources)}
      aria-labelledby="health-sources"
    >
      <div className={styles.cardHead}>
        <h2 id="health-sources" className="t-heading-1">
          {t.sources.title}
        </h2>
        <ul className={styles.legend}>
          {(['fresh', 'late', 'stale'] as const).map((s) => (
            <li key={s} className={styles.legendItem}>
              <span className={clsx(styles.swatch, styles[`swatch-${s}`])} aria-hidden />
              <span className={clsx('t-caption', styles.muted)}>{t.sources.state[s]}</span>
            </li>
          ))}
        </ul>
      </div>
      <p className={clsx('t-caption', styles.muted)}>{t.sources.barNote}</p>
      <ul className={styles.rows}>
        {rows.map((src) => {
          const view = sourceView(src, now);
          const expandable = src.id === 'push-devices' && !unknown;
          return (
            <li key={src.id} className={styles.rowItem}>
              {expandable ? (
                <>
                  <button
                    type="button"
                    className={clsx(styles.row, styles.rowButton)}
                    aria-expanded={open}
                    aria-controls={open ? listId : undefined}
                    onClick={() => {
                      setOpen((o) => !o);
                    }}
                  >
                    <RowBody
                      view={view}
                      unknown={false}
                      after={
                        <span className={styles.rowChevron} aria-hidden>
                          {open ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                        </span>
                      }
                    />
                  </button>
                  {open ? <DeviceList id={listId} now={now} /> : null}
                </>
              ) : (
                <div className={styles.row}>
                  <RowBody view={view} unknown={unknown} />
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
