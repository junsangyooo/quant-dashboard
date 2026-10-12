// 기기 (Figma 1:65384): this device (icon · name · 들어온 시각 · '이 기기'), '이 기기 로그아웃', then for a
// lost phone '다른 기기 모두 로그아웃' behind a confirm modal (no drawing). Each button has one line
// above it saying what it does (the owner, 2026-10-12).
import clsx from 'clsx';
import { useId, useState } from 'react';
import { useNavigate } from 'react-router';
import { Laptop, LoaderCircle, Monitor, Smartphone, type LucideIcon } from 'lucide-react';
import { accountCopy as t } from '../../copy/account';
import { useLogout, useLogoutOthers } from '../../api/queries';
import type { AccountResponse } from '../../api/types';
import { Button } from '../../components/Buttons';
import { InfoChip } from '../../components/Chips';
import { ConfirmModal } from '../../components/ConfirmModal';
import { formatDateTime } from '../../lib/format';
import styles from './Account.module.css';

type ThisDevice = AccountResponse['thisDevice'];

const KIND_ICON: Record<ThisDevice['kind'], LucideIcon> = {
  'iphone-app': Smartphone,
  'iphone-safari': Smartphone,
  mac: Laptop,
  other: Monitor,
};

/** 'iPhone · 홈 화면 앱': the home-screen app's User-Agent names no browser. */
export function deviceLabel(device: ThisDevice): string {
  return device.kind === 'iphone-app' && !device.name.includes('·')
    ? `${device.name} · ${t.devices.homeScreenApp}`
    : device.name;
}

export function DevicesCard({ device }: { device: ThisDevice }) {
  const titleId = useId();
  const navigate = useNavigate();
  const logout = useLogout();
  const others = useLogoutOthers();
  const [confirm, setConfirm] = useState(false);
  const Icon = KIND_ICON[device.kind];

  return (
    <section className={clsx(styles.card, styles.devicesCard)} aria-labelledby={titleId}>
      <h2 id={titleId} className="t-heading-1">
        {t.devices.title}
      </h2>
      <div className={styles.thisDevice}>
        <Icon size={24} aria-hidden />
        <div className={styles.deviceText}>
          <span className="t-body-strong">{deviceLabel(device)}</span>
          <span className={clsx('t-caption', styles.muted)}>
            {t.devices.enteredAt(formatDateTime(device.enteredAt))}
          </span>
        </div>
        <InfoChip>{t.devices.thisDevice}</InfoChip>
      </div>
      <hr className={styles.divider} />
      <p className={clsx('t-caption', styles.muted)}>{t.devices.logoutWhat}</p>
      <Button
        kind="default"
        className={styles.wide}
        disabled={logout.isPending}
        onClick={() => {
          logout.mutate(undefined, {
            onSuccess: () => {
              void navigate('/pin', { replace: true });
            },
          });
        }}
      >
        {logout.isPending ? (
          <LoaderCircle size={18} className={styles.spinner} aria-hidden />
        ) : null}
        {t.devices.logout}
      </Button>
      {logout.isError ? (
        <p className={clsx('t-caption', styles.error)} role="alert">
          {t.devices.failed}
        </p>
      ) : null}
      <hr className={styles.divider} />
      <p className={clsx('t-caption', styles.muted)}>{t.devices.othersWhat}</p>
      <Button
        kind="danger"
        className={styles.wide}
        disabled={others.isPending}
        onClick={() => {
          others.reset();
          setConfirm(true);
        }}
      >
        {others.isPending ? (
          <LoaderCircle size={18} className={styles.spinner} aria-hidden />
        ) : null}
        {t.devices.logoutOthers}
      </Button>
      <div className={styles.contents} aria-live="polite">
        {others.isSuccess ? (
          <p className={clsx('t-caption', styles.success)}>{t.devices.othersDone}</p>
        ) : null}
        {others.isError ? (
          <p className={clsx('t-caption', styles.error)}>{t.devices.failed}</p>
        ) : null}
      </div>
      <ConfirmModal
        open={confirm}
        title={t.devices.confirmTitle}
        cancelLabel={t.devices.cancel}
        confirmLabel={t.devices.confirm}
        onCancel={() => {
          setConfirm(false);
        }}
        onConfirm={() => {
          setConfirm(false);
          others.mutate();
        }}
      >
        <p>{t.devices.confirmBody}</p>
      </ConfirmModal>
    </section>
  );
}
