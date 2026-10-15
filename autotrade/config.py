"""Settings: paths, time zones, fees, instruments and the daily schedule.

These are defaults. On first run they are copied into the settings table of data/autotrade.db,
which is the truth afterwards (the paper start date and amount, the US ETF ticker, the mode).
Environment variables can override the defaults before that first run:

  AUTOTRADE_DB                  database path (default <repo>/data/autotrade.db)
  AUTOTRADE_PAPER_START_DATE    YYYY-MM-DD; empty = the first check day
  AUTOTRADE_PAPER_START_AMOUNT  won (default 10,000,000)
  AUTOTRADE_US_ETF              US S&P 500 ETF ticker (default SPYM)
  AUTOTRADE_PAPER_SHARES        rule shares of the paper ledger, 'index_half=80,discovery_3y=20'
  AUTOTRADE_LIVE_SHARES         the same for the live ledger (default index_half=100,discovery_3y=0)

The AI runner (phase 2) reads these on every run:

  AUTOTRADE_AI_CALLS            '1' = real subscription CLI calls are allowed (the owner's go;
                                without it the runner asks nothing, only its heartbeat is written,
                                and the tasks wait)
  AUTOTRADE_CLAUDE_BIN          the CLI to run; unset or not found: `claude` on PATH, then
                                /usr/local/bin/claude, then the newest nvm install
                                (autotrade/ai/cli.py find_claude; cron's PATH has none of them)
  AUTOTRADE_AI_BUDGET           monthly token budget for the health screen (default 2,000,000)
  DART_API_KEY                  DART open API key (Korean filings); without it DART is 'no-key'
  AUTOTRADE_SECRETS_ENV         a KEY=VALUE file to read DART_API_KEY from when it is not set
                                (on the server: /home/ubuntu/dotclaude/secrets/.env). The tick
                                and the AI runner both need it: the watch lists Korean filings,
                                the runner reads their texts. Neither passes it to the CLI.

Live orders (phase 3, autotrade/PHASE3.md) — read by the tick only:

  AUTOTRADE_LIVE_ORDERS         '1' = this process may use the Toss account: it reads the account
                                and, while the stored mode is 'live', sends orders (the first of
                                the two keys, ops notes 안전). Without it the tick never calls Toss.
                                The Toss keys (TOSS_CLIENT_ID, TOSS_CLIENT_SECRET,
                                TOSS_ACCOUNT_NO) are read from the AUTOTRADE_SECRETS_ENV file
                                only, one line each, never from the environment.
  AUTOTRADE_TOSS_KEY_EXPIRES    YYYY-MM-DD, the Toss client key's expiry if WTS shows one (the API
                                has none: PHASE3.md 1.6); the health screen warns 14 days before
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
    # Dividends of the paper ledger (autotrade/domain/dividends.py): tax withheld at the source,
    # and the trading days from the ex-date to the pay date when the source gives no pay date.
    kr_dividend_tax: Decimal = Decimal("0.154")
    us_dividend_tax: Decimal = Decimal("0.15")
    kr_dividend_pay_lag: int = 3
    us_dividend_pay_lag: int = 2
    # How far back the daily dividend job looks for ex-dates (covers a week-long outage).
    dividend_lookback_days: int = 45
    # Each rule's target share of a ledger, in percent (PHASE2.md §1). Until the owner sets them
    # the paper ledger tests the example table's 80/20; the live ledger gives the AI rule nothing.
    rule_shares: Mapping[str, Mapping[str, Decimal]] = field(
        default_factory=lambda: {
            "paper": {"index_half": Decimal(80), "discovery_3y": Decimal(20)},
            "live": {"index_half": Decimal(100), "discovery_3y": Decimal(0)},
        }
    )
    # The AI rule '3년 발굴' (PHASE2.md, autotrade/ai/).
    ai_calls_enabled: bool = False  # AUTOTRADE_AI_CALLS=1
    claude_bin: str | None = None  # AUTOTRADE_CLAUDE_BIN; None = look for it (find_claude)
    # tokens; over it the health screen shows a yellow todo. Measured 2026-10-15 on the 5.5 models:
    # a usual month ~480,000, a discovery month ~1,660,000 (the discovery alone ~1,180,000).
    ai_monthly_budget: int = 2_000_000
    ai_max_attempts: int = 3  # a task that failed this often waits for a person
    dart_api_key: str | None = None
    edgar_user_agent: str = "portfolio-dashboard/1.0 (contact: admin@jsyoo.dev)"
    discovery_max_picks: int = 20
    # Price shocks against the same market's index (T28): a day at -8% or 20 trading days at
    # -20%; once set off, the stock is not counted again for 20 trading days.
    shock_day: Decimal = Decimal("-0.08")
    shock_20d: Decimal = Decimal("-0.20")
    shock_window: int = 20
    # US stocks (D36): 22% on the year's foreign gains above the 2,500,000 won deduction.
    us_gains_tax: Decimal = Decimal("0.22")
    us_gains_deduction: Decimal = Decimal("2500000")
    # Live orders (phase 3, PHASE3.md 2.3-2.5).
    live_orders: bool = False  # AUTOTRADE_LIVE_ORDERS=1, the first key
    secrets_env: Path | None = None  # AUTOTRADE_SECRETS_ENV: the Toss keys are read from it
    toss_key_expires: date | None = None  # AUTOTRADE_TOSS_KEY_EXPIRES
    # A limit order's cap over the current price (buys) or under it (sells); fills are at market.
    live_limit_slippage: Decimal = Decimal("0.005")
    # Orders at or above this (won; dollars valued in won) are not sent: Toss asks a separate
    # confirmation from 100,000,000 won, which the engine never gives (a manual action instead).
    live_max_order_krw: Decimal = Decimal("100000000")
    # How old the account snapshot and the Toss check may be for the check, the preview and
    # turning live on.
    broker_max_age: timedelta = timedelta(minutes=15)
    # The tick's Toss sync while both markets are closed and nothing of ours is moving (nights,
    # weekends, holidays; engine/live.py fast_sync_reason): every 30 minutes, not every tick.
    # Meanwhile a look this much older than broker_max_age still counts (sync_max_age).
    broker_sync_slow: timedelta = timedelta(minutes=30)
    # A won and a dollar change in opposite directions is a conversion when its rate is within
    # this of the market rate (the owner converts in the app, PHASE3.md 2.4).
    live_fx_tolerance: Decimal = Decimal("0.03")
    # A broker order whose outcome is unknown is sent again with the same client order id only
    # within this time; Toss keeps the key 10 minutes (PHASE3.md 1.7).
    resend_window: timedelta = timedelta(minutes=9)

    @property
    def toss_dir(self) -> Path:
        """Where the tick keeps the Toss token: 0700, ignored by version control, hidden from the
        web service (deploy/autotrade.service InaccessiblePaths)."""
        return self.db_path.parent / "autotrade-toss"


def parse_shares(text: str) -> dict[str, Decimal]:
    """'index_half=80,discovery_3y=20' -> percent per rule; they must add up to 100."""
    out: dict[str, Decimal] = {}
    for part in text.split(","):
        rule, sep, pct = part.partition("=")
        if not sep or not rule.strip():
            raise ValueError(f"not a rule share: {part!r} (rule=percent)")
        out[rule.strip()] = Decimal(pct.strip())
    if sum(out.values(), Decimal(0)) != Decimal(100) or any(v < 0 for v in out.values()):
        raise ValueError(f"rule shares must be >= 0 and add up to 100: {text!r}")
    return out


def read_env_key(path: Path, name: str) -> str | None:
    """One KEY=VALUE line of an env file (quotes stripped). Only that key is read."""
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return None
    for line in lines:
        key, sep, value = line.strip().removeprefix("export ").partition("=")
        if sep and key.strip() == name:
            return value.strip().strip("'\"") or None
    return None


def load_config(env: Mapping[str, str] | None = None) -> Config:
    source = os.environ if env is None else env
    cfg = Config()
    db = source.get("AUTOTRADE_DB")
    start_date = source.get("AUTOTRADE_PAPER_START_DATE")
    amount = source.get("AUTOTRADE_PAPER_START_AMOUNT")
    us_etf = source.get("AUTOTRADE_US_ETF")
    shares = dict(cfg.rule_shares)
    for ledger, var in (("paper", "AUTOTRADE_PAPER_SHARES"), ("live", "AUTOTRADE_LIVE_SHARES")):
        if source.get(var):
            shares[ledger] = parse_shares(source[var])
    dart = source.get("DART_API_KEY") or None
    secrets_file = source.get("AUTOTRADE_SECRETS_ENV")
    if dart is None and secrets_file:
        dart = read_env_key(Path(secrets_file), "DART_API_KEY")
    budget = source.get("AUTOTRADE_AI_BUDGET")
    expires = source.get("AUTOTRADE_TOSS_KEY_EXPIRES")
    return Config(
        db_path=Path(db) if db else cfg.db_path,
        paper_start_date=date.fromisoformat(start_date) if start_date else None,
        paper_start_amount=Decimal(amount) if amount else cfg.paper_start_amount,
        us_etf_ticker=us_etf or cfg.us_etf_ticker,
        rule_shares=shares,
        ai_calls_enabled=source.get("AUTOTRADE_AI_CALLS") == "1",
        claude_bin=source.get("AUTOTRADE_CLAUDE_BIN") or None,
        ai_monthly_budget=int(budget) if budget else cfg.ai_monthly_budget,
        dart_api_key=dart,
        live_orders=source.get("AUTOTRADE_LIVE_ORDERS") == "1",
        secrets_env=Path(secrets_file) if secrets_file else None,
        toss_key_expires=date.fromisoformat(expires) if expires else None,
    )
