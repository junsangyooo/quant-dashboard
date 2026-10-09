// Words for the AI rule's metrics and margins (CONTRACT MetricRef · Margin). The server sends a
// dictionary key plus the company's own word (`param`) and a number with a unit code; the screen
// names them. Used by the 계획 card (gauge, rows) and the 규칙 flow cards.
//
// Every string here is NEW: 기획.md has none of them. The names follow the engine's metric
// dictionary (autotrade/domain/metrics.py labels); Figma 탐색 17:7108 draws '이익률' · '수주잔고' ·
// 'AI 매출' and the margins '2.3%p' · '3.1조' · '2분기'. Review with the owner.

export const metricCopy = {
  /** NEW — metric names by dictionary key. Segment and guidance names wrap the company's word. */
  names: {
    revenue: '매출',
    operating_income: '영업이익',
    net_income: '순이익',
    op_margin: '이익률',
    eps: 'EPS',
    fcf: 'FCF',
    ebitda_margin: 'EBITDA 마진',
    net_debt_to_ebitda: '순부채/EBITDA',
    backlog: '수주잔고',
    new_orders: '신규 수주',
    book_to_bill: '수주/매출',
    monthly_revenue_yoy: '월매출 전년비',
    segment_revenue: (segment: string) => `${segment} 매출`,
    segment_operating_income: (segment: string) => `${segment} 영업이익`,
    segment_op_margin: (segment: string) => `${segment} 이익률`,
    segment_backlog: (segment: string) => `${segment} 수주잔고`,
    guidance: (item: string) => item,
  },

  /** NEW — stand-ins when a segment or guidance metric arrives without the company's word. */
  noParam: { segment: '부문', guidance: '회사 전망' },

  /**
   * NEW — margin units: '2.3%p' (pp, from copy.units), '2.1%', '3.1조' · '450억' · '3,500만',
   * '$1.2B' · '$350M', '0.12x', '2분기' (two quarters left), '3개월', '1년'. A count has no unit.
   */
  units: {
    jo: '조',
    eok: '억',
    man: '만',
    usdBillion: 'B',
    usdMillion: 'M',
    times: 'x',
    quarter: '분기',
    month: '개월',
    year: '년',
  },
} as const;
