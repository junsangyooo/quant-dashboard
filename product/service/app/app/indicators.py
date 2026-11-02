"""일봉 지표(엔진 v2 · TASKS T-23). v1 엔진의 식(이동평균 · Wilder RSI · 직전 n일 최고가)은 글자 그대로 옮겼어요.

모든 지표는 날짜 순 배열이고, 값이 없는 자리는 None이에요(R-J1 '값 없음').
"""

from __future__ import annotations

import bisect
import math
from typing import Any


class Series:
    def __init__(self, bars: list[dict[str, Any]]) -> None:
        bars = sorted(bars, key=lambda b: b["d"])
        self.d = [b["d"] for b in bars]
        self.o = [float(b["o"] or b["c"]) for b in bars]
        self.h = [float(b["h"] or b["c"]) for b in bars]
        self.l = [float(b["l"] or b["c"]) for b in bars]
        self.c = [float(b["c"]) for b in bars]
        self.v = [float(b.get("v") or 0) for b in bars]
        self.idx = {d: i for i, d in enumerate(self.d)}
        self._cache: dict[tuple[Any, ...], list[float | None]] = {}

    def __len__(self) -> int:
        return len(self.c)

    def close_on_or_before(self, d: str) -> float | None:
        i = bisect.bisect_right(self.d, d) - 1
        return None if i < 0 else self.c[i]

    def index_on_or_before(self, d: str) -> int | None:
        i = bisect.bisect_right(self.d, d) - 1
        return None if i < 0 else i

    def last_date_on_or_before(self, d: str) -> str | None:
        i = self.index_on_or_before(d)
        return None if i is None else self.d[i]

    def _memo(self, key: tuple[Any, ...], make: Any) -> list[float | None]:
        if key not in self._cache:
            self._cache[key] = make()
        return self._cache[key]

    # ── v1 식 그대로 ────────────────────────────────────────────────────────

    def sma(self, n: int) -> list[float | None]:
        def make() -> list[float | None]:
            out: list[float | None] = [None] * len(self.c)
            total = 0.0
            for i, c in enumerate(self.c):
                total += c
                if i >= n:
                    total -= self.c[i - n]
                if i >= n - 1:
                    out[i] = total / n
            return out

        return self._memo(("sma", n), make)

    def rsi(self, period: int) -> list[float | None]:
        """Wilder RSI."""

        def make() -> list[float | None]:
            out: list[float | None] = [None] * len(self.c)
            if len(self.c) > period:
                gains = losses = 0.0
                for i in range(1, period + 1):
                    ch = self.c[i] - self.c[i - 1]
                    gains += max(ch, 0)
                    losses += max(-ch, 0)
                ag, al = gains / period, losses / period
                out[period] = _rsi(ag, al)
                for i in range(period + 1, len(self.c)):
                    ch = self.c[i] - self.c[i - 1]
                    ag = (ag * (period - 1) + max(ch, 0)) / period
                    al = (al * (period - 1) + max(-ch, 0)) / period
                    out[i] = _rsi(ag, al)
            return out

        return self._memo(("rsi", period), make)

    def prior_high(self, n: int) -> list[float | None]:
        """직전 n일(오늘 빼고) 고가의 최고치."""

        def make() -> list[float | None]:
            out: list[float | None] = [None] * len(self.c)
            for i in range(n, len(self.c)):
                out[i] = max(self.h[i - n : i])
            return out

        return self._memo(("ph", n), make)

    # ── v2에서 더한 것 ──────────────────────────────────────────────────────

    def prior_low(self, n: int) -> list[float | None]:
        def make() -> list[float | None]:
            out: list[float | None] = [None] * len(self.c)
            for i in range(n, len(self.c)):
                out[i] = min(self.l[i - n : i])
            return out

        return self._memo(("pl", n), make)

    def ema(self, n: int, src: list[float | None] | None = None) -> list[float | None]:
        values = src if src is not None else self.c

        def make() -> list[float | None]:
            out: list[float | None] = [None] * len(values)
            k = 2 / (n + 1)
            prev: float | None = None
            count = 0
            seed = 0.0
            for i, v in enumerate(values):
                if v is None:
                    continue
                if prev is None:
                    count += 1
                    seed += v
                    if count == n:
                        prev = seed / n
                        out[i] = prev
                    continue
                prev = v * k + prev * (1 - k)
                out[i] = prev
            return out

        if src is not None:
            return make()
        return self._memo(("ema", n), make)

    def macd(self, fast: int, slow: int, signal: int) -> tuple[list[float | None], list[float | None]]:
        f, s = self.ema(fast), self.ema(slow)
        line = [a - b if a is not None and b is not None else None for a, b in zip(f, s, strict=True)]
        return line, self.ema(signal, line)

    def bollinger(self, n: int, k: float) -> tuple[list[float | None], list[float | None]]:
        def make(sign: int) -> list[float | None]:
            mid = self.sma(n)
            out: list[float | None] = [None] * len(self.c)
            for i in range(n - 1, len(self.c)):
                m = mid[i]
                if m is None:
                    continue
                w = self.c[i - n + 1 : i + 1]
                sd = math.sqrt(sum((x - m) ** 2 for x in w) / n)
                out[i] = m + sign * k * sd
            return out

        return self._memo(("bbu", n, k), lambda: make(1)), self._memo(("bbl", n, k), lambda: make(-1))

    def ret(self, i: int, n: int) -> float | None:
        """n일 수익률(%)."""
        if i - n < 0 or self.c[i - n] <= 0:
            return None
        return (self.c[i] / self.c[i - n] - 1) * 100

    def change_pct(self, i: int) -> float | None:
        return self.ret(i, 1)

    def gap_pct(self, i: int) -> float | None:
        if i < 1 or self.c[i - 1] <= 0:
            return None
        return (self.o[i] / self.c[i - 1] - 1) * 100

    def from_high_52w(self, i: int) -> float | None:
        lo = max(0, i - 249)
        top = max(self.h[lo : i + 1])
        return (self.c[i] / top - 1) * 100 if top > 0 else None

    def turnover(self, i: int) -> float:
        """거래대금(억 원) = 종가 × 거래량(근사)."""
        return self.c[i] * self.v[i] / 1e8

    def volume_ratio(self, i: int, n: int) -> float | None:
        if i - n < 0:
            return None
        avg = sum(self.v[i - n : i]) / n
        return self.v[i] / avg * 100 if avg > 0 else None

    def volatility(self, i: int, n: int) -> float | None:
        """n일 일간 수익률 표준편차(연 환산 · %)."""
        if i - n < 0:
            return None
        rets = [self.c[j] / self.c[j - 1] - 1 for j in range(i - n + 1, i + 1) if self.c[j - 1] > 0]
        if len(rets) < 2:
            return None
        m = sum(rets) / len(rets)
        sd = math.sqrt(sum((r - m) ** 2 for r in rets) / (len(rets) - 1))
        return sd * math.sqrt(252) * 100

    def streak(self, i: int, up: bool) -> int:
        n = 0
        j = i
        while j >= 1 and ((self.c[j] > self.c[j - 1]) if up else (self.c[j] < self.c[j - 1])):
            n += 1
            j -= 1
        return n


def _rsi(ag: float, al: float) -> float:
    if al == 0:
        return 100.0 if ag > 0 else 50.0
    rs = ag / al
    return 100.0 - 100.0 / (1.0 + rs)
