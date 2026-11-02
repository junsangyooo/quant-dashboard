"""조건 15개와 단계 일곱 개(이름 · 숫자 칸 · 쓸 수 있는 매매 방식 · 도움말), 종목 이름, 글 꼴.

전략은 조건(노드)을 선으로 이은 그래프다(graph.py). 조건마다 단계(① 유니버스 ~ ⑦ 비중)가 있다.
숫자 입력 칸은 제품 기본값이 없다. 빈칸(null)과 범위 밖 값은 '문제'로 돌려준다.
"""

from __future__ import annotations

from typing import Any

SLOTS: list[tuple[str, str, str]] = [
    ("universe", "유니버스", "발굴"),
    ("signal", "신호", "발굴"),
    ("filter", "필터", "발굴"),
    ("select", "종목 선정", "발굴"),
    ("buy", "매수", "매매"),
    ("sell", "매도", "매매"),
    ("weight", "비중", "매매"),
]
SLOT_KEYS = [k for k, _, _ in SLOTS]
SLOT_NAMES = {k: n for k, n, _ in SLOTS}
CIRCLED = "①②③④⑤⑥⑦"
SLOT_CIRCLE = {k: CIRCLED[i] for i, k in enumerate(SLOT_KEYS)}
SLOT_LABEL = {k: f"{CIRCLED[i]} {n}" for i, (k, n, _) in enumerate(SLOTS)}

# 매매 방식: 놓은 조건으로 정해진다(graph.mode_of). 저장하지 않고 늘 계산한다.
MODES: dict[str, dict[str, str]] = {
    "event": {
        "name": "조건 충족 시 매매",
        "line": "신호가 나온 날 매수하고, 손절 · 익절 같은 매도 조건을 만족하면 매도해요",
    },
    "target": {
        "name": "목표 비중 리밸런싱",
        "line": "고른 종목을 정한 비중으로 보유하고, 리밸런싱 주기마다 비중을 다시 맞춰요",
    },
    "rank": {
        "name": "순위 교체 리밸런싱",
        "line": "리밸런싱 주기마다 신호가 강한 순으로 다시 골라, 순위에서 빠진 종목은 매도하고 새 종목을 매수해요",
    },
}

# 리밸런싱 주기 조건의 '리밸런싱 방식' 칸(숫자 칸 옆 선택)
HOW_OPTIONS: list[dict[str, str]] = [
    {"id": "target", "name": "목표 비중", "line": "정한 비중으로 보유하고 주기마다 비중을 맞춰요 · ⑥ 매도 조건은 쓰지 않아요"},
    {"id": "rank", "name": "순위 교체", "line": "주기마다 신호가 강한 순으로 다시 골라, 순위에서 빠진 종목은 매도해요"},
]
HOW_NAMES = {o["id"]: o["name"] for o in HOW_OPTIONS}


def _num(key: str, label: str, unit: str, lo: float, hi: float, integer: bool) -> dict[str, Any]:
    return {"key": key, "label": label, "unit": unit, "min": lo, "max": hi, "integer": integer}


