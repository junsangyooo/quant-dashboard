// 그래프 검사 글(서버 app/graph.py와 글자 하나까지 같다 · web/tests/graphMirror.test.ts가 대조한다).
// 낱말: 조건 · 연결 · 경로 · 분기 · 연결점(GLOSSARY 2절). 매매 방식 이름도 GLOSSARY 2절.

export const graphRules = {
  universeIn: '유니버스 앞에는 조건을 연결할 수 없어요',
  sell: '매도 조건은 매수 뒤에 연결해요',
  entry: '신호 · 필터는 매수 앞에 연결해요',
  select: '종목 선정은 매수 바로 앞에 하나만 놓아요',
  weight: '비중 조건은 매수에 연결해요',
  buyOnce: '매수 조건은 하나만 놓을 수 있어요',
  cycle: '선이 이미 지나온 조건으로 돌아가면 안 돼요',
  dup: '이미 연결돼 있어요',
  many: (max: number) => `경로가 너무 많아요 · 진입 경로는 최대 ${String(max)}개예요`,
  manySell: (max: number) => `경로가 너무 많아요 · 매도 경로는 최대 ${String(max)}개예요`,
  noNode: '없는 조건이에요',
  universeOnce: '유니버스는 하나만 놓을 수 있어요',
  onceNamed: (nameWithParticle: string) => `${nameWithParticle} 하나만 놓을 수 있어요`,
  nodeMax: (max: number) => `조건은 ${String(max)}개까지 놓을 수 있어요`,
};

export const kindNames = {
  blank: '빈칸',
  range: '범위 밖',
  required: '필요한 조건',
  unusable: '못 쓰는 조건',
  loose: '연결 없음',
  dead: '매수까지 연결 안 됨',
  rule: '연결 규칙',
  many: '경로가 너무 많아요',
} as const;

export const modeNames = {
  event: '조건 충족 시 매매',
  target: '목표 비중 리밸런싱',
  rank: '순위 교체 리밸런싱',
} as const;

export const howNames = { target: '목표 비중', rank: '순위 교체' } as const;

export const graphText = {
  choose: (labelWithParticle: string) => `${labelWithParticle} 골라 주세요`,
  enter: (labelWithParticle: string) => `${labelWithParticle} 입력해 주세요`,
  notSymbol: (bad: string) => `한국 종목 6자리 코드가 아니에요: ${bad}`,
  tooManySymbols: (max: number) => `종목은 ${String(max)}개까지 입력할 수 있어요`,
  notNumber: (label: string, range: string) => `${label}에 숫자를 입력해 주세요 (${range})`,
  between: (labelWithParticle: string, range: string) =>
    `${labelWithParticle} ${range} 사이로 입력해 주세요`,
  integer: (labelWithParticle: string) => `${labelWithParticle} 정수로 입력해 주세요`,
  blankTitle: (name: string) => `빈칸 · ${name}`,
  rangeTitle: (title: string) => `범위 밖 · ${title}`,
  requiredTitle: (stage: string) => `필요한 조건 · ${stage}`,
  needUniverse: '종목 직접 지정 조건이 있어야 해요',
  needBuy: '다음 날 시가 매수 조건이 있어야 해요',
  needEqual: '동일 비중 조건이 있어야 해요',
  needSelect: (mode: string) => `${mode}에는 신호 강도 상위 n종목이 있어야 해요`,
  needSelectHint: '목록에서 ④ 종목 선정을 끌어 와 매수 바로 앞 선 위에 놓아 주세요',
  noSignal: (k: number) =>
    `진입 경로 ${String(k)}에 신호가 없어요 · 신호 없이 연결하면 매일 모든 종목이 매수 후보가 돼요`,
  noSignalHint: (next: string) =>
    `목록에서 신호 조건을 끌어 와 ①과 ${next} 사이 선 위에 놓아 주세요`,
  needSell: (mode: string) => `${mode}에는 매도 경로가 하나 이상 있어야 해요`,
  needSellHint: '⑥ 매도 조건을 끌어 와 ⑤ 매수 뒤에 연결해 주세요',
  unusableTitle: (title: string) => `못 쓰는 조건 · ${title}`,
  unusable: (mode: string, stage: string) =>
    `${mode}에서는 ${stage} 조건을 쓸 수 없어요 · 순위 교체를 고르거나 이 조건을 삭제해 주세요`,
  looseTitle: (title: string) => `연결 없음 · ${title}`,
  loose: '선으로 연결해야 전략에 들어가요',
  deadTitle: '매수까지 연결 안 됨',
  dead: (k: number, last: string, target: string) =>
    `진입 경로 ${String(k)} · ${last} 뒤를 ${target}에 연결해 주세요`,
  buyTarget: '⑤ 매수',
  ruleTitle: (a: string, b: string) => `연결 규칙 · ${a} → ${b}`,
  manyShort: (max: number) => `진입 경로 · 매도 경로는 ${String(max)}개까지예요`,
  more: (first: string, n: number) => `${first} 외 ${String(n)}`,
};
