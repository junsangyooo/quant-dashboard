"""가치 · 재무 값(엔진 v2 · TASKS T-23 · DATA-CATALOG 2-3-3).

- 재무 행은 `DartStore.financial_rows`가 돌려준 것(연결 우선 · 접수일 다음 거래일부터 · R-J9)을 받아요.
- 흐름 계정(매출액 · 영업이익 · 당기순이익)은 최근 4분기 합(TTM). 분기 금액: 1분기 · 반기 · 3분기 보고서는
  `amount`(3개월), 사업보고서는 연간 − (1 ~ 3분기)로 4분기를 만들어요.
- 시가총액 = 토스 수정 종가 × DART 주식 총수 × 수정 계수(수정 전 종가 ÷ 수정 종가). 분할 · 무상증자로 주식 수가
  바뀐 뒤의 수정 종가도 그 시점 주식 수와 맞게 돼요(주식 수 근사 칩 · Q-T5).
"""

from __future__ import annotations

from typing import Any

QUARTER = {"11013": 1, "11012": 2, "11014": 3, "11011": 4}
FLOWS = ("매출액", "영업이익", "당기순이익")


def quarterly(rows: list[dict[str, Any]], account: str) -> dict[tuple[int, int], float]:
    """(연도, 분기) → 그 분기 금액."""
    raw: dict[tuple[int, int], float] = {}
    for r in rows:
        if r["account"] == account and r.get("amount") is not None and r["reprt"] in QUARTER:
            raw[(int(r["year"]), QUARTER[r["reprt"]])] = float(r["amount"])
    out: dict[tuple[int, int], float] = {}
    for (y, q), v in raw.items():
        if q < 4:
            out[(y, q)] = v
        elif all((y, k) in raw for k in (1, 2, 3)):
            out[(y, 4)] = v - sum(raw[(y, k)] for k in (1, 2, 3))
    return out


def _prev(y: int, q: int) -> tuple[int, int]:
    return (y, q - 1) if q > 1 else (y - 1, 4)


def ttm(rows: list[dict[str, Any]], account: str, upto: tuple[int, int] | None = None) -> float | None:
    """최근 4분기 합. 4분기가 이어서 다 있어야 해요."""
    qs = quarterly(rows, account)
    if not qs:
        return None
    y, q = upto or max(qs)
    total = 0.0
    for _ in range(4):
        if (y, q) not in qs:
            return None
        total += qs[(y, q)]
        y, q = _prev(y, q)
    return total


def latest(rows: list[dict[str, Any]], account: str) -> float | None:
    best = None
    for r in rows:
        if r["account"] == account and r.get("amount") is not None and r["reprt"] in QUARTER:
            key = (int(r["year"]), QUARTER[r["reprt"]])
            if best is None or key > best[0]:
                best = (key, float(r["amount"]))
    return best[1] if best else None


def market_cap(close_adj: float, shares: float | None, factor: float = 1.0) -> float | None:
    """억 원. factor = 수정 전 종가 ÷ 수정 종가."""
    if not shares or close_adj <= 0:
        return None
    return close_adj * factor * shares / 1e8


def _state(now: float | None, before: float | None) -> str | None:
    if now is None:
        return None
    if before is None:
        return "profit" if now > 0 else "loss"
    if before <= 0 < now:
        return "turn_profit"
    if before > 0 >= now:
        return "turn_loss"
    return "profit" if now > 0 else "loss"


def _growth(now: float | None, before: float | None) -> float | None:
    if now is None or before is None or before <= 0:
        return None  # 전년 적자면 값 없음
    return (now / before - 1) * 100


def values(rows: list[dict[str, Any]], close_adj: float, shares: float | None, factor: float = 1.0,
           dps: float | None = None) -> dict[str, Any]:
    """그날 쓸 수 있는 가치 · 재무 값. 값이 없으면 None(R-J1)."""
    cap = market_cap(close_adj, shares, factor)
    sales, op, net = (ttm(rows, a) for a in FLOWS)
    equity, debt = latest(rows, "자본총계"), latest(rows, "부채총계")
    won = cap * 1e8 if cap is not None else None
    out: dict[str, Any] = {
        "market_cap": cap,
        "per": won / net if won is not None and net and net > 0 else None,  # 적자는 값 없음
        "pbr": won / equity if won is not None and equity and equity > 0 else None,
        "psr": won / sales if won is not None and sales and sales > 0 else None,
        "roe": net / equity * 100 if net is not None and equity and equity > 0 else None,
        "op_margin": op / sales * 100 if op is not None and sales and sales > 0 else None,
        "debt_ratio": debt / equity * 100 if debt is not None and equity and equity > 0 else None,
        "dividend_yield": dps / (close_adj * factor) * 100 if dps and close_adj > 0 else None,
    }
    qs_sales = quarterly(rows, "매출액")
    if qs_sales:
        y, q = max(qs_sales)
        out["sales_growth"] = _growth(qs_sales.get((y, q)), qs_sales.get((y - 1, q)))
    else:
        out["sales_growth"] = None
    state: dict[str, str | None] = {}
    for key, acct in (("op_income", "영업이익"), ("net_income", "당기순이익")):
        qs = quarterly(rows, acct)
        if qs:
            y, q = max(qs)
            state[key] = _state(qs.get((y, q)), qs.get((y - 1, q)))
            out[f"profit_growth_{key}"] = _growth(qs.get((y, q)), qs.get((y - 1, q)))
        else:
            state[key] = None
            out[f"profit_growth_{key}"] = None
    out["profit_state"] = state
    annual = {int(r["year"]): float(r["amount"]) for r in rows
              if r["account"] == "매출액" and r["reprt"] == "11011" and r.get("amount") is not None}
    if annual:
        last = max(annual)
        if all(last - k in annual for k in range(4)) and annual[last - 3] > 0:
            out["sales_growth_3y"] = ((annual[last] / annual[last - 3]) ** (1 / 3) - 1) * 100
        else:
            out["sales_growth_3y"] = None
    else:
        out["sales_growth_3y"] = None
    return out
