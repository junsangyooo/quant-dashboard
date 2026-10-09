// SCR-HOME 자산 (기획 §5): 지금 자산 → 자산 변동 → 계획 → 구성 on 390; 1440 puts 구성 in the
// right column (Figma 1:51434 · 1:54828). Header, banner and the mode-change chip are the shell's.
import clsx from 'clsx';
import { useState } from 'react';
import { useHome, useLedger, useNow } from '../../api/queries';
import type { HomePeriod, HomeResponse } from '../../api/types';
import { Gauge } from '../../charts/Gauge';
import { LinkButton } from '../../components/Buttons';
import { ErrorBlock, Skeleton, SkeletonBlock } from '../../components/State';
import { copy } from '../../copy';
import { homeCopy } from '../../copy/home';
import { planCopy } from '../../copy/plan';
import { pageTitle, useDocumentTitle } from '../../shell/page';
import { toneMap } from '../Plan/words';
import { CompositionCard } from './CompositionCard';
import { Hero } from './Hero';
import { PlanPreview } from './PlanPreview';
import { TrendCard } from './TrendCard';
import { WIDE, useMediaQuery } from './useMedia';
import styles from './Home.module.css';

/** Card frames, titles and tabs stay; every number, name and graph is a grey bar (1:53948). */
export function HomeSkeleton({ wide }: { wide: boolean }) {
  return (
    <div className={styles.columns} aria-busy="true">
      <div className={styles.left}>
        <div className={styles.hero}>
          <div className={styles.labelRow}>
            <Skeleton text="caption" width={121} />
            <Skeleton text="caption" width={77} />
          </div>
          <Skeleton text="display" width={220} />
          <div className={styles.chips}>
            <Skeleton text="caption" width={159} />
            <Skeleton text="caption" width={153} />
          </div>
          <Skeleton text="label" width={240} />
        </div>
        <div className={clsx(styles.trend, wide && styles.card)}>
          <Skeleton text="label" width={200} />
          <SkeletonBlock height={wide ? 300 : 180} />
          <Skeleton text="caption" width="100%" />
        </div>
        <section className={clsx(styles.card, styles.planCard)} aria-label={homeCopy.plan.title}>
          <div className={styles.cardHead}>
            <h2 className="t-heading-1">{homeCopy.plan.title}</h2>
            <LinkButton to="/plan">{homeCopy.plan.link}</LinkButton>
          </div>
          <div className={styles.planRule}>
            <div className={styles.nameRow}>
              <Skeleton text="body-strong" width={64} />
              <Skeleton text="caption" width={120} />
            </div>
            <Skeleton text="label" width={200} />
            <div className={styles.skeletonGauge}>
              <Gauge value={null} label={planCopy.gauge.empty} />
              <div className={styles.skeletonLines}>
                <Skeleton text="caption" width={110} />
                <Skeleton text="title" width={88} />
                <Skeleton text="caption" width={106} />
              </div>
            </div>
          </div>
          <Skeleton text="caption" width={240} />
        </section>
      </div>
      <div className={styles.right}>
        <section
          className={clsx(styles.card, styles.composition)}
          aria-label={homeCopy.composition.title}
        >
          <div className={styles.cardHead}>
            <h2 className="t-heading-1">{homeCopy.composition.title}</h2>
          </div>
          <SkeletonBlock height={12} />
          <div className={styles.skeletonRows}>
            {[0, 1, 2, 3, 4].map((i) => (
              <div key={i} className={styles.skeletonRow}>
                <span className={styles.skeletonLogo} />
                <div className={styles.skeletonLines}>
                  <Skeleton text="body-strong" width={96} />
                  <Skeleton text="caption" width={72} />
                </div>
                <div className={styles.skeletonLinesEnd}>
                  <Skeleton text="figure" width={80} />
                  <Skeleton text="caption" width={56} />
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function HomeBody({
  home,
  now,
  wide,
  onPeriod,
}: {
  home: HomeResponse;
  now: string | null;
  wide: boolean;
  onPeriod: (p: HomePeriod) => void;
}) {
  const tones = toneMap(
    home.composition.groups.flatMap((g) =>
      g.rows.flatMap((r) => (r.instrument ? [r.instrument] : [])),
    ),
  );
  return (
    <div className={styles.columns}>
      <div className={styles.left}>
        <Hero home={home} now={now} />
        <TrendCard home={home} wide={wide} onPeriod={onPeriod} />
        <PlanPreview home={home} now={now} wide={wide} tones={tones} />
      </div>
      <div className={styles.right}>
        <CompositionCard home={home} wide={wide} tones={tones} />
      </div>
    </div>
  );
}

export function HomeScreen() {
  useDocumentTitle(pageTitle('home'));
  const [period, setPeriod] = useState<HomePeriod | undefined>(undefined);
  const home = useHome(period ? { period } : {});
  const ledger = useLedger();
  const now = useNow();
  const wide = useMediaQuery(WIDE);

  // Keep the previous answer of the same ledger while another period loads (no flash); a
  // ledger switch (another device) drops it so the skeleton shows.
  const [kept, setKept] = useState<HomeResponse | null>(null);
  if (home.data && home.data !== kept) setKept(home.data);
  const data = home.data ?? (kept !== null && kept.ledger === ledger ? kept : null);

  return (
    <div className={styles.page}>
      <h1 className="sr-only">{copy.pages.home}</h1>
      {data ? (
        <HomeBody home={data} now={now} wide={wide} onPeriod={setPeriod} />
      ) : home.isError ? (
        <ErrorBlock
          message={homeCopy.errors.load}
          onRetry={() => void home.refetch()}
          retrying={home.isFetching}
        />
      ) : (
        <HomeSkeleton wide={wide} />
      )}
    </div>
  );
}