# 조건: slot(단계), 이름(n 자리 그대로), 요약 제목({key} 자리에 숫자), 숫자 칸, 쓸 수 있는 매매 방식, 도움말.
# help_rebalance: 리밸런싱 방식(목표 비중 · 순위 교체)에서 뜻이 다른 신호의 도움말.
PIECES: dict[str, dict[str, Any]] = {
    "manual_list": {
        "slot": "universe",
        "name": "종목 직접 지정",
        "title": "종목 직접 지정",
        "params": [{"key": "symbols", "label": "종목 코드", "kind": "symbols", "min": 1, "max": 30}],
        "modes": ["event", "target", "rank"],
        "help": "한국 종목 6자리 코드를 쉼표로 입력해요 (예: 005930, 000660)",
    },
    "ma_cross_up": {
        "slot": "signal",
        "name": "n일 이동평균선 상향 돌파",
        "title": "{n}일 이동평균선 상향 돌파",
        "params": [_num("n", "이동평균", "일", 2, 250, True)],
        "modes": ["event", "target", "rank"],
        "help": "종가가 n일 이동평균선을 아래에서 위로 넘은 날이에요 · 조건 충족 시 매매에서는 넘은 그날만 신호예요",
        "help_rebalance": "리밸런싱 방식에서는 종가가 n일 이동평균선 위에 있는 날이에요 · 조건 충족 시 매매에서는 넘은 그날만이에요",
    },
    "rsi_below": {
        "slot": "signal",
        "name": "RSI(n일) 기준값 미만",
        "title": "RSI({period}일) 기준값 {level} 미만",
        "params": [
            _num("period", "RSI 기간", "일", 2, 50, True),
            {**_num("level", "기준값", "", 5, 50, False), "range_name": "RSI 값"},
        ],
        "modes": ["event", "target", "rank"],
        "help": "RSI가 기준값보다 낮은 날이에요 · 낮을수록 신호가 강해요",
    },
    "high_breakout": {
        "slot": "signal",
        "name": "n일 최고가 돌파",
        "title": "{n}일 최고가 돌파",
        "params": [_num("n", "기간", "일", 5, 250, True)],
        "modes": ["event", "target", "rank"],
        "help": "종가가 직전 n일 고가의 최고치를 넘은 날이에요 · 조건 충족 시 매매에서는 넘은 그날만 신호예요",
        "help_rebalance": "리밸런싱 방식에서는 종가가 직전 n일 고가의 최고치 위에 있는 날이에요 · 조건 충족 시 매매에서는 넘은 그날만이에요",
    },
    "min_turnover": {
        "slot": "filter",
        "name": "거래대금 n억 원 이상",
        "title": "거래대금 {n}억 원 이상",
        "params": [_num("n", "거래대금", "억 원", 0.1, 100000, False)],
        "modes": ["event", "target", "rank"],
        "help": "그날 종가 × 거래량이 n억 원 이상인 종목만 남겨요",
    },
    "min_price": {
        "slot": "filter",
        "name": "주가 n원 이상",
        "title": "주가 {n}원 이상",
        "params": [_num("n", "주가", "원", 1, 10000000, True)],
        "modes": ["event", "target", "rank"],
        "help": "그날 종가가 n원 이상인 종목만 남겨요",
    },
    "top_n": {
        "slot": "select",
        "name": "신호 강도 상위 n종목",
        "title": "신호 강도 상위 {n}종목",
        "params": [_num("n", "종목 수", "종목", 1, 30, True)],
        "modes": ["event", "target", "rank"],
        "help": "신호가 강한 순으로 n종목까지 보유해요",
    },
    "next_open": {
        "slot": "buy",
        "name": "다음 날 시가 매수",
        "title": "다음 날 시가 매수",
        "params": [],
        "modes": ["event", "target", "rank"],
        "help": "신호가 나온 다음 거래일 시가에 매수해요",
    },
    "stop_loss": {
        "slot": "sell",
        "name": "손절 −n%",
        "title": "손절 −{pct}%",
        "params": [_num("pct", "손절", "%", 1, 50, False)],
        "modes": ["event", "rank"],
        "help": "종가가 매수가보다 n% 이상 내려가면 다음 날 시가에 매도해요",
    },
    "take_profit": {
        "slot": "sell",
        "name": "익절 +n%",
        "title": "익절 +{pct}%",
        "params": [_num("pct", "익절", "%", 1, 500, False)],
        "modes": ["event", "rank"],
        "help": "종가가 매수가보다 n% 이상 오르면 다음 날 시가에 매도해요",
    },
    "max_hold": {
        "slot": "sell",
        "name": "최대 보유 n거래일",
        "title": "최대 보유 {n}거래일",
        "params": [_num("n", "보유 기간", "거래일", 1, 250, True)],
        "modes": ["event", "rank"],
        "help": "매수한 날부터 n거래일이 지나면 다음 날 시가에 매도해요",
    },
    "ma_break_down": {
        "slot": "sell",
        "name": "n일 이동평균선 하향 이탈",
        "title": "{n}일 이동평균선 하향 이탈",
        "params": [_num("n", "이동평균", "일", 2, 250, True)],
        "modes": ["event", "rank"],
        "help": "종가가 n일 이동평균선 아래로 내려가면 다음 날 시가에 매도해요",
    },
    "equal": {
        "slot": "weight",
        "name": "동일 비중",
        "title": "동일 비중",
        "params": [],
        "modes": ["event", "target", "rank"],
        "help": "보유할 종목에 같은 금액을 배분해요",
    },
    "max_per_stock": {
        "slot": "weight",
        "name": "종목당 최대 비중 n%",
        "title": "종목당 최대 비중 {pct}%",
        "params": [_num("pct", "최대 비중", "%", 1, 100, False)],
        "modes": ["event", "target", "rank"],
        "help": "한 종목에 총자산의 n%보다 많이 넣지 않아요",
    },
    "rebalance_every": {
        "slot": "weight",
        "name": "리밸런싱 주기 n거래일",
        "title": "리밸런싱 주기 {n}거래일",
        "params": [
            _num("n", "주기", "거래일", 1, 250, True),
            {"key": "how", "label": "리밸런싱 방식", "kind": "choice", "options": [o["id"] for o in HOW_OPTIONS]},
        ],
        "modes": ["target", "rank"],
        "help": "n거래일마다 비중을 다시 맞추거나 순위를 다시 매겨요",
    },
}

