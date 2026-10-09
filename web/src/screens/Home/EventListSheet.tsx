// 사건 목록: a grouped '[n]' marker opens the list of its events; each opens that day's panel.
// Also the ⓘ 표식 범례 sheet (시작 · 리밸런싱 · 일부 실패 · 진행 중 · 배당 · 입금 · 출금 · 실전 켬/끔).
import { Link } from 'react-router';
import type { ChartEvent } from '../../charts/geometry/lineChart';
import { EventMarker, type EventKind } from '../../components/Markers';
import { homeCopy } from '../../copy/home';
import { Sheet } from './Sheet';
import styles from './Home.module.css';

export function EventListSheet({
  events,
  onClose,
}: {
  events: readonly ChartEvent[];
  onClose: () => void;
}) {
  return (
    <Sheet title={homeCopy.eventList} onClose={onClose}>
      <ul className={styles.sheetList}>
        {events.map((e, i) => (
          <li key={`${e.date}-${e.kind}-${String(i)}`}>
            <Link to={`/day/${e.date}`} className={styles.sheetLink}>
              <span aria-hidden>
                <EventMarker kind={e.kind} label={e.label} inert />
              </span>
              <span className="t-body">{e.label}</span>
            </Link>
          </li>
        ))}
      </ul>
    </Sheet>
  );
}

const LEGEND: readonly { kind: EventKind; label: string }[] = [
  { kind: 'start', label: homeCopy.legend.start },
  { kind: 'rebalance', label: homeCopy.legend.rebalance },
  { kind: 'partialFail', label: homeCopy.legend.partialFail },
  { kind: 'rebalanceInProgress', label: homeCopy.legend.inProgress },
  { kind: 'dividend', label: homeCopy.legend.dividend },
  { kind: 'deposit', label: homeCopy.legend.deposit },
  { kind: 'withdraw', label: homeCopy.legend.withdraw },
  { kind: 'liveOn', label: homeCopy.legend.live },
];

export function LegendSheet({ onClose }: { onClose: () => void }) {
  return (
    <Sheet title={homeCopy.legend.title} onClose={onClose}>
      <ul className={styles.legendGrid}>
        {LEGEND.map((item) => (
          <li key={item.kind} className={styles.legendEntry}>
            <EventMarker kind={item.kind} label={item.label} inert />
            <span className="t-body" aria-hidden>
              {item.label}
            </span>
          </li>
        ))}
      </ul>
    </Sheet>
  );
}
