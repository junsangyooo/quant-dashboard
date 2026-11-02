"""조건 카탈로그 v2(TASKS T-20 · DATA-CATALOG 1절 = SPEC 4-9 · ENGINE-RULES 11-3 항목 id 사전).

항목마다: id · 이름 · 분류 · 비교(op) · 매개변수(params) · 값 범위 · 단위 · 출처 · 백테스트 여부 · 블록(단계) ·
④ 정렬 여부 · 잠금 이유 · 시작 가능 날짜 · 강도 식(R-M3) · 꼬리 칩 · v1 별칭(R-C8).

- 문서 열 글자(`text_*`)는 DATA-CATALOG 1절 표의 글자 그대로예요. `tests/test_catalog.py`가 문서 표를 읽어
  항목 수 · id · op · 블록 열 · 글자 열이 같은지 봐요. 문서를 바꾸면 이 파일도 같이 바꿔요.
- 값 범위는 근거 없는 제안값이에요(가정 · SPEC 4-9).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

STAGES = ("universe", "signal", "filter", "select", "buy", "sell", "weight")
CIRCLE = dict(zip("①②③④⑤⑥⑦", STAGES, strict=True))
STAGE_CIRCLE = {v: k for k, v in CIRCLE.items()}
STAGE_NAME = {"universe": "유니버스", "signal": "신호", "filter": "필터", "select": "종목 선정", "buy": "매수",
              "sell": "매도", "weight": "비중"}
OPS = ("gte", "lte", "lt", "between", "cross_up", "cross_down", "above", "below", "top_n", "top_pct", "bottom_pct",
       "consec", "within_days", "not_within_days", "exclude", "pick", "aligned_up", "aligned_down", "fixed")
OP_NAME = {"gte": "이상", "lte": "이하", "lt": "미만", "between": "사이", "cross_up": "상향 돌파",
           "cross_down": "하향 돌파", "above": "위", "below": "아래", "top_n": "상위 n", "top_pct": "상위 n%",
           "bottom_pct": "하위 n%", "consec": "n일 연속", "within_days": "최근 n일 안에 있음",
           "not_within_days": "없음", "exclude": "제외", "pick": "고르기", "aligned_up": "정배열",
           "aligned_down": "역배열", "fixed": "정해진 비교"}
EXECS = ("intraday", "broker", "close")  # 장중 감시 · 조건주문(토스) · 종가 확인(R-X1)
EXEC_NAME = {"intraday": "장중 감시", "broker": "조건주문(토스)", "close": "종가 확인"}
RANK_OPS = ("top_n", "top_pct", "bottom_pct")
NO_VALUE_OPS = ("cross_up", "cross_down", "above", "below", "aligned_up", "aligned_down", "exclude")

# 시작 가능 날짜(R-J10 · SPEC 4-7): DART 재무는 2015년 보고서부터 → 2016-04-01
DART_FIN_START = (date(2016, 4, 1), "DART 재무가 2015년 보고서부터예요")
DART_LIST_START = (date(2015, 1, 2), "DART 공시가 2015년부터예요")
LOCK_DART = "dart"

# 꼬리 칩(SPEC 4-3 · 4-7)
CHIP_LIVE_ONLY = "실전에서만 적용 · 백테스트 미반영"
CHIP_SECTOR_NOW = "지금 섹터 기준"
CHIP_SHARES = "주식 수 근사 · 분할 · 무상증자 종목은 틀릴 수 있어요"
CHIP_YESTERDAY = "어제까지"


@dataclass(frozen=True)
class Num:
    lo: float
    hi: float
    unit: str = ""
    integer: bool = False


@dataclass(frozen=True)
class Param:
    key: str
    label: str
    num: Num | None = None  # 숫자
    choices: tuple[str, ...] = ()  # 고르기 값(비우지 않음 · R-C2는 숫자만 비움)
    blankable: bool = True  # 복사 글에서 비우는가(숫자는 비움, 고르기는 남김)
    when_op: tuple[str, ...] = ()  # 이 비교일 때만 쓰는 키


@dataclass(frozen=True)
class Item:
    id: str
    name: str  # 화면 이름(문서 '항목' 열)
    category: str
    ops: tuple[str, ...]
    stages: frozenset[str]
    sortable: bool = False  # ④ 정렬 항목으로 쓸 수 있나
    params: tuple[Param, ...] = ()
    value: Num | None = None  # 이상 · 이하 · 사이 · n일 등 값
    rank: Num | None = None  # 상위 n · 상위 n% · 하위 n% 값
    choices: tuple[str, ...] = ()  # 고르기 값(시장 · 종목 유형 · 흑자 등)
    lock: str | None = None
    start: tuple[date, str] | None = None
    strength: dict[str, str] = field(default_factory=dict)  # op → 식 이름(R-M3). 없으면 강도 없음
    execs: tuple[str, ...] = ()  # ⑥ 보유 줄이 고를 수 있는 실행 방식
    chips: tuple[str, ...] = ()
    alias: tuple[str, ...] = ()  # v1 조건 id
    # DATA-CATALOG 1절 열 글자 그대로
    text_ops: str = ""
    text_range: str = ""
    text_unit: str = ""
    text_source: str = ""
    text_backtest: str = ""
    text_blocks: str = ""

    @property
    def backtest(self) -> str:
        """yes · partial · no"""
        if self.text_backtest.startswith("아니오"):
            return "no"
        if self.text_backtest.startswith(("일부만", "항목 따라")):
            return "partial"
        return "yes"

    def has_strength(self, op: str) -> bool:
        return op in self.strength


def _stages(*circles: str) -> frozenset[str]:
    return frozenset(CIRCLE[c] for c in circles)


SIG_FILT_SELL = _stages("②", "③", "⑥")
MA_STRENGTH = {"cross_up": "close_over_line", "above": "close_over_line",
               "cross_down": "line_over_close", "below": "line_over_close"}
WHO = ("foreign", "institution", "individual")
DISCLOSURE_KINDS = ("buyback", "treasury_sale", "rights_issue", "bonus_issue", "capital_reduction", "cb", "bw",
                    "merger", "split", "business_transfer", "lawsuit", "default", "rehabilitation", "dissolution",
                    "earnings")
SORT_BY = ("strength", "return_n", "turnover", "market_cap", "per", "pbr", "psr", "dividend_yield", "roe", "op_margin",
           "sales_growth", "volatility")

_N = Param("n", "기간", Num(2, 250, "일", True))

ITEMS: tuple[Item, ...] = (
    # 종목 정보
    Item("manual_list", "종목 직접 지정", "종목 정보", ("pick",), _stages("①"), value=Num(1, 30, "종목", True),
         alias=("manual_list",), text_ops="고르기", text_range="1~30", text_unit="종목", text_source="토스 stocks",
         text_backtest="예", text_blocks="①"),
    Item("market", "시장", "종목 정보", ("pick",), _stages("①"), choices=("KOSPI", "KOSDAQ"),
         text_ops="코스피 · 코스닥 고르기", text_range="—", text_unit="—", text_source="토스 stocks",
         text_backtest="예(시장 이전 미반영)", text_blocks="①"),
    Item("security_type", "종목 유형", "종목 정보", ("pick",), _stages("①"), choices=("stock", "etf", "etn", "reit"),
         text_ops="주식 · ETF · ETN · 리츠 고르기", text_range="—", text_unit="—", text_source="토스 stocks",
         text_backtest="예", text_blocks="①"),
    Item("exclude_preferred", "우선주 제외", "종목 정보", ("exclude",), _stages("①"), text_ops="제외",
         text_range="—", text_unit="—", text_source="토스 isCommonShare", text_backtest="예", text_blocks="①"),
    Item("exclude_leveraged", "레버리지 · 인버스 ETF 제외", "종목 정보", ("exclude",), _stages("①"),
         text_ops="제외", text_range="—", text_unit="—", text_source="토스 leverageFactor", text_backtest="예",
         text_blocks="①"),
    Item("listed_days", "상장 기간", "종목 정보", ("gte",), _stages("①", "③"), value=Num(30, 3650, "일", True),
         text_ops="이상", text_range="30~3,650", text_unit="일", text_source="토스 listDate", text_backtest="예",
         text_blocks="① ③"),
    Item("sector", "섹터", "종목 정보", ("pick", "exclude"), _stages("①", "③"),
         params=(Param("level", "분류", choices=("large", "mid", "small"), blankable=False),),
         chips=(CHIP_SECTOR_NOW,), text_ops="고르기 · 제외", text_range="대 · 중 · 소", text_unit="—",
         text_source="토스 sectors", text_backtest="일부만(지금 분류)", text_blocks="① ③"),
    Item("exclude_warning", "거래정지 · 정리매매 · 투자경고 · 투자위험 제외", "종목 정보", ("exclude",), _stages("①"),
         chips=(CHIP_LIVE_ONLY,), text_ops="제외", text_range="—", text_unit="—", text_source="토스 stocks · warnings",
         text_backtest="아니오(실전에서만 적용)", text_blocks="①"),
    # 시세
    Item("price", "주가", "시세", ("gte", "lte", "between"), SIG_FILT_SELL, value=Num(1, 10_000_000, "원"),
         alias=("min_price",), text_ops="이상 · 이하 · 사이", text_range="1~10,000,000", text_unit="원",
         text_source="토스 candles", text_backtest="예", text_blocks="② ③ ⑥"),
    Item("change_pct", "등락률(전일 대비)", "시세", ("gte", "lte"), SIG_FILT_SELL, value=Num(-30, 30, "%"),
         text_ops="이상 · 이하", text_range="−30~30", text_unit="%", text_source="토스 candles", text_backtest="예",
         text_blocks="② ③ ⑥"),
    Item("return_n", "n일 수익률", "시세", ("gte", "lte", "top_pct", "bottom_pct"), SIG_FILT_SELL, sortable=True,
         params=(Param("n", "기간", Num(1, 250, "일", True)),), value=Num(-100, 1000, "%"), rank=Num(1, 100, "%", True),
         strength={"gte": "return_over_level"}, text_ops="이상 · 이하 · 상위 n% · 하위 n%",
         text_range="기간 1~250 · 값 −100~1,000 · 순위 1~100", text_unit="%", text_source="토스 candles",
         text_backtest="예", text_blocks="② ③ ⑥ · ④ 정렬"),
    Item("high_n", "n일 최고가(신고가)", "시세", ("cross_up",), _stages("②"),
         params=(Param("n", "기간", Num(5, 250, "일", True)),), strength={"cross_up": "close_over_high"},
         alias=("high_breakout",), text_ops="상향 돌파", text_range="5~250(52주 = 250)", text_unit="일",
         text_source="토스 candles", text_backtest="예", text_blocks="②"),
    Item("from_52w_high", "52주 최고가 대비", "시세", ("gte", "lte"), SIG_FILT_SELL, value=Num(-100, 0, "%"),
         text_ops="이상 · 이하", text_range="−100~0", text_unit="%", text_source="토스 candles", text_backtest="예",
         text_blocks="② ③ ⑥"),
    Item("low_n", "n일 최저가(신저가)", "시세", ("cross_down",), _stages("②", "⑥"),
         params=(Param("n", "기간", Num(5, 250, "일", True)),), strength={"cross_down": "low_over_close"},
         text_ops="하향 돌파", text_range="5~250", text_unit="일", text_source="토스 candles", text_backtest="예",
         text_blocks="② ⑥"),
    Item("gap", "시가 갭", "시세", ("gte",), _stages("②", "⑥"),
         params=(Param("dir", "방향", choices=("up", "down"), blankable=False),), value=Num(0, 30, "%"),
         text_ops="상승 갭 · 하락 갭 이상", text_range="0~30", text_unit="%", text_source="토스 candles",
         text_backtest="예", text_blocks="② ⑥"),
    Item("volume", "거래량", "시세", ("gte", "lte"), _stages("②", "③"), value=Num(1, 1_000_000_000, "주", True),
         text_ops="이상 · 이하", text_range="1~10억", text_unit="주", text_source="토스 candles", text_backtest="예",
         text_blocks="② ③"),
    Item("turnover", "거래대금", "시세", ("gte", "lte", "top_n"), _stages("②", "③"), sortable=True,
         value=Num(0.1, 100_000, "억 원"), rank=Num(1, 500, "종목", True), alias=("min_turnover",),
         text_ops="이상 · 이하 · 상위 n", text_range="0.1~100,000 · 순위 1~500", text_unit="억 원",
         text_source="토스 candles(종가 × 거래량)", text_backtest="예(근사)", text_blocks="② ③ · ④ 정렬"),
    Item("volume_ratio", "거래량 비율(n일 평균 대비)", "시세", ("gte", "lte"), _stages("②", "③"),
         params=(Param("n", "기간", Num(2, 250, "일", True)),), value=Num(0, 10_000, "%"), text_ops="이상 · 이하",
         text_range="기간 2~250 · 값 0~10,000", text_unit="%", text_source="토스 candles", text_backtest="예",
         text_blocks="② ③"),
    Item("volatility", "변동성(n일)", "시세", ("gte", "lte", "bottom_pct"), _stages("③"), sortable=True,
         params=(Param("n", "기간", Num(5, 250, "일", True)),), value=Num(0, 500, "%"), rank=Num(1, 100, "%", True),
         text_ops="이상 · 이하 · 하위 n%", text_range="기간 5~250 · 값 0~500", text_unit="%",
         text_source="토스 candles", text_backtest="예", text_blocks="③ · ④ 정렬"),
    # 기술적
    Item("ma", "이동평균선", "기술적", ("cross_up", "cross_down", "above", "below"), SIG_FILT_SELL, params=(_N,),
         strength=MA_STRENGTH, alias=("ma_cross_up", "ma_break_down"), text_ops="상향 돌파 · 하향 돌파 · 위 · 아래",
         text_range="2~250", text_unit="일", text_source="토스 candles", text_backtest="예", text_blocks="② ③ ⑥"),
    Item("ema", "지수이동평균선", "기술적", ("cross_up", "cross_down", "above", "below"), SIG_FILT_SELL, params=(_N,),
         strength=MA_STRENGTH, text_ops="위와 같음", text_range="2~250", text_unit="일", text_source="토스 candles",
         text_backtest="예", text_blocks="② ③ ⑥"),
    Item("ma_cross", "이동평균선 교차", "기술적", ("cross_up", "cross_down"), _stages("②", "⑥"),
         params=(Param("short", "단기", Num(2, 250, "일", True)), Param("long", "장기", Num(2, 250, "일", True))),
         strength={"cross_up": "short_over_long", "cross_down": "long_over_short"},
         text_ops="골든크로스 · 데드크로스", text_range="단기 · 장기 2~250", text_unit="일", text_source="토스 candles",
         text_backtest="예", text_blocks="② ⑥"),
    Item("ma_align", "이동평균선 배열", "기술적", ("aligned_up", "aligned_down"), SIG_FILT_SELL,
         params=tuple(Param(k, "기간", Num(2, 250, "일", True)) for k in ("n1", "n2", "n3")),
         text_ops="정배열 · 역배열", text_range="기간 3개 2~250", text_unit="일", text_source="토스 candles",
         text_backtest="예", text_blocks="② ③ ⑥"),
    Item("disparity", "이격도", "기술적", ("gte", "lte"), SIG_FILT_SELL, params=(_N,), value=Num(50, 200, "%"),
         text_ops="이상 · 이하", text_range="기간 2~250 · 값 50~200", text_unit="%", text_source="토스 candles",
         text_backtest="예", text_blocks="② ③ ⑥"),
    Item("rsi", "RSI", "기술적", ("gte", "lte", "lt", "cross_up", "cross_down"), SIG_FILT_SELL,
         params=(Param("period", "기간", Num(2, 50, "일", True)),), value=Num(0, 100),
         strength={"lt": "level_over_rsi", "lte": "level_over_rsi", "cross_up": "rsi_over_level",
                   "cross_down": "level_over_rsi"},
         alias=("rsi_below",), text_ops="이상 · 이하 · 미만 · 상향 돌파 · 하향 돌파", text_range="기간 2~50 · 값 0~100",
         text_unit="—", text_source="토스 candles", text_backtest="예", text_blocks="② ③ ⑥"),
    Item("macd", "MACD", "기술적", ("cross_up", "cross_down"), _stages("②", "⑥"),
         params=(Param("fast", "단기", Num(2, 100, "", True)), Param("slow", "장기", Num(2, 100, "", True)),
                 Param("signal", "시그널", Num(2, 100, "", True)),
                 Param("line", "기준선", choices=("signal", "zero"), blankable=False)),
         strength={"cross_up": "macd_up", "cross_down": "macd_down"},
         text_ops="시그널선 상향 · 하향 돌파 · 0선 상향 · 하향 돌파", text_range="12 · 26 · 9(2~100)", text_unit="—",
         text_source="토스 candles", text_backtest="예", text_blocks="② ⑥"),
    Item("bollinger", "볼린저밴드", "기술적", ("cross_up", "cross_down"), _stages("②", "⑥"),
         params=(Param("n", "기간", Num(5, 250, "일", True)), Param("k", "배수", Num(0.5, 5, "배"))),
         strength={"cross_up": "close_over_upper", "cross_down": "lower_over_close"},
         text_ops="상단 상향 돌파 · 하단 하향 돌파", text_range="기간 5~250 · 배수 0.5~5", text_unit="배",
         text_source="토스 candles", text_backtest="예", text_blocks="② ⑥"),
    Item("streak", "연속 상승 · 하락", "기술적", ("consec",), SIG_FILT_SELL,
         params=(Param("dir", "방향", choices=("up", "down"), blankable=False),), value=Num(2, 20, "일", True),
         text_ops="n일 연속", text_range="2~20", text_unit="일", text_source="토스 candles", text_backtest="예",
         text_blocks="② ③ ⑥"),
    # 가치
    Item("market_cap", "시가총액", "가치", ("gte", "lte", "top_n", "bottom_pct"), _stages("①", "③"), sortable=True,
         value=Num(1, 10_000_000, "억 원"), rank=Num(1, 100, "", True), lock=LOCK_DART, start=DART_FIN_START,
         chips=(CHIP_SHARES,), text_ops="이상 · 이하 · 상위 n · 하위 n%", text_range="1~10,000,000 · 순위 1~100",
         text_unit="억 원", text_source="토스 수정 종가 × DART 주식 총수 × 수정 계수",
         text_backtest="일부만(주식 수 맞춤 확인 전)", text_blocks="① ③ · ④ 정렬"),
    Item("per", "PER(최근 4분기 합)", "가치", ("gte", "lte", "between", "bottom_pct"), _stages("③", "⑥"),
         sortable=True, value=Num(0, 1000, "배"), rank=Num(1, 100, "%", True), lock=LOCK_DART, start=DART_FIN_START,
         chips=(CHIP_SHARES,), text_ops="이상 · 이하 · 사이 · 하위 n%", text_range="0~1,000", text_unit="배",
         text_source="위 + DART 순이익", text_backtest="일부만(공시일 기준 · 적자는 값 없음)",
         text_blocks="③ ⑥ · ④ 정렬"),
    Item("pbr", "PBR", "가치", ("gte", "lte", "between", "bottom_pct"), _stages("③", "⑥"), sortable=True,
         value=Num(0, 100, "배"), rank=Num(1, 100, "%", True), lock=LOCK_DART, start=DART_FIN_START,
         chips=(CHIP_SHARES,), text_ops="위와 같음", text_range="0~100", text_unit="배",
         text_source="위 + DART 자본총계", text_backtest="일부만", text_blocks="③ ⑥ · ④ 정렬"),
    Item("psr", "PSR(최근 4분기 합)", "가치", ("gte", "lte", "between", "bottom_pct"), _stages("③", "⑥"),
         sortable=True, value=Num(0, 1000, "배"), rank=Num(1, 100, "%", True), lock=LOCK_DART, start=DART_FIN_START,
         chips=(CHIP_SHARES,), text_ops="위와 같음", text_range="0~1,000", text_unit="배",
         text_source="위 + DART 매출액", text_backtest="일부만", text_blocks="③ ⑥ · ④ 정렬"),
    Item("dividend_yield", "배당수익률(전년 배당)", "가치", ("gte", "lte", "top_n"), _stages("③"), sortable=True,
         value=Num(0, 50, "%"), rank=Num(1, 100, "", True), lock=LOCK_DART, start=DART_FIN_START,
         chips=(CHIP_SHARES,), text_ops="이상 · 이하 · 상위 n", text_range="0~50", text_unit="%",
         text_source="DART 배당 ÷ 토스 종가(수정 계수 반영)", text_backtest="일부만(행 이름은 개발 때 확인)",
         text_blocks="③ · ④ 정렬"),
    # 수익성 · 성장성 · 안정성
    Item("roe", "ROE", "수익성", ("gte", "lte", "top_pct"), _stages("③"), sortable=True, value=Num(-100, 200, "%"),
         rank=Num(1, 100, "%", True), lock=LOCK_DART, start=DART_FIN_START, text_ops="이상 · 이하 · 상위 n%",
         text_range="−100~200", text_unit="%", text_source="DART", text_backtest="예", text_blocks="③ · ④ 정렬"),
    Item("op_margin", "영업이익률", "수익성", ("gte", "lte"), _stages("③"), sortable=True, value=Num(-100, 100, "%"),
         lock=LOCK_DART, start=DART_FIN_START, text_ops="이상 · 이하", text_range="−100~100", text_unit="%",
         text_source="DART", text_backtest="예", text_blocks="③ · ④ 정렬"),
    Item("profit_state", "흑자 · 적자 · 흑자전환 · 적자전환(영업이익 · 순이익)", "수익성", ("pick",), SIG_FILT_SELL,
         params=(Param("line", "기준", choices=("op_income", "net_income"), blankable=False),),
         choices=("profit", "loss", "turn_profit", "turn_loss"), lock=LOCK_DART, start=DART_FIN_START,
         text_ops="고르기", text_range="—", text_unit="—", text_source="DART", text_backtest="예",
         text_blocks="② ③ ⑥"),
    Item("sales_growth", "매출액 증가율(전년 동기 대비)", "성장성", ("gte", "lte", "top_pct"), _stages("③"),
         sortable=True, value=Num(-100, 1000, "%"), rank=Num(1, 100, "%", True), lock=LOCK_DART, start=DART_FIN_START,
         text_ops="이상 · 이하 · 상위 n%", text_range="−100~1,000", text_unit="%", text_source="DART",
         text_backtest="예", text_blocks="③ · ④ 정렬"),
    Item("profit_growth", "영업이익 · 순이익 증가율", "성장성", ("gte", "lte"), _stages("③"),
         params=(Param("line", "기준", choices=("op_income", "net_income"), blankable=False),),
         value=Num(-100, 1000, "%"), lock=LOCK_DART, start=DART_FIN_START, text_ops="이상 · 이하(전년 적자면 값 없음)",
         text_range="−100~1,000", text_unit="%", text_source="DART", text_backtest="예", text_blocks="③"),
    Item("sales_growth_3y", "최근 3년 평균 매출 증가율", "성장성", ("gte", "lte"), _stages("③"),
         value=Num(-100, 500, "%"), lock=LOCK_DART, start=DART_FIN_START, text_ops="이상 · 이하",
         text_range="−100~500", text_unit="%", text_source="DART 사업보고서", text_backtest="예", text_blocks="③"),
    Item("debt_ratio", "부채비율", "안정성", ("gte", "lte"), _stages("③", "⑥"), value=Num(0, 2000, "%"),
         lock=LOCK_DART, start=DART_FIN_START, text_ops="이상 · 이하", text_range="0~2,000", text_unit="%",
         text_source="DART", text_backtest="예", text_blocks="③ ⑥"),
    # 수급
    Item("net_buy", "외국인 · 기관 · 개인 순매수(어제까지 n일 합)", "수급", ("gte", "lte", "consec"), SIG_FILT_SELL,
         params=(Param("who", "투자자", choices=WHO, blankable=False), Param("n", "기간", Num(1, 60, "일", True)),
                 Param("unit", "단위", choices=("shares", "pct_volume"), blankable=False),
                 Param("side", "방향", choices=("buy", "sell"), blankable=False, when_op=("consec",))),
         value=Num(-1_000_000_000, 1_000_000_000, "주"), chips=(CHIP_YESTERDAY,),
         text_ops="이상 · 이하 · n일 연속 순매수 · 순매도", text_range="기간 1~60 · 주, 또는 거래량 대비 −100~100%",
         text_unit="주 · %", text_source="토스 investor-trading(확정치)", text_backtest="일부만(깊이 개발 때 확인)",
         text_blocks="② ③ ⑥"),
    Item("foreign_ratio", "외국인 지분율(어제 확정치)", "수급", ("gte", "lte", "consec"), _stages("③"),
         params=(Param("n", "기간", Num(2, 60, "일", True), when_op=("consec",)),), value=Num(0, 100, "%"),
         chips=(CHIP_YESTERDAY,), text_ops="이상 · 이하 · n일 증가", text_range="0~100", text_unit="%",
         text_source="토스 investor-trading", text_backtest="일부만", text_blocks="③"),
    # 이벤트 · 시장
    Item("disclosure", "공시", "이벤트", ("within_days", "not_within_days"), SIG_FILT_SELL,
         params=(Param("kind", "공시 종류", choices=DISCLOSURE_KINDS, blankable=False),), value=Num(1, 60, "일", True),
         lock=LOCK_DART, start=DART_LIST_START, text_ops="최근 n일 안에 있음 · 없음", text_range="1~60", text_unit="일",
         text_source="DART 주요사항 · list.json", text_backtest="예(접수일 다음 거래일부터)", text_blocks="② ③ ⑥"),
    Item("index_ma", "코스피 · 코스닥 지수 이동평균선", "시장", ("above", "below", "cross_up", "cross_down"),
         _stages("③", "⑥"), params=(Param("index", "지수", choices=("KOSPI", "KOSDAQ"), blankable=False), _N),
         text_ops="위 · 아래 · 상향 돌파 · 하향 돌파", text_range="2~250", text_unit="일",
         text_source="토스 market-indicators", text_backtest="예(깊이 개발 때 확인)", text_blocks="③ ⑥"),
    # 보유(⑥) · 매수 · 종목 선정 · 비중
    Item("stop_loss", "손절", "보유", ("fixed",), _stages("⑥"), value=Num(1, 50, "%"), execs=EXECS,
         alias=("stop_loss",), text_ops="매수가보다 n% 내려가면", text_range="1~50", text_unit="%",
         text_source="앱 체결 기록 + 토스 시세", text_backtest="예", text_blocks="⑥ · 실행 3종"),
    Item("take_profit", "익절", "보유", ("fixed",), _stages("⑥"), value=Num(1, 500, "%"), execs=EXECS,
         alias=("take_profit",), text_ops="매수가보다 n% 오르면", text_range="1~500", text_unit="%",
         text_source="위와 같음", text_backtest="예", text_blocks="⑥ · 실행 3종"),
    Item("trailing_stop", "트레일링 스톱", "보유", ("fixed",), _stages("⑥"), value=Num(1, 50, "%"),
         execs=("intraday", "close"), text_ops="매수 뒤 최고가보다 n% 내려가면", text_range="1~50", text_unit="%",
         text_source="위와 같음", text_backtest="예", text_blocks="⑥ · 장중 감시 · 종가 확인"),
    Item("max_hold", "최대 보유", "보유", ("fixed",), _stages("⑥"), value=Num(1, 250, "거래일", True),
         execs=("close",), alias=("max_hold",), text_ops="n거래일 경과", text_range="1~250", text_unit="거래일",
         text_source="앱 기록 + 장 운영 정보", text_backtest="예", text_blocks="⑥ · 종가 확인"),
    Item("next_open", "다음 날 시가 매수 · 판 뒤 다시 사지 않는 기간", "매수", ("fixed",), _stages("⑤"),
         value=Num(0, 20, "거래일", True), alias=("next_open",), text_ops="고정 · n거래일", text_range="0~20",
         text_unit="거래일", text_source="—", text_backtest="예", text_blocks="⑤"),
    Item("top_n", "정렬", "종목 선정", ("top_n",), _stages("④"),
         params=(Param("by", "항목", choices=SORT_BY, blankable=False),
                 Param("order", "순서", choices=("desc", "asc"), blankable=False),
                 Param("n", "기간", Num(1, 250, "일", True))),
         value=Num(1, 30, "종목", True), alias=("top_n",), text_ops="[항목] 높은 순 · 낮은 순 상위 n종목",
         text_range="1~30", text_unit="종목", text_source="위 항목들", text_backtest="항목 따라", text_blocks="④"),
    Item("equal", "동일 비중", "비중", ("fixed",), _stages("⑦"), alias=("equal",), text_ops="고정", text_range="—",
         text_unit="—", text_source="—", text_backtest="예", text_blocks="⑦"),
    Item("max_per_stock", "종목당 최대 비중", "비중", ("fixed",), _stages("⑦"), value=Num(1, 100, "%"),
         alias=("max_per_stock",), text_ops="이하", text_range="1~100", text_unit="%", text_source="—",
         text_backtest="예", text_blocks="⑦"),
    Item("rebalance_every", "리밸런싱 주기", "비중", ("fixed",), _stages("⑦"),
         params=(Param("how", "리밸런싱 방식", choices=("target", "rank"), blankable=False),),
         value=Num(1, 250, "거래일", True), alias=("rebalance_every",), text_ops="n거래일 · 목표 비중 / 순위 교체",
         text_range="1~250", text_unit="거래일", text_source="—", text_backtest="예", text_blocks="⑦"),
)

CATALOG: dict[str, Item] = {i.id: i for i in ITEMS}
V1_ALIASES: dict[str, str] = {a: i.id for i in ITEMS for a in i.alias}
SORTABLE: tuple[str, ...] = ("strength", *[i.id for i in ITEMS if i.sortable])


def item(item_id: str) -> Item:
    return CATALOG[item_id]


def items_for(stage: str) -> list[Item]:
    return [i for i in ITEMS if stage in i.stages]


def locked(item_id: str, *, dart: bool) -> bool:
    """DART 키가 없으면 잠기는 항목인가(SPEC 4-7 · R-P4)."""
    return CATALOG[item_id].lock == LOCK_DART and not dart


def start_date(item_ids: list[str]) -> tuple[date, str] | None:
    """이 항목들을 쓴 전략의 시작 가능 날짜(가장 늦은 것) · 이유(R-J10)."""
    starts = [CATALOG[i].start for i in item_ids if i in CATALOG and CATALOG[i].start]
    return max(starts, key=lambda s: s[0]) if starts else None  # type: ignore[return-value,index]


def describe() -> list[dict[str, Any]]:
    """화면용 사전(조건 추가 메뉴 · 줄 편집 패널)."""
    out = []
    for i in ITEMS:
        out.append({
            "id": i.id, "name": i.name, "category": i.category, "ops": list(i.ops),
            "op_names": [OP_NAME[o] for o in i.ops], "stages": sorted(i.stages, key=STAGES.index),
            "sortable": i.sortable, "lock": i.lock, "backtest": i.backtest, "chips": list(i.chips),
            "execs": list(i.execs), "unit": i.text_unit, "source": i.text_source,
            "start": i.start[0].isoformat() if i.start else None, "start_reason": i.start[1] if i.start else None,
            "params": [{"key": p.key, "label": p.label, "choices": list(p.choices),
                        "min": p.num.lo if p.num else None, "max": p.num.hi if p.num else None,
                        "integer": p.num.integer if p.num else None, "when_op": list(p.when_op)} for p in i.params],
            "value": None if i.value is None else {"min": i.value.lo, "max": i.value.hi, "unit": i.value.unit,
                                                   "integer": i.value.integer},
            "rank": None if i.rank is None else {"min": i.rank.lo, "max": i.rank.hi},
            "choices": list(i.choices),
        })
    return out


CHOICE_NAMES: dict[str, str] = {
    "KOSPI": "코스피", "KOSDAQ": "코스닥", "stock": "주식", "etf": "ETF", "etn": "ETN", "reit": "리츠",
    "profit": "흑자", "loss": "적자", "turn_profit": "흑자전환", "turn_loss": "적자전환",
}


# ── 줄 편집 패널 글(SPEC 4-3 오른쪽 패널: 도움말 · 출처 · 백테스트 반영 · 시작 가능 날짜) ──────

HELP: dict[str, str] = {
    "manual_list": "고른 종목만 봐요. 같은 단계의 다른 조건은 이 목록을 다시 걸러요.",
    "market": "코스피 · 코스닥 가운데 고른 시장의 종목만 봐요.",
    "security_type": "주식 · ETF · ETN · 리츠 가운데 고른 유형만 봐요.",
    "exclude_preferred": "우선주를 빼고 보통주만 봐요.",
    "exclude_leveraged": "레버리지 · 인버스 ETF를 빼요.",
    "listed_days": "상장한 지 n일이 지난 종목만 봐요.",
    "sector": "토스 섹터로 고르거나 빼요. 과거도 지금 분류로 봐요.",
    "exclude_warning": "거래정지 · 정리매매 · 투자경고 · 투자위험 종목을 빼요. 실전에서만 적용해요.",
    "price": "종가가 이 범위에 있는 날이에요.",
    "change_pct": "전날 종가보다 오르거나 내린 비율이에요.",
    "return_n": "n거래일 전 종가보다 오른 비율이에요.",
    "high_n": "종가가 직전 n일 고가의 최고치를 넘은 날이에요.",
    "from_52w_high": "52주 최고가보다 얼마나 아래에 있는지예요.",
    "low_n": "종가가 직전 n일 저가의 최저치 아래로 내려간 날이에요.",
    "gap": "시가가 전날 종가보다 n% 넘게 높거나 낮게 시작한 날이에요.",
    "volume": "그날 거래량이에요.",
    "turnover": "종가 × 거래량으로 셈한 그날 거래대금이에요.",
    "volume_ratio": "그날 거래량이 직전 n일 평균의 몇 %인지예요.",
    "volatility": "최근 n일 수익률이 얼마나 흔들렸는지예요.",
    "ma": "종가와 n일 이동평균선을 비교해요. 같은 값은 아래로 봐요.",
    "ema": "종가와 n일 지수이동평균선을 비교해요.",
    "ma_cross": "단기 이동평균선이 장기선을 넘으면 골든크로스, 아래로 내려가면 데드크로스예요.",
    "ma_align": "이동평균선 셋이 짧은 순으로 위에 있으면 정배열이에요.",
    "disparity": "종가가 n일 이동평균선의 몇 %인지예요.",
    "rsi": "n일 동안 오른 폭과 내린 폭으로 셈한 0~100 값이에요.",
    "macd": "단기 · 장기 지수이동평균선의 차이가 시그널선이나 0선을 넘는 날이에요.",
    "bollinger": "종가가 볼린저밴드 상단을 넘거나 하단 아래로 내려간 날이에요.",
    "streak": "종가가 n일 연속 오르거나 내린 날이에요.",
    "market_cap": "수정 종가 × DART 주식 수예요. 분할 · 무상증자 종목은 틀릴 수 있어요.",
    "per": "주가를 최근 4분기 순이익 합으로 나눈 값이에요. 적자라 값이 없으면 이 줄은 맞지 않아요.",
    "pbr": "주가를 최근 자본총계로 나눈 값이에요.",
    "psr": "주가를 최근 4분기 매출액 합으로 나눈 값이에요.",
    "dividend_yield": "전년 주당 배당금을 종가로 나눈 값이에요.",
    "roe": "최근 4분기 순이익 합을 자본총계로 나눈 값이에요.",
    "op_margin": "최근 4분기 영업이익을 매출액으로 나눈 값이에요.",
    "profit_state": "최근 분기 영업이익 · 순이익이 흑자인지, 전년 같은 분기보다 흑자전환 · 적자전환했는지예요.",
    "sales_growth": "최근 분기 매출액이 전년 같은 분기보다 늘어난 비율이에요.",
    "profit_growth": "최근 분기 영업이익 · 순이익이 전년 같은 분기보다 늘어난 비율이에요. 전년이 적자면 값이 없어요.",
    "sales_growth_3y": "최근 3년 사업보고서 매출액의 연평균 증가율이에요.",
    "debt_ratio": "부채총계를 자본총계로 나눈 값이에요.",
    "net_buy": "어제까지 n일 동안 외국인 · 기관 · 개인이 순매수한 양이에요.",
    "foreign_ratio": "어제 확정된 외국인 지분율이에요.",
    "disclosure": "최근 n거래일 안에 그 공시가 있었는지예요. 접수일 다음 거래일부터 맞아요.",
    "index_ma": "코스피 · 코스닥 지수가 n일 이동평균선 위에 있는지예요.",
    "stop_loss": "매수가보다 n% 내려가면 팔아요.",
    "take_profit": "매수가보다 n% 오르면 팔아요.",
    "trailing_stop": "매수 뒤 최고가보다 n% 내려가면 팔아요. 최고가는 전날까지로 셈해요.",
    "max_hold": "산 뒤 n거래일이 지나면 팔아요.",
    "next_open": "확인한 다음 거래일 시가에 사요. 판 뒤 n거래일 동안은 다시 사지 않아요.",
    "top_n": "후보를 고른 항목 순으로 줄 세워 상위 n종목까지 사요. 값이 없는 종목은 맨 뒤예요.",
    "equal": "같은 금액으로 나눠 사요.",
    "max_per_stock": "한 종목에 이 비중보다 많이 사지 않아요.",
    "rebalance_every": "n거래일마다 목표 비중이나 순위로 다시 맞춰요.",
}

SOURCE_DISPLAY: dict[str, str] = {
    "per": "DART 순이익 · 토스 수정 종가",
    "pbr": "DART 자본총계 · 토스 수정 종가",
    "psr": "DART 매출액 · 토스 수정 종가",
    "market_cap": "DART 주식 수 · 토스 수정 종가",
}


def backtest_display(item: Item) -> str:
    """'일부만(공시일 기준 · 적자는 값 없음)' → '일부만 · 공시일 기준'."""
    text = item.text_backtest
    if "(" not in text:
        return text
    head, _, rest = text.partition("(")
    first = rest.rstrip(")").split(" · ")[0]
    return f"{head} · {first}"
