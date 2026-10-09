// SCR-MODE 모의투자·실전 (Figma 1:64094 · 1:64317 · 1:64451 · 1:64669 · 1:64799 · 1:64956 ·
// 1:65110 · 1:65140). Section order by state (기획 §5 레이아웃 의도):
//   모의투자          세그먼트 → (두 장부) → 성적 → 켜기 전 점검 → 첫 주문 미리보기 → 실전으로 켜기
//   모의투자 · 점검 ✕ 세그먼트 → 점검 → 미리보기 → 켜기(비활성) → (두 장부) → 성적
//   실전              세그먼트 + 기간 칩 → 두 장부 → 성적 → 실전 끄기
//   끄기 실패         빨간 카드 → 세그먼트 → 두 장부(실전 기간) → 성적
// From 900px: left 7 of 12 (세그먼트 · 두 장부 · 성적 · 점검), right 5 (미리보기 · 켜기 · 끄기).
import clsx from 'clsx';
import { useRef, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { copy } from '../../copy';
import { modeCopy as t } from '../../copy/mode';
import { queryKeys, useCancelRetry, useMode, useNow, useShell } from '../../api/queries';
import type { ModeResponse } from '../../api/types';
import { InfoChip } from '../../components/Chips';
import { ModeSwitch } from '../../components/Controls';
import { ErrorBlock, Skeleton, SkeletonBlock } from '../../components/State';
import { PageTitle } from '../../shell/PageTitle';
import { pageTitle, useDocumentTitle } from '../../shell/page';
import { useMediaQuery } from '../Pin/useMediaQuery';
import { CancelFailedCard, PerformanceCard, PreflightSection, PreviewCard } from './Sections';
import { TurnOffSection } from './TurnOff';
import { TurnOnCard } from './TurnOn';
import { TwoLedgersCard } from './TwoLedgers';
import { blockingCauses, modeLine, periodChip, type OkPreview } from './text';
import styles from './Mode.module.css';

const WIDE = '(min-width: 900px)';

function scrollToCard(el: HTMLElement | null) {
  if (!el) return;
  // jsdom has neither; both stay optional here.
  const media = (window as Partial<Window>).matchMedia;
  const reduced = media?.('(prefers-reduced-motion: reduce)').matches ?? false;
  (el as Partial<HTMLElement>).scrollIntoView?.({
    behavior: reduced ? 'auto' : 'smooth',
    block: 'start',
  });
  el.querySelector<HTMLElement>('input:not([disabled]), button:not([disabled])')?.focus({
    preventScroll: true,
  });
}

function ModeSkeleton() {
  return (
    <div className={styles.column} aria-busy="true">
      <SkeletonBlock height={57} />
      <Skeleton text="body" width={220} />
      <SkeletonBlock height={400} />
      <SkeletonBlock height={260} />
    </div>
  );
}

export function ModeScreen() {
  useDocumentTitle(pageTitle('mode'));
  const q = useMode();
  const shell = useShell();
  const now = useNow();
  const wide = useMediaQuery(WIDE);
  const client = useQueryClient();
  const cancelRetry = useCancelRetry();
  const turnOnRef = useRef<HTMLElement>(null);
  const turnOffRef = useRef<HTMLDivElement>(null);
  /** A preview a 409 preview-changed brought, kept while the server still shows the old one. */
  const [changed, setChanged] = useState<{
    preview: OkPreview;
    at: string;
    replaced: string | null;
  } | null>(null);

  let body: ReactNode;
  if (q.isPending) {
    body = <ModeSkeleton />;
  } else if (q.isError && !q.data) {
    body = (
      <ErrorBlock message={t.error} onRetry={() => void q.refetch()} retrying={q.isFetching} />
    );
  } else {
    const m: ModeResponse = q.data;
    const serverHash = m.preview?.kind === 'ok' ? m.preview.hash : null;
    const override = changed !== null && changed.replaced === serverHash ? changed : null;
    const preview = override?.preview ?? m.preview;
    const cancelFailed = m.cancelFailed && m.cancelFailed.length > 0 ? m.cancelFailed : null;
    const canTurnOnBlock = m.mode === 'paper' && cancelFailed === null;
    const checksBlocked =
      canTurnOnBlock &&
      !m.canTurnOn.ok &&
      m.canTurnOn.cause === 'checks' &&
      blockingCauses(m.preflight).count > 0;
    const firstCheckAt =
      shell.data?.status.kind === 'before-first' ? shell.data.status.firstCheckAt : null;
    const chip = periodChip(m);

    const modeSection = (
      <section key="mode" className={styles.modeSection} aria-label={t.segment}>
        <ModeSwitch
          value={m.mode}
          aria-label={t.segment}
          onSelect={(next) => {
            if (next === m.mode) return;
            scrollToCard(next === 'live' ? turnOnRef.current : turnOffRef.current);
          }}
        />
        <div className={styles.modeLine}>
          {chip ? <InfoChip>{chip}</InfoChip> : null}
          <p className={clsx('t-body', styles.muted)}>{modeLine(m)}</p>
        </div>
      </section>
    );
    const cancelCard = cancelFailed ? (
      <CancelFailedCard
        key="cancel"
        orders={cancelFailed}
        retrying={cancelRetry.isPending}
        failed={
          cancelRetry.isSuccess ? cancelRetry.data.cancelFailed.length > 0 : cancelRetry.isError
        }
        onRetry={() => {
          cancelRetry.mutate(undefined, {
            onSuccess: (res) => {
              // The answer is authoritative: drop the card at once, the refetch confirms it.
              client.setQueryData<ModeResponse>(queryKeys.mode, (old) =>
                old
                  ? { ...old, cancelFailed: res.cancelFailed.length > 0 ? res.cancelFailed : null }
                  : old,
              );
            },
          });
        }}
      />
    ) : null;
    const twoLedgers = m.twoLedgers ? <TwoLedgersCard key="two" data={m.twoLedgers} /> : null;
    const performance = (
      <PerformanceCard
        key="performance"
        performance={m.performance}
        firstCheckAt={firstCheckAt}
        showLink={m.twoLedgers === null}
      />
    );
    const preflight =
      canTurnOnBlock && m.preflight ? (
        <PreflightSection key="preflight" preflight={m.preflight} now={now} />
      ) : null;
    const previewCard =
      canTurnOnBlock && preview ? (
        <PreviewCard
          key="preview"
          preview={preview}
          preflight={m.preflight}
          changedAt={override?.at ?? null}
          now={now}
        />
      ) : null;
    const turnOn = canTurnOnBlock ? (
      <TurnOnCard
        key="turn-on"
        ref={turnOnRef}
        mode={m}
        preview={preview}
        onPreviewChanged={(next, at) => {
          setChanged({ preview: next, at, replaced: serverHash });
        }}
      />
    ) : null;
    const turnOff =
      m.mode === 'live' ? <TurnOffSection key="turn-off" ref={turnOffRef} now={now} /> : null;

    let left: ReactNode[];
    let right: ReactNode[];
    if (cancelCard) {
      left = [cancelCard, modeSection, twoLedgers, performance];
      right = [];
    } else if (m.mode === 'live') {
      left = [modeSection, twoLedgers, performance];
      right = [turnOff];
    } else if (checksBlocked) {
      left = [modeSection, preflight, twoLedgers, performance];
      right = [previewCard, turnOn];
    } else {
      left = [modeSection, twoLedgers, performance, preflight];
      right = [previewCard, turnOn];
    }
    // 390 reads one column; the blocked order puts 미리보기 · 켜기 before 성적.
    const narrow = checksBlocked
      ? [modeSection, preflight, previewCard, turnOn, twoLedgers, performance]
      : [...left, ...right];

    body = wide ? (
      <div className={styles.twoColumns}>
        <div className={clsx(styles.column, styles.left)}>{left}</div>
        <div className={clsx(styles.column, styles.right)}>{right}</div>
      </div>
    ) : (
      <div className={styles.column}>{narrow}</div>
    );
  }

  return (
    <div className={styles.screen}>
      <PageTitle>{copy.pages.mode}</PageTitle>
      {body}
    </div>
  );
}
