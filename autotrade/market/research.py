"""Public data for judging picks (phase 2): adjusted closes and valuation ratios.

- Adjusted closes (dividends and splits folded in) from Yahoo, by Yahoo symbol, so the indexes
  (069500.KS, SPY) need no instrument row. Price shocks (T28) and scoring (T24 score.py) use
  them. They are never stored: Yahoo rewrites the past when a dividend comes, which is right for
  returns and wrong for a ledger (raw closes live in market_prices).
- Valuation ratios from Yahoo's quote summary: forward PER, trailing PER, PBR. T24 flagged a
  doubtful forward PER for a Korean stock, so the buy confirmation sees the number with its
  source, and the AI decides.
- What a symbol is (Yahoo's quoteType: 'EQUITY', 'ETF', 'MUTUALFUND' ...): the quarterly
  discovery only adds companies (a Korean ETF would be charged the stock sale tax, and an index
  ETF is where the rule parks its money).
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Protocol

from autotrade.domain.money import dec
from autotrade.market.sources import import_yfinance, with_retries

Series = list[tuple[date, Decimal]]
VALUATION_KEYS = {"per_fwd": "forwardPE", "per": "trailingPE", "pbr": "priceToBook"}


class AdjustedSource(Protocol):
    name: str

    def fetch_adjusted(self, symbol: str, start: date, end: date) -> Series: ...


class ValuationSource(Protocol):
    name: str

    def fetch_valuation(self, symbol: str) -> dict[str, Decimal]: ...

    def fetch_quote_type(self, symbol: str) -> str: ...


def _number(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        as_float = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(as_float) or math.isinf(as_float):
        return None
    return dec(as_float)


class YahooAdjustedSource:
    name = "yfinance-adjusted"

    def __init__(self, yf_module: Any | None = None, attempts: int = 2) -> None:
        self._yf = yf_module
        self.attempts = attempts

    def _module(self) -> Any:
        if self._yf is None:
            self._yf = import_yfinance()
        return self._yf

    def fetch_adjusted(self, symbol: str, start: date, end: date) -> Series:
        def fetch() -> Series:
            frame = (
                self._module()
                .Ticker(symbol)
                .history(
                    start=start.isoformat(),
                    end=(end + timedelta(days=1)).isoformat(),
                    interval="1d",
                    auto_adjust=True,
                    actions=False,
                )
            )
            out: Series = []
            if frame is None or len(frame) == 0:
                return out
            for idx, row in frame.iterrows():
                close = _number(row["Close"])
                if close is not None and close > 0:
                    out.append((idx.date(), close))
            return out

        return with_retries(fetch, self.attempts)


class YahooValuationSource:
    name = "yfinance-info"

    def __init__(self, yf_module: Any | None = None, attempts: int = 2) -> None:
        self._yf = yf_module
        self.attempts = attempts

    def _module(self) -> Any:
        if self._yf is None:
            self._yf = import_yfinance()
        return self._yf

    def fetch_valuation(self, symbol: str) -> dict[str, Decimal]:
        def fetch() -> dict[str, Decimal]:
            info = self._module().Ticker(symbol).info or {}
            out: dict[str, Decimal] = {}
            for key, field in VALUATION_KEYS.items():
                value = _number(info.get(field))
                if value is not None:
                    out[key] = value
            return out

        return with_retries(fetch, self.attempts)

    def fetch_quote_type(self, symbol: str) -> str:
        def fetch() -> str:
            kind = (self._module().Ticker(symbol).info or {}).get("quoteType")
            if not isinstance(kind, str) or not kind:
                raise ValueError(f"{symbol}: no quoteType")
            return kind.upper()

        return with_retries(fetch, self.attempts)
