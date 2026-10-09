// 거르기: two chip rows that apply together — 규칙 (전체 [n] · rule [n]) and 종류 (marker + name + n).
// Counts come from the server (filters.*); 시작 counts in 전체 only (Figma 1:59344 '거르기').
import clsx from 'clsx';
import { Sparkles } from 'lucide-react';
import type { HistoryResponse } from '../../api/types';
import { RuleSelectChip } from '../../components/Chips';
import { EventMarker, type EventKind as MarkerKind } from '../../components/Markers';
import { historyCopy as hc } from '../../copy/history';
import { ruleName, type KindFilter } from './historyModel';
import styles from './History.module.css';

const KIND_MARKER: Record<KindFilter, MarkerKind | null> = {
  rebalance: 'rebalance',
  deposit: 'deposit',
  withdrawal: 'withdraw',
  dividend: 'dividend',
  failed: 'runFail',
  ai: null,
};

export interface FiltersProps {
  filters: HistoryResponse['filters'];
  rule: string;
  kind: KindFilter | null;
  onRule: (rule: string) => void;
  onKind: (kind: KindFilter | null) => void;
}

export function Filters({ filters, rule, kind, onRule, onKind }: FiltersProps) {
  return (
    <div className={clsx(styles.filters, styles.filtersArea)}>
      <div className={styles.chipRow} role="group" aria-label={hc.filters.rules}>
        <RuleSelectChip
          selected={rule === 'all'}
          name={hc.filters.all}
          weight={filters.total}
          onClick={() => {
            onRule('all');
          }}
        />
        {filters.rules.map(({ rule: r, count }) => (
          <RuleSelectChip
            key={r.id}
            selected={rule === r.id}
            name={ruleName(r)}
            weight={count}
            ai={r.ai}
            onClick={() => {
              onRule(r.id);
            }}
          />
        ))}
      </div>
      <div className={styles.chipRow} role="group" aria-label={hc.filters.kinds}>
        {filters.kinds.map(({ kind: k, count }) => {
          const marker = KIND_MARKER[k];
          const name = hc.filters.kind[k];
          return (
            <button
              key={k}
              type="button"
              className={styles.kindChip}
              aria-pressed={kind === k}
              onClick={() => {
                onKind(kind === k ? null : k);
              }}
            >
              {marker ? (
                <span aria-hidden className={styles.kindMarker}>
                  <EventMarker kind={marker} label={name} inert />
                </span>
              ) : (
                <span className={styles.aiMarker} aria-hidden>
                  <Sparkles size={14} />
                </span>
              )}
              <span className="t-caption">{hc.filters.chip(name, count)}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
