"""Period keys of the metric table: quarters, months, fiscal quarters and years.

  2026Q2        calendar quarter          (KR filings, most US companies)
  FY2026Q4      a company's fiscal quarter (Broadcom 'FQ4', Modine 'FY27 Q1' -> FY2027Q1)
  2026-08       month                     (TSMC monthly revenue)
  FY2027        fiscal or calendar year   (guidance, annual FCF)

Keys sort in time order within one kind. 'previous' is the period before (quarter -> quarter,
month -> month, year -> year) and 'year_ago' the same period one year earlier.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_QUARTER = re.compile(r"^(FY)?(\d{4})Q([1-4])$")
_MONTH = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
_YEAR = re.compile(r"^FY(\d{4})$")


class PeriodError(ValueError):
    pass


@dataclass(frozen=True, order=True)
class Period:
    kind: str  # 'quarter' | 'fquarter' | 'month' | 'year'
    year: int
    sub: int  # quarter 1-4, month 1-12, 0 for a year

    @property
    def key(self) -> str:
        if self.kind == "quarter":
            return f"{self.year}Q{self.sub}"
        if self.kind == "fquarter":
            return f"FY{self.year}Q{self.sub}"
        if self.kind == "month":
            return f"{self.year}-{self.sub:02d}"
        return f"FY{self.year}"

    @property
    def family(self) -> str:
        """Periods of one family can be compared ('quarter' and 'fquarter' are different)."""
        return self.kind

    def previous(self) -> Period:
        if self.kind in ("quarter", "fquarter"):
            if self.sub == 1:
                return Period(self.kind, self.year - 1, 4)
            return Period(self.kind, self.year, self.sub - 1)
        if self.kind == "month":
            if self.sub == 1:
                return Period(self.kind, self.year - 1, 12)
            return Period(self.kind, self.year, self.sub - 1)
        return Period(self.kind, self.year - 1, 0)

    def year_ago(self) -> Period:
        return Period(self.kind, self.year - 1, self.sub)


def parse_period(key: str) -> Period:
    m = _QUARTER.match(key)
    if m:
        return Period("fquarter" if m.group(1) else "quarter", int(m.group(2)), int(m.group(3)))
    m = _MONTH.match(key)
    if m:
        return Period("month", int(m.group(1)), int(m.group(2)))
    m = _YEAR.match(key)
    if m:
        return Period("year", int(m.group(1)), 0)
    raise PeriodError(f"not a period key: {key!r} (2026Q2, FY2026Q4, 2026-08, FY2027)")


def is_period(key: str) -> bool:
    try:
        parse_period(key)
    except PeriodError:
        return False
    return True
