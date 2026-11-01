// 캔버스 편집 (Figma MVP 화면 '11 · 캔버스 편집' 28장 · '좁은 창 편집 · 보기만').
import { version } from './particles';

export const editorCopy = {
  title: (name: string) => `${name} 편집`,
  back: '전략',
  newTitle: '새 전략',
  chipNew: '새 전략 · 저장하면 버전 1',
  chipNewOnly: '저장하면 버전 1',
  chipFrom: (no: number, next: number) =>
    `버전 ${String(no)}에서 편집 · 저장하면 버전 ${String(next)}`,
  chipSaved: (no: number) => `버전 ${String(no)} · 저장됨`,
  chipViewOnly: (no: number) => `버전 ${String(no)} · 보기만`,
  chipViewOnlyNew: '새 전략 · 보기만',
  save: (next: number) => `${version(next, '으로')} 저장`,
  nothingToSave: '저장할 값 없음',
  saving: '저장 중',
  saved: (no: number) => `${version(no, '으로')} 저장했어요`,
  toBacktest: '백테스트 ›',
  saveFailed: '저장하지 못했어요',

  status: {
    okTitle: '문제 없음 · 모두 채웠어요',
    okBody: '저장하면 백테스트와 모의투자를 할 수 있어요',
    savedTitle: (no: number) => `문제 없음 · 버전 ${String(no)}`,
    savedBody: '백테스트와 모의투자를 할 수 있어요',
    problemsTitle: (n: number, parts: string) => `문제 ${String(n)}개 · ${parts}`,
    part: (name: string, n: number) => `${name} ${String(n)}`,
    body: '저장은 돼요 · 문제를 해결해야 백테스트와 모의투자를 할 수 있어요',
    howBody: '리밸런싱 방식을 골라 주세요 · 저장은 돼요',
    open: '문제 목록 보기',
  },

  palette: {
    title: (n: number) => `조건 목록 · ${String(n)}`,
    lead: '끌어서 캔버스에 놓거나, 눌러서 추가해요',
    search: '조건 이름 검색',
    once: '하나만 놓아요',
    placed: (n: number) => `${String(n)}개 놓음`,
    moving: '옮기는 중',
    none: '이 검색에 맞는 조건 0개',
  },

  mode: {
    label: '매매 방식',
    blank: '리밸런싱 방식을 골라 주세요',
    explainTitle: '매매 방식은 놓은 조건으로 정해져요',
    explain: [
      '리밸런싱 주기가 없으면 · 조건 충족 시 매매',
      '리밸런싱 주기가 있으면 · 그 조건의 리밸런싱 방식대로 목표 비중 리밸런싱이나 순위 교체 리밸런싱',
      '방식이 바뀌면 돌파 신호의 뜻도 바뀌어요 · 조건 충족 시 매매는 넘은 그날만, 리밸런싱 방식은 위에 있는 날 모두예요',
      '방식마다 쓸 수 없는 조건이 있어요 · 목표 비중 리밸런싱에서는 ⑥ 매도를 쓰지 않아요',
    ],
    changed: (nameWithParticle: string, need: number, cannot: number) =>
      cannot > 0
        ? `매매 방식이 ${nameWithParticle} 바뀌었어요 · 필요한 조건 ${String(need)} · 못 쓰는 조건 ${String(cannot)}`
        : `매매 방식이 ${nameWithParticle} 바뀌었어요 · 필요한 조건 ${String(need)}`,
  },

  readHow:
    '선을 따라 한 경로 위의 조건이 모두 맞으면 통과해요 · 경로가 여러 개면 하나라도 통과하면 돼요',

  empty: {
    title: '왼쪽 목록에서 조건을 끌어 와 놓아요',
    body: '선 위에 놓으면 두 조건 사이에 들어가요 · 빈 곳에 놓으면 조건 옆 연결점을 끌어 선으로 이어요',
  },

  tags: { branch: '분기 · 하나라도', chain: '연결 · 모두' },
  chips: {
    blank: '빈칸',
    range: '범위 밖',
    loose: '연결 없음',
    unusable: '못 씀',
    rule: '연결 규칙',
    dead: '매수까지 연결 안 됨',
  },

  tool: {
    layout: '자동 정렬',
    undo: '되돌리기',
    redo: '다시 하기',
    zoomOut: '축소',
    zoomIn: '확대',
    zoom: (pct: number) => `${String(pct)}%`,
    fit: '화면에 맞춤',
    keys: '단축키',
    canvas: '전략 캔버스',
    dropLegend: '점선 위에 놓으면 두 조건 사이에 들어가요 · 빈 곳에 놓아도 돼요',
  },

  keys: {
    title: '단축키',
    rows: [
      ['Tab', '다음 조건으로 옮겨요 · Shift+Tab은 앞으로'],
      ['Enter', '조건을 골라요 · 고른 뒤에는 다음 조건 연결'],
      ['Delete', '고른 조건이나 선을 삭제해요'],
      ['Ctrl+Z', '되돌리기 · Ctrl+Shift+Z는 다시 하기'],
      ['Esc', '고른 것을 풀어요'],
    ] as const,
    mac: 'Mac에서는 Ctrl 대신 ⌘를 눌러요',
  },

  toast: {
    layout: '자동 정렬했어요 · 단계 순서로 열을 맞추고 ⑦ 비중은 ⑤ 매수 아래에 놓아요',
    removed: (label: string) => `조건을 삭제했어요 · ${label}`,
    removedWithLines: (label: string) => `조건을 삭제했어요 · ${label} · 선도 함께 삭제했어요`,
    edgeRemoved: '연결을 삭제했어요',
    chainSell:
      '이어서 연결한 조건은 같은 날 모두 맞아야 해요 · 하나라도 맞으면 매도하려면 ⑤ 매수에서 따로 연결해요',
    chainEntry: '이어서 연결한 조건은 같은 날 모두 맞아야 해요',
    undo: '되돌리기',
  },

  paths: {
    title: '이 전략의 경로',
    lead: '경로 하나 위의 조건은 모두 맞아야 해요 · 경로끼리는 하나라도 통과하면 돼요',
    entry: (n: number) => `진입 경로 ${String(n)}개`,
    anyPass: '하나라도 통과',
    allPass: '모두 맞아야 통과',
    entryLead: (n: string) => `통과하면 매수 후보가 되고, ④ 신호 강도 순으로 ${n}종목까지 골라요`,
    entryLeadNoSelect: '통과한 종목을 모두 보유해요',
    entryLimit: (max: number) =>
      `진입 경로는 ${String(max)}개까지예요 · ${String(max)}개를 넘는 연결은 만들 수 없어요`,
    entryRow: (k: number) => `진입 경로 ${String(k)}`,
    sell: (n: number) => `매도 경로 ${String(n)}개`,
    sellNone: '매도 경로 없음',
    sellNoneLead: '⑥ 매도 조건을 ⑤ 매수 뒤에 연결하면 생겨요',
    sellAny: '하나라도 맞으면',
    sellAll: '모두 맞아야',
    sellLead: '맞으면 다음 날 시가에 매도해요',
    sellRow: (k: number) => `매도 경로 ${String(k)}`,
    chainLine: (names: string) => `${names} 같은 날 모두 맞아야 매도해요`,
    weight: '비중',
    weightTogether: '함께 적용',
    weightRow: '⑦ 비중',
    conds: (n: number) => `조건 ${String(n)}개`,
    blanks: (n: number) => `빈칸 ${String(n)}`,
    ranges: (n: number) => `범위 밖 ${String(n)}`,
    dead: '매수까지 연결 안 됨',
    noSignal: '신호 없음',
    more: (n: number) => `${String(n)}개 더 보기`,
    less: '접기',
    hoverNote: '경로에 포인터를 올리면 캔버스에서 그 경로가 진하게 보여요',
    buy: '⑤ 매수',
    noPaths: '① 유니버스에서 ⑤ 매수까지 연결하면 진입 경로가 생겨요',
    required: (n: number, parts: string) => `필요한 조건 ${String(n)} · ${parts}`,
  },

  problems: {
    title: (n: number) => `문제 ${String(n)}개`,
    close: '닫기',
    lead: '누르면 그 조건으로 이동하고 오른쪽에서 수정할 수 있어요',
    go: '이동',
    tip: (kind: string, short: string) => `${kind} · ${short}`,
  },

  node: {
    picked: '고른 조건',
    none: '고른 조건이 없어요',
    pathsTitle: '이 조건이 지나는 경로',
    pathsCount: (all: number, mine: number, kind: string) =>
      `${kind} ${String(all)}개 중 ${String(mine)}개`,
    entryKind: '진입 경로',
    sellKind: '매도 경로',
    noPath: '이 조건은 아직 어느 경로에도 없어요',
    twoBoxes: '숫자 칸 두 개를 모두 채워야 빈칸이 없어져요',
    repeat: '같은 조건을 여러 번 놓을 수 있어요 · 숫자는 조건마다 따로예요',
    weightNote: '비중 조건은 ⑤ 매수로 들어가는 선으로만 연결해요',
    next: '다음 조건 연결',
    remove: '조건 삭제',
    removeNote: 'Delete 키로도 삭제해요 · 삭제 뒤 알림에서 되돌리기를 누를 수 있어요',
    allowed: (range: string) => `허용 ${range}`,
    allowedNamed: (name: string, range: string) => `허용 ${name} ${range}`,
    symbolsLine: (names: string, max: number) => `${names} · 최대 ${String(max)}개`,
    symbolsMax: (max: number) => `최대 ${String(max)}개`,
    how: '리밸런싱 방식',
    howBlank: '빈칸이에요 · 골라야 매매 방식이 정해져요',
    howNote: '리밸런싱 방식에서는 돌파 신호가 넘은 그날만이 아니라 위에 있는 날 모두예요',
    middleNote:
      '가운데 조건을 삭제해도 앞뒤를 자동으로 연결하지 않아요 · 끊긴 곳은 문제로 표시돼요',
  },

  next: {
    head: (ok: number, no: number) =>
      no > 0
        ? `연결할 수 있는 조건 ${String(ok)}개 · 연결할 수 없는 조건 ${String(no)}개`
        : `연결할 수 있는 조건 ${String(ok)}개`,
    keys: 'Tab으로 옮기고 Enter로 골라요',
    deadFixed: (pathWithParticle: string) => `${pathWithParticle} 매수까지 연결돼요`,
    looseFixed: '연결 없음 문제가 하나 줄어요',
    chain: (from: string, stageWithParticle: string) =>
      `${from} 뒤에 ${stageWithParticle} 이어서 연결해요`,
    plain: (a: string, bWithParticle: string) => `${a} → ${bWithParticle} 연결돼요`,
    none: '연결할 수 있는 조건이 없어요',
  },

  edge: {
    picked: '고른 연결',
    title: (a: string, b: string) => `${a} → ${b}`,
    inEntry: (listWithParticle: string) => `진입 경로 ${listWithParticle} 이루는 선이에요`,
    inSell: (listWithParticle: string) => `매도 경로 ${listWithParticle} 이루는 선이에요`,
    weightLine: '비중을 ⑤ 매수에 연결하는 선이에요',
    noPath: '아직 어느 경로에도 들어가지 않은 선이에요',
    effectTitle: '삭제하면 바뀌는 것',
    pathGone: (pathWithParticle: string) => `${pathWithParticle} 없어져요`,
    becomesDead: (labelWithParticle: string) =>
      `${labelWithParticle} 매수까지 연결 안 됨 문제로 표시돼요`,
    becomesLoose: (labelWithParticle: string) => `${labelWithParticle} 연결 없음 문제로 표시돼요`,
    modeChange: (nameWithParticle: string) => `매매 방식이 ${nameWithParticle} 바뀌어요`,
    nothing: '경로는 그대로예요',
    remove: '연결 삭제',
    removeNote: 'Delete 키로도 삭제해요 · 삭제 뒤 알림에서 되돌리기를 누를 수 있어요',
  },

  connect: {
    infoTitle: '보라색으로 켜진 연결점에만 연결할 수 있어요',
    after: (from: string, listWithParticle: string) =>
      `${from} 뒤에는 ${listWithParticle} 연결해요`,
    selectOnly: '④ 종목 선정이 있으면 매수 앞은 ④ 하나뿐이에요',
    badTitle: '여기에는 연결할 수 없어요',
    bad: (a: string, bWithParticle: string, why: string) =>
      `${a}에서 ${bWithParticle}는 연결하지 않아요 · ${why}`,
    badTip: (why: string) =>
      why.startsWith('경로가 너무 많아요') ? why : `${why} · 놓아도 선은 생기지 않아요`,
    whyLong: (why: string) => why,
    okTip: (a: string, bWithParticle: string) => `놓으면 ${a} → ${bWithParticle} 연결돼요`,
    rulesTitle: '연결 규칙',
    rules: [
      '① 유니버스 · ⑤ 매수는 하나씩만 놓아요',
      '② 신호 · ③ 필터 · ④ 종목 선정은 ①과 ⑤ 사이에 연결해요',
      '④ 종목 선정은 매수 바로 앞에 하나만 놓아요',
      '⑥ 매도는 ⑤ 매수 뒤에만 연결해요',
      '⑦ 비중은 ⑤ 매수로 들어가는 선만 연결해요',
      '선이 이미 지나온 조건으로 돌아가면 안 돼요',
      '같은 두 조건 사이 선은 하나예요 · 이미 연결돼 있으면 선이 생기지 않아요',
      '진입 경로 · 매도 경로는 20개까지예요',
    ] as const,
  },

  drop: {
    tip: (aWithParticle: string, b: string) => `놓으면 ${aWithParticle} ${b} 사이에 들어가요`,
    previewTitle: (pathWithParticle: string) => `놓으면 ${pathWithParticle} 바뀌어요`,
    previewNote: '이어서 연결한 조건은 같은 날 모두 맞아야 해요 · 숫자는 비어 있어요',
    freeTitle: '빈 곳에 놓으면 선 없이 놓여요',
    freeNote: '조건 옆 연결점을 끌어 선으로 이어요 · 숫자는 비어 있어요',
  },

  add: {
    title: '조건 추가',
    split: (node: string, n: number) =>
      `${node} 뒤에서 선이 ${String(n)}개로 갈라져요 · 어느 선에 추가할까요`,
    which: '어느 선에 추가할까요',
    between: (a: string, b: string) => `${a} → ${b} 사이`,
    goesInto: (path: string) => `${path}에 들어가요`,
    free: '캔버스 빈 곳에 놓기',
    freeLine: '선은 직접 연결해요',
    toBuy: '⑤ 매수에 연결',
    toBuyLine: '⑤ 매수로 들어가는 선으로 연결해요',
    afterBuy: '⑤ 매수 뒤에 분기로 연결',
    afterBuyLine: '하나라도 맞으면 매도하는 매도 경로가 하나 더 생겨요',
    go: '추가',
    note: '연결할 수 없는 자리는 이유와 함께 흐리게 보여요 · 숫자는 비어 있어요',
    cannot: (why: string) => why,
  },

  leave: {
    title: '저장하지 않고 나갈까요?',
    body: (parts: string, no: number) =>
      `저장하지 않은 변경이 사라져요 · ${parts} · ${version(no, '은')} 그대로예요`,
    bodyNew: '저장하지 않은 새 전략은 남지 않아요',
    added: (n: number) => `조건 추가 ${String(n)}`,
    removed: (n: number) => `조건 삭제 ${String(n)}`,
    lines: (n: number) => `연결 변경 ${String(n)}`,
    values: (n: number) => `숫자 변경 ${String(n)}`,
    moved: (n: number) => `배치 변경 ${String(n)}`,
    stay: '계속 편집',
    go: '나가기',
  },

  narrow: {
    title: '편집은 창을 넓혀서 해요',
    body: '창 폭이 1024 이상이면 조건을 놓고 이을 수 있어요 · 지금은 화면에 맞춰 보기만 해요',
    count: (n: number) => `조건 ${String(n)}개`,
  },
};
