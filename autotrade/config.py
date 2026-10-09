"""Settings: paths, time zones, fees, instruments and the daily schedule.

These are defaults. On first run they are copied into the settings table of data/autotrade.db,
which is the truth afterwards (the paper start date and amount, the US ETF ticker, the mode).
Environment variables can override the defaults before that first run:

  AUTOTRADE_DB                  database path (default <repo>/data/autotrade.db)
  AUTOTRADE_PAPER_START_DATE    YYYY-MM-DD; empty = the first check day
  AUTOTRADE_PAPER_START_AMOUNT  won (default 10,000,000)
  AUTOTRADE_US_ETF              US S&P 500 ETF ticker (default SPYM)
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, time, timedelta
from decimal import Decimal
from pathlib import Path

from autotrade.domain.money import FeeRates
from autotrade.domain.stages import StageTimes

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = REPO_ROOT / "data" / "autotrade.db"

# The SPDR Portfolio S&P 500 ETF was ticker SPLG until 2025-10-30 and trades as SPYM since
# 2025-10-31 (same fund, renamed by State Street; OCC memo 57498, MIAX alert 2025-10-30).
# ops notes names SPLG as the candidate; SPLG no longer quotes, so the default is SPYM.
# Whether Toss sells it is still to be checked (ops notes).
DEFAULT_US_ETF = "SPYM"
DEFAULT_KR_ETF = "069500"  # KODEX 200


@dataclass(frozen=True)
class Config:
    db_path: Path = DEFAULT_DB_PATH
    fees: FeeRates = field(default_factory=FeeRates)
    stage_times: StageTimes = field(default_factory=StageTimes)
    check_time: time = time(8, 30)
    retry_time: time = time(9, 30)
    snapshot_time: time = time(16, 0)
    threshold: Decimal = Decimal("0.02")
    fx_step_krw: Decimal = Decimal("1000")
    kr_etf_ticker: str = DEFAULT_KR_ETF
    kr_etf_name: str = "KOSPI200 ETF"
    us_etf_ticker: str = DEFAULT_US_ETF
    us_etf_name: str = "S&P 500 ETF"
    paper_start_amount: Decimal = Decimal("10000000")
    paper_start_date: date | None = None
    # When a session's close is expected to be downloadable.
    kr_publication_lag: timedelta = timedelta(minutes=20)
    us_publication_lag: timedelta = timedelta(hours=1)
    # A rate older than this, counted in weekday hours, is stale for a check.
    fx_max_age: timedelta = timedelta(hours=24)
    # A paper conversion uses a quote at most this old at the stage time.
    fx_fill_max_age: timedelta = timedelta(minutes=60)
    bar_lookback_days: int = 14


def load_config(env: Mapping[str, str] | None = None) -> Config:
    source = os.environ if env is None else env
    cfg = Config()
    db = source.get("AUTOTRADE_DB")
    start_date = source.get("AUTOTRADE_PAPER_START_DATE")
    amount = source.get("AUTOTRADE_PAPER_START_AMOUNT")
    us_etf = source.get("AUTOTRADE_US_ETF")
    return Config(
        db_path=Path(db) if db else cfg.db_path,
        paper_start_date=date.fromisoformat(start_date) if start_date else None,
        paper_start_amount=Decimal(amount) if amount else cfg.paper_start_amount,
        us_etf_ticker=us_etf or cfg.us_etf_ticker,
    )
