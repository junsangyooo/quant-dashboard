// SCR-RULES 규칙 (Figma 1:60971 · 1:61226 · 1:61661 · 1:61916 · 1:62197), view only.
// One rule at a time: 390 rule chips / 1100px up a list of rule cards with '보기 전용' → rule head
// (name · 자산의 % · 목표, status chip · AI chip · 예시) → fixed rule: six summary tiles / AI rule:
// '흐름' chips when it has several start lanes, then the node-card flow → '계획에서 지금 위치 보기 ›'.
// The rule id is in the path (/rules/:ruleId) and the lane in ?lane=.
import clsx from 'clsx';
import { Sparkles } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router';
import { ruleStatusChip } from '../../api/adapters';
import { useRule, useRules, useShell } from '../../api/queries';
import type { FlowDisplay, RuleDetailResponse, RulesListResponse } from '../../api/types';
import { LinkButton } from '../../components/Buttons';
import { AiChip, RebalanceChip, RuleSelectChip } from '../../components/Chips';
import { ErrorBlock, ExampleChip, Skeleton, SkeletonBlock } from '../../components/State';
import { copy } from '../../copy';
import { rulesCopy as rc } from '../../copy/rules';
import { formatPercent } from '../../lib/format';
import { pageTitle, useDocumentTitle } from '../../shell/page';
import { ruleName } from '../History/historyModel';
import { useMinWidth } from '../History/useMinWidth';
import { FlowCanvas } from './FlowCanvas';
import { RuleTiles } from './RuleTiles';
import styles from './Rules.module.css';

type ListItem = RulesListResponse['rules'][number];

function laneLabel(lane: FlowDisplay['lanes'][number]): string {
  switch (lane.label.kind) {
    case 'daily':
      return rc.flow.lane.daily(lane.label.time ?? '');
    case 'earnings':
      return rc.flow.lane.earnings;
    case 'monthly':
      return rc.flow.lane.monthly;
    case 'quarterly':
      return rc.flow.lane.quarterly;
  }
}

