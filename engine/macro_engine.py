"""
AlphaMind AI — Global Macro, Rates, FX & Sentiment Engine
Analyzes macroeconomic indicators, yield curves, interest rate expectations, FX dynamics,
and volatility spillovers across 6 major economic regions: US, TW, JP, KR, HK, EU.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
import numpy as np


class MacroRegion(str, Enum):
    US = "US"
    TW = "TW"
    JP = "JP"
    KR = "KR"
    HK = "HK"
    EU = "EU"


class MonetaryPolicyStance(str, Enum):
    EASING = "EASING"                         # 降息寬鬆循環
    TIGHTENING = "TIGHTENING"                 # 升息緊縮循環
    RESTRICTIVE_HOLD = "RESTRICTIVE_HOLD"     # 高利率限制性常態
    NEUTRAL = "NEUTRAL"                       # 中性政策


@dataclass(frozen=True)
class RegionalRatesAndFX:
    region: MacroRegion
    central_bank_policy_rate: float           # 基準政策利率 (%)
    yield_2y: Optional[float]                 # 2 年期公債殖利率 (%)
    yield_10y: Optional[float]                # 10 年期公債殖利率 (%)
    fx_rate: float                            # 對美元匯率 (USD/TWD, USD/JPY, USD/KRW, USD/HKD, EUR/USD)
    fx_change_pct_1d: float                   # 單日匯率升貶幅 (%)
    volatility_index: float                   # 波動率 (US: VIX, EU: VSTOXX, JP: VNKY, KR: VKOSPI, TW: TAIWAVIX, HK: VHSI)
    term_structure_ratio: Optional[float] = 1.0 # 短期/長期波動率比值 (e.g. VIX9D / VIX)


@dataclass(frozen=True)
class RateHikeExpectation:
    region: MacroRegion
    next_meeting_date: str
    prob_cut: float                           # 降息隱含機率 (0.0 ~ 1.0)
    prob_hold: float                          # 維持機率
    prob_hike: float                          # 升息隱含機率
    implied_terminal_rate: Optional[float]    # 隱含終點利率 (%)


@dataclass
class GlobalMacroCompositeAnalysis:
    timestamp: datetime
    dxy_index: float                          # 美元指數
    us_yield_spread_10y_2y: float             # 美債 10Y - 2Y 利差
    is_yield_curve_inverted: bool             # 是否處於殖利率倒掛
    is_bear_steepening: bool                  # 是否為熊市陡峭化 (長端利率暴衝)
    carry_trade_unwind_risk: float            # 日圓套利平倉風險 (0 ~ 100)
    emerging_asia_capital_flight_risk: float  # 台韓港外資提款風險 (0 ~ 100)
    global_volatility_spillover_index: float  # 全球波動率共振恐慌度 (0 ~ 100)
    macro_regime_multiplier: float            # 總經部位縮放係數 (0.2 ~ 1.2)
    regional_policy_stances: Dict[MacroRegion, MonetaryPolicyStance]
    key_warnings: List[str]


class GlobalMacroEngine:
    """
    跨市場總經、利率、匯率與市場情緒分析引擎：
    1. 追蹤 US, TW, JP, KR, HK, EU 六大市場的政策利率、公債長短天期利差與匯率變動。
    2. 評估日圓利差交易（Carry Trade）平倉引發的全球流動性收縮風險。
    3. 計算亞洲新興市場（台、韓、港）因強勢美元與長端美債殖利率暴衝導致的外資提款賣壓。
    4. 輸出「總經部位調節乘數（macro_regime_multiplier）」，動態縮放個股策略進場倉位。
    """

    def __init__(
        self,
        dxy_pressure_threshold: float = 104.5,
        us_10y_yield_stress_level: float = 4.40,
        jpy_appreciation_alert_pct: float = -1.2, # 日圓單日升值超過 1.2% (USD/JPY 下跌)
    ) -> None:
        self.dxy_pressure_threshold = dxy_pressure_threshold
        self.us_10y_yield_stress_level = us_10y_yield_stress_level
        self.jpy_appreciation_alert_pct = jpy_appreciation_alert_pct

    def evaluate(
        self,
        rates_fx: Dict[MacroRegion, RegionalRatesAndFX],
        rate_expectations: Dict[MacroRegion, RateHikeExpectation],
        dxy_index: float,
        timestamp: Optional[datetime] = None,
    ) -> GlobalMacroCompositeAnalysis:
        ts = timestamp or datetime.now()
        warnings: List[str] = []

        us_data = rates_fx.get(MacroRegion.US)
        jp_data = rates_fx.get(MacroRegion.JP)
        tw_data = rates_fx.get(MacroRegion.TW)
        kr_data = rates_fx.get(MacroRegion.KR)
        eu_data = rates_fx.get(MacroRegion.EU)

        # 1. 美債殖利率曲線分析 (10Y - 2Y)
        us_spread = 0.0
        is_inverted = False
        is_bear_steep = False

        if us_data and us_data.yield_10y is not None and us_data.yield_2y is not None:
            us_spread = us_data.yield_10y - us_data.yield_2y
            is_inverted = us_spread < 0.0
            # 熊陡 (Bear Steepening): 10 年期高於警戒線且利差持續走擴
            is_bear_steep = (us_data.yield_10y >= self.us_10y_yield_stress_level and us_spread > 0.15)
            if is_inverted:
                warnings.append("US_YIELD_CURVE_INVERTED: 殖利率曲線倒掛，景氣衰退前瞻警示。")
            if is_bear_steep:
                warnings.append("US_BEAR_STEEPENING: 長端美債利率飆升，壓抑科技成長股本益比。")

        # 2. 日圓套利交易平倉風險 (Carry Trade Unwind Risk)
        carry_risk = 0.0
        if jp_data:
            # USD/JPY 單日大幅下挫 (日圓暴升) + 日本公債利率走高 + VNKY 飆升
            fx_shock = max(0.0, -jp_data.fx_change_pct_1d) # 升值幅度
            vix_shock = max(0.0, (jp_data.volatility_index - 20.0) / 10.0)
            carry_risk = min(100.0, (fx_shock * 35.0) + (vix_shock * 30.0))
            if jp_data.fx_change_pct_1d <= self.jpy_appreciation_alert_pct:
                warnings.append(f"JPY_SURGE_CARRY_UNWIND: 日圓急升 ({jp_data.fx_change_pct_1d:.2f}%)，引發全球利差平倉賣壓。")

        # 3. 亞洲新興市場 (台、韓、港) 外資提款壓力
        capital_flight_risk = 0.0
        dxy_factor = max(0.0, (dxy_index - 100.0) / (self.dxy_pressure_threshold - 100.0)) * 40.0
        asia_depreciation = 0.0
        if tw_data and kr_data:
            # USD/TWD, USD/KRW 單日貶值 (匯率上漲為貶值)
            tw_dep = max(0.0, tw_data.fx_change_pct_1d)
            kr_dep = max(0.0, kr_data.fx_change_pct_1d)
            asia_depreciation = ((tw_dep + kr_dep) / 2.0) * 40.0

        us_yield_pressure = 0.0
        if us_data and us_data.yield_10y and us_data.yield_10y >= self.us_10y_yield_stress_level:
            us_yield_pressure = min(20.0, (us_data.yield_10y - self.us_10y_yield_stress_level) * 50.0)

        capital_flight_risk = min(100.0, dxy_factor + asia_depreciation + us_yield_pressure)
        if capital_flight_risk >= 65.0:
            warnings.append(f"EM_CAPITAL_FLIGHT_HIGH: 美元強勢 ({dxy_index:.1f}) 與亞幣重貶，外資提款台韓權值股風險驟升。")

        # 4. 全球波動率共振恐慌指數 (Global Volatility Spillover)
        vol_values = [r.volatility_index for r in rates_fx.values() if r.volatility_index > 0]
        avg_vol = float(np.mean(vol_values)) if vol_values else 15.0

        # 期限結構倒掛檢查 (短天期波動率大於長天期即為 Backwardation 恐慌)
        backwardation_count = sum(1 for r in rates_fx.values() if r.term_structure_ratio and r.term_structure_ratio > 1.05)
        vol_spillover = min(100.0, (max(0.0, avg_vol - 15.0) / 20.0 * 70.0) + (backwardation_count * 10.0))

        if vol_spillover >= 60.0:
            warnings.append("GLOBAL_VOLATILITY_SPIKE: 歐美亞主要指數波動率共振攀升，短線系統性風險擴大。")

        # 5. 各國貨幣政策週期狀態
        stances: Dict[MacroRegion, MonetaryPolicyStance] = {}
        for reg in MacroRegion:
            exp = rate_expectations.get(reg)
            if not exp:
                stances[reg] = MonetaryPolicyStance.NEUTRAL
                continue
            if exp.prob_cut >= 0.60:
                stances[reg] = MonetaryPolicyStance.EASING
            elif exp.prob_hike >= 0.50:
                stances[reg] = MonetaryPolicyStance.TIGHTENING
            elif rates_fx.get(reg) and rates_fx[reg].central_bank_policy_rate >= 3.5:
                stances[reg] = MonetaryPolicyStance.RESTRICTIVE_HOLD
            else:
                stances[reg] = MonetaryPolicyStance.NEUTRAL

        # 6. 計算總經部位縮放係數 (Macro Regime Multiplier: 0.2 ~ 1.2)
        # 基準 1.0；若恐慌、外資提款或日圓急升，降低交易部位；若寬鬆且波動低，可加乘至 1.2
        penalty = (carry_risk * 0.003) + (capital_flight_risk * 0.004) + (vol_spillover * 0.004)
        regime_mult = max(0.20, min(1.20, 1.10 - penalty))

        return GlobalMacroCompositeAnalysis(
            timestamp=ts,
            dxy_index=dxy_index,
            us_yield_spread_10y_2y=round(us_spread, 4),
            is_yield_curve_inverted=is_inverted,
            is_bear_steepening=is_bear_steep,
            carry_trade_unwind_risk=round(carry_risk, 2),
            emerging_asia_capital_flight_risk=round(capital_flight_risk, 2),
            global_volatility_spillover_index=round(vol_spillover, 2),
            macro_regime_multiplier=round(regime_mult, 2),
            regional_policy_stances=stances,
            key_warnings=warnings,
        )
