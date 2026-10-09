"""'지수 반반': KOSPI200 ETF and a US-listed S&P 500 ETF, 50:50 in won, ±2%p band.

Vault 5-설계/파이프라인.md '장투'. Phase 1 gives it 100% of the ledger (pipeline: 장투 지금 100%).
"""

from __future__ import annotations

from decimal import Decimal

from autotrade.domain.instruments import Instrument
from autotrade.rules.model import RuleDef, RuleTarget

RULE_ID = "index_half"
HALF = Decimal("0.5")


def index_half(kr_etf: Instrument, us_etf: Instrument, threshold: Decimal) -> RuleDef:
    return RuleDef(
        rule_id=RULE_ID,
        name="지수 반반",
        kind="fixed",
        asset_share=Decimal("1"),
        targets=(
            RuleTarget(kr_etf.instrument_id, HALF),
            RuleTarget(us_etf.instrument_id, HALF),
        ),
        threshold=threshold,
        check_time="08:30",
        display={
            "kind": "tiles",
            "what": {"instruments": [kr_etf.instrument_id, us_etf.instrument_id], "basis": "krw"},
            "when": {"time": "08:30", "days": "weekdays", "tz": "KST"},
            "condition": {"threshold_pp": str(threshold * 100)},
            "action": {"stages": ["sell", "fx", "buy"]},
            # Measured, not expected: T09, after tax, one year, 100% stocks (파이프라인.md 장투).
            "measured": {
                "median": "9.5",
                "mean": "11.9",
                "bad_year": "-13.6",
                "worst": "-33.5",
                "period": "2015-2025",
                "after_tax": True,
                "source": "T09",
            },
        },
    )
