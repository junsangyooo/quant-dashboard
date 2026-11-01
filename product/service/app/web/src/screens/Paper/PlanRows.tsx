// Plan pieces shared by 자산 (오늘 계획 카드) and 계획.
import clsx from 'clsx';
import type { Judgement, PlanDetail, ReasonRow } from '../../api/mvp';
import { Dots } from '../../components/Dots';
import { SideTag } from '../../components/Tags';
import { planCopy } from '../../copy/paper';
import { formatKrw, formatMonthDay, formatMonthDayWeekday } from '../../lib/format';
import { shares } from '../../lib/money';
import { dayTime } from '../../lib/when';
import styles from './Paper.module.css';

/** 이유 한 줄의 묶음들('② 신호' · '20일 최고가 돌파' · '종가 112,400원'). */
export function reasonParts(r: ReasonRow, withName: boolean, entry?: string | null): string[] {
  const extras: string[] = [];
  if (r.close !== undefined) extras.push(planCopy.close(formatKrw(r.close)));
  if (entry) extras.push(planCopy.bought(formatMonthDay(entry)));
  // 엔진이 지은 이유('종목 선정 · 상위 3종목 안' · '필터 미충족')는 글 안에 단계 이름이 있다
  if (r.special || !withName) return [`${r.circle} ${r.display}`, ...extras];
  return [`${r.circle} ${r.name}`, r.text, ...extras];
}

/** '10/30(금)' — 계획이 체결될 시가의 날(서버가 정한 값). */
export function fillDay(plans: readonly PlanDetail[]): string {
  const d = plans[0]?.fill_d;
  return d ? formatMonthDayWeekday(d) : '';
}

export function lastLine(last: Judgement | null): string {
  return last ? dayTime(last.made_at) : '';
}

/** 자산 화면 '오늘 계획' rows: tag · 종목 · 금액 or 수량 · first reason. */
export function PlanSummaryRows({ plans }: { plans: readonly PlanDetail[] }) {
  return (
    <ul className="stack-row">
      {plans.map((p) => (
        <li key={`${p.side}-${p.sym}`} className={styles.summaryRow}>
          <SideTag side={p.side} />
          <div className="stack-tight">
            <span className="t-body-strong">
              {p.name} {p.sym}
            </span>
            <span className="t-caption c-muted">
              <Dots
                parts={[
                  p.side === 'buy' ? planCopy.approx(formatKrw(p.value ?? 0)) : shares(p.qty ?? 0),
                  ...(p.reasons[0] ? reasonParts(p.reasons[0], false) : []),
                ]}
              />
            </span>
          </div>
        </li>
      ))}
    </ul>
  );
}

/** 계획 화면 카드: 매수 n종목 / 매도 n종목 with each stock and its reasons. */
export function PlanCard({ side, plans }: { side: 'buy' | 'sell'; plans: readonly PlanDetail[] }) {
  if (plans.length === 0) return null;
  return (
    <section className={styles.planCard}>
      <h2 className={clsx('t-heading-1', styles.planHead)}>
        <SideTag side={side} />
        {side === 'buy' ? planCopy.buyCount(plans.length) : planCopy.sellCount(plans.length)}
      </h2>
      {plans.map((p) => (
        <div key={p.sym} className="stack-inline">
          <div className={styles.planStock}>
            <span>
              <span className="t-body-strong">{p.name}</span>{' '}
              <span className="t-caption c-muted">{p.sym}</span>
            </span>
            <span className="t-caption">
              <Dots
                parts={[
                  side === 'buy'
                    ? planCopy.approx(formatKrw(p.value ?? 0))
                    : p.held_qty !== undefined && p.held_qty !== null && p.held_qty === p.qty
                      ? planCopy.sellAll(shares(p.qty))
                      : shares(p.qty ?? 0),
                  planCopy.atOpen(formatMonthDayWeekday(p.fill_d)),
                ]}
              />
            </span>
          </div>
          <div className={styles.reasons}>
            <p className="t-caption">{planCopy.reason}</p>
            {p.reasons.map((r, i) => (
              <p key={`${r.slot}-${String(i)}`} className="t-caption">
                <Dots
                  parts={reasonParts(
                    r,
                    true,
                    side === 'sell' && i === p.reasons.length - 1 ? p.entry_d : null,
                  )}
                />
              </p>
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}
