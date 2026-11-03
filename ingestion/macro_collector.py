"""
AlphaMind AI — Global Macro & FX Data Collector
Collects global interest rates, currency pairs, volatility indices, and FedWatch probabilities
for the 6 regions: US, TW, JP, KR, HK, EU.
"""

from datetime import datetime
from typing import Dict, Optional
from alphamind.engine.macro_engine import (
    MacroRegion,
    RateHikeExpectation,
    RegionalRatesAndFX,
)


class GlobalMacroCollector:
    """全球總經與市場情緒資料收集器"""

    @staticmethod
    def get_latest_snapshot(
        dxy_override: Optional[float] = None,
        jpy_shock_pct: Optional[float] = None,
    ) -> tuple[Dict[MacroRegion, RegionalRatesAndFX], Dict[MacroRegion, RateHikeExpectation], float]:
        """產出當前六大區域總經快照（支援即時注入或模擬參數）"""
        dxy = dxy_override if dxy_override is not None else 103.8
        jpy_chg = jpy_shock_pct if jpy_shock_pct is not None else -0.30

        rates_fx = {
            MacroRegion.US: RegionalRatesAndFX(
                region=MacroRegion.US,
                central_bank_policy_rate=4.75,
                yield_2y=4.15,
                yield_10y=4.38,
                fx_rate=1.0,
                fx_change_pct_1d=0.10,
                volatility_index=15.8,
                term_structure_ratio=0.96,
            ),
            MacroRegion.TW: RegionalRatesAndFX(
                region=MacroRegion.TW,
                central_bank_policy_rate=2.00,
                yield_2y=1.30,
                yield_10y=1.58,
                fx_rate=32.15,
                fx_change_pct_1d=0.20,
                volatility_index=16.2,
                term_structure_ratio=0.98,
            ),
            MacroRegion.JP: RegionalRatesAndFX(
                region=MacroRegion.JP,
                central_bank_policy_rate=0.25,
                yield_2y=0.48,
                yield_10y=1.05,
                fx_rate=153.20,
                fx_change_pct_1d=jpy_chg,
                volatility_index=22.4,
                term_structure_ratio=1.02,
            ),
            MacroRegion.KR: RegionalRatesAndFX(
                region=MacroRegion.KR,
                central_bank_policy_rate=3.25,
                yield_2y=2.90,
                yield_10y=3.05,
                fx_rate=1375.0,
                fx_change_pct_1d=0.35,
                volatility_index=18.5,
                term_structure_ratio=1.01,
            ),
            MacroRegion.HK: RegionalRatesAndFX(
                region=MacroRegion.HK,
                central_bank_policy_rate=4.75,
                yield_2y=3.75,
                yield_10y=3.95,
                fx_rate=7.77,
                fx_change_pct_1d=0.01,
                volatility_index=21.8,
                term_structure_ratio=1.03,
            ),
            MacroRegion.EU: RegionalRatesAndFX(
                region=MacroRegion.EU,
                central_bank_policy_rate=3.25,
                yield_2y=2.10,
                yield_10y=2.30,
                fx_rate=1.088,
                fx_change_pct_1d=-0.10,
                volatility_index=17.2,
                term_structure_ratio=0.97,
            ),
        }

        expectations = {
            MacroRegion.US: RateHikeExpectation(
                region=MacroRegion.US,
                next_meeting_date="2026-12-16",
                prob_cut=0.80,
                prob_hold=0.20,
                prob_hike=0.0,
                implied_terminal_rate=3.50,
            ),
            MacroRegion.EU: RateHikeExpectation(
                region=MacroRegion.EU,
                next_meeting_date="2026-12-12",
                prob_cut=0.70,
                prob_hold=0.30,
                prob_hike=0.0,
                implied_terminal_rate=2.50,
            ),
            MacroRegion.JP: RateHikeExpectation(
                region=MacroRegion.JP,
                next_meeting_date="2026-12-19",
                prob_cut=0.0,
                prob_hold=0.45,
                prob_hike=0.55,
                implied_terminal_rate=0.75,
            ),
        }

        return rates_fx, expectations, dxy