function RuleList({ rules, selected }: { rules: readonly ListItem[]; selected: string }) {
  return (
    <ul className={styles.ruleList}>
      {rules.map(({ rule, share, status }) => {
        const chip = ruleStatusChip(status, rule.ai);
        const current = rule.id === selected;
        return (
          <li key={rule.id}>
            <Link
              to={`/rules/${rule.id}`}
              replace
              preventScrollReset
              className={clsx(styles.ruleCard, current && styles.ruleCardOn)}
              aria-current={current ? 'page' : undefined}
            >
              <span className={styles.ruleCardStripe} aria-hidden />
              <span className={styles.ruleCardBody}>
                <span className={styles.ruleCardName}>
                  {rule.ai ? <Sparkles size={16} className={styles.aiIcon} aria-hidden /> : null}
                  <span className={clsx('t-body-strong', styles.grow)}>{ruleName(rule)}</span>
                  <span className="t-heading-1">{formatPercent(share.pct)}</span>
                </span>
                <span className={styles.shareBar} aria-hidden>
                  <span
                    className={clsx(
                      styles.shareFill,
                      rule.colorIndex === 0 ? styles.strategy1 : styles.strategy2,
                    )}
                    style={{ width: `${String(Math.min(100, share.pct))}%` }}
                  />
                </span>
                <span className={styles.chipRow}>
                  <RebalanceChip state={chip.state}>{chip.label}</RebalanceChip>
                  <AiChip included={rule.ai} />
                </span>
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

function RuleChips({ rules, selected }: { rules: readonly ListItem[]; selected: string }) {
  const navigate = useNavigate();
  return (
    <div className={styles.ruleChips} role="group" aria-label={copy.pages.rules}>
      {rules.map(({ rule, share }) => (
        <RuleSelectChip
          key={rule.id}
          selected={rule.id === selected}
          name={ruleName(rule)}
          weight={formatPercent(share.pct)}
          ai={rule.ai}
          onClick={() => {
            void navigate(`/rules/${rule.id}`, { replace: true, preventScrollReset: true });
          }}
        />
      ))}
    </div>
  );
}

function RuleHead({
  detail,
  children,
}: {
  detail: RuleDetailResponse;
  /** '흐름' chips: part of the head, 8 under the status chips (Figma 17:5855 '흐름 고르기'). */
  children?: ReactNode;
}) {
  const chip = ruleStatusChip(detail.status, detail.rule.ai);
  const name = ruleName(detail.rule);
  return (
    <div className={styles.ruleHead}>
      <div className={styles.titleRow}>
        <h1 className={clsx(name.length > 8 ? styles.titleLong : styles.title)}>{name}</h1>
        <p className={styles.share}>
          <span className={clsx('t-caption', styles.muted)}>{rc.shareOf}</span>
          <span className="t-heading-1">{formatPercent(detail.share.pct)}</span>
          {detail.share.target !== null ? (
            <span className={clsx('t-caption', styles.muted)}>
              {rc.target(formatPercent(detail.share.target, 0))}
            </span>
          ) : null}
        </p>
      </div>
      <div className={styles.chipRow}>
        <RebalanceChip state={chip.state}>{chip.label}</RebalanceChip>
        <AiChip included={detail.rule.ai} />
        <ExampleChip show={detail.example} />
      </div>
      {children}
    </div>
  );
}

function LaneChips({ display, ruleId }: { display: FlowDisplay; ruleId: string }) {
  const navigate = useNavigate();
  if (display.lanes.length < 2) return null;
  return (
    <div className={styles.lanes} role="group" aria-labelledby={`lanes-${ruleId}`}>
      <span id={`lanes-${ruleId}`} className={clsx('t-caption', styles.muted)}>
        {rc.flow.lanes}
      </span>
      {display.lanes.map((lane) => (
        <RuleSelectChip
          key={lane.id}
          selected={lane.id === display.lane}
          name={laneLabel(lane)}
          onClick={() => {
            void navigate(`/rules/${ruleId}?lane=${encodeURIComponent(lane.id)}`, {
              replace: true,
              preventScrollReset: true,
            });
          }}
        />
      ))}
    </div>
  );
}

function DetailSkeleton() {
  return (
    <div className={styles.detail} aria-busy="true">
      <div className={styles.ruleHead}>
        <Skeleton text="title" width={160} />
        <Skeleton text="label" width={220} />
      </div>
      <div className={styles.tiles}>
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <SkeletonBlock key={i} height={178} />
        ))}
      </div>
    </div>
  );
}

function Detail({ id, lane, nowIso }: { id: string; lane: string | null; nowIso: string | null }) {
  const q = useRule(id, lane ? { lane } : {});
  if (q.isPending) return <DetailSkeleton />;
  if (!q.data) {
    return (
      <div className={styles.detail}>
        <h1 className="sr-only">{copy.pages.rules}</h1>
        <ErrorBlock
          message={copy.state.errors.rules}
          onRetry={() => void q.refetch()}
          retrying={q.isFetching}
        />
      </div>
    );
  }
  const detail = q.data;
  // Sources that were stale at the last check (CONTRACT RuleDetailResponse.stale): the '지금'
  // box says '낡음' and the deviation points hide (기획 §5 SCR-RULES error 자료 낡음).
  const stale = detail.stale.length > 0;
  return (
    <div className={styles.detail}>
      <RuleHead detail={detail}>
        {detail.display.kind === 'flow' ? (
          <LaneChips display={detail.display} ruleId={detail.rule.id} />
        ) : null}
      </RuleHead>
      {detail.display.kind === 'flow' ? (
        <FlowCanvas
          display={detail.display}
          name={ruleName(detail.rule)}
          colorIndex={detail.rule.colorIndex}
          ai={detail.rule.ai}
          nowIso={nowIso}
          stale={stale}
        />
      ) : (
        <RuleTiles display={detail.display} colorIndex={detail.rule.colorIndex} stale={stale} />
      )}
      <div>
        <LinkButton to={`/plan#rule-${detail.rule.id}`}>{rc.planLink}</LinkButton>
      </div>
    </div>
  );
}

export function RulesScreen() {
  const { ruleId } = useParams();
  const [params] = useSearchParams();
  const wide = useMinWidth(1100);
  const list = useRules();
  const shell = useShell();
  useDocumentTitle(pageTitle('rules'));

  const rules = list.data?.rules ?? [];
  const known = rules.find((r) => r.rule.id === ruleId);
  const selected = known?.rule.id ?? rules[0]?.rule.id ?? null;
  const many = rules.length > 1;
  const lane = params.get('lane');
  // The list head's '예시' chip (CONTRACT RulesListResponse rules[].example).
  const example = rules.some((r) => r.example);

  if (list.isPending) {
    return (
      <div className={styles.page} aria-busy="true">
        <h1 className="sr-only">{copy.pages.rules}</h1>
        {wide ? (
          <div className={styles.side}>
            <SkeletonBlock height={100} />
            <SkeletonBlock height={100} />
          </div>
        ) : (
          <SkeletonBlock height={36} />
        )}
        <DetailSkeleton />
      </div>
    );
  }

  if (!list.data || selected === null) {
    return (
      <div className={styles.page}>
        <h1 className="sr-only">{copy.pages.rules}</h1>
        <ErrorBlock
          message={copy.state.errors.rules}
          onRetry={() => void list.refetch()}
          retrying={list.isFetching}
        />
      </div>
    );
  }

  return (
    <div className={clsx(styles.page, many && styles.pageWithList)}>
      {many && wide ? (
        <div className={styles.side}>
          <div className={styles.listHead}>
            <span className={clsx('t-label', styles.muted, styles.grow)}>
              {rc.count(rules.length)}
            </span>
            <ExampleChip show={example} />
          </div>
          <RuleList rules={rules} selected={selected} />
          <p className={clsx('t-caption', styles.muted)}>{rc.viewOnly}</p>
        </div>
      ) : null}
      {many && !wide ? <RuleChips rules={rules} selected={selected} /> : null}
      <Detail id={selected} lane={lane} nowIso={shell.data?.now ?? null} />
    </div>
  );
}
