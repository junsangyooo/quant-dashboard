// Shared screen states every screen uses (기획 §5 상태 표): skeletons, the shell banner, the
// offline and other-device chips, the '예시' chip, one '낡음' tag per section, and the
// '다시 불러오기' error block. Copy comes from copy.ts.
import clsx from 'clsx';
import type { ReactNode } from 'react';
import { useLocation } from 'react-router';
import { copy } from '../copy';
import { bannerLink, bannerText } from '../api/adapters';
import { useConnection, useLastLoadedAt, useModeChange, useShell } from '../api/queries';
import { formatTime } from '../lib/format';
import { LinkButton, Button } from './Buttons';
import { InfoChip, SignalChip } from './Chips';
import { AlertBanner, StaleTag } from './Notices';
import type { TextStyle } from './Text';
import styles from './State.module.css';

// ── skeletons ────────────────────────────────────────────────────────────────

export interface SkeletonProps {
  /** Text style of the line it stands in for; keeps that line's height. Default body. */
  text?: TextStyle | undefined;
  /** Width of the hidden text (px or any CSS length). */
  width?: number | string | undefined;
  className?: string | undefined;
}

/** A grey bar where a number or a name will be (Figma 1:50024). */
export function Skeleton({ text = 'body', width = '100%', className }: SkeletonProps) {
  return (
    <span className={clsx(styles.line, `t-${text}`, className)} aria-hidden>
      <span className={clsx(styles.bar, styles[`bar-${text}`])} style={{ width }} />
    </span>
  );
}

/** A grey block for a graph or a card body ('스켈레톤 그래프', radius/card). */
export function SkeletonBlock({
  height,
  className,
}: {
  height: number;
  className?: string | undefined;
}) {
  return <span className={clsx(styles.block, className)} style={{ height }} aria-hidden />;
}

// ── shell-driven chips and banner ────────────────────────────────────────────

/** '16:11 다른 기기에서 실전 → 모의투자로 바뀜' (칩/신호 주의); place at the top of the body. */
export function ModeChangedChip() {
  const change = useModeChange();
  if (!change) return null;
  return (
    <SignalChip kind="warn">
      {copy.state.modeChanged(
        formatTime(change.at),
        copy.mode[change.from],
        copy.state.modeTo[change.to],
      )}
    </SignalChip>
  );
}

/** '16:10 불러온 값 · 연결 안 됨' (칩/정보) beside the numbers it qualifies; hidden when online. */
export function OfflineChip() {
  const connection = useConnection();
  const loadedAt = useLastLoadedAt();
  if (connection !== 'offline' || loadedAt === null) return null;
  return <InfoChip>{copy.state.offlineLoaded(formatTime(loadedAt))}</InfoChip>;
}

/** 이상 배너 from /api/shell (one at a time; the server picks it). */
export function ShellBanner({ className }: { className?: string | undefined }) {
  const shell = useShell();
  const { pathname } = useLocation();
  const data = shell.data;
  const banner = data?.banner ?? null;
  if (!data || !banner) return null;
  const link = bannerLink(banner, pathname);
  return (
    <AlertBanner
      className={className}
      action={link ? <LinkButton to={link.to}>{link.label}</LinkButton> : null}
    >
      {bannerText(banner, data.mode)}
    </AlertBanner>
  );
}

/** '예시' chip next to the ledger name; only fixture data sets `example`. */
export function ExampleChip({ show }: { show: boolean }) {
  return show ? <InfoChip>{copy.state.example}</InfoChip> : null;
}

/** One '낡음' tag for a section the response lists as stale (e.g. HomeResponse.stale). */
export function StaleMark<Section extends string>({
  stale,
  section,
}: {
  stale: readonly Section[];
  section: Section;
}) {
  return stale.includes(section) ? <StaleTag /> : null;
}

// ── errors ───────────────────────────────────────────────────────────────────

export interface ErrorBlockProps {
  /** copy.state.errors.* ('기록을 못 불러왔어요' …). */
  message: ReactNode;
  onRetry: () => void;
  /** While the retry is running. */
  retrying?: boolean | undefined;
  className?: string | undefined;
}

/** Body-area error with '다시 불러오기' (기록 · 그날 · 규칙 · 작동). */
export function ErrorBlock({ message, onRetry, retrying, className }: ErrorBlockProps) {
  return (
    <div className={clsx(styles.error, className)} role="status">
      <p className="t-body">{message}</p>
      <Button kind="default" onClick={onRetry} disabled={retrying}>
        {copy.state.retry}
      </Button>
    </div>
  );
}
