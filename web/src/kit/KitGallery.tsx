// /_kit — every Figma component and variant (DEV builds only). Each box carries the Figma
// node id it reproduces (data-figma-id) so screenshots can be paired with Figma exports.
import { createContext, useContext, useState, type CSSProperties, type ReactNode } from 'react';
import { useSearchParams } from 'react-router';
import {
  ArrowLeftRight,
  Check,
  ChevronRight,
  CircleCheck,
  CircleMinus,
  CirclePlus,
  Settings,
} from 'lucide-react';
import { copy, kitCopy } from '../copy';
import { Flag, InitialLogo, KindBadge, ModeBadge } from '../components/Badges';
import {
  Button,
  CollapseButton,
  ExpandButton,
  IconButton,
  LinkButton,
} from '../components/Buttons';
import {
  AiChip,
  ExceptionChip,
  HeaderStatusChip,
  InfoChip,
  LegendChip,
  PeriodChip,
  RebalanceChip,
  RuleSelectChip,
  SignalChip,
} from '../components/Chips';
import { ConfirmModal } from '../components/ConfirmModal';
import { Checkbox, KeypadKey, ModeSwitch, PinCell, Toggle } from '../components/Controls';
import { Header } from '../components/Header';
import {
  CalendarCell,
  EventMarker,
  type CalendarState,
  type EventKind,
} from '../components/Markers';
import { BottomTabs, NavItem, type TabKey } from '../components/Nav';
import { NodeCard, NodeIcon, NodeRow, NodeRowLabel } from '../components/NodeCard';
import { AlertBanner, ModeStrip, StaleTag } from '../components/Notices';
import { CheckRow, ExpandRow, OrderRow, StatusLine } from '../components/Rows';
import { RuleBlock, RuleCardHead, RuleTargetCell } from '../components/Rules';
import { Text } from '../components/Text';
import { CalendarGrid } from '../charts/CalendarGrid';
import { ChartTable } from '../charts/ChartTable';
import { CompositionBar } from '../charts/CompositionBar';
import { DeviationBand } from '../charts/DeviationBand';
import { DriftChart } from '../charts/DriftChart';
import { Gauge } from '../charts/Gauge';
import { HistoryChart } from '../charts/HistoryChart';
import { LineChart } from '../charts/LineChart';
import { Waterfall } from '../charts/Waterfall';
import { DRIFT_1440, DRIFT_390 } from '../charts/geometry/drift';
import {
  LINE_HISTORY_1440,
  LINE_HISTORY_390,
  LINE_HOME_1440,
  LINE_HOME_390,
  niceYAxis,
} from '../charts/geometry/lineChart';
import {
  driftIndex,
  driftMomentum,
  paperCalendar,
  paperCalendarState,
  paperDaily3m,
  paperDailySinceStart,
  paperEvents,
  untouchedDaily3m,
} from '../fixtures/charts';
import { formatKrw, formatKrwSigned, formatMonthDay, formatMonthDayWeekday } from '../lib/format';
import { useDocumentTitle } from '../shell/page';
import styles from './KitGallery.module.css';

/** `?only=<id>` renders a single variant box at the page origin. */
const OnlyContext = createContext<string | null>(null);

function Section({ name, id, children }: { name: string; id: string; children: ReactNode }) {
  const only = useContext(OnlyContext);
  return (
    <section className={styles.section} data-figma-set={id}>
      {only === null ? (
        <div className={styles.sectionHead}>
          <h2 className="t-heading-1">{name}</h2>
          <span className={`t-micro ${styles.muted ?? ''}`}>{id}</span>
        </div>
      ) : null}
      <div className={styles.variants}>{children}</div>
    </section>
  );
}

function V({
  name,
  id,
  width,
  children,
}: {
  name: string;
  id: string;
  width?: number | undefined;
  children: ReactNode;
}) {
  const only = useContext(OnlyContext);
  const style: CSSProperties | undefined = width === undefined ? undefined : { width };
  if (only !== null && only !== id) return null;
  return (
    <div className={styles.variant}>
      {only === null ? <span className={`t-micro ${styles.muted ?? ''}`}>{name}</span> : null}
      <div className={styles.box} data-figma-id={id} style={style}>
        {children}
      </div>
    </div>
  );
}

const EVENT_VARIANTS: readonly [EventKind, string, string][] = [
  ['rebalance', '종류=리밸런싱', '1:4817'],
  ['rebalanceInProgress', '종류=리밸런싱 중', '1:4823'],
  ['partialFail', '종류=일부 실패', '1:4829'],
  ['deposit', '종류=입금', '1:4836'],
  ['withdraw', '종류=출금', '1:4841'],
  ['dividend', '종류=배당', '1:4846'],
  ['liveOn', '종류=실전 켬', '1:4852'],
  ['start', '종류=시작', '1:41983'],
];

const CALENDAR_VARIANTS: readonly [CalendarState, string][] = [
  ['ok', '1:24071'],
  ['rebalance', '1:24072'],
  ['rebalanceInProgress', '1:24078'],
  ['partialFail', '1:24084'],
  ['fail', '1:24090'],
  ['noRun', '1:24094'],
  ['holiday', '1:24098'],
  ['future', '1:24100'],
  ['beforeRecord', '1:24101'],
  ['oneMarketHoliday', '1:39577'],
  ['awaitingQuote', '1:42668'],
];

const TAB_VARIANTS: readonly [TabKey, string, string][] = [
  ['home', '1:4890', '1:4999'],
  ['plan', '1:4914', '1:5025'],
  ['history', '1:4938', '1:5051'],
  ['rules', '1:4962', '1:5077'],
];