# 하나만 놓을 수 있는 조건: 단계로(① · ④ · ⑤) 또는 조건 종류로(⑦ 비중 셋)
ONCE_STAGES = {"universe", "select", "buy"}
ONCE_PIECES = {"equal", "max_per_stock", "rebalance_every"}

NAMES = {
    "005930": "삼성전자",
    "000660": "SK하이닉스",
    "373220": "LG에너지솔루션",
    "207940": "삼성바이오로직스",
    "005380": "현대차",
    "000270": "기아",
    "068270": "셀트리온",
    "035420": "NAVER",
    "035720": "카카오",
    "005490": "POSCO홀딩스",
    "051910": "LG화학",
    "006400": "삼성SDI",
    "105560": "KB금융",
    "055550": "신한지주",
    "012330": "현대모비스",
    "028260": "삼성물산",
    "066570": "LG전자",
    "003550": "LG",
    "032830": "삼성생명",
    "086790": "하나금융지주",
    "069500": "KODEX 200",
    "247540": "에코프로비엠",
    "086520": "에코프로",
    "^KS11": "코스피",
}


def stock_name(symbol: str) -> str:
    return NAMES.get(symbol, symbol)


def stage_of(piece: str) -> str:
    return str(PIECES[piece]["slot"])


def num_text(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"  # 화면(JavaScript String(true))과 같게
    if not isinstance(v, (int, float)):
        return str(v)
    if float(v).is_integer():
        return f"{int(v):,}"
    return f"{v:,.6f}".rstrip("0").rstrip(".")


def symbols_short(syms: list[str]) -> str:
    """'삼성전자 외 9'(조건 카드 · 그래프 요약)."""
    if not syms:
        return ""
    first = stock_name(syms[0])
    return first if len(syms) == 1 else f"{first} 외 {len(syms) - 1}"


def symbols_text(syms: list[str]) -> str:
    """'삼성전자 · SK하이닉스 · 현대차 외 2'(입력 칸 아래)."""
    names = [stock_name(s) for s in syms[:3]]
    more = f" 외 {len(syms) - 3}" if len(syms) > 3 else ""
    return f"{' · '.join(names)}{more}"


def piece_title(item: dict[str, Any]) -> str:
    """조건 제목: 숫자 자리에 값('20일 최고가 돌파'), 빈칸이면 'n'. 종목은 '종목 직접 지정 · 삼성전자 외 9'."""
    spec = PIECES.get(item.get("piece", ""))
    if spec is None:
        return str(item.get("piece"))
    params = item.get("params") or {}
    if item["piece"] == "manual_list":
        syms = params.get("symbols") or []
        if not syms:
            return spec["title"]
        return f"{spec['title']} · {symbols_short(syms)}"
    out = spec["title"]
    if item["piece"] == "rsi_below" and params.get("level") is None:
        out = out.replace(" {level}", "")
    for p in spec["params"]:
        if p.get("kind") == "choice":
            continue
        v = params.get(p["key"])
        text = "n" if v is None else num_text(v)
        out = out.replace("{" + p["key"] + "}", text)
    if item["piece"] == "rebalance_every" and params.get("how") in HOW_NAMES:
        out = f"{out} · {HOW_NAMES[params['how']]}"
    return out


def has_batchim(word: str) -> bool:
    """마지막 글자에 받침이 있는가. 숫자는 읽는 소리로(0 영 · 1 일 · 3 삼 · 6 육 · 7 칠 · 8 팔),
    '%'(퍼센트)는 없음, 영어는 l · m · n · r(엘 · 엠 · 엔 · 알)만 있음. 끝의 괄호는 건너뛴다('… (3)'은 3).
    화면 쪽 web/src/graph/rules.ts와 같다."""
    last = word.strip().rstrip(" )]")[-1:] or "a"
    if "0" <= last <= "9":
        return last in "013678"
    code = ord(last)
    if 0xAC00 <= code <= 0xD7A3:
        return (code - 0xAC00) % 28 != 0
    return last.lower() in "lmnr"


def josa(word: str, pair: str) -> str:
    """word + 조사. pair는 '이/가' · '은/는' · '을/를' · '과/와' · '으로/로'."""
    a, b = pair.split("/")
    if pair == "으로/로":
        last = word.strip().rstrip(" )]")[-1:]
        code = ord(last) if last else 0
        rieul = (0xAC00 <= code <= 0xD7A3 and (code - 0xAC00) % 28 == 8) or last in "178"
        return word + (a if has_batchim(word) and not rieul else b)
    return word + (a if has_batchim(word) else b)
