// 전략 목록 · 새 전략 시트 · 전략 상세 · 예시 상세 · 복사한 전략 붙여 넣기 · 모의투자 시작/끝내기 · 시작하기
// (Figma MVP 화면 08 · 09 · 10 · 12 · 14).

export const strategyCopy = {
  title: '전략',
  new: '새 전략',
  importLink: '복사한 전략 붙여 넣기',
  rowLine: (no: number, mode: string, saved: string) =>
    `버전 ${String(no)} · ${mode} · ${saved} 저장`,
  emptyTitle: '아직 전략이 없어요',
  emptyBody: '빈 캔버스에서 만들거나, 예시에서 시작하거나, 복사한 전략을 가져와요',

  steps: {
    title: '시작하기',
    done: (n: number) => `4단계 중 ${String(n)}단계 완료`,
    lead: '모의투자를 시작하면 여기에 자산이 보여요',
    rows: [
      {
        title: '1 · API 키 연결 (선택)',
        done: '연결했어요 · 보유 평가에 토스 현재가를 써요',
        todo: '토스 API 키를 연결하면 보유 평가에 토스 현재가를 써요 · 하지 않아도 돼요',
        link: 'API 키 연결',
      },
      {
        title: '2 · 전략 만들기',
        done: '전략을 만들었어요',
        todo: '빈 캔버스나 예시에서 시작해요',
        link: '전략 만들기',
      },
      {
        title: '3 · 백테스트',
        done: '백테스트를 실행했어요',
        todo: '전략을 저장하면 백테스트를 실행할 수 있어요',
        link: '백테스트',
      },
      {
        title: '4 · 모의투자 시작',
        done: '모의투자를 시작했어요',
        todo: '백테스트한 전략으로 시작해요 · 실전 주문은 내지 않아요',
        link: '모의투자 시작',
      },
    ],
  },

  examples: {
    title: '예시 전략 4개',
    lead: '숫자를 채워 둔 예시예요 · 눌러서 보고 바로 백테스트할 수 있어요',
    chip: '예시',
    meta: (nodes: number, entry: number, sell: number) =>
      sell > 0
        ? `조건 ${String(nodes)}개 · 진입 경로 ${String(entry)}개 · 매도 경로 ${String(sell)}개`
        : `조건 ${String(nodes)}개 · 진입 경로 ${String(entry)}개`,
    pick: (mode: string, nodes: number) => `${mode} · 조건 ${String(nodes)}개`,
  },

  sheet: {
    title: '새 전략',
    name: '전략 이름',
    namePlaceholder: '예: 내 대형주 돌파',
    nameHint:
      '비워 두면 고른 예시 이름으로 저장해요 · 이름이 겹치면 이름 끝에 (2)처럼 숫자를 더해요',
    from: '어디서 시작할까요',
    blank: '빈 캔버스',
    blankLine:
      '① 종목 직접 지정 → ④ 신호 강도 상위 n종목 → ⑤ 다음 날 시가 매수 ← ⑦ 동일 비중이 놓인 채로 열려요 · 종목과 숫자는 비어 있어요',
    example: '예시에서 시작',
    exampleLine: '숫자를 채워 둔 예시를 복사해요 · 수정해서 써 보세요',
    paste: '복사한 전략 붙여 넣기',
    pasteLine: '전략 복사로 받은 글을 가져와요 · 숫자는 비어 있어요',
    create: '만들기',
    note: '만들면 편집 화면에서 바로 열려요',
  },

  detail: {
    back: '전략',
    edit: '편집',
    backtest: '백테스트',
    copy: '전략 복사',
    copied: '복사했어요 · 붙여 넣을 곳에 그대로 붙여 넣으세요',
    problemsTitle: (n: number) => `문제 ${String(n)}개를 해결해야 해요`,
    problemsBody: '저장은 돼요 · 문제를 해결해야 백테스트와 모의투자를 할 수 있어요',
    problemsWhere: (parts: string) => `${parts} · 편집에서 수정해요`,
    part: (label: string, n: number) => `${label} ${String(n)}`,
    runningTitle: (no: number) => `모의투자 중 · 버전 ${String(no)}`,
    start: '시작',
    cash0: '시작 금액',
    now: '지금 자산',
    end: '모의투자 끝내기',
    endNote: '끝내도 기록은 남아요',
    beforeTitle: '모의투자 전',
    beforeLine: (no: number, problems: number) =>
      problems === 0
        ? `버전 ${String(no)} · 문제 0 · 시작 금액을 정하면 평일 16:30에 자동으로 확인해요`
        : `버전 ${String(no)} · 문제 ${String(problems)}개`,
    startPaper: '모의투자 시작',
    pastTitle: '지난 모의투자',
    pastRow: (no: number, range: string) => `버전 ${String(no)} · ${range}`,
    pastLine: (n: number) => `거래 ${String(n)}회 · 기록 보기`,
    graphTitle: (no: number, n: number) => `버전 ${String(no)} · 조건 ${String(n)}개`,
    graphLine: (entry: number, sell: number) =>
      `진입 경로 ${String(entry)}개 · 매도 경로 ${String(sell)}개 · 누르면 편집에서 열려요`,
    graphLineNarrow: (entry: number, sell: number) =>
      `진입 경로 ${String(entry)}개 · 매도 경로 ${String(sell)}개 · 누르면 크게 볼 수 있어요 · 편집은 창을 넓혀서 해요`,
    openEditor: '편집에서 열기',
    bigView: '크게 보기',
    readHow:
      '선을 따라 한 경로 위의 조건이 모두 맞으면 통과해요 · 경로가 여러 개면 하나라도 통과하면 돼요',
    versions: (n: number) => `버전 ${String(n)}개`,
    versionLine: (saved: string, problems: number) => `${saved} 저장 · 문제 ${String(problems)}`,
    cannotDelete: '모의투자 기록이 있는 전략은 삭제할 수 없어요',
    delete: '전략 삭제',
    deleteTitle: '전략을 삭제할까요?',
    deleteBody: (name: string) => `${name}의 버전이 모두 삭제돼요 · 되돌릴 수 없어요`,
  },

  example: {
    back: '전략',
    noteTitle: '숫자는 예시예요 · 그대로 백테스트할 수 있어요',
    noteBody:
      '예시는 보기만 해요 · 수정하려면 이 예시로 새 전략을 만들어요 · 이름이 겹치면 이름 끝에 (2)처럼 숫자를 더해요',
    backtest: '백테스트',
    copy: '이 예시로 새 전략',
    graphTitle: (n: number) => `조건 ${String(n)}개`,
    graphLine: (entry: number, sell: number) =>
      sell > 0
        ? `진입 경로 ${String(entry)}개 · 매도 경로 ${String(sell)}개 · 예시는 보기만 해요`
        : `진입 경로 ${String(entry)}개 · 예시는 보기만 해요`,
  },

  start: {
    title: '모의투자 시작',
    strategy: '전략',
    strategyLine: (name: string, no: number) => `${name} · 버전 ${String(no)}`,
    cash: '시작 금액',
    cashHint: '10만 원 ~ 100억 원',
    unit: '원',
    first: (check: string, time: string, fill: string) =>
      `첫 확인 ${check} ${time} · 첫 모의 체결 ${fill} 시가`,
    firstBodyNow: (fill: string) =>
      `지금 확인하고 ${fill} 시가에 모의 체결해요 · 실전 주문은 내지 않아요`,
    firstBodyLater: (check: string, fill: string) =>
      `${check} 16:30에 자동으로 확인하고 ${fill} 시가에 모의 체결해요 · 실전 주문은 내지 않아요`,
    previewLoading: '첫 확인 날짜를 계산하고 있어요',
    previewFailed: '첫 확인 날짜를 계산하지 못했어요',
    previewRetry: '다시 시도',
    otherTitle: '지금 실행 중인 모의투자가 있어요',
    otherBody: (name: string, no: number, since: string) =>
      `${name} · 버전 ${String(no)} · ${since} 시작 · 시작하면 그 모의투자를 끝내고 새로 시작해요 · 기록은 남아요`,
    go: '모의투자 시작',
    goReplace: '끝내고 새로 시작',
  },

  end: {
    title: '모의투자를 끝낼까요?',
    line: (name: string, no: number) => `${name} · 버전 ${String(no)}`,
    since: (d: string, days: number) => `${d}부터 ${String(days)}일`,
    body: (last: string, held: number) =>
      held > 0
        ? `마지막 평가 ${last} 종가 · 보유하던 ${String(held)}종목은 기록에 남아요 · 다시 이어 갈 수는 없어요`
        : `마지막 평가 ${last} 종가 · 다시 이어 갈 수는 없어요`,
    go: '끝내기',
  },

  import: {
    back: '전략',
    title: '복사한 전략 붙여 넣기',
    lead: '사이트 실험실이나 전략 상세에서 전략 복사로 받은 글을 그대로 붙여 넣으세요',
    placeholder: '여기에 복사한 전략을 붙여 넣으세요',
    paste: '붙여 넣기',
    check: '확인',
    notCopy: '복사한 전략 글이 아니에요',
    notCopyBody:
      '복사한 곳에서 전략 복사를 다시 누르고, 첫 줄부터 마지막 줄까지 그대로 붙여 넣으세요',
    badGraphBody: (detail: string) =>
      `${detail} · 복사한 곳에서 연결을 수정한 뒤 전략 복사를 다시 눌러 주세요`,
    target: '가져올 전략',
    name: '전략 이름',
    renamed: '같은 이름의 전략이 있어서 이름 끝에 (2)를 더했어요',
    renamedN: (tailWithParticle: string) =>
      `같은 이름의 전략이 있어서 이름 끝에 ${tailWithParticle} 더했어요`,
    source: '출처',
    mode: '매매 방식',
    numbersTitle: '숫자는 직접 입력해요',
    numbersBody: (n: number) =>
      `복사한 전략에는 구조만 담겨요 · 숫자는 직접 정해요 · 빈칸 ${String(n)}개`,
    summary: '구조 요약',
    summaryLine: (nodes: number, entry: number, sell: number, blanks: number) =>
      `조건 ${String(nodes)}개 · 진입 경로 ${String(entry)}개 · 매도 경로 ${String(sell)}개 · 빈칸 ${String(blanks)}개`,
    accept: '가져오기',
    acceptNote: '가져오면 새 전략 버전 1로 저장돼요',
  },
};