const homeAxis = niceYAxis(
  [...paperDaily3m, ...untouchedDaily3m].flatMap((p) => (p.value === null ? [] : [p.value])),
);
const historyAxis = niceYAxis(
  paperDailySinceStart.flatMap((p) => (p.value === null ? [] : [p.value])),
);
const homeEvents = paperEvents.filter((e) => e.date >= '2026-07-07' && e.kind !== 'runFail');
const driftEvents = paperEvents.filter(
  (e) => e.kind === 'rebalance' || e.kind === 'rebalanceInProgress',
);
const dayHref = (date: string) => `/day/${date}`;

export function KitGallery() {
  useDocumentTitle(`${kitCopy.title} · ${copy.wordmark}`);
  const [toggle, setToggle] = useState(true);
  const [check, setCheck] = useState(true);
  const [mode, setMode] = useState<'paper' | 'live'>('paper');
  const [expanded, setExpanded] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [params] = useSearchParams();
  const only = params.get('only');

  return (
    <OnlyContext value={only}>
      <main
        id="main"
        className={only === null ? styles.kit : `${styles.kit ?? ''} ${styles.isolated ?? ''}`}
      >
        <h1 className={only === null ? 't-title' : 'sr-only'}>{kitCopy.title}</h1>

        <Section name="헤더" id="1:4987 · 1:5103">
          <V name="헤더/390" id="1:4987" width={390}>
            <Header
              mode="paper"
              status={{ status: 'ok', label: copy.headerStatus.ok('08:30') }}
              current={null}
              layout="390"
            />
          </V>
          {TAB_VARIANTS.map(([key, , id]) => (
            <div key={id} className={styles.scroll}>
              <V name={`헤더/1440/현재=${copy.nav[key]}`} id={id} width={1440}>
                <Header
                  mode="paper"
                  status={{ status: 'ok', label: copy.headerStatus.ok('08:30') }}
                  current={key}
                  layout="1440"
                />
              </V>
            </div>
          ))}
        </Section>

        <Section name="내비" id="1:4986 · 1:1297">
          {TAB_VARIANTS.map(([key, id]) => (
            <V key={id} name={`내비/하단 탭/현재=${copy.nav[key]}`} id={id} width={390}>
              <BottomTabs current={key} layout="390" />
            </V>
          ))}
          <V name="내비/항목/상태=현재" id="1:1291">
            <NavItem to="/" current>
              {copy.nav.home}
            </NavItem>
          </V>
          <V name="내비/항목/상태=기본" id="1:1294">
            <NavItem to="/history" current={false}>
              {copy.nav.history}
            </NavItem>
          </V>
        </Section>

        <Section name="배지" id="1:4751 · 1:4783">
          <V name="배지/모드/모드=모의투자" id="1:4747">
            <ModeBadge mode="paper" />
          </V>
          <V name="배지/모드/모드=실전" id="1:4749">
            <ModeBadge mode="live" />
          </V>
          <V name="배지/종류" id="1:4783">
            <KindBadge>{kitCopy.kinds.etf}</KindBadge>
          </V>
        </Section>

        <Section name="칩/헤더 상태" id="1:4758">
          <V name="상태=정상" id="1:4752">
            <HeaderStatusChip status="ok">{copy.headerStatus.ok('08:30')}</HeaderStatusChip>
          </V>
          <V name="상태=점검" id="1:4755">
            <HeaderStatusChip status="check">{copy.headerStatus.check(2)}</HeaderStatusChip>
          </V>
          <V name="상태=오류" id="1:42662">
            <HeaderStatusChip status="error">{copy.headerStatus.check(2)}</HeaderStatusChip>
          </V>
          <V name="상태=확인 불가" id="1:42665">
            <HeaderStatusChip status="unknown">{copy.headerStatus.check(2)}</HeaderStatusChip>
          </V>
        </Section>

        <Section name="칩/리밸런싱 상태" id="1:4782">
          <V name="상태=목표 범위 안" id="1:4761">
            <RebalanceChip state="inRange" />
          </V>
          <V name="상태=리밸런싱 예정" id="1:4764">
            <RebalanceChip state="scheduled" />
          </V>
          <V name="상태=리밸런싱 중" id="1:4767">
            <RebalanceChip state="inProgress" />
          </V>
          <V name="상태=일부 실패" id="1:4770">
            <RebalanceChip state="partialFail" />
          </V>
          <V name="상태=휴장" id="1:4773">
            <RebalanceChip state="holiday" />
          </V>
          <V name="상태=시세 대기" id="1:4776">
            <RebalanceChip state="awaitingQuote" />
          </V>
          <V name="상태=출금 대기" id="1:4779">
            <RebalanceChip state="withdrawPending" />
          </V>
        </Section>

        <Section name="칩" id="1:1310 · 1:4865 · 1:28627 · 1:16699 · 1:4759 · 1:16662 · 1:24119">
          <V name="칩/기간/선택=예" id="1:1306">
            <PeriodChip selected>{kitCopy.periods[0]}</PeriodChip>
          </V>
          <V name="칩/기간/선택=아니오" id="1:1308">
            <PeriodChip selected={false}>{kitCopy.periods[0]}</PeriodChip>
          </V>
          <V name="칩/범례/켜짐=예" id="1:4857">
            <LegendChip on>{kitCopy.legendPaper}</LegendChip>
          </V>
          <V name="칩/범례/켜짐=아니오" id="1:4861">
            <LegendChip on={false}>{kitCopy.legendPaper}</LegendChip>
          </V>
          <V name="칩/신호/종류=정상" id="1:28615">
            <SignalChip kind="ok">{kitCopy.signals.ok}</SignalChip>
          </V>
          <V name="칩/신호/종류=주의" id="1:28618">
            <SignalChip kind="warn">{kitCopy.signals.warn}</SignalChip>
          </V>
          <V name="칩/신호/종류=오류" id="1:28621">
            <SignalChip kind="error">{kitCopy.signals.error}</SignalChip>
          </V>
          <V name="칩/신호/종류=확인 불가" id="1:28624">
            <SignalChip kind="unknown">{kitCopy.signals.unknown}</SignalChip>
          </V>
          <V name="칩/예외/종류=휴장" id="1:16664">
            <ExceptionChip kind="holiday" />
          </V>
          <V name="칩/예외/종류=시세 대기" id="1:16674">
            <ExceptionChip kind="awaitingQuote" />
          </V>
          <V name="칩/예외/종류=출금 대기" id="1:16682">
            <ExceptionChip kind="withdrawPending" />
          </V>
          <V name="칩/예외/종류=새 현금" id="1:16692">
            <ExceptionChip kind="newCash" />
          </V>
          <V name="칩/정보" id="1:4759">
            <InfoChip>{kitCopy.info}</InfoChip>
          </V>
          <V name="칩/AI 개입/개입=AI 없음" id="1:16646">
            <AiChip included={false} />
          </V>
          <V name="칩/AI 개입/개입=AI 판단 포함" id="1:16655">
            <AiChip included />
          </V>
          <V name="칩/규칙 선택/선택=예" id="1:24103">
            <RuleSelectChip selected name={kitCopy.ruleIndex} weight={kitCopy.ruleIndexWeight} />
          </V>
          <V name="칩/규칙 선택/선택=아니오" id="1:24111">
            <RuleSelectChip
              selected={false}
              name={kitCopy.ruleIndex}
              weight={kitCopy.ruleIndexWeight}
            />
          </V>
          <V name="칩/규칙 선택 (AI=예)" id="1:24111-ai">
            <RuleSelectChip
              selected={false}
              ai
              name={kitCopy.ruleMomentum}
              weight={kitCopy.ruleMomentumWeight}
            />
          </V>
        </Section>

        <Section name="버튼" id="1:2467 · 1:1298 · 1:1302 · 1:1354 · 1:2971">
          <V name="종류=기본, 상태=보통" id="1:2455">
            <Button kind="default">{kitCopy.buttons.cancel}</Button>
          </V>
          <V name="종류=기본, 상태=비활성" id="1:2457">
            <Button kind="default" disabled>
              {kitCopy.buttons.cancel}
            </Button>
          </V>
          <V name="종류=주요, 상태=보통" id="1:2459">
            <Button kind="primary">{kitCopy.buttons.primary}</Button>
          </V>
          <V name="종류=주요, 상태=비활성" id="1:2461">
            <Button kind="primary" disabled>
              {kitCopy.buttons.primary}
            </Button>
          </V>
          <V name="종류=위험, 상태=보통" id="1:2463">
            <Button kind="danger">{kitCopy.buttons.danger}</Button>
          </V>
          <V name="종류=위험, 상태=비활성" id="1:2465">
            <Button kind="danger" disabled>
              {kitCopy.buttons.danger}
            </Button>
          </V>
          <V name="버튼/아이콘" id="1:1298">
            <IconButton icon={Settings} label={copy.settings} />
          </V>
          <V name="버튼/링크" id="1:1302">
            <LinkButton>{kitCopy.linkButton}</LinkButton>
          </V>
          <V name="버튼/펼침" id="1:1354">
            <ExpandButton>{kitCopy.expandButton}</ExpandButton>
          </V>
          <V name="버튼/접기" id="1:2971">
            <CollapseButton />
          </V>
        </Section>

        <Section name="배너 · 띠 · 표시" id="1:1311 · 1:1290 · 1:1349">
          <V name="배너/이상" id="1:1311" width={390}>
            <AlertBanner action={<LinkButton to="/health">{kitCopy.bannerLink}</LinkButton>}>
              {kitCopy.banner}
            </AlertBanner>
          </V>
          <V name="띠/모드/모드=모의" id="1:1282" width={390}>
            <ModeStrip mode="paper">{kitCopy.modeStripPaper}</ModeStrip>
          </V>
          <V name="띠/모드/모드=Live" id="1:1286" width={390}>
            <ModeStrip mode="live">{kitCopy.modeStripLive}</ModeStrip>
          </V>
          <V name="표시/낡음" id="1:1349">
            <StaleTag />
          </V>
        </Section>

        <Section name="줄" id="1:1348 · 1:28672 · 1:4887 · 1:2490">
          <V name="상태 줄/상태=정상" id="1:1322" width={310}>
            <StatusLine tone="ok">{kitCopy.statusLines.ok}</StatusLine>
          </V>
          <V name="상태 줄/상태=경고" id="1:1328" width={310}>
            <StatusLine tone="warn">{kitCopy.statusLines.warn}</StatusLine>
          </V>
          <V name="상태 줄/상태=오류" id="1:1335" width={310}>
            <StatusLine tone="error">{kitCopy.statusLines.error}</StatusLine>
          </V>
          <V name="상태 줄/상태=대기" id="1:1342" width={310}>
            <StatusLine tone="wait">{kitCopy.statusLines.wait}</StatusLine>
          </V>
          <V name="줄/점검/상태=통과" id="1:28645" width={310}>
            <CheckRow
              state="pass"
              name={kitCopy.checkRows.pass.name}
              description={kitCopy.checkRows.pass.desc}
            />
          </V>
          <V name="줄/점검/상태=막힘" id="1:28652" width={310}>
            <CheckRow
              state="blocked"
              name={kitCopy.checkRows.blocked.name}
              description={kitCopy.checkRows.blocked.desc}
              to="/health"
            />
          </V>
          <V name="줄/점검/상태=경고" id="1:28662" width={310}>
            <CheckRow
              state="warn"
              name={kitCopy.checkRows.warn.name}
              description={kitCopy.checkRows.warn.desc}
              to="/health"
            />
          </V>
          <V name="주문 행/상태=체결" id="1:4866">
            <OrderRow state="filled" stateLabel="체결" time={kitCopy.orderRows.filled.time}>
              {kitCopy.orderRows.filled.text}
            </OrderRow>
          </V>
          <V name="주문 행/상태=대기" id="1:4872">
            <OrderRow state="pending" stateLabel="대기" time={kitCopy.orderRows.pending.time}>
              {kitCopy.orderRows.pending.text}
            </OrderRow>
          </V>
          <V name="주문 행/상태=실패" id="1:4880">
            <OrderRow state="failed" stateLabel="실패" time={kitCopy.orderRows.failed.time}>
              {kitCopy.orderRows.failed.text}
            </OrderRow>
          </V>
          <V name="행/펼침/펼침=접힘" id="1:2478" width={310}>
            <ExpandRow
              title={kitCopy.expandRow.title}
              subtitle={kitCopy.expandRow.subtitle}
              expanded={expanded}
              onToggle={() => {
                setExpanded((v) => !v);
              }}
            >
              <Text variant="caption" tone="muted">
                {formatKrw(10_084_600)} · {formatKrwSigned(12_300)}
              </Text>
            </ExpandRow>
          </V>
          <V name="행/펼침/펼침=펼침" id="1:2484" width={310}>
            <ExpandRow
              title={kitCopy.expandRow.title}
              subtitle={kitCopy.expandRow.subtitle}
              expanded
            />
          </V>
        </Section>

        <Section
          name="입력 · 키 · 토글 · 체크 · 스위치"
          id="1:2454 · 1:28681 · 1:2472 · 1:2477 · 1:28644"
        >
          <V name="입력/PIN 칸/상태=빈" id="1:2448">
            <PinCell state="empty" />
          </V>
          <V name="입력/PIN 칸/상태=채움" id="1:2449">
            <PinCell state="filled" />
          </V>
          <V name="입력/PIN 칸/상태=포커스" id="1:2451">
            <PinCell state="focus" />
          </V>
          <V name="입력/PIN 칸/상태=오류" id="1:2452">
            <PinCell state="error" />
          </V>
          <V name="입력/PIN 칸/상태=비활성" id="1:2453">
            <PinCell state="disabled" />
          </V>
          <V name="키/숫자/종류=숫자" id="1:28673">
            <KeypadKey kind="digit" digit="1" />
          </V>
          <V name="키/숫자/종류=지우기" id="1:28675">
            <KeypadKey kind="delete" />
          </V>
          <V name="키/숫자/종류=빈" id="1:28680">
            <KeypadKey kind="blank" />
          </V>
          <V name="토글/켜짐=예" id="1:2468">
            <Toggle checked aria-label={kitCopy.toggle} />
          </V>
          <V name="토글/켜짐=아니오" id="1:2470">
            <Toggle checked={false} aria-label={kitCopy.toggle} />
          </V>
          <V name="토글 (조작)" id="toggle-live">
            <div className={styles.row}>
              <Text variant="body" id="kit-toggle-label">
                {kitCopy.toggle}
              </Text>
              <Toggle checked={toggle} onChange={setToggle} aria-labelledby="kit-toggle-label" />
            </div>
          </V>
          <V name="체크/선택=예" id="1:2473">
            <Checkbox checked onChange={() => undefined} aria-label={kitCopy.checkbox} />
          </V>
          <V name="체크/선택=아니오" id="1:2476">
            <Checkbox checked={false} onChange={() => undefined} aria-label={kitCopy.checkbox} />
          </V>
          <V name="체크 (조작)" id="check-live">
            <Checkbox checked={check} onChange={setCheck}>
              {kitCopy.checkbox}
            </Checkbox>
          </V>
          <V name="스위치/모드/선택=모의투자" id="1:28628" width={350}>
            <ModeSwitch value="paper" aria-label={copy.pages.mode} />
          </V>
          <V name="스위치/모드/선택=실전" id="1:28636" width={350}>
            <ModeSwitch value="live" aria-label={copy.pages.mode} />
          </V>
          <V name="스위치/모드 (조작)" id="switch-live" width={350}>
            <ModeSwitch value={mode} onSelect={setMode} aria-label={copy.pages.mode} />
          </V>
          <V name="PIN 6칸 · 키패드 (SCR-PIN)" id="1:51276-pin">
            <div className={styles.column}>
              <div className={styles.pinRow}>
                <PinCell state="filled" />
                <PinCell state="filled" />
                <PinCell state="filled" />
                <PinCell state="focus" />
                <PinCell state="empty" />
                <PinCell state="empty" />
              </div>
              <div className={styles.keypad}>
                {['1', '2', '3', '4', '5', '6', '7', '8', '9'].map((d) => (
                  <KeypadKey key={d} kind="digit" digit={d} />
                ))}
                <KeypadKey kind="blank" />
                <KeypadKey kind="digit" digit="0" />
                <KeypadKey kind="delete" />
              </div>
            </div>
          </V>
        </Section>

        <Section name="모달/확인" id="1:2491">
          <V name="모달/확인" id="1:2491" width={350}>
            <ConfirmModal
              presentation="inline"
              open
              title={kitCopy.modalTitle}
              cancelLabel={kitCopy.buttons.cancel}
              confirmLabel={kitCopy.modalConfirm}
              onCancel={() => undefined}
              onConfirm={() => undefined}
            >
              {kitCopy.modalBody}
            </ConfirmModal>
          </V>
          <V name="모달 열기 (조작)" id="modal-live">
            <Button
              kind="danger"
              onClick={() => {
                setModalOpen(true);
              }}
            >
              {kitCopy.modalOpen}
            </Button>
            <ConfirmModal
              open={modalOpen}
              title={kitCopy.modalTitle}
              cancelLabel={kitCopy.buttons.cancel}
              confirmLabel={kitCopy.modalConfirm}
              onCancel={() => {
                setModalOpen(false);
              }}
              onConfirm={() => {
                setModalOpen(false);
              }}
            >
              {kitCopy.modalBody}
            </ConfirmModal>
          </V>
        </Section>

        <Section name="국기 · 로고/이니셜" id="1:4816 · 1:16573">
          <V name="국기/나라=KR" id="1:4785">
            <Flag country="kr" />
          </V>
          <V name="국기/나라=US" id="1:4806">
            <Flag country="us" />
          </V>
          <V name="국기/나라=코인" id="1:4813">
            <Flag country="coin" />
          </V>
          <V name="로고/이니셜/크기=32" id="1:4888">
            <InitialLogo initials="K2" size={32} />
          </V>
          <V name="로고/이니셜/크기=20" id="1:16571">
            <InitialLogo initials="K2" size={20} />
          </V>
        </Section>

        <Section name="표식" id="1:4856 · 1:24067">
          {EVENT_VARIANTS.map(([kind, name, id]) => (
            <V key={id} name={name} id={id}>
              <EventMarker kind={kind} label={copy.event[kind]} inert />
            </V>
          ))}
          <V name="표식/실행 실패" id="1:24067">
            <EventMarker kind="runFail" label={copy.event.runFail} inert />
          </V>
        </Section>

        <Section name="칸/실행 달력" id="1:24102">
          {CALENDAR_VARIANTS.map(([state, id]) => (
            <V key={id} name={`상태=${copy.calendar.state[state]}`} id={id}>
              <CalendarCell state={state} label={copy.calendar.state[state]} />
            </V>
          ))}
        </Section>

        <Section name="규칙" id="1:16741 · 1:16743 · 1:16769">
          <V name="규칙/블록/종류=시간" id="1:16701">
            <RuleBlock kind="time">{kitCopy.ruleBlocks.time}</RuleBlock>
          </V>
          <V name="규칙/블록/종류=AI" id="1:16707">
            <RuleBlock kind="ai">{kitCopy.ruleBlocks.ai}</RuleBlock>
          </V>
          <V name="규칙/블록/종류=조건" id="1:16715">
            <RuleBlock kind="condition">{kitCopy.ruleBlocks.condition}</RuleBlock>
          </V>
          <V name="규칙/블록/종류=그대로" id="1:16718">
            <RuleBlock kind="hold">{kitCopy.ruleBlocks.hold}</RuleBlock>
          </V>
          <V name="규칙/블록/종류=매도" id="1:16721">
            <RuleBlock kind="sell">{kitCopy.ruleBlocks.sell}</RuleBlock>
          </V>
          <V name="규칙/블록/종류=환전" id="1:16727">
            <RuleBlock kind="exchange">{kitCopy.ruleBlocks.exchange}</RuleBlock>
          </V>
          <V name="규칙/블록/종류=매수" id="1:16735">
            <RuleBlock kind="buy">{kitCopy.ruleBlocks.buy}</RuleBlock>
          </V>
          <V name="규칙/목표 칸" id="1:16743">
            <RuleTargetCell initials="K2" country="kr">
              50%
            </RuleTargetCell>
          </V>
          <V name="규칙 카드/머리" id="1:16769" width={310}>
            <RuleCardHead
              name={kitCopy.ruleCardHead.name}
              shareLabel={kitCopy.ruleCardHead.shareLabel}
              share={kitCopy.ruleCardHead.share}
              fraction={0.8}
              status="inProgress"
              ai={false}
            />
          </V>
        </Section>

        <Section name="노드/D 지금 값 카드" id="1:19963">
          <V name="종류=시작" id="1:19626" width={236}>
            <NodeCard
              kind="start"
              title={kitCopy.nodes.start.title}
              now={
                <NodeRow>
                  <Text variant="caption" grow>
                    {kitCopy.nodes.start.next}
                  </Text>
                  <Text variant="caption" tone="muted">
                    {kitCopy.nodes.start.in}
                  </Text>
                </NodeRow>
              }
            >
              <Text variant="caption" tone="muted">
                {kitCopy.nodes.start.sub}
              </Text>
            </NodeCard>
          </V>
          <V name="종류=종목" id="1:19709" width={236}>
            <NodeCard
              kind="asset"
              title={kitCopy.nodes.asset.title}
              nowSuffix={kitCopy.nodes.asset.nowSuffix}
              now={
                <>
                  {(
                    [
                      ['삼', 3, kitCopy.assets.samsung, '42.0%', '+1.4%', 'gain'],
                      ['NV', 1, kitCopy.assets.nvda, '39.0%', '+1.7%', 'gain'],
                      ['B', 5, kitCopy.assets.btc, '18.9%', '−15.1%', 'loss'],
                    ] as const
                  ).map(([ini, tone, name, share, pnl, dir]) => (
                    <NodeRow key={name}>
                      <InitialLogo initials={ini} size={20} tone={tone} />
                      <Text variant="caption" grow>
                        {name}
                      </Text>
                      <Text variant="label">{share}</Text>
                      <Text variant="caption" tone={dir}>
                        {pnl}
                      </Text>
                    </NodeRow>
                  ))}
                </>
              }
            >
              <NodeRow>
                <NodeRow tight>
                  <InitialLogo initials="삼" size={20} tone={3} />
                  <InitialLogo initials="NV" size={20} tone={1} />
                  <InitialLogo initials="B" size={20} tone={5} />
                </NodeRow>
                <Text variant="caption" tone="muted">
                  {kitCopy.nodes.asset.more}
                </Text>
              </NodeRow>
              <NodeRow tight>
                <Flag country="kr" />
                <Flag country="us" />
                <Flag country="coin" />
                <KindBadge>{kitCopy.kinds.stock}</KindBadge>
                <KindBadge>{kitCopy.kinds.coin}</KindBadge>
              </NodeRow>
            </NodeCard>
          </V>
          <V name="종류=데이터" id="1:19737" width={236}>
            <NodeCard
              kind="data"
              title={kitCopy.nodes.data.title}
              nowSuffix={kitCopy.nodes.data.nowSuffix}
              now={
                <>
                  {(
                    [
                      ['1', kitCopy.assets.samsung, '+6.2%'],
                      ['2', kitCopy.assets.nvda, '+4.8%'],
                      ['3', kitCopy.assets.btc, '+0.9%'],
                    ] as const
                  ).map(([rank, name, ret]) => (
                    <NodeRow key={rank}>
                      <Text variant="caption" tone="muted">
                        {rank}
                      </Text>
                      <Text variant="caption" grow>
                        {name}
                      </Text>
                      <Text variant="label" tone="gain">
                        {ret}
                      </Text>
                    </NodeRow>
                  ))}
                </>
              }
            >
              <Text variant="caption" tone="muted">
                {kitCopy.nodes.data.sub}
              </Text>
            </NodeCard>
          </V>
          <V name="종류=AI 판단" id="1:19774" width={236}>
            <NodeCard
              kind="ai"
              title={kitCopy.nodes.ai.title}
              nowSuffix={kitCopy.nodes.ai.nowSuffix}
              now={
                <>
                  <NodeRow>
                    <NodeRow tight>
                      <InitialLogo initials="삼" size={20} tone={3} />
                      <InitialLogo initials="NV" size={20} tone={1} />
                      <InitialLogo initials="B" size={20} tone={5} />
                    </NodeRow>
                    <Text variant="caption" grow>
                      {kitCopy.nodes.ai.picked}
                    </Text>
                  </NodeRow>
                  <Text variant="caption" tone="muted">
                    {kitCopy.nodes.ai.same}
                  </Text>
                </>
              }
            >
              {kitCopy.nodes.ai.rows.map(([k, v]) => (
                <NodeRow key={k}>
                  <NodeRowLabel>{k}</NodeRowLabel>
                  <Text
                    variant={k === 'AI' ? 'label' : 'caption'}
                    tone={k === 'AI' ? 'ai' : undefined}
                    grow
                  >
                    {v}
                  </Text>
                </NodeRow>
              ))}
            </NodeCard>
          </V>
          <V name="종류=비중" id="1:19806" width={236}>
            <NodeCard
              kind="weight"
              title={kitCopy.nodes.weight.title}
              now={
                <>
                  <Text variant="label" as="p">
                    {kitCopy.nodes.weight.now}
                  </Text>
                  <Text variant="caption" tone="muted" as="p">
                    {kitCopy.nodes.weight.target}
                  </Text>
                </>
              }
            >
              <NodeRow>
                {(
                  [
                    ['삼', 3, '42'],
                    ['NV', 1, '40'],
                    ['B', 5, '18'],
                  ] as const
                ).map(([ini, tone, w]) => (
                  <NodeRow key={ini} tight>
                    <InitialLogo initials={ini} size={20} tone={tone} />
                    <Text variant="label">{w}</Text>
                  </NodeRow>
                ))}
              </NodeRow>
              <Text variant="caption" tone="muted">
                {kitCopy.nodes.weight.sub}
              </Text>
            </NodeCard>
          </V>
          <V name="종류=조건" id="1:19835" width={236}>
            <NodeCard
              kind="condition"
              title={kitCopy.nodes.condition.title}
              now={
                <>
                  <NodeRow>
                    <Text variant="caption" grow>
                      {kitCopy.nodes.condition.value}
                    </Text>
                    <Text variant="label" tone="warning">
                      {kitCopy.nodes.condition.over}
                    </Text>
                  </NodeRow>
                  <DeviationBand
                    size="compact"
                    points={[{ value: 2.4, kind: 'before' }]}
                    label={`${kitCopy.nodes.condition.value} · ${kitCopy.nodes.condition.band}`}
                  />
                  <NodeRow>
                    <Text variant="caption" tone="muted">
                      {'−4'}
                    </Text>
                    <Text variant="caption" tone="muted" grow align="center">
                      {kitCopy.nodes.condition.band}
                    </Text>
                    <Text variant="caption" tone="muted">
                      {'+4'}
                    </Text>
                  </NodeRow>
                </>
              }
            >
              <Text variant="caption" tone="muted">
                {kitCopy.nodes.condition.sub}
              </Text>
            </NodeCard>
          </V>
          <V name="종류=행동" id="1:19894" width={236}>
            <NodeCard
              kind="action"
              title={kitCopy.nodes.action.title}
              nowSuffix={kitCopy.nodes.action.nowSuffix}
              now={
                <>
                  {kitCopy.nodes.action.rows.map(([what, when], i) => (
                    <NodeRow key={what}>
                      <NodeIcon
                        icon={[CircleMinus, ArrowLeftRight, CirclePlus][i] ?? CircleMinus}
                      />
                      <Text variant="caption" grow>
                        {what}
                      </Text>
                      <Text variant="caption" tone="muted">
                        {when}
                      </Text>
                    </NodeRow>
                  ))}
                </>
              }
            >
              <NodeRow tight>
                <NodeRow tight>
                  <NodeIcon icon={CircleMinus} />
                  <Text variant="caption">{kitCopy.ruleBlocks.sell}</Text>
                </NodeRow>
                <Text variant="caption" tone="muted">
                  <ChevronRight size={16} aria-hidden />
                </Text>
                <NodeRow tight>
                  <NodeIcon icon={ArrowLeftRight} />
                  <Text variant="caption">{kitCopy.ruleBlocks.exchange}</Text>
                </NodeRow>
                <Text variant="caption" tone="muted">
                  <ChevronRight size={16} aria-hidden />
                </Text>
                <NodeRow tight>
                  <NodeIcon icon={CirclePlus} />
                  <Text variant="caption">{kitCopy.ruleBlocks.buy}</Text>
                </NodeRow>
              </NodeRow>
            </NodeCard>
          </V>
          <V name="종류=예외" id="1:19940" width={236}>
            <NodeCard
              kind="exception"
              title={kitCopy.nodes.exception.title}
              now={
                <NodeRow>
                  <Text variant="caption" tone="success">
                    <CircleCheck size={16} aria-hidden />
                  </Text>
                  <Text variant="caption" grow>
                    {kitCopy.nodes.exception.none}
                  </Text>
                </NodeRow>
              }
            >
              <NodeRow tight>
                <ExceptionChip kind="holiday" />
                <ExceptionChip kind="awaitingQuote" />
              </NodeRow>
              <NodeRow tight>
                <ExceptionChip kind="withdrawPending" />
              </NodeRow>
            </NodeCard>
          </V>
          <V name="종류=결과" id="1:19962" width={236}>
            <NodeCard
              kind="result"
              title={kitCopy.nodes.result.title}
              now={
                <>
                  <NodeRow>
                    <RebalanceChip state="inRange" />
                  </NodeRow>
                  <NodeRow>
                    <Text variant="caption" tone="success">
                      <Check size={16} aria-hidden />
                    </Text>
                    <Text variant="caption" grow>
                      {kitCopy.nodes.result.last}
                    </Text>
                  </NodeRow>
                </>
              }
            >
              <Text variant="caption" tone="muted">
                {kitCopy.nodes.result.sub}
              </Text>
            </NodeCard>
          </V>
        </Section>

        <Section name="차트 (SVG)" id="chart">
          <V name="반원 게이지 · +0.2%p" id="1:66098">
            <Gauge value={0.2} label="KOSPI200 ETF +0.2%p" />
          </V>
          <V name="반원 게이지 · 시세 대기" id="gauge-empty">
            <Gauge value={null} label={copy.rebalance.awaitingQuote} />
          </V>
          <V name="벗어남 띠 · 전 52.3 → 후 50.2" id="1:60048" width={324}>
            <DeviationBand
              width={324}
              points={[
                { value: 2.3, kind: 'before', label: `${copy.chart.before} 52.3` },
                { value: 0.2, kind: 'after', label: `${copy.chart.after} 50.2` },
              ]}
              label={`${copy.chart.before} 52.3 → ${copy.chart.after} 50.2`}
            />
          </V>
          <V name="구성 막대 · 81.1 / 18.3 / 0.6" id="1:51538" width={310}>
            <CompositionBar
              width={310}
              label="지수 반반 81.1% · [예시] 종목 모멘텀 18.3% · 현금 0.6%"
              segments={[
                { key: 'index', value: 81.1, tone: 'strategy-1' },
                { key: 'momentum', value: 18.3, tone: 'strategy-2' },
                { key: 'cash', value: 0.6, tone: 'cash' },
              ]}
            />
          </V>
          <V name="구성 막대 · 출금 대기 빗금" id="1:52441" width={310}>
            <CompositionBar
              width={310}
              label="지수 반반 75.7% · [예시] 종목 모멘텀 18.5% · 현금 0.8% · 출금 대기 5.0%"
              segments={[
                { key: 'index', value: 75.7, tone: 'strategy-1' },
                { key: 'momentum', value: 18.5, tone: 'strategy-2' },
                { key: 'cash', value: 0.8, tone: 'cash' },
                { key: 'pending', value: 5.0, tone: 'cash', pending: true },
              ]}
            />
          </V>
          <V name="구성 막대 · 목표 비중(점선)" id="1:54747" width={310}>
            <CompositionBar
              width={310}
              label="목표 비중 지수 반반 80% · [예시] 종목 모멘텀 20%"
              segments={[
                { key: 'index', value: 80, tone: 'strategy-1', outline: true },
                { key: 'momentum', value: 20, tone: 'strategy-2', outline: true },
              ]}
            />
          </V>
          <V name="전후 비중 · 전 52.3 | 47.7" id="1:59964" width={284}>
            <CompositionBar
              width={284}
              barHeight={24}
              height={32}
              target={{ at: 0.5, band: [0.48, 0.52] }}
              label="전 KOSPI200 ETF 52.3% · S&P 500 ETF 47.7%"
              segments={[
                { key: 'kospi', value: 52.3, tone: 'cat-1', label: '52.3%', labelTone: 'inverse' },
                { key: 'sp500', value: 47.7, tone: 'cat-2', label: '47.7%', labelTone: 'primary' },
              ]}
            />
          </V>
          <V name="자산 변동 · 1440 (3개월)" id="1:54865" width={752}>
            <LineChart
              width={752}
              layout={LINE_HOME_1440}
              start="2026-07-07"
              end="2026-10-07"
              axis={homeAxis}
              mine={{ key: 'mine', points: paperDaily3m }}
              baseline={{ key: 'base', points: untouchedDaily3m }}
              events={homeEvents}
              hrefFor={dayHref}
              onLegend={() => undefined}
              label={`${copy.chart.myAssets} ${formatMonthDay('2026-07-07')} ${formatKrw(10_021_000)} → ${formatMonthDay('2026-10-07')} ${formatKrw(10_243_800)}`}
            />
          </V>
          <V name="자산 변동 · 390 (3개월)" id="1:51467" width={350}>
            <LineChart
              width={350}
              layout={LINE_HOME_390}
              start="2026-07-07"
              end="2026-10-07"
              axis={homeAxis}
              mine={{ key: 'mine', points: paperDaily3m }}
              baseline={{ key: 'base', points: untouchedDaily3m }}
              events={homeEvents}
              hrefFor={dayHref}
              onLegend={() => undefined}
              label={copy.chart.myAssets}
            />
          </V>
          <V name="기록 자산 그래프 · 1440 (8/21 선택)" id="1:60255" width={760}>
            <HistoryChart
              width={760}
              layout={LINE_HISTORY_1440}
              start="2026-07-01"
              end="2026-10-07"
              axis={historyAxis}
              mine={{ key: 'mine', points: paperDailySinceStart }}
              events={paperEvents}
              hrefFor={dayHref}
              selected="2026-08-21"
              label={copy.chart.myAssets}
            />
          </V>
          <V name="기록 자산 그래프 · 390" id="1:58229" width={326}>
            <HistoryChart
              width={326}
              layout={LINE_HISTORY_390}
              start="2026-07-01"
              end="2026-10-07"
              axis={historyAxis}
              mine={{ key: 'mine', points: paperDailySinceStart }}
              events={paperEvents}
              hrefFor={dayHref}
              label={copy.chart.myAssets}
            />
          </V>
          <V name="벗어남 흐름 · 1440 (지수 반반)" id="1:57679" width={384}>
            <DriftChart
              width={384}
              layout={DRIFT_1440}
              start="2026-07-07"
              end="2026-10-07"
              series={[{ key: 'index', tone: 1, points: driftIndex }]}
              events={driftEvents.filter((e) => e.date !== '2026-09-14')}
              hrefFor={dayHref}
              label={kitCopy.ruleIndex}
            />
          </V>
          <V name="벗어남 흐름 · 390" id="1:56046" width={350}>
            <DriftChart
              width={350}
              layout={DRIFT_390}
              bandHeight={26}
              start="2026-07-07"
              end="2026-10-07"
              series={[
                { key: 'index', tone: 1, points: driftIndex },
                { key: 'momentum', tone: 2, points: driftMomentum },
              ]}
              events={driftEvents}
              hrefFor={dayHref}
              label={`${kitCopy.ruleIndex} · ${kitCopy.ruleMomentum}`}
            />
          </V>
          <V name="변동 분해 (폭포) · 그림 없음" id="waterfall" width={350}>
            <Waterfall
              width={350}
              label={copy.waterfall.end}
              formatValue={(s) =>
                s.kind === 'anchor' ? formatKrw(s.value) : formatKrwSigned(s.value)
              }
              steps={[
                { key: 'start', label: copy.waterfall.start, kind: 'anchor', value: 10_021_000 },
                { key: 'deposit', label: copy.waterfall.deposit, kind: 'cashflow', value: 0 },
                { key: 'withdraw', label: copy.waterfall.withdraw, kind: 'cashflow', value: 0 },
                { key: 'market', label: copy.waterfall.market, kind: 'change', value: 206_825 },
                { key: 'dividend', label: copy.waterfall.dividend, kind: 'change', value: 16_243 },
                { key: 'fee', label: copy.waterfall.fee, kind: 'change', value: -268 },
                { key: 'end', label: copy.waterfall.end, kind: 'anchor', value: 10_243_800 },
              ]}
            />
          </V>
          <V name="매일 확인 달력 · 1440" id="1:59604" width={370}>
            <CalendarGrid
              start={paperCalendar.start}
              end={paperCalendar.end}
              stateOf={paperCalendarState}
              labelOf={(date, state) =>
                `${formatMonthDayWeekday(date)} ${copy.calendar.state[state]}`
              }
              hrefOf={(date, state) => (state === 'future' ? undefined : dayHref(date))}
              label={copy.pages.history}
            />
          </V>
          <V name="매일 확인 달력 · 390 (가로 스크롤)" id="1:58302" width={322}>
            <CalendarGrid
              start={paperCalendar.start}
              end={paperCalendar.end}
              stateOf={paperCalendarState}
              labelOf={(date, state) =>
                `${formatMonthDayWeekday(date)} ${copy.calendar.state[state]}`
              }
              label={copy.pages.history}
            />
          </V>
          <V name="표로 보기 (접근성 대체)" id="table">
            <div className={styles.tableWrap}>
              <ChartTable
                caption={copy.chart.tableView}
                columns={[copy.chart.dateColumn, copy.chart.myAssets]}
                rows={paperDaily3m
                  .filter((p) => p.date.endsWith('-07'))
                  .map((p) => [
                    formatMonthDay(p.date),
                    p.value === null ? '—' : formatKrw(p.value),
                  ])}
              />
            </div>
          </V>
        </Section>
      </main>
    </OnlyContext>
  );
}
